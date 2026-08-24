---
name: hermes-sglang-deploy
label: Hermes SGLang集成部署
description: 将开源 AI Agent 框架（Hermes Agent）集成到 FastAPI API Gateway，并对接自部署 SGLang 大模型推理服务的完整部署流程。覆盖：环境配置、Hermes Agent 封装为 Python 库、SGLang OpenAI 兼容端点对接、provider=custom 绕过 Hermes 内部 router、健康检查连通性探测、Docker 生产镜像构建、端到端集成测试。当需要搭建 Hermes+SGLang 集成网关、配置 LLM 自部署推理服务、排查 SGLang 连接问题、或执行 AI Agent 测试用例生成全链路验证时触发。
---

# Hermes SGLang 集成部署

将 Hermes Agent（开源 AI Agent 框架）封装为 FastAPI REST API 服务，对接 SGLang 自部署大模型，实现 VCU 测试用例生成全链路。

## 核心架构

```
Web 前端 → FastAPI REST API → HermesService → Hermes AIAgent (Python 库)
                                        ↓                    ↓
                                 domain_router         SGLang /v1 端点
                                (VCU 领域 prompt)     (OpenAI 兼容)
```

- **provider=custom**：绕过 Hermes 内部 provider router，直接用 `api_key` + `base_url` 构造 OpenAI 兼容 client
- **ephemeral_system_prompt**：在 AIAgent 创建时注入领域 system prompt，与 user message 分离
- **Mock 降级**：SGLang 不可达时自动返回模拟数据，保证 API 链路可联调
- **SQLite 持久化**：6 表存储会话/文档/需求/用例/脚本/知识库分块

## 部署流程

### 1. 配置环境

复制 `assets/env.example` 为 `.env`，填入 SGLang 地址：

```env
HERMES_LLM_PROVIDER=custom
HERMES_LLM_MODEL=qwen3-4b
HERMES_LLM_API_KEY=sglang-dummy-key
HERMES_LLM_BASE_URL=http://<sglang-ip>:30000/v1
```

SGLang 默认不鉴权，API Key 填任意非空字符串。详见 [references/sglang_config.md](references/sglang_config.md)。

### 2. 验证 SGLang 连通性

运行 `scripts/test_sglang_connection.py`，测试 `/v1/models` 和 `/v1/chat/completions` 两个端点：

```bash
python scripts/test_sglang_connection.py --base-url http://localhost:30000/v1 --model qwen3-4b
```

两个端点均通过后，再启动 Gateway。

### 3. 安装 Hermes

```bash
# 克隆 Hermes Agent 仓库
git clone --depth 1 https://github.com/NousResearch/hermes-agent.git hermes-agent

# 安装依赖
pip install -e ./hermes-agent
pip install -r requirements.txt
```

### 4. 启动 API Gateway

```bash
python -m api_gateway.main
# 或
uvicorn api_gateway.main:app --port 8100
```

### 5. 健康检查

```bash
# 综合健康检查（含 SGLang 连通性）
curl http://localhost:8100/health

# SGLang 专用诊断
curl http://localhost:8100/health/sglang
```

`sglang.reachable: true` 表示连接正常。

### 6. 端到端集成测试

```bash
python scripts/test_integration.py --host http://localhost:8100
```

测试完整流水线：创建会话 → 上传文档 → 生成需求 → 生成用例 → 生成脚本 → 验证持久化 → 清理。

### 7. Docker 部署

```bash
docker-compose up -d
# API: localhost:8100 | RAGFlow: localhost:9380 | Nginx: localhost:80
```

## 关键文件说明

| 文件 | 作用 |
|---|---|
| `assets/env.example` | 环境配置模板（SGLang 端点） |
| `assets/Dockerfile` | 生产镜像（COPY hermes-agent + skills + patches） |
| `assets/docker-compose.yml` | Docker 编排（含 healthcheck） |
| `assets/config.py` | 全局配置管理（SGLang 健康检查 + 环境变量同步） |
| `assets/hermes_service.py` | Hermes AIAgent 封装核心（惰性导入 + 会话隔离 + Mock 降级） |
| `assets/health.py` | 健康检查路由（含 SGLang 连通性探测） |
| `scripts/test_sglang_connection.py` | SGLang 冒烟测试 |
| `scripts/test_integration.py` | 端到端集成测试 |

## 参考资料

- **SGLang 配置详解**：[references/sglang_config.md](references/sglang_config.md) — 环境变量映射、provider 路由、Docker 连接方式
- **架构设计**：[references/architecture.md](references/architecture.md) — Hermes 封装方式、AIAgent 参数、错误分类、JSON 容错
- **排障指南**：[references/troubleshooting.md](references/troubleshooting.md) — SGLang 不可达、Hermes 导入失败、Python 3.10 兼容性

## 运行模式

| 模式 | 条件 | 行为 |
|---|---|---|
| real-hermes | Hermes + API Key + SGLang 可达 | 真实 LLM 生成 |
| mock | Hermes 可用但 SGLang 不可达 | API 链路正常，AI 返回模拟数据 |
| unavailable | Hermes 导入失败 | 全部 Mock |
