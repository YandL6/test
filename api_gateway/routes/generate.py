"""
测试用例生成路由 — Phase 2

POST /api/v1/sessions/{id}/generate/requirements — 生成需求点
POST /api/v1/sessions/{id}/generate/testcases   — 生成测试用例
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api_gateway.models.responses import ok, APIError, ErrorCode
from api_gateway.models.requests import GenerateRequirementsRequest, GenerateTestcasesRequest
from api_gateway.services.session_service import session_service
from api_gateway.services.hermes_service import HermesService, extract_json
from api_gateway.services.domain_router import build_user_message, get_domain

router = APIRouter(prefix="/api/v1/sessions", tags=["生成"])


@router.post("/{session_id}/generate/requirements")
async def generate_requirements(session_id: str, req: GenerateRequirementsRequest):
    """基于已上传的需求文档，调用 Agent 生成结构化需求点。"""
    try:
        s = await session_service.get(session_id)
    except KeyError:
        raise APIError(ErrorCode.SESSION_NOT_FOUND, f"会话不存在: {session_id}", status_code=404)

    documents = s.get("documents", [])
    doc = None
    if req.document_id:
        doc = next((d for d in documents if d["doc_id"] == req.document_id), None)
    elif documents:
        doc = documents[-1]

    if doc is None:
        raise APIError(ErrorCode.FILE_NOT_FOUND, "会话中没有可处理的文档，请先上传", status_code=400)

    doc_content = f"文档名称: {doc.get('filename','')}\n解析内容: {doc.get('parsed_text','')[:3000]}"
    prompt = build_user_message(s.get("domain", "general"), "generate_requirements", context=doc_content)
    if req.prompt_hint:
        prompt += f"\n\n附加提示: {req.prompt_hint}"

    if req.stream:
        return EventSourceResponse(_stream_requirements(session_id, prompt, s.get("domain", "general")))
    else:
        raw = await HermesService.send_message(session_id, prompt, domain_id=s.get("domain", "general"))
        result = extract_json(raw)
        if isinstance(result, list):
            result = await session_service.add_requirements(session_id, result)
        return ok(result)


async def _stream_requirements(session_id: str, prompt: str, domain: str) -> AsyncIterator[dict]:
    yield {"event": "status", "data": json.dumps({"status": "generating", "domain": domain})}
    accumulated = ""
    try:
        async for chunk in HermesService.send_message_stream(session_id, prompt, domain_id=domain):
            accumulated += chunk
            yield {"event": "chunk", "data": json.dumps({"chunk": chunk})}
        try:
            result = extract_json(accumulated)
            if isinstance(result, list):
                result = await session_service.add_requirements(session_id, result)
            yield {"event": "result", "data": json.dumps({"data": result})}
        except APIError as e:
            yield {"event": "result", "data": json.dumps({"data": accumulated, "parse_error": e.message})}
    except APIError as e:
        yield {"event": "error", "data": json.dumps({"code": int(e.code), "message": e.message})}


@router.post("/{session_id}/generate/testcases")
async def generate_testcases(session_id: str, req: GenerateTestcasesRequest):
    """基于需求点，调用 Agent 生成测试用例。"""
    try:
        s = await session_service.get(session_id)
    except KeyError:
        raise APIError(ErrorCode.SESSION_NOT_FOUND, f"会话不存在: {session_id}", status_code=404)

    reqs = s.get("requirements", [])
    if req.requirement_ids:
        reqs = [r for r in reqs if r.get("id") in req.requirement_ids]

    if not reqs:
        raise APIError(ErrorCode.BAD_REQUEST, "会话中没有需求点，请先生成", status_code=400)

    req_context = json.dumps(reqs, ensure_ascii=False)
    prompt = build_user_message(s.get("domain", "general"), "generate_testcases", context=req_context)

    if req.stream:
        return EventSourceResponse(_stream_testcases(session_id, prompt, s.get("domain", "general")))
    else:
        raw = await HermesService.send_message(session_id, prompt, domain_id=s.get("domain", "general"))
        result = extract_json(raw)
        if isinstance(result, list):
            result = await session_service.add_testcases(session_id, result)
        return ok(result)


async def _stream_testcases(session_id: str, prompt: str, domain: str = "general") -> AsyncIterator[dict]:
    yield {"event": "status", "data": json.dumps({"status": "generating"})}
    accumulated = ""
    try:
        async for chunk in HermesService.send_message_stream(session_id, prompt, domain_id=domain):
            accumulated += chunk
            yield {"event": "chunk", "data": json.dumps({"chunk": chunk})}
        try:
            result = extract_json(accumulated)
            if isinstance(result, list):
                result = await session_service.add_testcases(session_id, result)
            yield {"event": "result", "data": json.dumps({"data": result})}
        except APIError as e:
            yield {"event": "result", "data": json.dumps({"data": accumulated, "parse_error": e.message})}
    except APIError as e:
        yield {"event": "error", "data": json.dumps({"code": int(e.code), "message": e.message})}
