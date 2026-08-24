# Hermes VCU Gateway

> ABCD 四模块 Phase 3 — 接入自部署 SGLang 大模型 + 全链路集成测试 + 生产部署

**版本：0.3.0-phase3**

## 项目结构

```
hermes-vcu-gateway/
├── hermes-agent/              # Hermes Agent 仓库（setup_hermes.sh 自动克隆）
├── api_gateway/               # ★ B 模块 API 网关层
│   ├── main.py                # FastAPI 主入口
│   ├── config.py              # 全局配置管理（Phase 3: SGLang 配置 + custom provider 环境同步）
│   ├── database.py            # SQLite 异步数据库层（6 表）
│   ├── routes/                # 路由层（对外接口）
│   │   ├── health.py          # ★ Phase 3: 健康检查 + SGLang 连通性探测
│   │   ├── session.py         # 会话管理 + 文件上传
│   │   ├── generate.py        # 需求点生成 + 测试用例生成
│   │   └── script_kb.py       # 测试脚本生成 + 知识库检索
│   ├── middleware/            # 中间件（错误处理 / 认证 / 日志）
│   ├── models/                # 数据模型（请求 / 响应 / 错误码）
│   ├── services/              # 服务层
│   │   ├── hermes_service.py  # ★ Hermes AIAgent 封装（核心）
│   │   ├── session_service.py # 会话状态管理
│   │   └── domain_router.py   # 领域路由配置（VCU 档位/扭矩）
│   └── utils/
├── tests/                     # ★ Phase 3 测试套件
│   ├── test_sglang_connection.py  # SGLang 连通性冒烟测试
│   └── test_integration.py        # 端到端集成测试
├── nginx/nginx.conf           # Nginx 反向代理配置（A 模块）
├── docker-compose.yml         # ★ Phase 3: Docker 编排（含 healthcheck + SGLang 可选服务）
├── Dockerfile                 # ★ Phase 3: 生产镜像（含 hermes-agent + skills + patches）
├── setup_hermes.sh            # Hermes 安装脚本
├── run.sh                     # 启动脚本
├── run_test.py                # Phase 1/2 全链路测试
├── requirements.txt           # Python 依赖
├── .env.example               # ★ Phase 3: SGLang 配置模板
└── README.md                  # 本文件
```

## Phase 3 快速开始

### 前置条件

- SGLang 已部署到服务器，模型已加载（如 Qwen3-4B）
- SGLang 服务监听 `0.0.0.0:30000`，提供 OpenAI 兼容 `/v1` 端点

### 1. 配置

```bash
cp .env.example .env
```

编辑 `.env`，确认以下配置：

```env
HERMES_LLM_PROVIDER=custom
HERMES_LLM_MODEL=qwen3-4b
HERMES_LLM_API_KEY=sglang-dummy-key
HERMES_LLM_BASE_URL=http://<sglang-ip>:30000/v1
```

### 2. 冒烟测试 SGLang

```bash
python tests/test_sglang_connection.py --base-url http://localhost:30000/v1
```

确认 `/v1/models` 和 `/v1/chat/completions` 均通过后，再启动 Gateway。

### 3. 安装并启动

```bash
# 安装 Hermes
bash setup_hermes.sh

# 启动 API Gateway
python -m api_gateway.main
# 或
uvicorn api_gateway.main:app --port 8100
```

### 4. 健康检查

```bash
# 综合健康检查（含 SGLang 连通性）
curl http://localhost:8100/health

# 专测 SGLang 连通性
curl http://localhost:8100/health/sglang
```

### 5. 端到端集成测试

```bash
python tests/test_integration.py --host http://localhost:8100
```

### 6. Docker 部署

```bash
docker-compose up -d
# API: http://localhost:8100
# RAGFlow: http://localhost:9380
# Nginx: http://localhost:80
```

## SGLang 配置说明

### 为什么 provider=custom

SGLang 提供 OpenAI 兼容的 `/v1` 端点，但不在 Hermes 的 provider router 内置列表中。设置 `provider=custom` 后，`hermes_service.py` 会直接传入 `api_key` + `base_url` 构造 OpenAI 兼容 client，绕过 provider router。

### .env 关键字段

| 字段 | 值 | 说明 |
|---|---|---|
| `HERMES_LLM_PROVIDER` | `custom` | 绕过 provider router，直接走 OpenAI 兼容端点 |
| `HERMES_LLM_MODEL` | `qwen3-4b` | 与 SGLang `--model-path` 对应 |
| `HERMES_LLM_API_KEY` | `sglang-dummy-key` | SGLang 默认不鉴权，填任意非空字符串 |
| `HERMES_LLM_BASE_URL` | `http://<ip>:30000/v1` | SGLang 的 OpenAI 兼容端点 |

### Docker 内部连接 SGLang

- SGLang 在宿主机运行：`HERMES_LLM_BASE_URL=http://host.docker.internal:30000/v1`
- SGLang 在同一 Docker 网络：在 `docker-compose.yml` 取消注释 sglang 服务，或手动设置网络别名

