#!/usr/bin/env bash
# ============================================
# Hermes VCU Gateway 启动脚本
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "启动 Hermes VCU Gateway..."
echo ""

# 方式 1: 直接 uvicorn
if command -v uvicorn &> /dev/null; then
    uvicorn api_gateway.main:app --host 0.0.0.0 --port 8100 --reload
# 方式 2: python -m
else
    python -m api_gateway.main
fi
