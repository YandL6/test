# 排障指南

## SGLang 不可达

### 症状

`curl http://localhost:8100/health` 返回 `sglang.reachable: false`。

### 排查步骤

1. **确认 SGLang 进程在运行**
   ```bash
   ps aux | grep sglang
   ```

2. **确认端口开放**
   ```bash
   curl http://<sglang-ip>:30000/v1/models
   ```
   返回 JSON 列出已加载模型即可。

3. **Docker 内访问宿主机**
   - 确认 `host.docker.internal` 可用
   - 或使用 `--network host` 模式
   - 或在 `docker-compose.yml` 中取消注释 sglang 服务

4. **防火墙**
   ```bash
   # iptables
   sudo iptables -L -n | grep 30000
   # firewalld
   sudo firewall-cmd --list-ports
   ```

5. **跳过检测（临时）**
   `.env` 中设置 `SGLANG_HEALTH_SKIP=true`，健康检查不再探测 SGLang。

## Hermes 导入失败

### 症状

`/health` 返回 `hermes_available: false`，日志显示 `Hermes 未安装或导入失败`。

### 排查步骤

1. **确认 hermes-agent 目录存在**
   ```bash
   ls hermes-agent/run_agent.py
   ```

2. **确认 Hermes 依赖已安装**
   ```bash
   cd hermes-agent && pip install -e .
   ```

3. **查看 Gateway 日志**
   ```bash
   tail -100 ./logs/*.log
   ```

4. **手动测试导入**
   ```python
   import sys
   sys.path.insert(0, "./hermes-agent")
   from run_agent import AIAgent
   print("OK")
   ```

## Python 3.10 兼容性

### 症状

`re.error: bad escape` 或 `possessive quantifier` 报错。

### 原因

`hermes-agent/agent/redact.py` 使用了 Python 3.11+ 的占有量词语法（`++`、`*+`），在 Python 3.10 下会报 `re.error`。

### 解决

Gateway 启动时自动检测 Python 版本并应用补丁文件 `patches/redact_py310_fixed.py`。如补丁未自动应用，手动执行：

```bash
cp patches/redact_py310_fixed.py hermes-agent/agent/redact.py
```

## 环境变量冲突

### 症状

Hermes Agent 使用了错误的 LLM provider 或 API Key。

### 原因

Hermes-agent 在导入时自动加载 `HERMES_HOME/.env` 文件，可能与 Gateway 的 `.env` 冲突。

### 解决

`config.sync_hermes_env()` 会在导入前将 Gateway 配置映射到 Hermes 期望的变量名。确保：
1. `.env` 中 `HERMES_LLM_PROVIDER` 设置正确
2. `HERMES_HOME` 环境变量指向项目根目录（由 `_set_hermes_home()` 自动设置）
3. 不要在 `hermes-agent/` 目录下放置 `.env` 文件

## SSE 流式输出卡住

### 症状

生成请求发出后长时间无响应，SSE 连接挂起。

### 排查步骤

1. 检查 SGLang 是否在推理（GPU 利用率）
2. 检查 `max_tokens` 设置是否过大
3. 检查 `SANDBOX_TIMEOUT` 是否足够
4. 查看 Gateway 日志中是否有线程异常

## JSON 解析失败

### 症状

`HERMES_JSON_PARSE_FAILED` 错误，AI 返回内容无法解析为 JSON。

### 解决

`extract_json()` 已实现 4 级容错（代码块 → 数组 → 对象 → 整体）。如仍失败，可能是模型输出格式不稳定。尝试：
1. 降低 `temperature` 到 0.1-0.3
2. 在 user message 中强调"严格 JSON 格式，不包含额外文本"
3. 使用更大的模型（如 Qwen3-14B）改善格式遵循能力
