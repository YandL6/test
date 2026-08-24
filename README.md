# Hermes VCU Gateway

> 基于 Nous Research 开源 Hermes AI Agent + 自部署 SGLang 大模型，
> 自动生成 VCU（整车控制器）测试用例与自动化脚本的全链路平台。

**版本：0.4.0** · 重庆大学 · MIT License

📖 **[详细使用指南](USAGE.md)** — 安装、配置、API 调用、Docker 部署、FAQ 全覆盖

---

## ✨ v0.4.0 新特性

- **DeepSeek 风格前端**：左侧栏会话历史 + 右侧主区域对话式工作流，参考 DeepSeek 界面风格
- **重庆大学视觉融合**：校色深红 (#C81623) 配色方案 + CQU 品牌元素
- **开箱即用**：一键安装脚本（`setup_hermes.sh --venv`），自动检测环境、克隆、安装、配置
- **根路由前端**：访问 `http://localhost:8100/` 直接打开界面（不再需要 `/static/index.html`）
- **预检启动**：`run.sh` 启动前自动检查 Python / .env / 依赖 / Hermes 目录
- **Makefile**：`make setup` / `make dev` / `make test` / `make docker-up` 一键操作
- **知识库搜索栏**：界面底部集成知识库检索入口
- **会话历史管理**：侧边栏按日期分组展示历史会话，支持点击切换 / 删除

---

## 🚀 快速开始

```bash
# 1. 克隆
git clone https://github.com/YandL6/test.git hermes-vcu-gateway
cd hermes-vcu-gateway

# 2. 一键安装（含虚拟环境）
bash setup_hermes.sh --venv

# 3. 配置 LLM 地址
vi .env  # 修改 HERMES_LLM_BASE_URL 指向你的 SGLang

# 4. 启动
source .venv/bin/activate
bash run.sh
```

打开浏览器访问 `http://localhost:8100` 即可使用。

> **即使没有 SGLang**，平台也能以 Mock 模式运行——API 链路完整可用，AI 生成返回模拟数据。

---

## 项目结构

```
hermes-vcu-gateway/
├── api_gateway/               # API 网关层
│   ├── main.py                # FastAPI 入口（根路由返回前端）
│   ├── config.py              # 配置管理（SGLang + provider=custom）
│   ├── database.py            # SQLite 异步数据库（6 表）
│   ├── routes/                # 路由层
│   │   ├── health.py          # 健康检查 + SGLang 连通性探测
│   │   ├── session.py         # 会话管理 + 文件上传
│   │   ├── generate.py        # 需求点 + 测试用例生成（SSE）
│   │   └── script_kb.py       # 脚本生成 + 知识库检索
│   ├── services/              # 服务层
│   │   ├── hermes_service.py  # Hermes AIAgent 封装（核心）
│   │   ├── session_service.py # 会话状态管理
│   │   └── domain_router.py   # 领域路由（VCU 档位/扭矩）
│   ├── middleware/            # 中间件（错误处理 / 认证 / 日志）
│   ├── models/                # 数据模型
│   └── static/
│       └── index.html         # 前端界面（DeepSeek + CQU 风格）
├── skills/                    # VCU 领域 skills
│   ├── vcu_gear/SKILL.md      # 档位管理
│   └── vcu_torque/SKILL.md    # 扭矩管理
├── tests/                     # 测试套件
│   ├── test_sglang_connection.py  # SGLang 冒烟测试
│   └── test_integration.py        # 端到端集成测试
├── patches/                   # Python 3.10 兼容补丁
├── nginx/nginx.conf           # Nginx 反向代理配置
├── hermes-sglang-deploy/      # 部署技能包（已发布 SkillHub）
├── docker-compose.yml         # Docker 编排
├── Dockerfile                 # 生产镜像
├── setup_hermes.sh            # 一键安装脚本
├── run.sh                     # 启动脚本（含预检）
├── Makefile                   # 命令快捷方式
├── requirements.txt           # Python 依赖
├── .env.example               # 配置模板
├── USAGE.md                   # 使用指南
└── LICENSE                    # MIT
```

---

## 常用命令

```bash
make setup          # 一键安装（含虚拟环境）
make dev            # 开发模式启动（热重载）
make prod           # 生产模式启动
make test           # 运行所有测试
make health         # 健康检查
make docker-up      # Docker 启动
make clean          # 清理临时文件
```

---

## API 接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 前端界面 |
| GET | `/docs` | Swagger API 文档 |
| GET | `/health` | 健康检查（Hermes + SGLang） |
| GET | `/health/sglang` | SGLang 连通性诊断 |
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

完整接口说明详见 [USAGE.md](USAGE.md#6-api-接口调用)。

---

## SGLang 配置

SGLang 提供 OpenAI 兼容的 `/v1` 端点，设置 `provider=custom` 可绕过 Hermes 内部 provider router 直连。

```env
HERMES_LLM_PROVIDER=custom
HERMES_LLM_MODEL=qwen3-4b
HERMES_LLM_API_KEY=sglang-dummy-key
HERMES_LLM_BASE_URL=http://localhost:30000/v1
```

SGLang 部署详见 [USAGE.md](USAGE.md#7-sglang-部署对接)。

---

## 运行模式

| 模式 | 条件 | 行为 |
|------|------|------|
| `real-hermes` | Hermes 安装 + API Key 配置 + SGLang 可达 | 真实 LLM 生成 |
| `mock` | Hermes 安装但 SGLang 不可达 | API 可用，AI 生成返回模拟数据 |
| `unavailable` | Hermes 未安装 | 全部 Mock，API 仍可联调 |

---

## hermes-sglang-deploy 技能包

仓库内含 `hermes-sglang-deploy/` 目录——Hermes+SGLang 集成部署的可复用技能，已发布至 Aily SkillHub。

SkillHub 分享链接：https://aily.feishu.cn/skills/shared/ad1612b4-e4b2-4dcf-b25d-356d53ab76e3

---

## License

MIT — 见 [LICENSE](LICENSE)
