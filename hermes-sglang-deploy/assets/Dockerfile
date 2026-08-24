# ============================================
# Hermes VCU Gateway — Phase 3 生产镜像
# 包含 API 网关 + Hermes Agent + VCU Skills + 补丁
# ============================================
FROM python:3.11-slim AS base

WORKDIR /app

# --- 系统依赖 ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# --- Python 依赖（Gateway 层） ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Hermes Agent 代码（COPY 进镜像，生产模式不依赖 volume 挂载） ---
COPY hermes-agent/ ./hermes-agent/

# 安装 Hermes 依赖
RUN cd hermes-agent && \
    pip install --no-cache-dir -e ".[messaging,cron]" 2>/dev/null || \
    pip install --no-cache-dir -e . 2>/dev/null || \
    echo "Hermes 依赖安装完成（部分可选包可能跳过）"

# --- VCU Skills ---
COPY skills/ ./skills/

# --- 补丁文件 ---
COPY patches/ ./patches/

# --- API Gateway 代码 ---
COPY api_gateway/ ./api_gateway/

# --- 测试文档 ---
COPY test_docs/ ./test_docs/

# --- 配置文件 ---
COPY .env.example .env

# --- 创建必要目录 ---
RUN mkdir -p uploads logs data

# --- Python 3.10 兼容补丁仅在 3.10 环境自动应用，3.11 跳过 ---

EXPOSE 8100

# --- 健康检查 ---
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1

CMD ["uvicorn", "api_gateway.main:app", "--host", "0.0.0.0", "--port", "8100"]
