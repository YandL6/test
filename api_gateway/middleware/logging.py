"""
请求日志中间件

记录每个请求的方法、路径、耗时、状态码。
使用 loguru 输出结构化日志。
"""
from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from loguru import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件。"""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        method = request.method
        path = request.url.path

        response = await call_next(request)

        elapsed_ms = (time.time() - start) * 1000
        status = response.status_code

        # 根据状态码选择日志级别
        if status >= 500:
            logger.error(f"{method} {path} → {status} ({elapsed_ms:.0f}ms)")
        elif status >= 400:
            logger.warning(f"{method} {path} → {status} ({elapsed_ms:.0f}ms)")
        else:
            logger.info(f"{method} {path} → {status} ({elapsed_ms:.0f}ms)")

        return response
