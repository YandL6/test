# Hermes Python 3.10 兼容性补丁

## 问题

Hermes Agent 要求 Python 3.11+，但沙箱环境为 Python 3.10.12。

`agent/redact.py` 中有 2 处正则使用了 Python 3.11+ 的 **possessive 量词**（`++`、`*+`），在 Python 3.10 下会抛出 `re.error: multiple repeat`。

## 修复

将 possessive 量词替换为标准量词（功能正确，仅失去 possessive 优化）：

### 补丁 1: `_CFG_DOTTED_RE` (约 203 行)

```diff
- rf"([A-Za-z0-9_\-]++\.[A-Za-z0-9_.\-]*{_SECRET_CFG_NAMES}[A-Za-z0-9_.\-]*+"
- rf"|[A-Za-z0-9_.\-]*{_SECRET_CFG_NAMES}[A-Za-z0-9_.\-]*\.[A-Za-z0-9_.\-]++)"
+ rf"([A-Za-z0-9_\-]+\.[A-Za-z0-9_.\-]*{_SECRET_CFG_NAMES}[A-Za-z0-9_.\-]*"
+ rf"|[A-Za-z0-9_.\-]*{_SECRET_CFG_NAMES}[A-Za-z0-9_.\-]*\.[A-Za-z0-9_.\-]+)"
```

### 补丁 2: `_YAML_ASSIGN_RE` (约 227 行)

```diff
- rf"(^[ \t]*+[A-Za-z0-9_.\-]*{_YAML_CFG_NAMES}[A-Za-z0-9_.\-]*+)(:[ \t]*+)(?!['\"])([^\s&]++)",
+ rf"(^[ \t]*[A-Za-z0-9_.\-]*{_YAML_CFG_NAMES}[A-Za-z0-9_.\-]*)(:[ \t]*)(?!['\"])([^\s&]+)",
```

## 应用方法

```bash
# 将补丁文件覆盖到 Hermes 安装目录
cp patches/redact_py310_fixed.py hermes-agent/agent/redact.py
```

## 验证

```bash
python3 -c "
import sys; sys.path.insert(0, 'hermes-agent')
from run_agent import AIAgent
print('AIAgent imported OK')
"
```
