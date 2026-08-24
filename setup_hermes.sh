#!/usr/bin/env bash
# ============================================
# Hermes VCU Gateway — 一键安装脚本
# ============================================
# 功能：检测环境 → 克隆 Hermes → 安装依赖 → 初始化配置
#
# 用法：bash setup_hermes.sh [--venv]
#   --venv  创建并使用 Python 虚拟环境
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_DIR="${SCRIPT_DIR}/hermes-agent"
USE_VENV=false
PYTHON_BIN=""

# --- 参数解析 ---
for arg in "$@"; do
    case "$arg" in
        --venv) USE_VENV=true ;;
        --help|-h)
            echo "用法: bash setup_hermes.sh [--venv]"
            echo "  --venv  创建并使用 Python 虚拟环境（推荐）"
            exit 0 ;;
    esac
done

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Hermes VCU Gateway — 一键安装           ║"
echo "║   重庆大学 · VCU 智能测试用例生成平台    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ============================================
# 1. 检测 Python 版本 (>=3.10)
# ============================================
echo "── [1/6] 检测 Python 环境 ─────────────────"

if command -v python3 &> /dev/null; then
    PYTHON_BIN="python3"
elif command -v python &> /dev/null; then
    PYTHON_BIN="python"
else
    echo "❌ 未找到 Python，请安装 Python 3.10+"
    echo "   Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "   macOS: brew install python@3.11"
    exit 1
fi

PY_VERSION=$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
echo "   Python: ${PYTHON_BIN} (v${PY_VERSION})"

PY_MAJOR=$(${PYTHON_BIN} -c 'import sys; print(sys.version_info[0])')
PY_MINOR=$(${PYTHON_BIN} -c 'import sys; print(sys.version_info[1])')

if [ "${PY_MAJOR}" -lt 3 ] || ([ "${PY_MAJOR}" -eq 3 ] && [ "${PY_MINOR}" -lt 10 ]); then
    echo "❌ Python ${PY_VERSION} 版本过低，需要 3.10+"
    exit 1
fi
echo "   ✅ 版本符合要求 (≥3.10)"

# ============================================
# 2. 检测 git
# ============================================
echo ""
echo "── [2/6] 检测 git ────────────────────────"
if ! command -v git &> /dev/null; then
    echo "⚠  未检测到 git，将跳过 Hermes 克隆"
    echo "   如需完整功能，请安装 git: sudo apt install git"
    SKIP_HERMES_CLONE=true
else
    echo "   ✅ git $(git --version | awk '{print $3}')"
    SKIP_HERMES_CLONE=false
fi

# ============================================
# 3. 虚拟环境（可选）
# ============================================
VENV_DIR="${SCRIPT_DIR}/.venv"

if [ "${USE_VENV}" = true ]; then
    echo ""
    echo "── [3/6] 创建虚拟环境 ────────────────────"
    if [ ! -d "${VENV_DIR}" ]; then
        ${PYTHON_BIN} -m venv "${VENV_DIR}"
        echo "   ✅ 虚拟环境已创建: ${VENV_DIR}"
    else
        echo "   ⏭  虚拟环境已存在，跳过创建"
    fi
    # 激活虚拟环境
    source "${VENV_DIR}/bin/activate"
    PYTHON_BIN="python"
    PIP_BIN="pip"
    echo "   ✅ 已激活虚拟环境"
else
    echo ""
    echo "── [3/6] 跳过虚拟环境（未指定 --venv） ──"
    PIP_BIN="${PYTHON_BIN} -m pip"
fi

# 确保 pip 可用
${PYTHON_BIN} -m pip install --upgrade pip -q 2>/dev/null || true

# ============================================
# 4. 克隆 Hermes Agent 仓库
# ============================================
echo ""
echo "── [4/6] 安装 Hermes Agent ────────────────"

if [ "${SKIP_HERMES_CLONE}" = true ]; then
    echo "   ⚠  跳过 Hermes 克隆（git 未安装）"
    echo "      平台将以 Mock 模式运行（API 可用但 AI 生成返回模拟数据）"
