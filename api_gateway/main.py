"""
Hermes VCU Gateway — FastAPI 主入口

B 模块 Phase 1: API 网关层

功能：
1. 将 Hermes AIAgent 封装为 REST API 服务
2. 提供 VCU 测试用例生成全链路接口（需求点 → 用例 → 脚本）
3. SSE 流式响应
4. 统一错误处理 + 认证 + 日志
5. 文件上传支持
6. 知识库检索接口（RAGFlow 对接预留）

启动: python -m api_gateway.main  或  uvicorn api_gateway.main:app --port 8100
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from api_gateway.config import config
from api_gateway.middleware.error_handler import ErrorHandlerMiddleware
from api_gateway.middleware.auth import AuthMiddleware
from api_gateway.middleware.logging import LoggingMiddleware
from api_gateway.routes import health, session, generate, script_kb


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="Hermes VCU Gateway",
        description=(
            "B 模块 API 网关层 — 将 Hermes AIAgent 封装为 REST API 服务，"
            "面向 VCU 测试用例生成全链路。"
        ),
        version="0.3.0-phase3",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- 中间件（注册顺序: 后注册的先执行） ---
    # CORS — 允许 Web 前端和桌面端跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Phase 2 联调时收紧为具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)

    # --- 路由注册 ---
    app.include_router(health.router)
    app.include_router(session.router)
    app.include_router(generate.router)
    app.include_router(script_kb.script_router)
    app.include_router(script_kb.kb_router)

    # --- 静态文件服务（C 模块 Web 前端） ---
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        logger.info(f"  Web 前端: http://localhost:{config.PORT}/static/index.html")

    # --- 启动事件 ---
    @app.on_event("startup")
    async def on_startup():
        Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
        Path(config.LOG_DIR).mkdir(parents=True, exist_ok=True)
        # Phase 2: 初始化数据库
        from api_gateway.database import init_db, get_stats
        await init_db()
        stats = await get_stats()
        logger.info("=" * 60)
        logger.info(f"Hermes VCU Gateway 启动 — Phase 3 (SGLang)")
        logger.info(f"  监听: {config.HOST}:{config.PORT}")
        logger.info(f"  Hermes 目录: {config.hermes_path}")
        logger.info(f"  LLM: {config.LLM_PROVIDER} / {config.LLM_MODEL}")
        logger.info(f"  沙箱: {config.SANDBOX_BACKEND}")
        logger.info(f"  开发模式: {config.is_dev_mode()}")
        logger.info(f"  数据库: SQLite 持久化已启用")
        logger.info(f"  数据统计: 会话={stats['sessions']} 文档={stats['documents']} 需求={stats['requirements']} 用例={stats['testcases']} 脚本={stats['scripts']}")
        logger.info(f"  API 文档: http://localhost:{config.PORT}/docs")
        logger.info("=" * 60)

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Hermes VCU Gateway 关闭")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_gateway.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level=config.LOG_LEVEL.lower(),
    )
