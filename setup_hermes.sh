#!/usr/bin/env bash
# ============================================
# Hermes Agent 安装脚本
# ============================================
# 功能：克隆 Hermes 仓库、安装依赖、初始化配置
#
# 用法：bash setup_hermes.sh
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_DIR="${SCRIPT_DIR}/hermes-agent"

echo "=========================================="
echo "  Hermes Agent 安装脚本 (B 模块 Phase 1)"
echo "=========================================="
echo ""

# --- 1. 克隆 Hermes 仓库 ---
if [ -d "${HERMES_DIR}" ]; then
    echo "[1/4] Hermes 目录已存在，跳过克隆"
else
    echo "[1/4] 克隆 Hermes Agent 仓库..."
    git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "${HERMES_DIR}"
fi

# --- 2. 安装 Python 依赖 ---
echo "[2/4] 安装 API Gateway 依赖..."
pip install -r "${SCRIPT_DIR}/requirements.txt" 2>/dev/null || pip3 install -r "${SCRIPT_DIR}/requirements.txt"

echo "[3/4] 安装 Hermes Agent 依赖..."
cd "${HERMES_DIR}"
if command -v uv &> /dev/null; then
    echo "  使用 uv 安装..."
    uv pip install -e ".[messaging,cron]" 2>/dev/null || pip install -e ".[messaging,cron]"
else
    echo "  使用 pip 安装..."
    pip install -e ".[messaging,cron]" 2>/dev/null || pip3 install -e ".[messaging,cron]"
fi

# --- 3. 初始化 Hermes 配置 ---
echo "[4/4] 初始化 Hermes 配置..."
cd "${SCRIPT_DIR}"

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  已创建 .env 文件，请编辑配置 LLM API Key 等"
fi

# 创建必要目录
mkdir -p uploads logs

# --- 完成 ---
echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "下一步:"
echo "  1. 编辑 .env 文件，配置 LLM API Key"
echo "  2. 启动服务:"
echo "     python -m api_gateway.main"
echo "     或"
echo "     uvicorn api_gateway.main:app --port 8100 --reload"
echo ""
echo "  3. 访问 API 文档: http://localhost:8100/docs"
echo ""
echo "  4. 测试健康检查:"
echo "     curl http://localhost:8100/health"
echo ""