else
    if [ -d "${HERMES_DIR}" ]; then
        echo "   ⏭  Hermes 目录已存在，跳过克隆"
        # 验证关键文件存在
        if [ -f "${HERMES_DIR}/run_agent.py" ]; then
            echo "   ✅ run_agent.py 存在"
        else
            echo "   ⚠  目录存在但缺少 run_agent.py，可能克隆不完整"
            echo "      删除 ${HERMES_DIR} 后重新运行本脚本可修复"
        fi
    else
        echo "   📦 克隆 Hermes Agent 仓库..."
        if git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "${HERMES_DIR}" 2>/dev/null; then
            echo "   ✅ Hermes Agent 克隆成功"
        else
            echo "   ⚠  GitHub 克隆失败（可能是网络问题）"
            echo "      平台将以 Mock 模式运行"
            echo "      可手动执行: git clone https://github.com/NousResearch/hermes-agent.git ${HERMES_DIR}"
        fi
    fi

    # 安装 Hermes 依赖
    if [ -f "${HERMES_DIR}/pyproject.toml" ]; then
        echo "   📦 安装 Hermes 依赖..."
        cd "${HERMES_DIR}"
        ${PIP_BIN} install -e ".[messaging,cron]" -q 2>/dev/null || {
            echo "   ⚠  Hermes 依赖安装部分失败，尝试最小安装..."
            ${PIP_BIN} install -e . -q 2>/dev/null || true
        }
        cd "${SCRIPT_DIR}"
        echo "   ✅ Hermes 依赖安装完成"
    fi
fi

# ============================================
# 5. 安装 API Gateway 依赖
# ============================================
echo ""
echo "── [5/6] 安装 API Gateway 依赖 ─────────────"
${PIP_BIN} install -r "${SCRIPT_DIR}/requirements.txt" -q 2>/dev/null || {
    echo "   ⚠  部分依赖安装失败，尝试逐个安装..."
    while IFS= read -r line; do
        line=$(echo "$line" | sed 's/#.*//;s/^[[:space:]]*//;s/[[:space:]]*$//')
        [ -z "$line" ] && continue
        ${PIP_BIN} install "$line" -q 2>/dev/null || echo "   ⚠  跳过: $line"
    done < "${SCRIPT_DIR}/requirements.txt"
}
echo "   ✅ API Gateway 依赖安装完成"

# ============================================
# 6. 初始化配置和目录
# ============================================
echo ""
echo "── [6/6] 初始化配置 ───────────────────────"

# .env 文件
if [ ! -f "${SCRIPT_DIR}/.env" ]; then
    cp "${SCRIPT_DIR}/.env.example" "${SCRIPT_DIR}/.env"
    echo "   ✅ 已从模板创建 .env 文件"
    echo "   ⚠  请编辑 .env 配置 LLM 连接信息"
else
    echo "   ⏭  .env 已存在，跳过"
fi

# 必要目录
mkdir -p "${SCRIPT_DIR}/uploads" "${SCRIPT_DIR}/logs"
echo "   ✅ 已创建 uploads/ 和 logs/ 目录"

# 应用 Python 3.10 兼容补丁
if [ -f "${SCRIPT_DIR}/patches/redact_py310_fixed.py" ] && [ -d "${HERMES_DIR}/agent" ]; then
    PY_PATCH_CHECK=$(${PYTHON_BIN} -c 'import sys; print("3.11+" if sys.version_info >= (3,11) else "3.10")' 2>/dev/null || echo "unknown")
    if [ "${PY_PATCH_CHECK}" = "3.10" ]; then
        cp "${SCRIPT_DIR}/patches/redact_py310_fixed.py" "${HERMES_DIR}/agent/redact.py" 2>/dev/null && \
            echo "   ✅ 已应用 Python 3.10 兼容补丁" || true
    fi
fi

# ============================================
# 完成
# ============================================
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║           ✅ 安装完成！                   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "下一步操作:"
echo ""
if [ "${USE_VENV}" = true ]; then
    echo "  1. 激活虚拟环境:"
    echo "       source ${VENV_DIR}/bin/activate"
    echo ""
fi
echo "  2. 编辑 .env 配置 LLM 连接:"
echo "       vi .env"
echo "       # 重点修改 HERMES_LLM_BASE_URL 指向你的 SGLang 地址"
echo ""
echo "  3. 启动服务:"
echo "       bash run.sh"
echo "       # 或: python -m api_gateway.main"
echo ""
echo "  4. 打开浏览器访问:"
echo "       http://localhost:8100"
echo ""
echo "  5. 查看API文档:"
echo "       http://localhost:8100/docs"
echo ""
echo "  6. 运行测试:"
echo "       python tests/test_sglang_connection.py --base-url http://localhost:30000/v1"
echo "       python tests/test_integration.py --host http://localhost:8100"
echo ""
echo "  详细使用指南: 请阅读 USAGE.md"
echo ""
