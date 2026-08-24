#!/usr/bin/env python3
"""
Phase 3 — SGLang 连通性冒烟测试

测试 SGLang /v1 端点是否正常工作：
1. GET /v1/models — 列出可用模型
2. POST /v1/chat/completions — 发送一条测试对话，验证模型可推理

用法:
  python tests/test_sglang_connection.py
  python tests/test_sglang_connection.py --base-url http://192.168.1.100:30000/v1
  python tests/test_sglang_connection.py --model qwen3-4b --base-url http://localhost:30000/v1

依赖: httpx (已在 requirements.txt 中)
"""
import argparse
import json
import sys
import time

import httpx


def test_models_endpoint(base_url: str, api_key: str, timeout: int) -> dict:
    """测试 GET /v1/models 端点。"""
    url = f"{base_url.rstrip('/')}/models"
    print(f"\n[1] GET {url}")
    t0 = time.monotonic()
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        latency = int((time.monotonic() - t0) * 1000)
        print(f"    状态码: {resp.status_code} | 延迟: {latency}ms")

        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("id", "?") for m in data.get("data", [])]
            print(f"    可用模型: {models}")
            return {"pass": True, "models": models, "latency_ms": latency}
        else:
            print(f"    ❌ 非 200: {resp.text[:300]}")
            return {"pass": False, "latency_ms": latency, "error": f"HTTP {resp.status_code}"}
    except httpx.ConnectError as e:
        print(f"    ❌ 连接失败: {e}")
        return {"pass": False, "latency_ms": 0, "error": "connection refused"}
    except httpx.TimeoutException:
        print(f"    ❌ 超时 ({timeout}s)")
        return {"pass": False, "latency_ms": 0, "error": "timeout"}
    except Exception as e:
        print(f"    ❌ 异常: {e}")
        return {"pass": False, "latency_ms": 0, "error": str(e)}


def test_chat_completion(
    base_url: str, api_key: str, model: str, timeout: int
) -> dict:
    """测试 POST /v1/chat/completions 端点。"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    print(f"\n[2] POST {url}")
    print(f"    模型: {model}")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是汽车VCU测试领域助手，请简短回答。",
            },
            {
                "role": "user",
                "content": "请用一句话说明P挡切换到D挡的前提条件。",
            },
        ],
        "max_tokens": 256,
        "temperature": 0.3,
    }

    t0 = time.monotonic()
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        latency = int((time.monotonic() - t0) * 1000)
        print(f"    状态码: {resp.status_code} | 延迟: {latency}ms")

        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            print(f"    回复: {content[:200]}")
            print(f"    Token: prompt={usage.get('prompt_tokens','?')} completion={usage.get('completion_tokens','?')}")
            return {
                "pass": True,
                "latency_ms": latency,
                "reply": content,
                "tokens": usage,
            }
        else:
            print(f"    ❌ 非 200: {resp.text[:300]}")
            return {"pass": False, "latency_ms": latency, "error": f"HTTP {resp.status_code}"}
    except httpx.ConnectError as e:
        print(f"    ❌ 连接失败: {e}")
        return {"pass": False, "latency_ms": 0, "error": "connection refused"}
    except httpx.TimeoutException:
        print(f"    ❌ 超时 ({timeout}s)")
        return {"pass": False, "latency_ms": 0, "error": "timeout"}
    except Exception as e:
        print(f"    ❌ 异常: {e}")
        return {"pass": False, "latency_ms": 0, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="SGLang 连通性冒烟测试")
    parser.add_argument(
        "--base-url",
        default="http://localhost:30000/v1",
        help="SGLang API 地址 (默认 http://localhost:30000/v1)",
    )
    parser.add_argument(
        "--model",
        default="qwen3-4b",
        help="模型名称 (默认 qwen3-4b)",
    )
    parser.add_argument(
        "--api-key",
        default="sglang-dummy-key",
        help="API Key (SGLang 默认不鉴权，填任意非空字符串)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="请求超时秒数 (默认 30)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  SGLang 连通性冒烟测试 — Phase 3")
    print("=" * 60)
    print(f"  端点: {args.base_url}")
    print(f"  模型: {args.model}")
    print(f"  超时: {args.timeout}s")

    # Test 1: /v1/models
    r1 = test_models_endpoint(args.base_url, args.api_key, args.timeout)

    if not r1["pass"]:
        print("\n" + "=" * 60)
        print("  ❌ SGLang /v1/models 不可达，请检查:")
        print("    1. SGLang 服务是否已启动 (sglang.launch_server)")
        print("    2. 端口 30000 是否开放")
        print("    3. base-url 是否正确")
        print("=" * 60)
        sys.exit(1)

    # Test 2: chat completion
    r2 = test_chat_completion(args.base_url, args.api_key, args.model, args.timeout)

    # 汇总
    print("\n" + "=" * 60)
    print("  测试汇总")
    print("=" * 60)
    print(f"  /v1/models        : {'✅ 通过' if r1['pass'] else '❌ 失败'} ({r1.get('latency_ms',0)}ms)")
    print(f"  /v1/chat/completions: {'✅ 通过' if r2['pass'] else '❌ 失败'} ({r2.get('latency_ms',0)}ms)")

    if r1["pass"] and r2["pass"]:
        print("\n  ✅ SGLang 连通性测试全部通过！")
        print("  可将 .env 中 HERMES_LLM_BASE_URL 设为此地址。")
        sys.exit(0)
    else:
        print("\n  ❌ 存在失败项，请排查后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
