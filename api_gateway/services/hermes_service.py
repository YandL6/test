"""
Hermes 服务层 — B 模块的核心

职责：将 Hermes Agent 的 AIAgent 类当作 Python 库调用，
     对外封装成统一的"对话 → 工具调用 → 返回"服务接口。

关键设计：
1. 惰性初始化：首次调用时才 import Hermes 并创建 Agent 实例
2. 会话隔离：每个 session_id 对应一个独立的 AIAgent 实例
3. 兼容兜底：Hermes 未安装时降级为 Mock 模式，保证 API 可联调
4. JSON 容错：Hermes 返回的文本可能包含非标准 JSON，统一清洗
"""
from __future__ import annotations

import json
import re
import sys
import os
import shutil
import asyncio
import traceback
from typing import Any, AsyncIterator
from pathlib import Path

from loguru import logger

from api_gateway.config import config
from api_gateway.models.responses import APIError, ErrorCode

# --- Hermes 导入（惰性） ---
_hermes_imported = False
_hermes_agent_cls = None


def _set_hermes_home() -> None:
    """设置 HERMES_HOME 环境变量，让 Hermes 能发现 VCU skills 目录。

    Hermes-agent 通过 get_hermes_home() 读取 HERMES_HOME 环境变量，
    默认为 ~/.hermes。我们将其设为项目根目录，使 skills/vcu_*
    能被 Hermes 的 skill_utils.py 正确加载。
    """
    project_root = str(config.PROJECT_ROOT)
    if not os.environ.get("HERMES_HOME"):
        os.environ["HERMES_HOME"] = project_root
        logger.info(f"HERMES_HOME 设为: {project_root}")


def _apply_py310_patches() -> None:
    """自动应用 Python 3.10 兼容性补丁。

    hermes-agent/agent/redact.py 中使用了 Python 3.11+ 的占有量词
    语法（++、*+），在 Python 3.10 下会报 re.error。
    本方法在导入 Hermes 前用补丁文件覆盖原文件。
    """
    if sys.version_info >= (3, 11):
        return

    patch_path = config.PROJECT_ROOT / "patches" / "redact_py310_fixed.py"
    if not patch_path.exists():
        logger.warning(f"Python 3.10 补丁文件不存在: {patch_path}")
        return

    target = config.hermes_path / "agent" / "redact.py"
    if not target.exists():
        logger.warning(f"补丁目标文件不存在: {target}")
        return

    try:
        shutil.copy2(patch_path, target)
        logger.info(f"已应用 Python 3.10 兼容性补丁: {target}")
    except Exception as e:
        logger.error(f"应用 Python 3.10 补丁失败: {e}")


def _classify_hermes_error(e: Exception) -> tuple:
    """将 Hermes Agent 异常分类为 (ErrorCode, message, http_status)。

    Hermes-agent 的 error_classifier.py 定义了 FailoverReason 枚举，
    我们通过异常消息中的关键词进行映射。
    """
    msg = str(e).lower()

    # Rate limit / 429
    if any(k in msg for k in ["rate_limit", "rate limit", "429", "too many requests"]):
        return (
            ErrorCode.HERMES_RATE_LIMIT,
            "LLM 服务请求频率超限，请稍后重试",
            429,
        )

    # Context too long
    if any(k in msg for k in ["context_too_long", "context length", "too long", "maximum context", "token limit"]):
        return (
            ErrorCode.HERMES_CONTEXT_TOO_LONG,
            "输入内容过长，超出模型上下文限制，请精简输入",
            413,
        )

    # Provider down / connection error
    if any(k in msg for k in ["provider_down", "connection", "timeout", "unreachable", "refused", "econnrefused"]):
        return (
            ErrorCode.HERMES_PROVIDER_DOWN,
            "LLM 服务不可用，请检查模型服务状态",
            503,
        )

    # 默认 LLM 错误
    return (
        ErrorCode.HERMES_LLM_ERROR,
        f"Agent 调用失败: {e}",
        500,
    )


