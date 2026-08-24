"""
认证服务 (A 模块)

Phase 1: 简单 JWT Token 签发与校验
Phase 2: 对接企业账号体系
"""
from __future__ import annotations

import time
import hashlib
import hmac
import base64
import json

from api_gateway.config import config


class AuthService:
    """JWT 认证服务（简化版，不依赖外部库）。"""

    @staticmethod
    def _sign(data: str) -> str:
        return hmac.new(
            config.JWT_SECRET.encode(), data.encode(), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def create_token(user_id: str, name: str = "") -> str:
        """签发 JWT Token。"""
        payload = {
            "sub": user_id,
            "name": name,
            "iat": int(time.time()),
            "exp": int(time.time()) + config.JWT_EXPIRE_HOURS * 3600,
        }
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b"=").decode()
        signature = AuthService._sign(payload_b64)
        return f"{payload_b64}.{signature}"

    @staticmethod
    def verify_token(token: str) -> dict | None:
        """校验 JWT Token，返回 payload 或 None。"""
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None
            payload_b64, signature = parts
            expected_sig = AuthService._sign(payload_b64)
            if not hmac.compare_digest(signature, expected_sig):
                return None
            # 补 padding
            padding = 4 - len(payload_b64) % 4
            payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception:
            return None


auth_service = AuthService()
