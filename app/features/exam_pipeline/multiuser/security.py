from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4


_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@dataclass(slots=True)
class TokenStore:
    _tokens: dict[str, tuple[str, float]]
    _lock: RLock
    ttl_seconds: int

    def __init__(self, ttl_seconds: int | None = None) -> None:
        self._tokens = {}
        raw_ttl = ttl_seconds if ttl_seconds is not None else int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))
        if raw_ttl <= 0:
            raise ValueError("AUTH_TOKEN_TTL_SECONDS must be positive.")
        self.ttl_seconds = raw_ttl
        self._lock = RLock()

    def issue(self, user_id: str) -> str:
        token = uuid4().hex + uuid4().hex
        with self._lock:
            self._tokens[token] = (user_id, datetime.now(timezone.utc).timestamp() + self.ttl_seconds)
        return token

    def resolve(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._lock:
            record = self._tokens.get(token)
            if record is None:
                return None
            user_id, expires_at = record
            if datetime.now(timezone.utc).timestamp() >= expires_at:
                self._tokens.pop(token, None)
                return None
            return user_id

    def revoke(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)