def _ensure_hermes_imported() -> bool:
    """
    尝试将 Hermes 安装目录加入 sys.path 并导入 AIAgent。

    成功返回 True，失败返回 False（降级为 Mock 模式）。
    导入前完成：HERMES_HOME 设置、环境变量同步、Python 3.10 补丁。
    """
    global _hermes_imported, _hermes_agent_cls

    if _hermes_imported:
        return _hermes_agent_cls is not None

    _hermes_imported = True

    # P1-1: 设置 HERMES_HOME，让 Hermes 能发现 skills 目录
    _set_hermes_home()

    # P1-2: 同步环境变量到 Hermes 期望的变量名
    config.sync_hermes_env()

    # P2-2: 自动应用 Python 3.10 兼容性补丁
    _apply_py310_patches()

    hermes_path = str(config.hermes_python_path)

    if hermes_path not in sys.path:
        sys.path.insert(0, hermes_path)

    try:
        # Hermes 的核心 Agent 类在 run_agent.py 中
        from run_agent import AIAgent  # type: ignore

        _hermes_agent_cls = AIAgent
        logger.info(f"Hermes AIAgent 导入成功，路径: {hermes_path}")
        return True
    except ImportError as e:
        logger.warning(
            f"Hermes 未安装或导入失败: {e}\n"
            f"降级为 Mock 模式 — API 可用但 AI 生成功能返回模拟数据。\n"
            f"请运行 setup_hermes.sh 安装 Hermes。"
        )
        return False
    except Exception as e:
        logger.error(f"Hermes 导入异常: {e}\n{traceback.format_exc()}")
        return False


# --- 会话级 Agent 管理器 ---
class SessionAgentManager:
    """
    管理每个 session_id 对应的 Agent 实例。

    Phase 1 实现要点：
    - 创建会话时初始化 Agent（或延迟到首次对话）
    - 会话结束后清理资源
    - 多会话并发安全（用 asyncio.Lock 保护内部字典）
    """

    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str, profile: str = "default", domain_id: str = "general") -> Any:
        """获取或创建指定会话的 Agent 实例。

        domain_id 用于在创建时注入领域 system prompt（ephemeral_system_prompt）。
        已创建的 Agent 不受后续 domain_id 变更影响。
        """
        async with self._lock:
            if session_id in self._agents:
                return self._agents[session_id]

            agent = await self._create_agent(session_id, profile, domain_id)
            self._agents[session_id] = agent
            return agent

    async def _create_agent(self, session_id: str, profile: str, domain_id: str = "general") -> Any:
        """
        创建一个 AIAgent 实例。

        如果 Hermes 可用且配置了 LLM，则用真实 Agent；
        否则返回 MockAgent 降级。

        P0-2 增强：新增 6 个 AIAgent 构造参数：
        - session_id: 关联数据库 session
        - enabled_toolsets: 空列表，禁用所有工具（纯文本生成场景）
        - ephemeral_system_prompt: 通过 domain_router 注入领域 system prompt
        - max_tokens: 控制输出长度
        - save_trajectories: 开发模式保存对话轨迹
        - verbose_logging: 开发模式详细日志
        """
        hermes_ok = _ensure_hermes_imported()

        if hermes_ok and _hermes_agent_cls is not None:
            try:
                # P1-3: 从 domain_router 获取领域 system prompt
                from api_gateway.services.domain_router import build_system_prompt
                domain_prompt = build_system_prompt(domain_id)

                # AIAgent 接受 base_url/api_key/provider/model
                # 当 api_key + base_url 同时提供时，直接构造 client（绕过 provider router）
                init_kwargs: dict[str, Any] = {
                    "model": config.LLM_MODEL or "gpt-4o",
                    "max_iterations": 30,
                    "skip_memory": True,        # 跳过 Hermes 内部记忆
                    "skip_context_files": True,  # 不加载 Hermes context 文件
                    "load_soul_identity": False,
                    "quiet_mode": True,          # 抑制 Hermes 控制台输出
                    "skip_background_review": True,
                    # --- P0-2 新增参数 ---
                    "session_id": session_id,              # 关联数据库 session
                    "enabled_toolsets": [],                # 纯文本生成，禁用所有工具
                    "ephemeral_system_prompt": domain_prompt,  # 注入 VCU 领域 system prompt
                    "max_tokens": 4096,                    # 控制输出长度
                    "save_trajectories": config.is_dev_mode(),  # 开发模式保存轨迹
                    "verbose_logging": config.is_dev_mode(),     # 开发模式详细日志
                }
                # 必须同时提供 api_key + base_url 才能绕过 provider router
                if config.LLM_API_KEY and config.LLM_BASE_URL:
                    init_kwargs["api_key"] = config.LLM_API_KEY
                    init_kwargs["base_url"] = config.LLM_BASE_URL
                    init_kwargs["provider"] = config.LLM_PROVIDER or "custom"
                elif config.LLM_API_KEY:
                    # 有 key 但没 base_url — 设置 provider 让 Hermes 自己路由
                    init_kwargs["api_key"] = config.LLM_API_KEY
                    init_kwargs["provider"] = config.LLM_PROVIDER or "openai"
                else:
                    # 无 API key — 不能创建真实 Agent
                    logger.warning(
                        "无 LLM API Key 配置 (HERMES_LLM_API_KEY 为空)，降级 Mock 模式"
                    )
                    return _MockAgent(session_id)

                agent = _hermes_agent_cls(**init_kwargs)
                logger.info(
                    f"为会话 {session_id} 创建真实 Hermes AIAgent "
                    f"(provider={init_kwargs.get('provider', '?')}, "
                    f"model={init_kwargs.get('model', '?')}, "
                    f"domain={domain_id})"
                )
                return agent
            except Exception as e:
                logger.error(
                    f"创建 Hermes Agent 失败，降级 Mock: {e}\n{traceback.format_exc()}"
                )

        # Mock 模式
        return _MockAgent(session_id)

    async def remove(self, session_id: str):
        """清理指定会话的 Agent。"""
        async with self._lock:
            agent = self._agents.pop(session_id, None)
            if agent is not None and hasattr(agent, "cleanup"):
                try:
                    if asyncio.iscoroutinefunction(agent.cleanup):
                        await agent.cleanup()
                    else:
                        agent.cleanup()
                except Exception as e:
                    logger.warning(f"清理 Agent 异常 (session={session_id}): {e}")

    async def list_sessions(self) -> list[str]:
        async with self._lock:
            return list(self._agents.keys())


