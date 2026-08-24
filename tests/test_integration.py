#!/usr/bin/env python3
"""
Phase 3 — 端到端集成测试

测试完整流水线：上传需求文档 → 生成需求点 → 生成测试用例 → 生成测试脚本 → 验证持久化

前置条件：
  - API Gateway 已启动 (python -m api_gateway.main 或 docker-compose up)
  - SGLang 服务可达 (由 .env 中 HERMES_LLM_BASE_URL 指定)

用法:
  python tests/test_integration.py
  python tests/test_integration.py --host http://localhost:8100
  python tests/test_integration.py --host http://localhost:8100 --domain vcu_torque

依赖: httpx (已在 requirements.txt 中)
"""
import argparse
import json
import os
import sys
import time

import httpx

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_HOST = "http://localhost:8100"


def _request(name: str, method: str, url: str, **kwargs) -> dict | None:
    """执行 HTTP 请求并打印结果。"""
    print(f"\n{'─'*50}")
    print(f"[{name}] {method} {url.replace(DEFAULT_HOST, '')}")
    try:
        resp = httpx.request(method, url, timeout=60, **kwargs)
        print(f"  状态码: {resp.status_code}")
        data = resp.json()
        # 截断打印
        pretty = json.dumps(data, ensure_ascii=False, indent=2)
        print(f"  响应: {pretty[:500]}{'...' if len(pretty) > 500 else ''}")
        return data
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return None


def _request_sse(name: str, url: str, body: dict, timeout: int = 120) -> list:
    """执行 SSE 流式请求，收集所有事件。"""
    print(f"\n{'─'*50}")
    print(f"[{name}] POST {url.replace(DEFAULT_HOST, '')} (SSE)")
    events = []
    try:
        with httpx.stream("POST", url, json=body, timeout=timeout) as resp:
            print(f"  状态码: {resp.status_code}")
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    try:
                        evt = json.loads(line[5:].strip())
                        events.append(evt)
                        if "status" in evt:
                            print(f"  [status] {evt['status']}")
                        elif evt.get("event") == "chunk":
                            chunk = evt.get("data", "")
                            if isinstance(chunk, str):
                                print(f"  [chunk] {chunk[:80]}{'...' if len(chunk) > 80 else ''}")
                        elif evt.get("event") == "result":
                            print(f"  [result] 收到完整结果")
                        elif evt.get("event") == "error":
                            print(f"  [error] {evt.get('message', '')}")
                    except json.JSONDecodeError:
                        pass
        return events
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return events


def _extract_result(events: list) -> list | dict | None:
    """从 SSE 事件流中提取 result 事件的 data。"""
    for evt in reversed(events):
        if evt.get("event") == "result":
            data = evt.get("data")
            if isinstance(data, str):
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return None
            return data
    return None


