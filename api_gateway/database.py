"""
SQLite 异步数据库层 — Phase 2

替代 Phase 1 的内存字典存储，实现持久化。
使用 aiosqlite 提供异步访问，兼容 FastAPI 的 async 路由。

表结构：
  sessions      — 会话主表
  documents     — 上传的需求文档
  requirements  — AI 生成的需求点
  testcases     — AI 生成的测试用例
  scripts       — AI 生成的测试脚本
  kb_chunks     — 知识库分块（D 模块向量搜索基础）
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from loguru import logger
from api_gateway.config import config

# ── 建表 SQL ──────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    user_id       TEXT,
    domain        TEXT NOT NULL DEFAULT 'general',
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    filename      TEXT NOT NULL,
    file_type     TEXT,
    file_size     INTEGER DEFAULT 0,
    content       TEXT,
    parsed_text   TEXT,
    uploaded_at   REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS requirements (
    req_id        TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    doc_id        TEXT,
    name          TEXT NOT NULL,
    description   TEXT,
    priority      TEXT DEFAULT 'P1',
    category      TEXT,
    source        TEXT,
    created_at    REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS testcases (
    tc_id         TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    req_id        TEXT,
    title         TEXT NOT NULL,
    level         TEXT,
    module        TEXT,
    preconditions TEXT,
    test_steps    TEXT,
    expected      TEXT,
    tags          TEXT,
    created_at    REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS scripts (
    script_id     TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    tc_id         TEXT,
    name          TEXT NOT NULL,
    language      TEXT DEFAULT 'python',
    code          TEXT,
    description   TEXT,
    created_at    REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id      TEXT PRIMARY KEY,
    doc_id        TEXT,
    source        TEXT,
    chunk_text    TEXT NOT NULL,
    chunk_meta    TEXT,
    keywords      TEXT,
    created_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_documents_session ON documents(session_id);
CREATE INDEX IF NOT EXISTS idx_reqs_session ON requirements(session_id);
CREATE INDEX IF NOT EXISTS idx_tcs_session ON testcases(session_id);
CREATE INDEX IF NOT EXISTS idx_scripts_session ON scripts(session_id);
CREATE INDEX IF NOT EXISTS idx_kb_keywords ON kb_chunks(keywords);
"""

# ── 数据库管理 ────────────────────────────────────────────

_db_path: str = ""
_db_initialized: bool = False


def _get_db_path() -> str:
    global _db_path
    if not _db_path:
        db_dir = Path(config.UPLOAD_DIR).parent / "data"
        db_dir.mkdir(parents=True, exist_ok=True)
        _db_path = str(db_dir / "vcu_gateway.db")
    return _db_path


async def init_db():
    """初始化数据库 — 建表、建索引。应用启动时调用一次。"""
    global _db_initialized
    if _db_initialized:
        return
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    _db_initialized = True
    logger.info(f"数据库初始化完成: {path}")


def _gen_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


# ── Sessions CRUD ──────────────────────────────────────────

async def create_session(title: str, user_id: str | None, domain: str) -> dict:
    sid = _gen_id("sess_")
    now = time.time()
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO sessions (session_id, title, user_id, domain, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (sid, title, user_id, domain, now, now),
        )
        await db.commit()
    logger.info(f"DB: 创建会话 {sid} (title={title}, domain={domain})")
    return {"session_id": sid, "title": title, "user_id": user_id, "domain": domain, "status": "active", "created_at": now}


async def get_session(session_id: str) -> dict | None:
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = await cur.fetchone()
        if not row:
            return None
        return dict(row)


async def list_sessions(limit: int = 50, offset: int = 0) -> list[dict]:
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def update_session_status(session_id: str, status: str):
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ?",
            (status, time.time(), session_id),
        )
        await db.commit()


async def delete_session(session_id: str):
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute("DELETE FROM scripts WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM testcases WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM requirements WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM documents WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await db.commit()
    logger.info(f"DB: 删除会话 {session_id} 及其关联数据")


async def get_session_detail(session_id: str) -> dict | None:
    """获取会话完整详情（含文档/需求/用例/脚本）。"""
    sess = await get_session(session_id)
    if not sess:
        return None
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        # documents
        cur = await db.execute("SELECT * FROM documents WHERE session_id = ?", (session_id,))
        docs = [dict(r) for r in await cur.fetchall()]
        # requirements
        cur = await db.execute("SELECT * FROM requirements WHERE session_id = ?", (session_id,))
        reqs = [dict(r) for r in await cur.fetchall()]
        # testcases
        cur = await db.execute("SELECT * FROM testcases WHERE session_id = ?", (session_id,))
        tcs = [dict(r) for r in await cur.fetchall()]
        # scripts
        cur = await db.execute("SELECT * FROM scripts WHERE session_id = ?", (session_id,))
        scripts = [dict(r) for r in await cur.fetchall()]
    sess["documents"] = docs
    sess["requirements"] = reqs
    sess["testcases"] = tcs
    sess["scripts"] = scripts
    return sess


# ── Documents CRUD ────────────────────────────────────────

async def add_document(session_id: str, filename: str, file_type: str, file_size: int, content: str, parsed_text: str = "") -> dict:
    doc_id = _gen_id("doc_")
    now = time.time()
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO documents (doc_id, session_id, filename, file_type, file_size, content, parsed_text, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, session_id, filename, file_type, file_size, content, parsed_text, now),
        )
        await db.commit()
    return {"doc_id": doc_id, "session_id": session_id, "filename": filename, "uploaded_at": now}


