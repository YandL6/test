"""
统一错误处理中间件

捕获所有未处理异常，按统一格式返回错误响应。
确保前端永远收到结构化的 JSON，不会看到 500 堆栈。
"""
from __future__ import annotations

import json
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api_gateway.models.responses import APIError, ErrorCode, fail
from api_gateway.config import config


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """全局异常捕获中间件。"""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except APIError as e:
            # 业务异常 — 返回结构化错误
            return JSONResponse(
                status_code=e.status_code,
                content=fail(e.code, e.message, e.detail),
            )
        except json.JSONDecodeError as e:
            return JSONResponse(
                status_code=400,
                content=fail(
                    ErrorCode.VALIDATION_ERROR,
                    f"JSON 解析失败: {e}",
                ),
            )
        except Exception as e:
            # 未知异常 — 记录完整堆栈，返回 500
            tb = traceback.format_exc()
            detail = tb if config.LOG_LEVEL == "DEBUG" else None
            return JSONResponse(
                status_code=500,
                content=fail(
                    ErrorCode.INTERNAL_ERROR,
                    f"服务器内部错误: {e}",
                    detail=detail,
                ),
            )