## API 接口一览

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查（含 Hermes + SGLang 状态） |
| GET | `/health/sglang` | ★ Phase 3: SGLang 连通性详细诊断 |
| GET | `/api/v1/domains` | 列出可用功能域 |
| POST | `/api/v1/sessions` | 创建会话 |
| GET | `/api/v1/sessions` | 列出所有会话 |
| GET | `/api/v1/sessions/{id}` | 获取会话详情 |
| DELETE | `/api/v1/sessions/{id}` | 删除会话 |
| POST | `/api/v1/sessions/{id}/upload` | 上传需求文档 |
| POST | `/api/v1/sessions/{id}/generate/requirements` | 生成需求点（SSE） |
| POST | `/api/v1/sessions/{id}/generate/testcases` | 生成测试用例（SSE） |
| POST | `/api/v1/sessions/{id}/generate/scripts` | 生成测试脚本（SSE） |
| POST | `/api/v1/kb/search` | 知识库检索 |
| GET | `/api/v1/kb/stats` | 数据库统计 |

## 运行模式

| 模式 | 条件 | 行为 |
|---|---|---|
| `real-hermes` | Hermes 导入 + API Key 配置 + SGLang 可达 | 真实 LLM 生成 |
| `mock` | Hermes 导入但 SGLang 不可达 | API 链路可用，AI 生成返回模拟数据 |
| `unavailable` | Hermes 导入失败 | 全部 Mock |

## Phase 路线

| 阶段 | 全模块任务 | 状态 |
|---|---|---|
| Phase 1 (8/10-8/25) | A: Docker/Nginx 基础设施；B: 网关搭建+路由+Mock；C: 前端骨架；D: 领域 Prompt | ✅ 已完成 |
| Phase 2 (8/19-8/26) | A: 数据卷持久化；B: SQLite 6表+异步CRUD+分页+KB索引；C: 简约白主题前端；D: 知识库本地索引 | ✅ 已完成 |
| Phase 3 (8/27-9/10) | 接入自部署大模型；全链路集成测试；API 文档定稿；生产 Docker 镜像 | ✅ 本次交付 |
| Phase 4 (9/11-9/30) | 兼容性测试；Bug 修复；上线交付 | 待开发 |

## Phase 3 变更明细（2026-08-24）

### 新增

- **SGLang 配置**：`.env.example` 切换为 `provider=custom` + SGLang 端点
- **config.py**：新增 `SGLANG_HEALTH_TIMEOUT` / `SGLANG_HEALTH_SKIP` 配置；`sync_hermes_env()` 支持 custom/vllm/sglang provider 的环境变量映射
- **健康检查增强**：`/health` 返回 SGLang 连通性状态（reachable / models / latency）；新增 `/health/sglang` 专测端点
- **Dockerfile 生产化**：COPY hermes-agent + skills + patches 进镜像，不依赖 volume 挂载；加入 HEALTHCHECK
- **docker-compose.yml**：加入 healthcheck；SGLang 可选服务模板（注释状态）
- **SGLang 冒烟测试**：`tests/test_sglang_connection.py` — 测试 `/v1/models` + `/v1/chat/completions`
- **端到端集成测试**：`tests/test_integration.py` — 完整流水线：上传→需求→用例→脚本→验证→清理
- **版本号**：0.2.0 → 0.3.0

### 与其他模块的接口

| 对接模块 | 接口 |
|---|---|
| **A 炉龙** | docker-compose.yml + nginx.conf + Dockerfile + .env 中的基础设施配置 |
| **C 阳兴** | 全部 REST API 接口；SSE 流式协议；`/health/sglang` 连通性诊断 |
| **D 淞豪** | domain_router.py 中的 skill_path；skills/ 目录下的 SKILL.md |



## hermes-sglang-deploy 技能包

本仓库还包含 `hermes-sglang-deploy/` 目录——将 Hermes+SGLang 集成部署流程沉淀为可复用技能，已在 Aily SkillHub 发布。

```
hermes-sglang-deploy/
├── SKILL.md              # 7 步部署流程
├── scripts/              # 测试脚本
│   ├── test_sglang_connection.py  # SGLang 冒烟测试
│   └── test_integration.py        # 端到端集成测试
├── references/           # 参考文档
│   ├── sglang_config.md          # 环境变量映射 + provider 路由
│   ├── architecture.md           # Hermes 封装 + 错误分类 + JSON 容错
│   └── troubleshooting.md        # 排障指南
└── assets/               # 模板和参考实现
    ├── env.example               # .env 配置模板
    ├── Dockerfile               # 生产镜像
    ├── docker-compose.yml       # Docker 编排
    ├── config.py                # 全局配置管理
    ├── hermes_service.py        # Hermes AIAgent 封装核心
    └── health.py                # 健康检查路由
```

SkillHub 分享链接：https://aily.feishu.cn/skills/shared/ad1612b4-e4b2-4dcf-b25d-356d53ab76e3

## License

MIT
