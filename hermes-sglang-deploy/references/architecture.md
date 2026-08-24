# 架构设计

## Hermes 封装方式

```
Web 前端 → REST API (FastAPI) → HermesService → Hermes AIAgent (Python 库)
                                         ↓
                                    domain_router (选择领域 Prompt)
```

### 惰性导入

首次调用时才 `sys.path.insert` + `import AIAgent`，避免启动延迟。导入前执行：
1. `_set_hermes_home()` — 设置 `HERMES_HOME` 环境变量指向项目根目录，让 Hermes 发现 VCU skills
2. `config.sync_hermes_env()` — 将 Gateway 配置同步到 Hermes 期望的环境变量名
3. `_apply_py310_patches()` — Python 3.10 环境自动应用正则兼容补丁

### 会话隔离

每个 `session_id` 对应一个独立的 AIAgent 实例，由 `SessionAgentManager` 用 `asyncio.Lock` 管理内部字典。首次创建时通过 `domain_id` 注入领域 system prompt（`ephemeral_system_prompt`），已创建的 Agent 不受后续 domain_id 变更影响。

### Mock 降级

SGLang 不可达或无 API Key 时，自动降级为 `_MockAgent`，返回模拟 VCU 测试数据（需求点/用例/脚本），保证 API 链路可联调。Mock Agent 根据 user message 中的关键词匹配任务类型返回对应模拟数据。

### SSE 流式输出

真实 AIAgent 的 `chat()` 是同步方法，通过 `stream_callback` 参数实现流式输出。使用 `asyncio.Queue` 桥接同步回调到 async 迭代：
1. 创建 `asyncio.Queue`
2. 在线程池中执行同步 `chat(stream_callback=cb)`
3. 回调函数把流式输出推入队列
4. 主协程从队列消费并 yield 给 SSE

## 错误分类

`_classify_hermes_error()` 将异常映射为 `(ErrorCode, message, http_status)`：

| 异常关键词 | ErrorCode | HTTP Status |
|---|---|---|
| rate_limit / 429 | HERMES_RATE_LIMIT | 429 |
| context_too_long / token limit | HERMES_CONTEXT_TOO_LONG | 413 |
| connection / timeout / refused | HERMES_PROVIDER_DOWN | 503 |
| 其他 | HERMES_LLM_ERROR | 500 |

## JSON 容错

`extract_json()` 从可能混杂自然语言的文本中提取 JSON：
1. 尝试从 ` ```json ... ``` ` 代码块提取
2. 尝试找最外层 `[...]`（JSON 数组，贪婪匹配）
3. 尝试找最外层 `{...}`（JSON 对象，贪婪匹配）
4. 尝试整体 `json.loads()`

## 领域路由

`domain_router.py` 将 system prompt 与 user message 分离：
- `build_system_prompt(domain_id)` — 仅返回领域 system prompt，用于 `ephemeral_system_prompt`
- `build_user_message(domain_id, task, context)` — 仅返回 task 指令 + context
- `build_prompt(domain_id, task, context)` — 兼容旧接口，合并两者

## 数据库设计

6 张 SQLite 表（aiosqlite 异步操作）：

| 表名 | 用途 |
|---|---|
| `sessions` | 会话主表 |
| `documents` | 上传的需求文档 |
| `requirements` | AI 生成的需求点 |
| `testcases` | AI 生成的测试用例 |
| `scripts` | AI 生成的测试脚本 |
| `kb_chunks` | 知识库分块 |

文档上传后自动分块索引到 `kb_chunks` 表。KB 检索先查本地 SQLite，可选远程 RAGFlow。
