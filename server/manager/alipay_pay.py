"""Alipay OpenAPI — page pay / precreate + async notify (RSA2 公钥模式)."""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

DEFAULT_GATEWAY = "https://openapi.alipay.com/gateway.do"
SIGN_TYPE = "RSA2"
CHARSET = "utf-8"
FORMAT = "JSON"
VERSION = "1.0"


class AlipayPayError(Exception):
    """Business or transport error when calling Alipay."""


def _truthy(name: str) -> bool:
    return str(os.environ.get(name, "") or "").lower() in ("1", "true", "yes")


def _read_key_material(path: Path) -> bytes:
    raw = path.read_bytes().strip()
    if b"BEGIN" in raw:
        return raw
    # 开放平台工具常导出裸 base64（无 PEM 头）
    text = raw.decode("ascii", errors="ignore").replace("\n", "").replace("\r", "").strip()
    return text.encode("ascii")


def _load_private_key(pem_or_b64: bytes):
    if b"BEGIN" in pem_or_b64:
        data = pem_or_b64
    else:
        data = (
            b"-----BEGIN PRIVATE KEY-----\n"
            + pem_or_b64
            + b"\n-----END PRIVATE KEY-----\n"
        )
    return serialization.load_pem_private_key(data, password=None, backend=default_backend())


def _load_public_key(pem_or_b64: bytes):
    if b"BEGIN" in pem_or_b64:
        data = pem_or_b64
    else:
        data = (
            b"-----BEGIN PUBLIC KEY-----\n"
            + pem_or_b64
            + b"\n-----END PUBLIC KEY-----\n"
        )
    return serialization.load_pem_public_key(data, backend=default_backend())


def _sign_content(params: dict[str, str]) -> str:
    items = sorted((k, v) for k, v in params.items() if k != "sign" and v is not None and v != "")
    return "&".join(f"{k}={v}" for k, v in items)


def _rsa2_sign(private_key_pem: bytes, content: str) -> str:
    key = _load_private_key(private_key_pem)
    sig = key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


