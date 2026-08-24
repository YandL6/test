"""
会话管理路由 — Phase 2

POST   /api/v1/sessions              — 创建会话
GET    /api/v1/sessions              — 列出所有会话（分页）
GET    /api/v1/sessions/{id}         — 获取会话详情
DELETE /api/v1/sessions/{id}         — 删除会话
POST   /api/v1/sessions/{id}/upload  — 上传需求文档
"""
from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Query
from loguru import logger

from api_gateway.config import config
from api_gateway.models.responses import ok, fail, APIError, ErrorCode
from api_gateway.models.requests import CreateSessionRequest
from api_gateway.services.session_service import session_service

router = APIRouter(prefix="/api/v1/sessions", tags=["会话管理"])


@router.post("")
async def create_session(req: CreateSessionRequest):
    """创建新会话。"""
    s = await session_service.create(
        title=req.title,
        user_id=req.user_id,
        domain=req.domain,
    )
    return ok(s)


@router.get("")
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """列出所有会话（支持分页）。"""
    sessions = await session_service.list_all(limit=limit, offset=offset)
    return ok(sessions)


@router.get("/{session_id}")
async def get_session(session_id: str):
    """获取会话详情（含文档/需求/用例/脚本）。"""
    try:
        s = await session_service.get(session_id)
        return ok(s)
    except KeyError:
        raise APIError(
            ErrorCode.SESSION_NOT_FOUND,
            f"会话不存在: {session_id}",
            status_code=404,
        )


@router.delete("/{session_id}")
async def delete_session(session_id: str, bg: BackgroundTasks):
    """删除会话及其所有关联数据。"""
    try:
        await session_service.get(session_id)
    except KeyError:
        raise APIError(
            ErrorCode.SESSION_NOT_FOUND,
            f"会话不存在: {session_id}",
            status_code=404,
        )

    await session_service.delete(session_id)
    # 后台清理 Agent 资源
    from api_gateway.services.hermes_service import HermesService
    bg.add_task(HermesService.close_session, session_id)

    return ok({"session_id": session_id, "status": "deleted"})


@router.post("/{session_id}/upload")
async def upload_document(
    session_id: str,
    bg: BackgroundTasks,
    file: UploadFile = File(...),
):
    """上传需求文档。支持: .pdf / .docx / .xlsx / .txt / .md"""
    try:
        await session_service.get(session_id)
    except KeyError:
        raise APIError(
            ErrorCode.SESSION_NOT_FOUND,
            f"会话不存在: {session_id}",
            status_code=404,
        )

    content_bytes = await file.read()
    if len(content_bytes) > config.max_upload_bytes:
        raise APIError(
            ErrorCode.FILE_TOO_LARGE,
            f"文件超过最大限制 {config.MAX_UPLOAD_SIZE_MB}MB",
            status_code=413,
        )

    ext = Path(file.filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise APIError(
            ErrorCode.FILE_TYPE_NOT_ALLOWED,
            f"不支持的文件类型: {ext}",
            status_code=415,
        )

    # 保存到文件系统 + 解析文本
    upload_dir = Path(config.UPLOAD_DIR) / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    save_path = upload_dir / f"{doc_id}{ext}"
    save_path.write_bytes(content_bytes)

    # D 模块：解析文档文本
    parsed_text = ""
    try:
        from api_gateway.services.kb_service import DocumentParser
        parsed_text = DocumentParser.parse(save_path, ext)
    except Exception as e:
        logger.warning(f"文档解析失败（不影响上传）: {e}")
        parsed_text = content_bytes.decode("utf-8", errors="ignore")[:5000]

    # 存入数据库
    doc_info = await session_service.add_document(
        session_id,
        {
            "doc_id": doc_id,
            "filename": file.filename,
            "file_type": ext,
            "file_size": len(content_bytes),
            "content": content_bytes.decode("utf-8", errors="ignore")[:5000],
            "parsed_text": parsed_text,
        },
    )

    # 后台索引到知识库
    bg.add_task(_index_to_kb, doc_id, file.filename, parsed_text)

    logger.info(f"文档上传成功: {file.filename} → {save_path} (parsed={len(parsed_text)} chars)")
    return ok(doc_info)


async def _index_to_kb(doc_id: str, source: str, text: str):
    """后台任务：将文档分块索引到知识库。"""
    if not text.strip():
        return
    from api_gateway.database import add_kb_chunk
    # 简单分块：按段落 + 2000 字上限
    chunks = []
    for para in text.split("\n\n"):
        if len(para) > 2000:
            for i in range(0, len(para), 2000):
                chunks.append(para[i:i+2000])
        else:
            chunks.append(para)
    for chunk in chunks[:50]:  # 限制最多 50 个块
        if chunk.strip():
            await add_kb_chunk(doc_id, source, chunk.strip(), keywords=source)
    logger.info(f"知识库索引完成: {source} ({len(chunks[:50])} chunks)")