def main():
    parser = argparse.ArgumentParser(description="Phase 3 端到端集成测试")
    parser.add_argument("--host", default=DEFAULT_HOST, help="API Gateway 地址")
    parser.add_argument("--domain", default="vcu_gear", help="功能域 (vcu_gear / vcu_torque)")
    args = parser.parse_args()

    host = args.host.rstrip("/")
    domain = args.domain
    test_doc = os.path.join(PROJECT_DIR, "test_docs", "vcu_gear_requirements.md")

    print("=" * 60)
    print("  Hermes VCU Gateway — Phase 3 端到端集成测试")
    print("=" * 60)
    print(f"  服务: {host}")
    print(f"  功能域: {domain}")

    passed = 0
    failed = 0
    skipped = 0

    # ===== 1. 健康检查（含 SGLang 连通性） =====
    health = _request("健康检查", "GET", f"{host}/health")
    if not health or health.get("code") != 0:
        print("\n❌ 健康检查失败，终止测试")
        sys.exit(1)

    health_data = health["data"]
    if health_data.get("sglang", {}).get("reachable") is not True:
        print(f"\n⚠ SGLang 不可达: {health_data.get('sglang', {}).get('error', 'unknown')}")
        print("  将以 Mock 模式继续测试（验证 API 链路完整性）")
    else:
        print(f"\n✅ SGLang 可达，模型: {health_data['sglang']['models']}")
    passed += 1

    # ===== 2. 列出功能域 =====
    domains = _request("功能域列表", "GET", f"{host}/api/v1/domains")
    if domains and domains.get("code") == 0:
        passed += 1
    else:
        failed += 1

    # ===== 3. 创建会话 =====
    session = _request(
        "创建会话", "POST", f"{host}/api/v1/sessions",
        json={"title": f"Phase3集成测试-{domain}", "domain": domain, "user_id": "integration_test"},
    )
    if not session or session.get("code") != 0:
        print("\n❌ 创建会话失败，终止测试")
        failed += 1
        sys.exit(1)

    sid = session["data"]["session_id"]
    print(f"  → 会话 ID: {sid}")
    passed += 1

    try:
        # ===== 4. 上传需求文档 =====
        if os.path.exists(test_doc):
            with open(test_doc, "rb") as f:
                upload = _request(
                    "上传需求文档", "POST", f"{host}/api/v1/sessions/{sid}/upload",
                    files={"file": (os.path.basename(test_doc), f, "text/markdown")},
                )
            if upload and upload.get("code") == 0:
                passed += 1
            else:
                failed += 1
        else:
            print(f"\n⚠ 测试文档不存在: {test_doc}，跳过上传")
            skipped += 1

        # ===== 5. 生成需求点 (SSE) =====
        print(f"\n{'━'*50}")
        print("  [生成需求点] — 这一步可能需要 10-60 秒（取决于模型速度）")
        print(f"{'━'*50}")
        req_events = _request_sse(
            "生成需求点",
            f"{host}/api/v1/sessions/{sid}/generate/requirements",
            {"session_id": sid, "stream": True},
        )
        reqs = _extract_result(req_events)
        if reqs and isinstance(reqs, list) and len(reqs) > 0:
            print(f"\n  ✅ 生成 {len(reqs)} 条需求点")
            for r in reqs[:3]:
                print(f"    - {r.get('id','')}: {r.get('name','')} [{r.get('priority','')}]")
            passed += 1
        else:
            print(f"\n  ⚠ 需求点为空或解析失败（Mock 模式下也可能有数据）")
            failed += 1

        # ===== 6. 生成测试用例 (SSE) =====
        print(f"\n{'━'*50}")
        print("  [生成测试用例] — 这一步可能需要 10-60 秒")
        print(f"{'━'*50}")
        tc_events = _request_sse(
            "生成测试用例",
            f"{host}/api/v1/sessions/{sid}/generate/testcases",
            {"session_id": sid, "stream": True},
        )
        cases = _extract_result(tc_events)
        if cases and isinstance(cases, list) and len(cases) > 0:
            print(f"\n  ✅ 生成 {len(cases)} 条测试用例")
            for c in cases[:3]:
                print(f"    - {c.get('id','')}: {c.get('title','')} [{c.get('level','')}]")
            passed += 1
        else:
            print(f"\n  ⚠ 测试用例为空或解析失败")
            failed += 1

        # ===== 7. 生成测试脚本 (SSE) =====
        print(f"\n{'━'*50}")
        print("  [生成测试脚本] — 这一步可能需要 10-60 秒")
        print(f"{'━'*50}")
        script_events = _request_sse(
            "生成测试脚本",
            f"{host}/api/v1/sessions/{sid}/generate/scripts",
            {"session_id": sid, "stream": True, "script_format": "python"},
        )
        scripts = _extract_result(script_events)
        if scripts and isinstance(scripts, list) and len(scripts) > 0:
            print(f"\n  ✅ 生成 {len(scripts)} 个测试脚本")
            for s in scripts[:2]:
                sid_s = s.get("id", s.get("case_id", ""))
                code = s.get("script", s.get("code", ""))
                lines = code.count("\n") + 1 if code else 0
                print(f"    - {sid_s}: {lines} 行代码")
            passed += 1
        else:
            print(f"\n  ⚠ 测试脚本为空或解析失败")
            failed += 1

        # ===== 8. 会话详情验证 =====
        detail = _request("会话详情", "GET", f"{host}/api/v1/sessions/{sid}")
        if detail and detail.get("code") == 0:
            d = detail["data"]
            print(f"  需求: {len(d.get('requirements', []))} | 用例: {len(d.get('testcases', []))} | 脚本: {len(d.get('scripts', []))}")
            passed += 1
        else:
            failed += 1

        # ===== 9. 知识库搜索 =====
        kb = _request(
            "知识库搜索", "POST", f"{host}/api/v1/kb/search",
            json={"query": "P挡切换", "limit": 5},
        )
        if kb and kb.get("code") == 0:
            passed += 1
        else:
            failed += 1

        # ===== 10. 清理 — 删除会话 =====
        delete = _request("删除会话", "DELETE", f"{host}/api/v1/sessions/{sid}")
        if delete and delete.get("code") == 0:
            passed += 1
        else:
            failed += 1

    finally:
        # 确保清理
        try:
            httpx.delete(f"{host}/api/v1/sessions/{sid}", timeout=10)
        except:
            pass

    # ===== 汇总 =====
    print("\n" + "=" * 60)
    print("  端到端集成测试汇总")
    print("=" * 60)
    total = passed + failed + skipped
    print(f"  通过: {passed}/{total}")
    print(f"  失败: {failed}/{total}")
    print(f"  跳过: {skipped}/{total}")

    if failed == 0:
        print("\n  ✅ 全部通过！")
        sys.exit(0)
    else:
        print(f"\n  ❌ {failed} 项失败，请排查。")
        sys.exit(1)


if __name__ == "__main__":
    main()