def _rsa2_verify(public_key_pem: bytes, content: str, sign_b64: str) -> bool:
    try:
        key = _load_public_key(public_key_pem)
        key.verify(
            base64.b64decode(sign_b64),
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


@dataclass(frozen=True)
class AlipayPaySettings:
    enabled: bool
    app_id: str
    gateway: str
    app_private_key_pem: bytes
    alipay_public_key_pem: bytes
    notify_url: str
    return_url: str
    trade_mode: str  # page | precreate

    @classmethod
    def from_env(cls, *, base_dir: Path | None = None) -> AlipayPaySettings:
        root = base_dir or Path(".")
        enabled = _truthy("ALIPAY_ENABLED")
        app_id = str(os.environ.get("ALIPAY_APP_ID", "") or "").strip()
        gateway = str(os.environ.get("ALIPAY_GATEWAY", "") or "").strip() or DEFAULT_GATEWAY
        notify = str(os.environ.get("ALIPAY_NOTIFY_URL", "") or "").strip()
        return_url = str(os.environ.get("ALIPAY_RETURN_URL", "") or "").strip()
        mode = str(os.environ.get("ALIPAY_TRADE_MODE", "") or "page").strip().lower()
        if mode not in ("page", "precreate"):
            mode = "page"

        priv = b""
        pub = b""
        priv_path = str(os.environ.get("ALIPAY_APP_PRIVATE_KEY_PATH", "") or "").strip()
        pub_path = str(os.environ.get("ALIPAY_PUBLIC_KEY_PATH", "") or "").strip()
        if priv_path:
            p = Path(priv_path)
            if not p.is_absolute():
                p = root / p
            if p.is_file():
                priv = _read_key_material(p)
        if pub_path:
            p = Path(pub_path)
            if not p.is_absolute():
                p = root / p
            if p.is_file():
                pub = _read_key_material(p)

        return cls(
            enabled=enabled,
            app_id=app_id,
            gateway=gateway,
            app_private_key_pem=priv,
            alipay_public_key_pem=pub,
            notify_url=notify,
            return_url=return_url,
            trade_mode=mode,
        )

    def ready_for_pay(self) -> bool:
        if not self.enabled:
            return False
        return bool(
            self.app_id
            and self.app_private_key_pem
            and self.alipay_public_key_pem
            and self.notify_url
        )


def alipay_out_trade_no(order_id: str) -> str:
    """Alipay out_trade_no 最长 64；与微信一致用无连字符 UUID。"""
    return str(order_id).replace("-", "").lower()


def _common_params(cfg: AlipayPaySettings, method: str, biz: dict) -> dict[str, str]:
    from datetime import datetime, timezone

    params: dict[str, str] = {
        "app_id": cfg.app_id,
        "method": method,
        "format": FORMAT,
        "charset": CHARSET,
        "sign_type": SIGN_TYPE,
        "timestamp": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "version": VERSION,
        "notify_url": cfg.notify_url,
        "biz_content": json.dumps(biz, ensure_ascii=False, separators=(",", ":")),
    }
    if cfg.return_url and method == "alipay.trade.page.pay":
        params["return_url"] = cfg.return_url
    content = _sign_content(params)
    params["sign"] = _rsa2_sign(cfg.app_private_key_pem, content)
    return params


def build_page_pay_url(
    cfg: AlipayPaySettings,
    *,
    out_trade_no: str,
    subject: str,
    amount_yuan: Decimal,
) -> str:
    """电脑网站支付：返回带签名的网关 GET URL（前端可跳转或生成二维码）。"""
    if not cfg.ready_for_pay():
        raise AlipayPayError("支付宝未完整配置")
    total = f"{amount_yuan.quantize(Decimal('0.01'))}"
    biz = {
        "out_trade_no": out_trade_no,
        "product_code": "FAST_INSTANT_TRADE_PAY",
        "total_amount": total,
        "subject": (subject or "账户充值")[:256],
    }
    params = _common_params(cfg, "alipay.trade.page.pay", biz)
    return cfg.gateway.rstrip("?") + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def precreate_qr_code(
    cfg: AlipayPaySettings,
    *,
    out_trade_no: str,
    subject: str,
    amount_yuan: Decimal,
) -> str:
    """当面付预下单：返回 qr_code 字符串（需开通当面付产品）。"""
    if not cfg.ready_for_pay():
        raise AlipayPayError("支付宝未完整配置")
    total = f"{amount_yuan.quantize(Decimal('0.01'))}"
    biz = {
        "out_trade_no": out_trade_no,
        "total_amount": total,
        "subject": (subject or "账户充值")[:256],
    }
    params = _common_params(cfg, "alipay.trade.precreate", biz)
    body = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        cfg.gateway,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise AlipayPayError(f"支付宝预下单 HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise AlipayPayError(f"支付宝预下单网络错误: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AlipayPayError("支付宝预下单响应非 JSON") from e

    resp_key = "alipay_trade_precreate_response"
    node = data.get(resp_key) or {}
    if str(node.get("code") or "") != "10000":
        raise AlipayPayError(
            f"支付宝预下单失败: {node.get('sub_msg') or node.get('msg') or node}"
        )
    qr = str(node.get("qr_code") or "").strip()
    if not qr:
        raise AlipayPayError("支付宝预下单未返回 qr_code")
    return qr


def create_pay(
    cfg: AlipayPaySettings,
    *,
    out_trade_no: str,
    subject: str,
    amount_yuan: Decimal,
) -> dict[str, str]:
    """按 trade_mode 返回 pay_url 和/或 code_url。"""
    if cfg.trade_mode == "precreate":
        qr = precreate_qr_code(
            cfg, out_trade_no=out_trade_no, subject=subject, amount_yuan=amount_yuan
        )
        return {"code_url": qr, "pay_url": "", "channel": "alipay"}
    url = build_page_pay_url(
        cfg, out_trade_no=out_trade_no, subject=subject, amount_yuan=amount_yuan
    )
    # page 模式：pay_url 跳转；同时可作为二维码内容供支付宝 App 扫
    return {"code_url": url, "pay_url": url, "channel": "alipay"}


def verify_notify(cfg: AlipayPaySettings, form: dict[str, str]) -> dict[str, str]:
    """校验异步通知签名；成功返回去签后的参数字典。"""
    if not cfg.alipay_public_key_pem:
        raise AlipayPayError("未配置支付宝公钥")
    sign = (form.get("sign") or "").strip()
    sign_type = (form.get("sign_type") or SIGN_TYPE).strip()
    if not sign:
        raise AlipayPayError("缺少 sign")
    if sign_type.upper() != "RSA2":
        raise AlipayPayError(f"不支持的 sign_type={sign_type}")
    unsigned = {k: v for k, v in form.items() if k not in ("sign", "sign_type")}
    content = _sign_content(unsigned)
    if not _rsa2_verify(cfg.alipay_public_key_pem, content, sign):
        raise AlipayPayError("支付宝通知验签失败")
    return unsigned


def parse_notify_trade(form: dict[str, str]) -> tuple[str, str, str, Decimal]:
    """返回 out_trade_no, trade_no, trade_status, total_amount。"""
    out_no = (form.get("out_trade_no") or "").strip()
    trade_no = (form.get("trade_no") or "").strip()
    status = (form.get("trade_status") or "").strip()
    amt = Decimal(str(form.get("total_amount") or "0"))
    if not out_no:
        raise AlipayPayError("缺少 out_trade_no")
    return out_no, trade_no, status, amt
