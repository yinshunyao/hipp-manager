"""HMAC 会话：expires.phone.signature；可选 Redis/内存白名单以便登出吊销。"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Protocol

SESSION_SECONDS = 12 * 60 * 60
logger = logging.getLogger(__name__)


class TokenRegistry(Protocol):
    def remember(self, token: str, telephone: str, ttl: int) -> None: ...
    def active(self, token: str) -> bool: ...
    def forget(self, token: str) -> None: ...
    def forget_phone(self, telephone: str) -> None: ...


class MemoryTokenRegistry:
    def __init__(self) -> None:
        self._by_token: dict[str, tuple[str, float]] = {}
        self._by_phone: dict[str, set[str]] = {}

    def remember(self, token: str, telephone: str, ttl: int) -> None:
        self._by_token[token] = (telephone, time.time() + ttl)
        self._by_phone.setdefault(telephone, set()).add(token)

    def active(self, token: str) -> bool:
        item = self._by_token.get(token)
        if not item:
            return False
        phone, exp = item
        if exp < time.time():
            self.forget(token)
            return False
        return bool(phone)

    def forget(self, token: str) -> None:
        item = self._by_token.pop(token, None)
        if not item:
            return
        phone, _ = item
        bucket = self._by_phone.get(phone)
        if bucket:
            bucket.discard(token)
            if not bucket:
                self._by_phone.pop(phone, None)

    def forget_phone(self, telephone: str) -> None:
        for token in list(self._by_phone.get(telephone, ())):
            self.forget(token)


class RedisTokenRegistry:
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)

    @staticmethod
    def _tok_key(token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"mgr:tok:{digest}"

    @staticmethod
    def _phone_key(telephone: str) -> str:
        return f"mgr:tokphone:{telephone}"

    def remember(self, token: str, telephone: str, ttl: int) -> None:
        key = self._tok_key(token)
        phone_key = self._phone_key(telephone)
        pipe = self._r.pipeline()
        pipe.setex(key, ttl, telephone)
        pipe.sadd(phone_key, key)
        pipe.expire(phone_key, ttl)
        pipe.execute()

    def active(self, token: str) -> bool:
        return bool(self._r.get(self._tok_key(token)))

    def forget(self, token: str) -> None:
        key = self._tok_key(token)
        phone = self._r.get(key)
        pipe = self._r.pipeline()
        pipe.delete(key)
        if phone:
            pipe.srem(self._phone_key(str(phone)), key)
        pipe.execute()

    def forget_phone(self, telephone: str) -> None:
        phone_key = self._phone_key(telephone)
        keys = list(self._r.smembers(phone_key) or [])
        if keys:
            self._r.delete(*keys)
        self._r.delete(phone_key)


def make_registry(redis_url: str, *, prefer_memory: bool = False) -> TokenRegistry:
    if prefer_memory:
        return MemoryTokenRegistry()
    try:
        reg = RedisTokenRegistry(redis_url)
        reg._r.ping()  # type: ignore[attr-defined]
        return reg
    except Exception:
        logger.exception("会话白名单 Redis 不可用，回退内存")
        return MemoryTokenRegistry()


def _raw_token(header: str) -> str:
    return header[7:] if header.startswith("Bearer ") else header


OPS_PREFIX = "ops:"


def _issue_identity(
    secret: bytes,
    identity: str,
    now: int | None = None,
    registry: TokenRegistry | None = None,
) -> str:
    expires = (now if now is not None else int(time.time())) + SESSION_SECONDS
    payload = f"{expires}.{identity}"
    signature = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
    token = f"{payload}.{signature}"
    if registry is not None:
        registry.remember(token, identity, SESSION_SECONDS)
    return token


def _read_identity(
    secret: bytes,
    header: str,
    now: int | None = None,
    registry: TokenRegistry | None = None,
) -> str:
    token = _raw_token(header)
    pieces = token.split(".", 2)
    if len(pieces) != 3:
        return ""
    exp_text, identity, signature = pieces
    if not identity or "." in identity:
        return ""
    payload = f"{exp_text}.{identity}"
    expected = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return ""
    try:
        expires = int(exp_text)
    except ValueError:
        return ""
    if expires <= (now if now is not None else int(time.time())):
        return ""
    if registry is not None and not registry.active(token):
        return ""
    return identity


def issue(
    secret: bytes,
    telephone: str,
    now: int | None = None,
    registry: TokenRegistry | None = None,
) -> str:
    if not telephone.isdigit():
        raise ValueError("telephone must be digits")
    return _issue_identity(secret, telephone, now=now, registry=registry)


def read(
    secret: bytes,
    header: str,
    now: int | None = None,
    registry: TokenRegistry | None = None,
) -> str:
    identity = _read_identity(secret, header, now=now, registry=registry)
    if identity.isdigit():
        return identity
    return ""


def issue_ops(
    secret: bytes,
    username: str,
    now: int | None = None,
    registry: TokenRegistry | None = None,
) -> str:
    u = (username or "").strip()
    if not u or "." in u or ":" in u:
        raise ValueError("invalid ops username")
    return _issue_identity(secret, f"{OPS_PREFIX}{u}", now=now, registry=registry)


def read_ops(
    secret: bytes,
    header: str,
    now: int | None = None,
    registry: TokenRegistry | None = None,
) -> str:
    identity = _read_identity(secret, header, now=now, registry=registry)
    if identity.startswith(OPS_PREFIX):
        return identity[len(OPS_PREFIX) :]
    return ""


def revoke(header: str, registry: TokenRegistry | None) -> None:
    if registry is None:
        return
    token = _raw_token(header)
    if token:
        registry.forget(token)
