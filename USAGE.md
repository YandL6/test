# Hermes VCU Gateway — 使用指南

> 面向 VCU（整车控制器）测试用例智能生成的全链路平台。
> 基于 Nous Research 开源 Hermes AI Agent + 自部署 SGLang 大模型。

---

## 目录

1. [系统要求](#1-系统要求)
2. [快速开始（三步跑起来）](#2-快速开始三步跑起来)
3. [配置说明](#3-配置说明)
4. [运行模式](#4-运行模式)
5. [前端界面使用](#5-前端界面使用)
6. [API 接口调用](#6-api-接口调用)
7. [SGLang 部署对接](#7-sglang-部署对接)
8. [测试](#8-测试)
9. [Docker 部署](#9-docker-部署)
10. [常见问题](#10-常见问题)

---

## 1. 系统要求

| 项目 | 要求 |
|------|------|
| Python | ≥ 3.10 |
| pip | 最新版即可 |
| git | 推荐（用于克隆 Hermes Agent） |
| 操作系统 | Linux / macOS / Windows (WSL) |
| 内存 | ≥ 2GB（Gateway 本身），SGLang 需 GPU |
| 磁盘 | ≥ 1GB（代码+依赖），SGLang 模型另算 |

**SGLang 端（可选但推荐）**：
- NVIDIA GPU（≥ 8GB 显存，Qwen3-4B 级别）
- CUDA 12.x + 驱动
- 或使用 CPU 模式（速度较慢）

---

## 2. 快速开始（三步跑起来）

### 第一步：克隆仓库

```bash
git clone https://github.com/YandL6/test.git hermes-vcu-gateway
cd hermes-vcu-gateway
```

### 第二步：一键安装

```bash
bash setup_hermes.sh --venv
```

这个脚本会自动完成：
- 检测 Python 版本（≥3.10）
- 创建虚拟环境（`--venv` 参数）
- 克隆 Hermes Agent 仓库
- 安装所有 Python 依赖
- 从模板创建 `.env` 配置文件
- 应用 Python 3.10 兼容补丁
- 创建 `uploads/` 和 `logs/` 目录

### 第三步：启动服务

```bash
# 激活虚拟环境（如果用了 --venv）
source .venv/bin/activate

# 编辑配置（至少改一下 LLM 地址）
vi .env

# 启动
bash run.sh
```

打开浏览器访问 `http://localhost:8100`，即可看到前端界面。

> **即使没有 SGLang**，平台也能以 Mock 模式启动——API 链路完整可用，AI 生成返回模拟数据，方便接口联调。

---

## 3. 配置说明

所有配置集中在 `.env` 文件中（从 `.env.example` 复制）。核心配置项：

### 3.1 LLM 连接（最重要）

```env
# Provider — 使用 custom 绕过 Hermes 内部路由，直连 OpenAI 兼容端点
HERMES_LLM_PROVIDER=custom

# 模型名称（与 SGLang --model-path 对应）
HERMES_LLM_MODEL=qwen3-4b

# API Key — SGLang 默认不鉴权，填任意非空字符串
HERMES_LLM_API_KEY=sglang-dummy-key

# SGLang 地址（OpenAI 兼容 /v1 端点）
# 本地: http://localhost:30000/v1
# Docker 内访问宿主机: http://host.docker.internal:30000/v1
HERMES_LLM_BASE_URL=http://localhost:30000/v1
```

### 3.2 健康检查

```env
# SGLang 探测超时（秒）
SGLANG_HEALTH_TIMEOUT=5

# 设为 true 则跳过 SGLang 连通性检测（仅检查 Gateway 自身）
SGLANG_HEALTH_SKIP=false
```

### 3.3 服务端口

```env
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8100
```

### 3.4 其他配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `HERMES_HOME_DIR` | `./hermes-agent` | Hermes 安装目录 |
| `UPLOAD_DIR` | `./uploads` | 上传文件存储目录 |
| `MAX_UPLOAD_SIZE_MB` | `50` | 最大上传大小 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `API_TOKENS` | 空 | API Token 白名单（空=开发模式不鉴权） |

---

## 4. 运行模式

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| **real-hermes** | Hermes 已安装 + LLM API Key 已配置 + SGLang 可达 | 真实 LLM 生成测试用例 |
| **mock** | Hermes 已安装但 SGLang 不可达 | API 链路正常，AI 生成返回预置模拟数据 |
| **unavailable** | Hermes 未安装（克隆失败） | 全部 Mock，API 仍可联调 |

通过健康检查确认当前模式：

```bash
curl http://localhost:8100/health
```

返回示例：

```json
{
  "code": 0,
  "data": {
    "status": "healthy",
    "hermes_available": true,
    "sglang": {
      "reachable": true,
      "models": ["qwen3-4b"],
      "latency_ms": 23
    }
  }
}
```

---

## 5. 前端界面使用

前端界面参考 DeepSeek 的页面风格，结合重庆大学视觉风格设计。

### 界面布局

- **左侧栏**：项目 Logo、新建会话按钮、会话历史列表（按日期分组）、用户信息
- **右侧主区域**：
  - **未创建会话时**：居中欢迎屏，显示平台名称、功能域选择器、会话标题输入框
  - **已创建会话时**：五步工作流进度条 + 会话信息卡 + 文档上传区 + 生成操作区 + 结果展示区

### 工作流程

整个 VCU 测试用例生成流程分为五步：

```
① 创建会话 → ② 上传文档 → ③ 生成需求点 → ④ 生成测试用例 → ⑤ 生成测试脚本
```

#### 步骤一：创建会话

在欢迎屏选择功能域（VCU 档位管理 / VCU 扭矩管理 / 通用模式），输入会话标题，点击「创建会话」或按回车。

#### 步骤二：上传需求文档

点击上传区或拖拽文件上传。支持格式：`.pdf` / `.docx` / `.xlsx` / `.txt` / `.md`。

上传后系统会自动解析文档文本并存入数据库，同时后台索引到知识库。

#### 步骤三：生成需求点

点击「生成需求点」按钮。AI 会分析文档内容，提取结构化需求点（ID、功能名称、描述、优先级）。

生成过程中，**实时输出**标签页会以流式方式显示 AI 的思考过程和输出。

#### 步骤四：生成测试用例

需求点生成完成后，点击「生成测试用例」。AI 基于需求点，按 S0-S3 分级标准生成测试用例（标题、级别、前置条件、操作步骤、预期结果）。

#### 步骤五：生成测试脚本

测试用例生成完成后，点击「生成测试脚本」。AI 基于测试用例生成可执行的 Python 自动化测试脚本。

### 知识库检索

页面底部有知识库搜索栏，可输入关键词检索已索引的文档内容。

---

## 6. API 接口调用

所有接口以 `/api/v1/` 为前缀，返回统一格式：

```json
{ "code": 0, "data": {}, "message": "ok" }
```

### 6.1 健康检查

```bash
# 综合健康检查
curl http://localhost:8100/health

# SGLang 专测
curl http://localhost:8100/health/sglang
```

### 6.2 会话管理

```bash
# 创建会话
curl -X POST http://localhost:8100/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "P挡至D挡测试", "domain": "vcu_gear"}'

# 列出所有会话
curl http://localhost:8100/api/v1/sessions

# 获取会话详情（含文档/需求/用例/脚本）
curl http://localhost:8100/api/v1/sessions/{session_id}

# 删除会话
curl -X DELETE http://localhost:8100/api/v1/sessions/{session_id}
```

### 6.3 文件上传

```bash
curl -X POST http://localhost:8100/api/v1/sessions/{session_id}/upload \
  -F "file=@requirements.pdf"
```

### 6.4 生成接口（SSE 流式）

```bash
# 生成需求点（流式）
curl -X POST http://localhost:8100/api/v1/sessions/{session_id}/generate/requirements \
  -H "Content-Type: application/json" \
  -d '{"stream": true}'

# 生成测试用例
curl -X POST http://localhost:8100/api/v1/sessions/{session_id}/generate/testcases \
  -H "Content-Type: application/json" \
  -d '{"stream": true}'

# 生成测试脚本
curl -X POST http://localhost:8100/api/v1/sessions/{session_id}/generate/scripts \
  -H "Content-Type: application/json" \
  -d '{"stream": true}'
```

SSE 事件格式：
- `event: status` — 状态更新
- `event: chunk` — 流式文本片段
- `event: result` — 最终结构化结果
- `event: error` — 错误信息

### 6.5 知识库检索

```bash
# 检索
curl -X POST http://localhost:8100/api/v1/kb/search \
  -H "Content-Type: application/json" \
  -d '{"query": "P挡切换", "top_k": 10}'

# 统计
curl http://localhost:8100/api/v1/kb/stats
```

### 6.6 API 文档

完整的交互式 API 文档（Swagger UI）：

```
http://localhost:8100/docs
```

---

## 7. SGLang 部署对接

### 7.1 启动 SGLang

在 GPU 服务器上部署 SGLang（以 Qwen3-4B 为例）：

```bash
# 方法一：使用 SGLang 官方 Docker
docker run --gpus all \
  --shm-size 10g \
  -p 30000:30000 \
  -v /path/to/models:/models \
  lmsysorg/sglang:latest \
  python3 -m sglang.launch_server \
  --model-path /models/Qwen3-4B \
  --port 30000 \
  --host 0.0.0.0

# 方法二：pip 安装
pip install "sglang[all]"
python -m sglang.launch_server \
  --model-path Qwen3-4B \
  --port 30000 \
  --host 0.0.0.0
```

### 7.2 验证 SGLang

```bash
# 检查模型列表
curl http://localhost:30000/v1/models

# 测试对话
curl -X POST http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-4b",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'
```

或使用项目自带的测试脚本：

```bash
python tests/test_sglang_connection.py --base-url http://localhost:30000/v1
```

### 7.3 连接配置

在 `.env` 中设置：

```env
HERMES_LLM_BASE_URL=http://<sglang-ip>:30000/v1
```

- **SGLang 在同一台机器**：`http://localhost:30000/v1`
- **SGLang 在 Docker 宿主机**：`http://host.docker.internal:30000/v1`
- **SGLang 在远程服务器**：`http://<server-ip>:30000/v1`

---

## 8. 测试

### 8.1 SGLang 连通性测试

```bash
python tests/test_sglang_connection.py \
  --base-url http://localhost:30000/v1 \
  --model qwen3-4b
```

测试项：
- GET `/v1/models` — 获取可用模型列表
- POST `/v1/chat/completions` — 发送对话请求

### 8.2 端到端集成测试

```bash
python tests/test_integration.py --host http://localhost:8100
```

测试完整流水线：
1. 创建会话
2. 上传文档
3. 生成需求点（SSE）
4. 生成测试用例（SSE）
5. 生成测试脚本（SSE）
6. 验证数据库持久化
7. 清理测试数据

### 8.3 使用 Makefile

```bash
make test          # 运行所有测试
make test-sglang   # 仅测 SGLang
make test-integration  # 仅测集成
make health        # 健康检查
```

---

## 9. Docker 部署

### 9.1 一键启动

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f api-gateway

# 停止
docker-compose down
```

### 9.2 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| API Gateway | 8100 | 主服务 + 前端 |
| Nginx | 80 | 反向代理入口 |
| RAGFlow | 9380 | 知识库（可选） |

### 9.3 Docker 内连接 SGLang

在 `.env` 中设置：

```env
HERMES_LLM_BASE_URL=http://host.docker.internal:30000/v1
```

或在 `docker-compose.yml` 中取消注释 SGLang 服务定义，加入同一 Docker 网络。

### 9.4 生产 Dockerfile

项目自带的生产级 Dockerfile：
- 基于 `python:3.11-slim`
- 内含 Hermes Agent + skills + patches
- 带 HEALTHCHECK 指令
- 不依赖 volume 挂载（镜像内自带全部依赖）

---

## 10. 常见问题

### Q: 启动后访问页面显示「服务未连接」

A: 检查：
1. 服务是否真的在运行：`curl http://localhost:8100/health`
2. 端口是否被占用：`lsof -i :8100`
3. 防火墙是否放行 8100 端口

### Q: Hermes 导入失败，一直 Mock 模式

A: 常见原因：
1. Hermes Agent 未克隆成功 — 重新运行 `bash setup_hermes.sh`
2. Python 3.10 兼容性补丁未应用 — 检查 `hermes-agent/agent/redact.py` 是否已替换
3. Hermes 依赖未安装 — `cd hermes-agent && pip install -e .`

### Q: SGLang 连接超时

A: 检查：
1. SGLang 是否在运行：`curl http://<sglang-ip>:30000/v1/models`
2. 网络是否可达：`ping <sglang-ip>`
3. 防火墙是否放行 30000 端口
4. 临时跳过检查：在 `.env` 中设 `SGLANG_HEALTH_SKIP=true`

### Q: AI 生成结果为空或 JSON 解析失败

A: 可能原因：
1. 模型输出格式不稳定 — 尝试换一个更强大的模型
2. 输入文档内容过长 — 精简文档或分段上传
3. SGLang 超时 — 增大超时参数或降低并发

### Q: Docker 容器内无法访问宿主机 SGLang

A: 在 `.env` 中使用：
```
HERMES_LLM_BASE_URL=http://host.docker.internal:30000/v1
```
或在 `docker-compose.yml` 的 api-gateway 服务中添加：
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### Q: Python 3.10 报 re.error 正则错误

A: 这是 Hermes 的 `redact.py` 使用了 3.11+ 的正则语法。`setup_hermes.sh` 会自动应用补丁。如果手动安装，执行：
```bash
cp patches/redact_py310_fixed.py hermes-agent/agent/redact.py
```

---

## 项目结构

```
hermes-vcu-gateway/
├── api_gateway/              # API 网关层
│   ├── main.py               # FastAPI 入口
│   ├── config.py             # 配置管理
│   ├── database.py           # SQLite 异步数据库
│   ├── routes/               # 路由层
│   │   ├── health.py         # 健康检查 + SGLang 探测
│   │   ├── session.py        # 会话管理 + 文件上传
│   │   ├── generate.py       # 需求点 + 测试用例生成
│   │   └── script_kb.py      # 脚本生成 + 知识库检索
│   ├── services/             # 服务层
│   │   ├── hermes_service.py # Hermes AIAgent 封装（核心）
│   │   ├── session_service.py
│   │   ├── domain_router.py  # 领域路由（VCU 档位/扭矩）
│   │   └── kb_service.py     # 知识库 + 文档解析
│   ├── middleware/            # 中间件
│   ├── models/               # 数据模型
│   └── static/
│       └── index.html        # 前端界面
├── skills/                   # VCU 领域 skills
│   ├── vcu_gear/SKILL.md     # 档位管理
│   └── vcu_torque/SKILL.md   # 扭矩管理
├── patches/                  # 兼容性补丁
├── tests/                    # 测试套件
├── test_docs/                # 测试文档
├── nginx/                    # Nginx 配置
├── hermes-sglang-deploy/     # 部署技能包
├── Dockerfile                # 生产镜像
├── docker-compose.yml        # Docker 编排
├── setup_hermes.sh           # 一键安装脚本
├── run.sh                    # 启动脚本
├── Makefile                  # 命令快捷方式
├── requirements.txt          # Python 依赖
├── .env.example              # 配置模板
├── USAGE.md                  # 本文件
├── README.md                 # 项目说明
└── LICENSE                   # MIT 许可证
```

---

## 技术栈

- **后端**: FastAPI + Uvicorn + aiosqlite (SQLite 异步) + SSE-Starlette
- **AI 引擎**: Hermes Agent (Nous Research) + SGLang (Qwen3-4B)
- **前端**: 原生 HTML/CSS/JS（无框架依赖，单文件部署）
- **部署**: Docker + Docker Compose + Nginx
- **许可**: MIT
