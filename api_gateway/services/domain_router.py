"""
领域路由配置

按功能域（用例生成 / 脚本生成 / 知识库查询）配置对应的:
  - Prompt 模板（给 Hermes Agent 的系统指令）
  - 技能包路径（Hermes SKILL.md）
  - 默认参数

Phase 1 提供基础模板；
Phase 2 由 D 淞豪替换为真实 VCU 领域技能包后自动加载。
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass


@dataclass
class DomainConfig:
    """单个功能域的配置。"""
    domain_id: str
    name: str
    skill_path: str | None      # Hermes SKILL.md 路径（D 模块提供后填入）
    system_prompt: str          # 注入给 Agent 的系统 Prompt
    default_temperature: float = 0.3


# --- VCU 档位管理域 ---
GEAR_DOMAIN = DomainConfig(
    domain_id="vcu_gear",
    name="VCU 档位管理",
    skill_path="skills/vcu_gear/SKILL.md",  # D 模块提供的技能包
    system_prompt=(
        "你是汽车 VCU 档位管理测试用例生成专家。"
        "你的任务是根据用户提供的档位管理需求文档，"
        "提取结构化的功能需求点，并生成 S0/S1/S2/S3 四级测试用例。\n\n"
        "覆盖功能：P/R/N/D 挡切换逻辑、DriveReady 控制、换挡失败提示、"
        "P 挡闪烁控制、组合开关控制、插枪挡位控制、上下电挡位控制等。\n\n"
        "输出格式：严格 JSON，不包含任何额外文本。"
    ),
)

# --- VCU 扭矩管理域 ---
TORQUE_DOMAIN = DomainConfig(
    domain_id="vcu_torque",
    name="VCU 扭矩管理",
    skill_path="skills/vcu_torque/SKILL.md",
    system_prompt=(
        "你是汽车 VCU 扭矩管理测试用例生成专家。"
        "你的任务是根据用户提供的扭矩管理需求文档，"
        "提取结构化的功能需求点，并生成 S0/S1/S2/S3/S4 五级测试用例。\n\n"
        "覆盖功能：蠕行功能、滑行能量回收、减速缓行模式、"
        "制动能量回收 CRBS、扭矩限制、跨域扭矩交互等。\n\n"
        "输出格式：严格 JSON，不包含任何额外文本。"
    ),
)

# --- 通用域（兜底） ---
GENERAL_DOMAIN = DomainConfig(
    domain_id="general",
    name="通用",
    skill_path=None,
    system_prompt="你是一个汽车 VCU 测试领域的 AI 助手，根据用户需求生成测试用例和脚本。",
)

# --- 路由表 ---
_DOMAIN_MAP: dict[str, DomainConfig] = {
    "vcu_gear": GEAR_DOMAIN,
    "vcu_torque": TORQUE_DOMAIN,
    "vcu": GENERAL_DOMAIN,
    "general": GENERAL_DOMAIN,
}


def get_domain(domain_id: str) -> DomainConfig:
    """根据 domain_id 获取功能域配置，不存在则返回通用域。"""
    return _DOMAIN_MAP.get(domain_id, GENERAL_DOMAIN)


def list_domains() -> list[dict]:
    """列出所有可用功能域。"""
    return [
        {"domain_id": d.domain_id, "name": d.name, "has_skill": d.skill_path is not None}
        for d in _DOMAIN_MAP.values()
    ]


def build_system_prompt(domain_id: str) -> str:
    """获取指定功能域的 System Prompt。

    用于 AIAgent 的 ephemeral_system_prompt 参数，
    在 Agent 创建时注入，与 user message 分离。
    """
    domain = get_domain(domain_id)
    return domain.system_prompt


def build_user_message(domain_id: str, task: str, **kwargs) -> str:
    """
    根据功能域和任务类型，构建给 Hermes Agent 的 user message。

    仅包含 task 指令和 context，不包含 system prompt
    （system prompt 已通过 ephemeral_system_prompt 注入）。

    task: "generate_requirements" | "generate_testcases" | "generate_scripts"
    """
    task_prompts = {
        "generate_requirements": (
            "请从以下需求文档中提取结构化的功能需求点。\n"
            "每个需求点包含：编号、功能名称、需求描述、优先级（高/中/低）。\n"
            "以 JSON 数组格式返回，格式：\n"
            '[{"id": "REQ-001", "name": "功能名称", "description": "需求描述", "priority": "高"}]\n'
        ),
        "generate_testcases": (
            "请根据以下需求点，生成符合平台化测试用例库标准的测试用例。\n"
            "用例分级：S0（基础功能）/ S1（正常流程）/ S2（边界异常）/ S3（故障注入）。\n"
            "每条用例包含：编号、用例标题、前置条件、测试步骤、预期结果、级别。\n"
            "以 JSON 数组格式返回。\n"
        ),
        "generate_scripts": (
            "请根据以下测试用例，生成可执行的自动化测试脚本。\n"
            "脚本格式：Python + pytest 框架。\n"
            "每个用例对应一个 test 函数，包含完整的步骤断言。\n"
            "以 JSON 数组格式返回，每项包含：用例编号、脚本内容（代码字符串）。\n"
        ),
    }

    base = task_prompts.get(task, "")
    context = kwargs.get("context", "")

    return f"{base}\n\n以下是输入内容：\n{context}"


def build_prompt(domain_id: str, task: str, **kwargs) -> str:
    """
    根据功能域和任务类型，构建给 Hermes Agent 的完整 Prompt。

    兼容旧接口：合并 system_prompt + task 指令 + context。
    新代码应优先使用 build_system_prompt() + build_user_message() 分离调用。

    task: "generate_requirements" | "generate_testcases" | "generate_scripts"
    """
    domain = get_domain(domain_id)
    user_msg = build_user_message(domain_id, task, **kwargs)
    return f"{domain.system_prompt}\n\n{user_msg}"
