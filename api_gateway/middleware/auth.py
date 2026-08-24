"""
认证中间件

Phase 1 实现 Token 校验（从 Header 或 query 参数读取）。
开发模式下（API_TOKENS 为空）跳过认证。
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api_gateway.config import config
from api_gateway.models.responses import ErrorCode, fail


# 不需要认证的路径
PUBLIC_PATHS = {"/", "/health", "/api/v1/domains", "/docs", "/redoc", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    """API Token 认证中间件。"""

    async def dispatch(self, request: Request, call_next):
        # 开发模式 — 跳过
        if config.is_dev_mode():
            return await call_next(request)

        path = request.url.path

        # 公开路径 — 跳过
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # 从 Header 或 query 参数读取 Token
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.query_params.get("token", "")

        if token not in config.API_TOKENS:
            return JSONResponse(
                status_code=401,
                content=fail(
                    ErrorCode.UNAUTHORIZED,
                    "无效或缺失的 API Token",
                    detail="请在 Authorization Header 中提供 Bearer Token，或在 query 参数中提供 token",
                ),
            )

        return await call_next(request)
