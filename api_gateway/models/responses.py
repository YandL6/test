"""
统一响应与错误模型

所有 API 返回都遵循统一格式:
  成功: {"code": 0, "message": "ok", "data": {...}}
  失败: {"code": <非零错误码>, "message": "<错误描述>", "data": null}

错误码定义:
  1xxx — 通用错误（参数/服务器/未知）
  2xxx — 认证与权限
  3xxx — 会话与状态
  4xxx — 文件与上传
  5xxx — Hermes Agent 调用
  6xxx — 知识库
"""
from __future__ import annotations

from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(IntEnum):
    # --- 1xxx 通用 ---
    OK = 0
    BAD_REQUEST = 1001
    VALIDATION_ERROR = 1002
    INTERNAL_ERROR = 1999

    # --- 2xxx 认证 ---
    UNAUTHORIZED = 2001
    TOKEN_EXPIRED = 2002
    FORBIDDEN = 2003

    # --- 3xxx 会话 ---
    SESSION_NOT_FOUND = 3001
    SESSION_CONFLICT = 3002
    SESSION_CLOSED = 3003

    # --- 4xxx 文件 ---
    FILE_TOO_LARGE = 4001
    FILE_TYPE_NOT_ALLOWED = 4002
    FILE_NOT_FOUND = 4003
    FILE_PARSE_FAILED = 4004

    # --- 5xxx Hermes ---
    HERMES_NOT_READY = 5001
    HERMES_TIMEOUT = 5002
    HERMES_LLM_ERROR = 5003
    HERMES_TOOL_ERROR = 5004
    HERMES_JSON_PARSE_FAILED = 5005
    HERMES_RATE_LIMIT = 5006
    HERMES_CONTEXT_TOO_LONG = 5007
    HERMES_PROVIDER_DOWN = 5008

    # --- 6xxx 知识库 ---
    KB_QUERY_FAILED = 6001
    KB_DOC_NOT_FOUND = 6002


class ErrorResponse(BaseModel):
    """统一错误响应体。"""

    code: int = Field(..., description="非零错误码")
    message: str = Field(..., description="错误描述")
    data: None = Field(None, description="错误时始终为 null")
    detail: str | None = Field(None, description="调试用详细信息（生产环境可关闭）")


class SuccessResponse(BaseModel):
    """统一成功响应体。"""

    code: int = Field(0, description="0 表示成功")
    message: str = Field("ok", description="状态描述")
    data: Any = Field(None, description="业务数据")


# --- SSE 流式事件模型 ---
class SSEEvent(BaseModel):
    """SSE 流式推送事件。"""

    event: str = Field(..., description="事件类型: status | chunk | result | error")
    data: Any = Field(..., description="事件数据")


class APIError(Exception):
    """可在路由中直接 raise 的业务异常，由中间件统一捕获。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        detail: str | None = None,
        status_code: int = 400,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


def ok(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应。"""
    return {"code": 0, "message": message, "data": data}


def fail(
    code: ErrorCode,
    message: str,
    detail: str | None = None,
) -> dict:
    """构造失败响应。"""
    return {"code": int(code), "message": message, "data": None, "detail": detail}