# --- Mock Agent（Hermes 未安装时的降级实现） ---
class _MockAgent:
    """
    Hermes 未安装时的降级 Agent，返回模拟数据。

    保证 API Gateway 在没有 Hermes 的环境下也能联调路由与接口。
    根据入参 Prompt 中的关键词，返回对应类型的模拟 VCU 测试数据。
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        logger.info(f"创建 MockAgent (session={session_id})")

    async def chat(self, message: str, **kwargs) -> str:
        """返回模拟数据，根据 prompt 内容匹配任务类型。"""
        import json as _json

        # 判断任务类型 — 用 task prompt 中的独特短语匹配（非系统 prompt）
        if "从以下需求文档中提取" in message:
            return _json.dumps(self._mock_requirements(), ensure_ascii=False, indent=2)

        elif "生成符合平台化测试用例库标准" in message:
            return _json.dumps(self._mock_testcases(), ensure_ascii=False, indent=2)

        elif "生成可执行的自动化测试脚本" in message:
            return _json.dumps(self._mock_scripts(), ensure_ascii=False, indent=2)

        # 默认回复
        return _json.dumps(
            {"status": "mock", "message": "收到，Mock 模式返回模拟数据", "echo": message[:200]},
            ensure_ascii=False,
        )

    async def chat_stream(self, message: str, **kwargs) -> AsyncIterator[str]:
        """流式返回模拟数据。"""
        full = await self.chat(message, **kwargs)
        # 按字符分片流式返回
        chunk_size = 20
        for i in range(0, len(full), chunk_size):
            yield full[i:i + chunk_size]
            await asyncio.sleep(0.05)

    def _mock_requirements(self) -> list[dict]:
        """模拟 VCU 档位管理需求点。"""
        return [
            {"id": "REQ-001", "name": "P挡至D挡切换", "description": "车辆静止且制动踏板踩下时，P挡可切换至D挡，切换后进入DriveReady状态", "priority": "高"},
            {"id": "REQ-002", "name": "D挡至P挡切换", "description": "车速低于3km/h且制动踏板踩下时，D挡可切换至P挡，切换后驱动系统断开", "priority": "高"},
            {"id": "REQ-003", "name": "R挡切换条件", "description": "车辆静止且制动踏板踩下时，可从P/N切换至R挡，R挡时倒车灯点亮", "priority": "高"},
            {"id": "REQ-004", "name": "N挡滑行保护", "description": "N挡时驱动扭矩为零，车速超过10km/h时禁止切换至P/R挡", "priority": "中"},
            {"id": "REQ-005", "name": "DriveReady使能", "description": "D挡且制动释放后，DriveReady使能，驱动扭矩准备就绪", "priority": "高"},
            {"id": "REQ-006", "name": "换挡失败提示", "description": "不满足换挡条件时，仪表闪烁当前挡位指示灯，持续3秒", "priority": "中"},
            {"id": "REQ-007", "name": "P挡闪烁控制", "description": "车辆未Ready且挡位为P时，P挡指示灯以1Hz频率闪烁", "priority": "低"},
            {"id": "REQ-008", "name": "插枪挡位互锁", "description": "充电枪插入时，挡位锁定P挡，禁止切换至其他挡位", "priority": "中"},
        ]

    def _mock_testcases(self) -> list[dict]:
        """模拟 VCU 档位管理测试用例。"""
        return [
            {"id": "TC-GEAR-S0-001", "title": "P挡至D挡正常切换", "level": "S0", "precondition": "车辆静止，制动踏板踩下，当前挡位P，车辆READY", "steps": ["1. 确认仪表显示P挡", "2. 踩下制动踏板", "3. 拨动换挡杆至D挡"], "expected": "仪表显示D挡，DriveReady状态激活，驱动扭矩准备就绪"},
            {"id": "TC-GEAR-S0-002", "title": "D挡至P挡正常切换", "level": "S0", "precondition": "车速<3km/h，制动踏板踩下，当前挡位D", "steps": ["1. 车辆减速至静止", "2. 踩下制动踏板", "3. 按下P挡按键"], "expected": "仪表显示P挡，驱动系统断开，P挡锁止机构 engage"},
            {"id": "TC-GEAR-S0-003", "title": "P挡至R挡正常切换", "level": "S0", "precondition": "车辆静止，制动踏板踩下，当前挡位P", "steps": ["1. 确认P挡", "2. 踩制动", "3. 拨至R挡"], "expected": "仪表R挡亮起，倒车灯点亮，倒车影像激活"},
            {"id": "TC-GEAR-S1-001", "title": "行驶中D挡至N挡切换", "level": "S1", "precondition": "车速30km/h，当前挡位D，油门松开", "steps": ["1. 车速稳定30km/h", "2. 松开油门", "3. 拨至N挡"], "expected": "挡位切换至N，驱动扭矩降为零，车辆滑行"},
            {"id": "TC-GEAR-S2-001", "title": "未踩制动尝试P至D切换", "level": "S2", "precondition": "车辆静止，当前挡位P，制动踏板未踩下", "steps": ["1. 确认P挡", "2. 不踩制动", "3. 尝试拨至D挡"], "expected": "挡位保持P挡不变，仪表P挡指示灯闪烁3秒，提示换挡失败"},
            {"id": "TC-GEAR-S2-002", "title": "高速行驶尝试切P挡", "level": "S2", "precondition": "车速50km/h，当前挡位D", "steps": ["1. 车速50km/h", "2. 按下P挡按键"], "expected": "挡位保持D挡不变，仪表报警提示，P挡拒绝切换"},
            {"id": "TC-GEAR-S3-001", "title": "挡位传感器信号丢失", "level": "S3", "precondition": "车辆READY，当前D挡行驶中", "steps": ["1. 正常行驶", "2. 断开挡位传感器信号", "3. 观察系统响应"], "expected": "VCU报故障码，保持当前挡位，仪表报警，扭矩限制降级模式"},
            {"id": "TC-GEAR-S3-002", "title": "CAN通信中断时挡位控制", "level": "S3", "precondition": "车辆READY，D挡行驶", "steps": ["1. 正常行驶", "2. 模拟VCU与TCU CAN通信中断", "3. 尝试换挡"], "expected": "系统进入安全模式，保持当前挡位，扭矩限制，仪表报警"},
        ]

    def _mock_scripts(self) -> list[dict]:
        """模拟生成的测试脚本。"""
        return [
            {"id": "TC-GEAR-S0-001", "script": 'import pytest\n\ndef test_p_to_d_switch(driver, hmi):\n    """TC-GEAR-S0-001: P挡至D挡正常切换"""\n    # 前置: 车辆静止, P挡, READY\n    driver.set_gear("P")\n    driver.set_brake(True)\n    driver.set_ready(True)\n    assert hmi.get_gear_display() == "P"\n\n    # 执行: 拨至D挡\n    driver.move_shifter("D")\n    driver.wait(500)  # ms\n\n    # 验证\n    assert hmi.get_gear_display() == "D"\n    assert driver.get_drive_ready() is True\n    assert driver.get_torque_state() == "ready"\n'},
            {"id": "TC-GEAR-S0-002", "script": 'import pytest\n\ndef test_d_to_p_switch(driver, hmi):\n    """TC-GEAR-S0-002: D挡至P挡正常切换"""\n    # 前置: 车速<3km/h, D挡, 踩制动\n    driver.set_gear("D")\n    driver.set_speed(0)  # km/h\n    driver.set_brake(True)\n\n    # 执行: 按P挡按键\n    driver.press_p_button()\n    driver.wait(500)\n\n    # 验证\n    assert hmi.get_gear_display() == "P"\n    assert driver.get_drive_ready() is False\n    assert driver.get_park_lock() is True  # 锁止机构engage\n'},
            {"id": "TC-GEAR-S2-001", "script": 'import pytest\n\ndef test_p_to_d_without_brake(driver, hmi):\n    """TC-GEAR-S2-001: 未踩制动尝试P至D切换"""\n    # 前置: 静止, P挡, 不踩制动\n    driver.set_gear("P")\n    driver.set_brake(False)\n    driver.set_ready(True)\n\n    # 执行: 尝试拨至D挡\n    driver.move_shifter("D")\n    driver.wait(3000)  # 等待3秒闪烁\n\n    # 验证: 挡位不变, 闪烁提示\n    assert hmi.get_gear_display() == "P"  # 保持P挡\n    assert hmi.get_p_indicator_blinking() is True  # P灯闪烁\n'},
            {"id": "TC-GEAR-S3-001", "script": 'import pytest\n\ndef test_gear_sensor_loss(driver, hmi, fault_injector):\n    """TC-GEAR-S3-001: 挡位传感器信号丢失"""\n    # 前置: READY, D挡行驶\n    driver.set_gear("D")\n    driver.set_speed(40)\n    driver.set_ready(True)\n\n    # 执行: 断开传感器信号\n    fault_injector.disconnect("gear_sensor")\n    driver.wait(1000)\n\n    # 验证: 故障码 + 安全模式\n    assert hmi.get_fault_code() == "P0705"  # 挡位传感器故障\n    assert driver.get_gear() == "D"  # 保持当前挡位\n    assert hmi.get_warning_display() is True  # 报警\n    assert driver.get_torque_limit_mode() is True  # 降级模式\n'},
        ]


# --- 全局单例 ---
agent_manager = SessionAgentManager()


def _get_chat_params(agent: Any) -> list[str]:
    """获取 agent.chat 方法的参数名列表（用于检测 stream_callback 支持）。"""
    import inspect
    try:
        sig = inspect.signature(agent.chat)
        return list(sig.parameters.keys())
    except (ValueError, TypeError):
        return []


# --- JSON 容错工具 ---
def extract_json(text: str) -> Any:
    """
    从可能混杂自然语言的文本中提取 JSON。

    Hermes 返回的内容可能包含:
    - ```json ... ``` 代码块包裹
    - 前后有解释文字（"以下是结果：{...}"）
    - JSON 数组 [{...}, {...}] 或单个对象 {...}

    策略：优先找代码块 → 尝试找最外层 [..] 或 {...} → 再退而尝试整体 parse。
    """
    # 1. 尝试从 ```json ... ``` 代码块提取
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # 2. 尝试找最外层的 [...] (JSON 数组) — 贪婪匹配最外层方括号
    # 先尝试找从第一个 [ 到最后一个 ] 的内容
    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate = text[first_bracket:last_bracket + 1]
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # 3. 尝试找最外层的 {...} (JSON 对象) — 贪婪匹配
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 4. 尝试整体解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise APIError(
            ErrorCode.HERMES_JSON_PARSE_FAILED,
            "AI 返回内容无法解析为 JSON",
            detail=f"原始文本前500字: {text[:500]}",
        )


# --- 对外服务接口 ---
class HermesService:
    """
    B 模块对外暴露的统一服务层。

    路由层只调用这个类的方法，不直接碰 Hermes 内部。
    """

    @staticmethod
    async def send_message(
        session_id: str, message: str, domain_id: str = "general", **kwargs
    ) -> str:
        """
        向指定会的 Agent 发送消息，返回完整响应文本。

        domain_id 用于首次创建 Agent 时注入领域 system prompt。
        用于非流式场景（如知识库检索、快速问答）。
        真实 AIAgent.chat() 是同步方法，用 asyncio.to_thread 包装。
        """
        agent = await agent_manager.get_or_create(session_id, domain_id=domain_id)
        try:
            if asyncio.iscoroutinefunction(agent.chat):
                result = await agent.chat(message, **kwargs)
            else:
                # 真实 AIAgent.chat 是同步的 — 放到线程池执行
                result = await asyncio.to_thread(agent.chat, message, **kwargs)
            return result
        except asyncio.TimeoutError:
            raise APIError(
                ErrorCode.HERMES_TIMEOUT,
                "Agent 响应超时",
                detail=f"session={session_id}",
                status_code=504,
            )
        except APIError:
            raise
        except Exception as e:
            logger.error(f"Agent 调用异常: {e}\n{traceback.format_exc()}")
            # P2-1: Hermes 专用错误分类
            err_code, err_msg, http_status = _classify_hermes_error(e)
            raise APIError(
                err_code,
                err_msg,
                detail=traceback.format_exc(),
                status_code=http_status,
            )

    @staticmethod
    async def send_message_stream(
        session_id: str, message: str, domain_id: str = "general", **kwargs
    ) -> AsyncIterator[str]:
        """
        向指定会话的 Agent 发送消息，流式返回响应片段。

        domain_id 用于首次创建 Agent 时注入领域 system prompt。
        用于 SSE 推送场景（用例生成、脚本生成的实时输出）。
        真实 AIAgent 使用 stream_callback 参数实现流式输出。
        """
        agent = await agent_manager.get_or_create(session_id, domain_id=domain_id)
        try:
            if hasattr(agent, "chat_stream"):
                # MockAgent 支持 async chat_stream
                async for chunk in agent.chat_stream(message, **kwargs):
                    yield chunk
            elif hasattr(agent, "chat") and "stream_callback" in _get_chat_params(agent):
                # 真实 AIAgent.chat(stream_callback=...) — 用 asyncio.Queue 桥接同步回调到 async 迭代
                queue: asyncio.Queue = asyncio.Queue()
                loop = asyncio.get_event_loop()

                def _stream_cb(text: str):
                    """同步回调 — 把 LLM 流式输出推入 asyncio.Queue"""
                    if text:
                        asyncio.run_coroutine_threadsafe(queue.put(text), loop)

                def _run_chat():
                    """在线程池中执行同步 chat()"""
                    try:
                        final = agent.chat(message, stream_callback=_stream_cb)
                        if final:
                            asyncio.run_coroutine_threadsafe(queue.put(final), loop)
                    except Exception as e:
                        asyncio.run_coroutine_threadsafe(
                            queue.put(f"\n[ERROR] {e}"), loop
                        )
                    finally:
                        asyncio.run_coroutine_threadsafe(
                            queue.put(None), loop  # sentinel
                        )

                # 启动后台线程执行同步 chat
                import threading
                thread = threading.Thread(target=_run_chat, daemon=True)
                thread.start()

                # 从队列消费流式输出
                while True:
                    chunk = await queue.get()
                    if chunk is None:  # sentinel — 完成
                        break
                    yield chunk
            else:
                # 不支持流式 → 一次性返回
                result = await HermesService.send_message(session_id, message, domain_id=domain_id, **kwargs)
                yield result
        except APIError:
            raise
        except Exception as e:
            logger.error(f"Agent 流式调用异常: {e}\n{traceback.format_exc()}")
            # P2-1: Hermes 专用错误分类
            err_code, err_msg, http_status = _classify_hermes_error(e)
            raise APIError(
                err_code,
                err_msg,
                detail=traceback.format_exc(),
                status_code=http_status,
            )

    @staticmethod
    async def close_session(session_id: str):
        """关闭并清理指定会话的 Agent。"""
        await agent_manager.remove(session_id)
        logger.info(f"会话 {session_id} 的 Agent 已清理")

    @staticmethod
    async def list_active_sessions() -> list[str]:
        """列出当前活跃的会话 ID。"""
        return await agent_manager.list_sessions()