async def list_documents(session_id: str) -> list[dict]:
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT doc_id, session_id, filename, file_type, file_size, uploaded_at FROM documents WHERE session_id = ?", (session_id,))
        return [dict(r) for r in await cur.fetchall()]


# ── Requirements CRUD ─────────────────────────────────────

async def add_requirements(session_id: str, reqs: list[dict], doc_id: str | None = None) -> list[dict]:
    path = _get_db_path()
    now = time.time()
    result = []
    async with aiosqlite.connect(path) as db:
        for r in reqs:
            rid = r.get("id") or _gen_id("req_")
            await db.execute(
                "INSERT INTO requirements (req_id, session_id, doc_id, name, description, priority, category, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, session_id, doc_id, r.get("name", ""), r.get("description", ""), r.get("priority", "P1"), r.get("category", ""), r.get("source", ""), now),
            )
            result.append({**r, "id": rid, "session_id": session_id})
        await db.commit()
    return result


async def list_requirements(session_id: str) -> list[dict]:
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM requirements WHERE session_id = ? ORDER BY created_at", (session_id,))
        rows = [dict(r) for r in await cur.fetchall()]
    # 统一字段名供前端使用
    for r in rows:
        r["id"] = r.pop("req_id", "")
    return rows


# ── Test Cases CRUD ───────────────────────────────────────

async def add_testcases(session_id: str, testcases: list[dict]) -> list[dict]:
    path = _get_db_path()
    now = time.time()
    result = []
    async with aiosqlite.connect(path) as db:
        for tc in testcases:
            tcid = tc.get("id") or _gen_id("tc_")
            await db.execute(
                "INSERT INTO testcases (tc_id, session_id, req_id, title, level, module, preconditions, test_steps, expected, tags, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tcid, session_id, tc.get("req_id"), tc.get("title", ""), tc.get("level", ""), tc.get("module", ""), tc.get("preconditions", ""), json.dumps(tc.get("test_steps", []), ensure_ascii=False), tc.get("expected", ""), json.dumps(tc.get("tags", []), ensure_ascii=False), now),
            )
            result.append({**tc, "id": tcid, "session_id": session_id})
        await db.commit()
    return result


async def list_testcases(session_id: str) -> list[dict]:
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM testcases WHERE session_id = ? ORDER BY created_at", (session_id,))
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["id"] = r.pop("tc_id", "")
        # 解析 JSON 字段
        try:
            r["test_steps"] = json.loads(r.get("test_steps", "[]"))
        except (json.JSONDecodeError, TypeError):
            r["test_steps"] = []
        try:
            r["tags"] = json.loads(r.get("tags", "[]"))
        except (json.JSONDecodeError, TypeError):
            r["tags"] = []
    return rows


# ── Scripts CRUD ──────────────────────────────────────────

async def add_scripts(session_id: str, scripts: list[dict]) -> list[dict]:
    path = _get_db_path()
    now = time.time()
    result = []
    async with aiosqlite.connect(path) as db:
        for sc in scripts:
            scid = sc.get("id") or _gen_id("scr_")
            await db.execute(
                "INSERT INTO scripts (script_id, session_id, tc_id, name, language, code, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (scid, session_id, sc.get("tc_id"), sc.get("name", ""), sc.get("language", "python"), sc.get("code", ""), sc.get("description", ""), now),
            )
            result.append({**sc, "id": scid, "session_id": session_id})
        await db.commit()
    return result


async def list_scripts(session_id: str) -> list[dict]:
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM scripts WHERE session_id = ? ORDER BY created_at", (session_id,))
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["id"] = r.pop("script_id", "")
    return rows


# ── Knowledge Base (D 模块) ───────────────────────────────

async def add_kb_chunk(doc_id: str | None, source: str, chunk_text: str, keywords: str = "", chunk_meta: str = "") -> str:
    chunk_id = _gen_id("kb_")
    now = time.time()
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO kb_chunks (chunk_id, doc_id, source, chunk_text, chunk_meta, keywords, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chunk_id, doc_id, source, chunk_text, chunk_meta, keywords, now),
        )
        await db.commit()
    return chunk_id


async def search_kb(query: str, top_k: int = 5) -> list[dict]:
    """关键词搜索知识库（Phase 2 基础版，Phase 3 接入 RAGFlow 向量搜索）。"""
    path = _get_db_path()
    keywords = query.strip().split()
    if not keywords:
        return []
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        results = []
        for kw in keywords:
            cur = await db.execute(
                "SELECT chunk_id, doc_id, source, chunk_text, keywords FROM kb_chunks WHERE chunk_text LIKE ? OR keywords LIKE ? LIMIT ?",
                (f"%{kw}%", f"%{kw}%", top_k * 2),
            )
            rows = await cur.fetchall()
            for r in rows:
                d = dict(r)
                if d["chunk_id"] not in [x["chunk_id"] for x in results]:
                    results.append(d)
        return results[:top_k]


async def get_stats() -> dict:
    """获取数据库统计信息（健康检查用）。"""
    path = _get_db_path()
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM sessions")
        sess_count = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM documents")
        doc_count = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM requirements")
        req_count = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM testcases")
        tc_count = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM scripts")
        sc_count = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM kb_chunks")
        kb_count = (await cur.fetchone())[0]
    return {
        "sessions": sess_count,
        "documents": doc_count,
        "requirements": req_count,
        "testcases": tc_count,
        "scripts": sc_count,
        "kb_chunks": kb_count,
    }
