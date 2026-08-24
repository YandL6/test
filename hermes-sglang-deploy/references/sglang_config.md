# SGLang 配置详解

## 环境变量映射

### .env 关键字段

| 字段 | 值 | 说明 |
|---|---|---|
| `HERMES_LLM_PROVIDER` | `custom` | 绕过 Hermes provider router，直接走 OpenAI 兼容端点 |
| `HERMES_LLM_MODEL` | `qwen3-4b` | 与 SGLang `--model-path` 对应 |
| `HERMES_LLM_API_KEY` | `sglang-dummy-key` | SGLang 默认不鉴权，填任意非空字符串 |
| `HERMES_LLM_BASE_URL` | `http://<ip>:30000/v1` | SGLang 的 OpenAI 兼容端点 |
| `SGLANG_HEALTH_TIMEOUT` | `5` | 健康检查探测超时（秒） |
| `SGLANG_HEALTH_SKIP` | `false` | 设为 true 时跳过 SGLang 连通性检测 |

### 为什么 provider=custom

SGLang 提供 OpenAI 兼容的 `/v1` 端点，但不在 Hermes 的 provider router 内置列表中。设置 `provider=custom` 后，`hermes_service.py` 会直接传入 `api_key` + `base_url` 构造 OpenAI 兼容 client，绕过 provider router。

### sync_hermes_env() 环境变量映射逻辑

`config.py` 中的 `sync_hermes_env()` 方法根据 provider 类型设置不同的环境变量：

- **custom/vllm/sglang**：设置 `CUSTOM_API_KEY` + `CUSTOM_BASE_URL`，同时设置 `OPENAI_API_KEY` + `OPENAI_BASE_URL` 作为 fallback
- **openrouter**：设置 `OPENROUTER_API_KEY` + `OPENROUTER_BASE_URL`
- 通用：始终设置 `HERMES_LLM_API_KEY` + `HERMES_LLM_BASE_URL`

## Docker 内部连接 SGLang

| SGLang 部署位置 | BASE_URL |
|---|---|
| 同一台宿主机 | `http://host.docker.internal:30000/v1` |
| 同一 Docker 网络 | `http://sglang:30000/v1`（取消注释 compose 中 sglang 服务） |
| 另一台服务器 | `http://<服务器IP>:30000/v1` |

## SGLang 启动参考

```bash
# 基本启动
python -m sglang.launch_server \
    --model-path /models/qwen3-4b \
    --port 30000 \
    --host 0.0.0.0

# Docker 启动
docker run --gpus all -p 30000:30000 \
    -v /path/to/models:/models \
    sglang/sglang:latest \
    python3 -m sglang.launch_server \
    --model-path /models/qwen3-4b \
    --port 30000 --host 0.0.0.0
```

## AIAgent 构造参数

创建真实 Agent 时传入的关键参数：

```python
init_kwargs = {
    "model": config.LLM_MODEL,
    "max_iterations": 30,
    "skip_memory": True,
    "skip_context_files": True,
    "load_soul_identity": False,
    "quiet_mode": True,
    "skip_background_review": True,
    "session_id": session_id,
    "enabled_toolsets": [],
    "ephemeral_system_prompt": domain_prompt,
    "max_tokens": 4096,
    "save_trajectories": config.is_dev_mode(),
    "verbose_logging": config.is_dev_mode(),
}
# provider=custom 时同时提供 api_key + base_url
if config.LLM_API_KEY and config.LLM_BASE_URL:
    init_kwargs["api_key"] = config.LLM_API_KEY
    init_kwargs["base_url"] = config.LLM_BASE_URL
    init_kwargs["provider"] = "custom"
```
