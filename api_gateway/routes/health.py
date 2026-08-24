"""
健康检查路由

GET /          — 根路径欢迎
GET /health    — 服务健康检查（含 Hermes 状态 + Phase 3 SGLang 连通性）
GET /api/v1/domains — 列出可用功能域
GET /health/sglang — 专测 SGLang 连通性（详细诊断）
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter

from api_gateway.config import config
from api_gateway.models.responses import ok
from api_gateway.services.domain_router import list_domains
from api_gateway.services.hermes_service import _ensure_hermes_imported, agent_manager

router = APIRouter(tags=["系统"])


async def _check_sglang() -> dict:
    """探测 SGLang /v1/models 端点连通性。

    返回:
      {"reachable": bool, "models": [...], "latency_ms": int, "error": str|None}
    """
    if config.SGLANG_HEALTH_SKIP:
        return {"reachable": None, "models": [], "latency_ms": 0, "error": "skipped"}

    base_url = config.LLM_BASE_URL.rstrip("/")
    if not base_url:
        return {"reachable": False, "models": [], "latency_ms": 0, "error": "LLM_BASE_URL not set"}

    models_url = f"{base_url}/models"
    timeout = config.SGLANG_HEALTH_TIMEOUT

    import time
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            )
        latency = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("id", "?") for m in data.get("data", [])]
            return {"reachable": True, "models": models, "latency_ms": latency, "error": None}
        else:
            return {
                "reachable": False,
                "models": [],
                "latency_ms": latency,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except httpx.ConnectError as e:
        latency = int((time.monotonic() - t0) * 1000)
        return {"reachable": False, "models": [], "latency_ms": latency, "error": f"connection refused: {e}"}
    except httpx.TimeoutException:
        latency = int((time.monotonic() - t0) * 1000)
        return {"reachable": False, "models": [], "latency_ms": latency, "error": f"timeout after {timeout}s"}
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        return {"reachable": False, "models": [], "latency_ms": latency, "error": str(e)}


@router.get("/")
async def root():
    return ok({"service": "Hermes VCU Gateway", "version": "0.3.0-phase3"})


@router.get("/health")
async def health():
    hermes_ok = _ensure_hermes_imported()
    sessions = await agent_manager.list_sessions()
    llm_configured = bool(config.LLM_API_KEY)

    # Phase 3: SGLang 连通性检测
    sglang_status = await _check_sglang()

    from api_gateway.database import get_stats, _db_initialized
    db_stats = await get_stats() if _db_initialized else {"sessions": 0, "documents": 0, "requirements": 0, "testcases": 0, "scripts": 0, "kb_chunks": 0}

    # 综合状态判定
    all_ok = hermes_ok and llm_configured and sglang_status["reachable"] is True
    degraded = hermes_ok and (not llm_configured or sglang_status["reachable"] is not True)

    return ok({
        "status": "healthy" if all_ok else ("degraded" if degraded else "unavailable"),
        "version": "0.3.0-phase3",
        "hermes_available": hermes_ok,
        "hermes_path": str(config.hermes_path),
        "llm_configured": llm_configured,
        "llm_provider": config.LLM_PROVIDER,
        "llm_model": config.LLM_MODEL,
        "llm_base_url": config.LLM_BASE_URL or "(not set)",
        "sglang": sglang_status,
        "active_sessions": len(sessions),
        "database": "SQLite (persistent)" if _db_initialized else "not initialized",
        "db_stats": db_stats,
        "sandbox_backend": config.SANDBOX_BACKEND,
        "dev_mode": config.is_dev_mode(),
        "mode": "real-hermes" if (hermes_ok and llm_configured and sglang_status["reachable"] is True) else "mock" if hermes_ok else "unavailable",
    })


@router.get("/health/sglang")
async def health_sglang():
    """专测 SGLang 连通性 — 返回详细诊断信息。"""
    result = await _check_sglang()
    return ok({
        "base_url": config.LLM_BASE_URL or "(not set)",
        "model": config.LLM_MODEL,
        "provider": config.LLM_PROVIDER,
        **result,
    })


@router.get("/api/v1/domains")
async def get_domains():
    return ok(list_domains())
