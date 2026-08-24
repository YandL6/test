"""
会话服务层 — Phase 2

Phase 1 用内存字典，Phase 2 改为 SQLite 持久化。
接口保持兼容，路由层无需改动。
"""
from __future__ import annotations

import time
from typing import Any

from loguru import logger

from api_gateway import database as db


class SessionService:
    """会话管理服务（Phase 2 SQLite 版）。"""

    async def create(self, title: str, user_id: str | None, domain: str) -> dict:
        return await db.create_session(title, user_id, domain)

    async def get(self, session_id: str) -> dict:
        """获取会话详情（含文档/需求/用例/脚本）。"""
        detail = await db.get_session_detail(session_id)
        if detail is None:
            raise KeyError(session_id)
        return detail

    async def add_document(self, session_id: str, doc: dict):
        await db.add_document(
            session_id,
            filename=doc.get("filename", ""),
            file_type=doc.get("file_type", ""),
            file_size=doc.get("file_size", 0),
            content=doc.get("content", ""),
            parsed_text=doc.get("parsed_text", ""),
        )

    async def add_requirements(self, session_id: str, reqs: list[dict]):
        return await db.add_requirements(session_id, reqs)

    async def add_testcases(self, session_id: str, cases: list[dict]):
        return await db.add_testcases(session_id, cases)

    async def add_scripts(self, session_id: str, scripts: list[dict]):
        return await db.add_scripts(session_id, scripts)

    async def close(self, session_id: str):
        await db.update_session_status(session_id, "closed")

    async def delete(self, session_id: str):
        await db.delete_session(session_id)

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return await db.list_sessions(limit, offset)

    async def get_documents(self, session_id: str) -> list[dict]:
        return await db.list_documents(session_id)

    async def get_requirements(self, session_id: str) -> list[dict]:
        return await db.list_requirements(session_id)

    async def get_testcases(self, session_id: str) -> list[dict]:
        return await db.list_testcases(session_id)

    async def get_scripts(self, session_id: str) -> list[dict]:
        return await db.list_scripts(session_id)

    async def get_stats(self) -> dict:
        return await db.get_stats()

    def to_dict(self, s: dict) -> dict:
        """兼容旧接口 — dict 已经是 dict，直接返回。"""
        if isinstance(s, dict):
            return s
        return dict(s) if hasattr(s, '__iter__') else {}


# 单例
session_service = SessionService()
