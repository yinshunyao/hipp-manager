"""短信验证码：mock 或阿里云 Dysmsapi。"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Protocol

from manager.config import Settings

logger = logging.getLogger(__name__)

MOCK_CODE = "123456"


class CodeStore(Protocol):
    def set_code(self, phone: str, code: str, ttl: int) -> None: ...
    def get_code(self, phone: str) -> str: ...
    def delete_code(self, phone: str) -> None: ...
    def mark_sent(self, phone: str, interval: int) -> bool: ...


class MemoryCodeStore:
    def __init__(self) -> None:
        self._codes: dict[str, tuple[str, float]] = {}
        self._sent: dict[str, float] = {}

    def set_code(self, phone: str, code: str, ttl: int) -> None:
        self._codes[phone] = (code, time.time() + ttl)

    def get_code(self, phone: str) -> str:
        item = self._codes.get(phone)
        if not item:
            return ""
        code, exp = item
        if exp < time.time():
            self._codes.pop(phone, None)
            return ""
        return code

    def delete_code(self, phone: str) -> None:
        self._codes.pop(phone, None)

    def mark_sent(self, phone: str, interval: int) -> bool:
        now = time.time()
        last = self._sent.get(phone, 0)
        if now - last < interval:
            return False
        self._sent[phone] = now
        return True


class RedisCodeStore:
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)

    def set_code(self, phone: str, code: str, ttl: int) -> None:
        self._r.setex(f"mgr:sms:{phone}", ttl, code)

    def get_code(self, phone: str) -> str:
        return str(self._r.get(f"mgr:sms:{phone}") or "")

    def delete_code(self, phone: str) -> None:
        self._r.delete(f"mgr:sms:{phone}")

    def mark_sent(self, phone: str, interval: int) -> bool:
        key = f"mgr:sms:sent:{phone}"
        ok = self._r.set(key, "1", nx=True, ex=interval)
        return bool(ok)


def make_store(settings: Settings) -> CodeStore:
    if settings.sms_mock:
        return MemoryCodeStore()
    try:
        return RedisCodeStore(settings.redis_url)
    except Exception:
        logger.exception("Redis 不可用，回退内存验证码存储")
        return MemoryCodeStore()


def send_login_code(settings: Settings, store: CodeStore, phone: str) -> None:
    if not store.mark_sent(phone, settings.sms_send_interval):
        raise ValueError("发送过于频繁，请稍后再试")
    code = MOCK_CODE if settings.sms_mock else f"{random.randint(0, 999999):06d}"
    store.set_code(phone, code, settings.sms_valid_time)
    if settings.sms_mock:
        logger.info("SMS_MOCK phone=%s code=%s", phone, code)
        return
    _aliyun_send(settings, phone, code)


def verify_code(store: CodeStore, phone: str, code: str) -> bool:
    expected = store.get_code(phone)
    if not expected or expected != code.strip():
        return False
    store.delete_code(phone)
    return True


def _aliyun_send(settings: Settings, phone: str, code: str) -> None:
    if not (
        settings.sms_access_key_id
        and settings.sms_access_key_secret
        and settings.sms_sign_name
        and settings.sms_template_code
    ):
        raise ValueError("未配置阿里云短信")
    try:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.request import CommonRequest
    except ImportError as exc:
        raise ValueError("未安装 aliyun-python-sdk-core，无法发短信") from exc

    client = AcsClient(settings.sms_access_key_id, settings.sms_access_key_secret, "cn-hangzhou")
    request = CommonRequest()
    request.set_accept_format("json")
    request.set_domain("dysmsapi.aliyuncs.com")
    request.set_method("POST")
    request.set_protocol_type("https")
    request.set_version("2017-05-25")
    request.set_action_name("SendSms")
    request.add_query_param("PhoneNumbers", phone)
    request.add_query_param("SignName", settings.sms_sign_name)
    request.add_query_param("TemplateCode", settings.sms_template_code)
    request.add_query_param("TemplateParam", json.dumps({"code": code}, ensure_ascii=False))
    raw = client.do_action_with_exception(request)
    payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    if str(payload.get("Code") or "") != "OK":
        raise ValueError(str(payload.get("Message") or "短信发送失败")[:200])
