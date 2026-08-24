"""
测试脚本生成路由 + 知识库检索路由 — Phase 2

POST /api/v1/sessions/{id}/generate/scripts — 生成测试脚本
POST /api/v1/kb/search                     — 知识库检索（SQLite 本地 + RAGFlow 远程）
GET  /api/v1/kb/stats                       — 知识库统计
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api_gateway.models.responses import ok, APIError, ErrorCode
from api_gateway.models.requests import GenerateScriptsRequest, KBSearchRequest
from api_gateway.services.session_service import session_service
from api_gateway.services.hermes_service import HermesService, extract_json
from api_gateway.services.domain_router import build_user_message
from api_gateway.database import search_kb, get_stats

# --- 脚本生成路由 ---
script_router = APIRouter(prefix="/api/v1/sessions", tags=["脚本生成"])


@script_router.post("/{session_id}/generate/scripts")
async def generate_scripts(session_id: str, req: GenerateScriptsRequest):
    """基于测试用例生成可执行测试脚本。"""
    try:
        s = await session_service.get(session_id)
    except KeyError:
        raise APIError(ErrorCode.SESSION_NOT_FOUND, f"会话不存在: {session_id}", status_code=404)

    cases = s.get("testcases", [])
    if req.testcase_ids:
        cases = [c for c in cases if c.get("id") in req.testcase_ids]

    if not cases:
        raise APIError(ErrorCode.BAD_REQUEST, "会话中没有测试用例，请先生成", status_code=400)

    case_context = json.dumps(cases, ensure_ascii=False)
    prompt = build_user_message(s.get("domain", "general"), "generate_scripts", context=case_context)
    prompt += f"\n\n脚本格式要求: {req.script_format}"

    if req.stream:
        return EventSourceResponse(_stream_scripts(session_id, prompt, s.get("domain", "general")))
    else:
        raw = await HermesService.send_message(session_id, prompt, domain_id=s.get("domain", "general"))
        result = extract_json(raw)
        if isinstance(result, list):
            result = await session_service.add_scripts(session_id, result)
        return ok(result)


async def _stream_scripts(session_id: str, prompt: str, domain: str = "general") -> AsyncIterator[dict]:
    yield {"event": "status", "data": json.dumps({"status": "generating"})}
    accumulated = ""
    try:
        async for chunk in HermesService.send_message_stream(session_id, prompt, domain_id=domain):
            accumulated += chunk
            yield {"event": "chunk", "data": json.dumps({"chunk": chunk})}
        try:
            result = extract_json(accumulated)
            if isinstance(result, list):
                result = await session_service.add_scripts(session_id, result)
            yield {"event": "result", "data": json.dumps({"data": result})}
        except APIError as e:
            yield {"event": "result", "data": json.dumps({"data": accumulated, "parse_error": e.message})}
    except APIError as e:
        yield {"event": "error", "data": json.dumps({"code": int(e.code), "message": e.message})}


# --- 知识库检索路由 ---
kb_router = APIRouter(prefix="/api/v1/kb", tags=["知识库"])


@kb_router.post("/search")
async def kb_search(req: KBSearchRequest):
    """
    检索知识库。

    Phase 2: SQLite 本地关键词搜索 + RAGFlow 远程向量搜索（如果配置）。
    Phase 3: 完整向量搜索。
    """
    # 本地 SQLite 搜索
    local_results = await search_kb(req.query, req.top_k)

    # 如果配置了 RAGFlow，也查询远程
    remote_results = []
    from api_gateway.config import config
    if config.RAGFLOW_BASE_URL:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{config.RAGFLOW_BASE_URL}/api/v1/retrieval",
                    headers={"Authorization": f"Bearer {config.RAGFLOW_API_KEY}"},
                    json={"question": req.query, "top_k": req.top_k, "dataset_ids": []},
                )
                if resp.status_code == 200:
                    remote_results = resp.json().get("data", {}).get("chunks", [])
        except Exception:
            pass  # 远程不可用时只用本地

    return ok({
        "query": req.query,
        "local_count": len(local_results),
        "remote_count": len(remote_results),
        "local_results": local_results,
        "remote_results": remote_results,
    })


@kb_router.get("/stats")
async def kb_stats():
    """知识库统计信息。"""
    stats = await get_stats()
    return ok(stats)
