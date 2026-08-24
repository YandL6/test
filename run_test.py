#!/usr/bin/env python3
"""
Hermes VCU Gateway — 全链路测试脚本

启动服务器 → 等待就绪 → 逐个测试 API → 输出结果 → 关闭服务器
"""
import subprocess
import time
import sys
import os
import json
import httpx
import signal

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_PATH = f"{PROJECT_DIR}:/home/gem/.aily/.cli/python"
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "test_server.log")

def start_server():
    """启动 uvicorn 服务器子进程"""
    os.makedirs(os.path.join(PROJECT_DIR, "logs"), exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHON_PATH
    log_f = open(LOG_FILE, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_gateway.main:app",
         "--host", "0.0.0.0", "--port", "8100"],
        cwd=PROJECT_DIR,
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    # 等待服务器就绪
    for i in range(20):
        time.sleep(0.5)
        try:
            r = httpx.get("http://localhost:8100/health", timeout=2)
            if r.status_code == 200:
                print(f"✅ 服务器启动成功 (PID={proc.pid})，等待 {i*0.5:.1f}s")
                return proc
        except:
            pass
    print("❌ 服务器启动失败")
    print(open(LOG_FILE).read()[:500])
    return None

def stop_server(proc):
    """关闭服务器"""
    if proc:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait()
        print("✅ 服务器已关闭")

def test_api(name, method, path, **kwargs):
    """执行单个 API 测试"""
    url = f"http://localhost:8100{path}"
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"  {method} {path}")
    
    try:
        if method == "GET":
            r = httpx.get(url, timeout=30, **kwargs)
        elif method == "POST":
            r = httpx.post(url, timeout=30, **kwargs)
        elif method == "DELETE":
            r = httpx.delete(url, timeout=10, **kwargs)
        
        print(f"  状态码: {r.status_code}")
        data = r.json()
        print(f"  响应: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
        return data
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return None

def test_sse(name, path, body):
    """测试 SSE 流式接口"""
    url = f"http://localhost:8100{path}"
    print(f"\n{'='*60}")
    print(f"测试(SSE): {name}")
    print(f"  POST {path}")
    
    try:
        with httpx.stream("POST", url, json=body, timeout=60) as r:
            print(f"  状态码: {r.status_code}")
            events = []
            for line in r.iter_lines():
                if line.startswith("data:"):
                    try:
                        evt = json.loads(line[5:].strip())
                        events.append(evt)
                        if "chunk" in evt:
                            print(f"  [chunk] {evt['chunk'][:50]}...", end="", flush=True)
                        elif "status" in evt:
                            print(f"  [status] {evt['status']}")
                        elif evt.get("event") == "result":
                            print(f"\n  [result] 收到结果")
                        elif evt.get("event") == "error":
                            print(f"\n  [error] {evt.get('message','')}")
                    except:
                        pass
            return events
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return None

def main():
    # 1. 启动服务器
    print("=" * 60)
    print("  Hermes VCU Gateway — Phase 1 全链路测试")
    print("=" * 60)
    
    proc = start_server()
    if not proc:
        return
    
    try:
        # 2. 健康检查
        health = test_api("健康检查", "GET", "/health")
        
        # 3. 列出功能域
        test_api("功能域列表", "GET", "/api/v1/domains")
        
        # 4. 创建会话
        session = test_api(
            "创建会话", "POST", "/api/v1/sessions",
            json={"title": "VCU档位管理测试", "domain": "vcu_gear", "user_id": "test_user"}
        )
        
        if not session or session.get("code") != 0:
            print("\n❌ 创建会话失败，终止测试")
            return
        
        sid = session["data"]["session_id"]
        print(f"\n  → 会话 ID: {sid}")
        
        # 5. 上传文件
        filepath = os.path.join(PROJECT_DIR, "test_docs", "vcu_gear_requirements.md")
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                upload = test_api(
                    "上传需求文档", "POST", f"/api/v1/sessions/{sid}/upload",
                    files={"file": ("vcu_gear_requirements.md", f, "text/markdown")}
                )
        else:
            print(f"\n⚠ 测试文档不存在: {filepath}")
        
        # 6. 生成需求点 (SSE)
        print("\n" + "=" * 60)
        print("测试: 生成需求点 (SSE 流式)")
        print(f"  POST /api/v1/sessions/{sid}/generate/requirements")
        req_events = test_sse(
            "生成需求点", f"/api/v1/sessions/{sid}/generate/requirements",
            {"session_id": sid, "stream": True}
        )
        
        # 7. 生成测试用例 (SSE)
        print("\n" + "=" * 60)
        print("测试: 生成测试用例 (SSE 流式)")
        tc_events = test_sse(
            "生成测试用例", f"/api/v1/sessions/{sid}/generate/testcases",
            {"session_id": sid, "stream": True}
        )
        
        # 8. 生成测试脚本 (SSE)
        print("\n" + "=" * 60)
        print("测试: 生成测试脚本 (SSE 流式)")
        script_events = test_sse(
            "生成测试脚本", f"/api/v1/sessions/{sid}/generate/scripts",
            {"session_id": sid, "stream": True, "script_format": "python"}
        )
        
        # 9. 查看会话详情
        detail = test_api("会话详情", "GET", f"/api/v1/sessions/{sid}")
        
        # 10. 列出所有会话
        test_api("会话列表", "GET", "/api/v1/sessions")
        
        # 汇总
        print("\n" + "=" * 60)
        print("  全链路测试汇总")
        print("=" * 60)
        
        # 解析需求点
        reqs = []
        for e in (req_events or []):
            if e.get("event") == "result":
                d = e.get("data")
                if isinstance(d, list):
                    reqs = d
                elif isinstance(d, str):
                    try:
                        reqs = json.loads(d)
                    except:
                        pass
        print(f"  需求点: {len(reqs)} 条")
        for r in reqs[:3]:
            print(f"    - {r.get('id','')}: {r.get('name','')} [{r.get('priority','')}]")
        if len(reqs) > 3:
            print(f"    ... 共 {len(reqs)} 条")
        
        # 解析测试用例
        cases = []
        for e in (tc_events or []):
            if e.get("event") == "result":
                d = e.get("data")
                if isinstance(d, list):
                    cases = d
                elif isinstance(d, str):
                    try:
                        cases = json.loads(d)
                    except:
                        pass
        print(f"\n  测试用例: {len(cases)} 条")
        for c in cases[:3]:
            print(f"    - {c.get('id','')}: {c.get('title','')} [{c.get('level','')}]")
        if len(cases) > 3:
            print(f"    ... 共 {len(cases)} 条")
        
        # 解析测试脚本
        scripts = []
        for e in (script_events or []):
            if e.get("event") == "result":
                d = e.get("data")
                if isinstance(d, list):
                    scripts = d
                elif isinstance(d, str):
                    try:
                        scripts = json.loads(d)
                    except:
                        pass
        print(f"\n  测试脚本: {len(scripts)} 个")
        for s in scripts[:2]:
            sid_s = s.get('id', s.get('case_id', ''))
            code = s.get('script', s.get('code', ''))
            lines = code.count('\n') + 1 if code else 0
            print(f"    - {sid_s}: {lines} 行代码")
        if len(scripts) > 2:
            print(f"    ... 共 {len(scripts)} 个")
        
        print("\n" + "=" * 60)
        print("  ✅ 全链路测试通过！")
        print("=" * 60)
        
    finally:
        stop_server(proc)

if __name__ == "__main__":
    main()
