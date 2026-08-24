#!/usr/bin/env bash
# ============================================
# Hermes VCU Gateway — 启动脚本
# ============================================
# 用法：bash run.sh [--prod]
#   --prod  生产模式（关闭热重载）
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PROD_MODE=false
for arg in "$@"; do
    case "$arg" in
        --prod) PROD_MODE=true ;;
    esac
done

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Hermes VCU Gateway — 启动中...          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# --- 前置检查 ---
echo "── 前置检查 ──────────────────────────────"

# 1. Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "❌ 未检测到 Python，请先运行: bash setup_hermes.sh"
    exit 1
fi
PYTHON_BIN="python3"
command -v python3 &> /dev/null || PYTHON_BIN="python"

# 2. .env 文件
if [ ! -f ".env" ]; then
    echo "⚠  .env 文件不存在，从模板创建中..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "   ✅ 已创建 .env（请编辑配置 LLM 连接信息）"
    else
        echo "   ❌ .env.example 也不存在，请检查项目完整性"
        exit 1
    fi
fi

# 3. 依赖检查
if ! ${PYTHON_BIN} -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "⚠  缺少 Python 依赖，正在安装..."
    ${PYTHON_BIN} -m pip install -r requirements.txt -q 2>/dev/null || {
        echo "❌ 依赖安装失败，请手动运行: bash setup_hermes.sh"
        exit 1
    }
    echo "   ✅ 依赖安装完成"
fi

# 4. Hermes Agent 目录
HERMES_DIR="./hermes-agent"
if [ ! -d "${HERMES_DIR}" ]; then
    echo "⚠  Hermes Agent 未安装 — 将以 Mock 模式运行"
    echo "   如需完整 AI 功能，请运行: bash setup_hermes.sh"
else
    echo "   ✅ Hermes Agent 目录存在"
fi

# 5. 必要目录
mkdir -p uploads logs

echo "   ✅ 前置检查通过"
echo ""

# --- 启动 ---
PORT=$(${PYTHON_BIN} -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('GATEWAY_PORT', '8100'))" 2>/dev/null || echo "8100")

if [ "${PROD_MODE}" = true ]; then
    echo "🚀 生产模式启动 — http://0.0.0.0:${PORT}"
    echo ""
    exec ${PYTHON_BIN} -m uvicorn api_gateway.main:app --host 0.0.0.0 --port ${PORT}
else
    echo "🚀 开发模式启动 — http://localhost:${PORT}"
    echo ""
    exec ${PYTHON_BIN} -m uvicorn api_gateway.main:app --host 0.0.0.0 --port ${PORT} --reload
fi
