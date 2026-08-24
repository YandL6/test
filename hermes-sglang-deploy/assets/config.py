"""
Hermes VCU Gateway — 全局配置管理

从环境变量 / .env 文件加载配置，统一管理所有模块参数。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Config:
    """全局配置单例，各模块直接 import config 使用。"""

    # --- 服务 ---
    HOST: str = os.getenv("GATEWAY_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("GATEWAY_PORT", "8100"))

    # --- Hermes Agent ---
    HERMES_HOME_DIR: str = os.getenv("HERMES_HOME_DIR", "./hermes-agent")
    HERMES_PROFILE: str = os.getenv("HERMES_PROFILE", "default")
    LLM_PROVIDER: str = os.getenv("HERMES_LLM_PROVIDER", "openrouter")
    LLM_MODEL: str = os.getenv("HERMES_LLM_MODEL", "anthropic/claude-3.5-sonnet")
    LLM_API_KEY: str = os.getenv("HERMES_LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("HERMES_LLM_BASE_URL", "")

    # --- Phase 3: SGLang 健康检查 ---
    SGLANG_HEALTH_TIMEOUT: int = int(os.getenv("SGLANG_HEALTH_TIMEOUT", "5"))
    SGLANG_HEALTH_SKIP: bool = os.getenv("SGLANG_HEALTH_SKIP", "false").lower() == "true"

    # --- 沙箱 ---
    SANDBOX_BACKEND: str = os.getenv("HERMES_SANDBOX_BACKEND", "docker")
    SANDBOX_IMAGE: str = os.getenv("HERMES_SANDBOX_IMAGE", "python:3.11-slim")
    SANDBOX_TIMEOUT: int = int(os.getenv("HERMES_SANDBOX_TIMEOUT", "300"))

    # --- 知识库 RAGFlow ---
    RAGFLOW_BASE_URL: str = os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380")
    RAGFLOW_API_KEY: str = os.getenv("RAGFLOW_API_KEY", "")

    # --- 安全 ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me")
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "72"))
    API_TOKENS: list[str] = [
        t.strip() for t in os.getenv("API_TOKENS", "").split(",") if t.strip()
    ]

    # --- 日志 ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")

    # --- 文件上传 ---
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    ALLOWED_EXTENSIONS: list[str] = [
        ext.strip()
        for ext in os.getenv("ALLOWED_EXTENSIONS", ".pdf,.docx,.xlsx").split(",")
    ]

    # --- 项目根目录 ---
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

    @property
    def hermes_path(self) -> Path:
        """Hermes 安装目录的绝对路径。"""
        return (self.PROJECT_ROOT / self.HERMES_HOME_DIR).resolve()

    @property
    def hermes_python_path(self) -> Path:
        """将 Hermes 目录加入 sys.path 时的路径。"""
        return self.hermes_path

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    def is_dev_mode(self) -> bool:
        """开发模式：不校验 API Token。"""
        return len(self.API_TOKENS) == 0

    def sync_hermes_env(self) -> None:
        """将 Gateway 配置同步到 Hermes 期望的环境变量名。

        Hermes-agent 的 run_agent.py 在导入时自动加载 HERMES_HOME/.env，
        使用 provider 专属变量名（如 OPENROUTER_API_KEY）。
        本方法将 config 中的 LLM_API_KEY / LLM_BASE_URL 映射到 Hermes
        期望的变量名，确保两套配置不冲突。

        Phase 3: 当 provider=custom（SGLang 自部署）时，
        Hermes 内部会读取 CUSTOM_API_KEY / CUSTOM_BASE_URL 变量，
        同时也需要 OPENAI_API_KEY / OPENAI_BASE_URL 作为 OpenAI 兼容 fallback。
        """
        if not self.LLM_API_KEY:
            return

        provider = self.LLM_PROVIDER.lower()

        if provider in ("custom", "custom_api", "vllm", "sglang"):
            # Phase 3: SGLang / vLLM 自部署 — 使用 custom_api provider
            if not os.environ.get("CUSTOM_API_KEY"):
                os.environ["CUSTOM_API_KEY"] = self.LLM_API_KEY
            if self.LLM_BASE_URL and not os.environ.get("CUSTOM_BASE_URL"):
                os.environ["CUSTOM_BASE_URL"] = self.LLM_BASE_URL
            # 同时设置 OPENAI_* 变量，作为 Hermes 内部 OpenAI client 的 fallback
            if not os.environ.get("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = self.LLM_API_KEY
            if self.LLM_BASE_URL and not os.environ.get("OPENAI_BASE_URL"):
                os.environ["OPENAI_BASE_URL"] = self.LLM_BASE_URL
        elif provider == "openrouter":
            if not os.environ.get("OPENROUTER_API_KEY"):
                os.environ["OPENROUTER_API_KEY"] = self.LLM_API_KEY
            if self.LLM_BASE_URL and not os.environ.get("OPENROUTER_BASE_URL"):
                os.environ["OPENROUTER_BASE_URL"] = self.LLM_BASE_URL

        # 通用 fallback — 无论 provider 是什么，都设置 HERMES_ 前缀
        if not os.environ.get("HERMES_LLM_API_KEY"):
            os.environ["HERMES_LLM_API_KEY"] = self.LLM_API_KEY
        if self.LLM_BASE_URL and not os.environ.get("HERMES_LLM_BASE_URL"):
            os.environ["HERMES_LLM_BASE_URL"] = self.LLM_BASE_URL


config = Config()
