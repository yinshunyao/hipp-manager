"""WeChat Pay API v3 — Native scan (code_url) and notify verification."""

from __future__ import annotations

import base64
import json
import logging
import os
import ssl
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

NATIVE_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/native"
CERTIFICATES_PATH = "/v3/certificates"
SIGN_TYPE = "WECHATPAY2-SHA256-RSA2048"


def _looks_like_x509_cert_pem(data: bytes) -> bool:
    return b"BEGIN CERTIFICATE" in data and b"END CERTIFICATE" in data


def _looks_like_spki_public_key_pem(data: bytes) -> bool:
    """SubjectPublicKeyInfo PEM（微信文档中的「公钥」常为这种，非 X.509 证书）。"""
    return b"BEGIN PUBLIC KEY" in data and b"END PUBLIC KEY" in data


def _looks_like_private_key_pem(data: bytes) -> bool:
    return (
        b"BEGIN PRIVATE KEY" in data
        or b"BEGIN RSA PRIVATE KEY" in data
        or b"BEGIN EC PRIVATE KEY" in data
    )


class WeChatPayError(Exception):
    """Business or transport error when calling WeChat Pay."""


@dataclass(frozen=True)
class WeChatPaySettings:
    enabled: bool
    appid: str
    mchid: str
    mch_cert_serial: str
    mch_private_key_pem: bytes
    api_v3_key: str
    notify_url: str
    platform_cert_pem: bytes  # 单文件 X.509；目录模式或仅用 SPKI 时为空
    platform_spki_public_pem: bytes  # BEGIN PUBLIC KEY（SPKI）；与 platform_cert_pem 二选一（单文件）
    platform_cert_dir: Path | None  # 目录模式：GET /v3/certificates 缓存 {serial}.pem，初始可为空

    @classmethod
    def from_env(cls, *, base_dir: Path | None = None) -> WeChatPaySettings:
        import os

        def _b(name: str) -> bool:
            return str(os.environ.get(name, "") or "").lower() in ("1", "true", "yes")

        root = base_dir or Path(".")
        enabled = _b("WECHAT_PAY_ENABLED")
        appid = str(os.environ.get("WECHAT_PAY_APPID", "") or "").strip()
        mchid = str(os.environ.get("WECHAT_PAY_MCHID", "") or "").strip()
        serial = str(os.environ.get("WECHAT_PAY_MCH_CERT_SERIAL", "") or "").strip()
        key_path = str(os.environ.get("WECHAT_PAY_MCH_PRIVATE_KEY_PATH", "") or "").strip()
        api_v3 = str(os.environ.get("WECHAT_PAY_API_V3_KEY", "") or "").strip()
        notify = str(os.environ.get("WECHAT_PAY_NOTIFY_URL", "") or "").strip()
        plat_path = str(os.environ.get("WECHAT_PAY_PLATFORM_CERT_PATH", "") or "").strip()

        pem: bytes = b""
        if key_path:
            p = Path(key_path)
            if not p.is_absolute():
                p = root / p
            if p.is_file():
                pem = p.read_bytes()

        plat_pem: bytes = b""
        plat_spki: bytes = b""
        plat_dir: Path | None = None
        if plat_path:
            pp = Path(plat_path)
            if not pp.is_absolute():
                pp = root / pp
            if pp.is_file():
                raw_plat = pp.read_bytes()
                if _looks_like_x509_cert_pem(raw_plat):
                    plat_pem = raw_plat
                elif _looks_like_spki_public_key_pem(raw_plat):
                    plat_spki = raw_plat
                else:
                    if _looks_like_private_key_pem(raw_plat):
                        logger.warning(
                            "WECHAT_PAY_PLATFORM_CERT_PATH 指向了私钥 PEM，"
                            "不能用作微信平台验签公钥。"
                        )
                    elif raw_plat.strip():
                        logger.warning("WECHAT_PAY_PLATFORM_CERT_PATH 无法识别 PEM 类型")
            else:
                plat_dir = pp

        return cls(
            enabled=enabled,
            appid=appid,
            mchid=mchid,
            mch_cert_serial=serial,
            mch_private_key_pem=pem,
            api_v3_key=api_v3,
            notify_url=notify,
            platform_cert_pem=plat_pem,
            platform_spki_public_pem=plat_spki,
            platform_cert_dir=plat_dir,
        )

    def has_platform_verification_config(self) -> bool:
        return bool(
            self.platform_cert_pem or self.platform_spki_public_pem or self.platform_cert_dir is not None
        )

    def ready_for_prepay(self) -> bool:
        """商户 + APIv3 + 平台验签配置（单文件 PEM 或证书缓存目录，目录可由接口自动拉取）。"""
        if not self.enabled:
            return False
        return bool(
            self.appid
            and self.mchid
            and self.mch_cert_serial
            and self.mch_private_key_pem
            and self.api_v3_key
            and self.notify_url
            and self.has_platform_verification_config()
        )


def wechat_out_trade_no(order_id: str) -> str:
    """WeChat allows 6–32 chars; our UUID without hyphens is 32."""
    return str(order_id).replace("-", "").lower()


def yuan_to_fen(yuan: Decimal) -> int:
    return int((yuan * Decimal(100)).quantize(Decimal("1")))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", dir=str(path.parent), delete=False, suffix=".tmp"
    ) as f:
        f.write(data)
        tmp_name = f.name
    os.replace(tmp_name, path)


def _aes_gcm_decrypt(api_v3_key: str, associated_data: str, nonce: str, ciphertext_b64: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = api_v3_key.encode("utf-8")
    if len(key) != 32:
        raise WeChatPayError("APIv3 密钥须为 32 字节")

    nonce_bytes = nonce.encode("utf-8")
    ct = base64.b64decode(ciphertext_b64)
    aes = AESGCM(key)
    return aes.decrypt(nonce_bytes, ct, associated_data.encode("utf-8"))


def _wechat_v3_request(
    cfg: WeChatPaySettings,
    method: str,
    url_path: str,
    body: str,
) -> tuple[int, str]:
    """Call WeChat Pay API v3. Use body=\"\" for GET."""
    url = f"https://api.mch.weixin.qq.com{url_path}"
    auth = _sign_authorization(
        mchid=cfg.mchid,
        serial=cfg.mch_cert_serial,
        private_key_pem=cfg.mch_private_key_pem,
        method=method,
        url_path=url_path,
        body=body,
    )
    data_bytes = body.encode("utf-8") if body and method.upper() != "GET" else None
    headers = {
        "Accept": "application/json",
        "Authorization": auth,
        "User-Agent": "hipp-manager-WeChatPay/1.0",
    }
    if data_bytes is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data_bytes, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as resp:
            raw = resp.read().decode("utf-8")
            return resp.getcode(), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, raw
    except urllib.error.URLError as e:
        raise WeChatPayError(f"微信请求网络错误: {e.reason}") from e


def sync_platform_certificates(cfg: WeChatPaySettings) -> int:
    """GET /v3/certificates, decrypt PEMs with APIv3 key, write ``{{serial}}.pem`` into *platform_cert_dir*."""
    if cfg.platform_cert_dir is None:
        raise WeChatPayError("未配置平台证书缓存目录")
    d = cfg.platform_cert_dir
    d.mkdir(parents=True, exist_ok=True)

    code, raw = _wechat_v3_request(cfg, "GET", CERTIFICATES_PATH, "")
    if code != 200:
        raise WeChatPayError(f"拉取平台证书失败 HTTP {code}: {raw[:400]}")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise WeChatPayError("平台证书接口返回非 JSON") from e

    items = payload.get("data")
    if not isinstance(items, list):
        raise WeChatPayError("平台证书接口 data 格式异常")

    n = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        sn = str(item.get("serial_no") or "").strip()
        enc = item.get("encrypt_certificate")
        if not sn or not isinstance(enc, dict):
            continue
        if enc.get("algorithm") != "AEAD_AES_256_GCM":
            continue
        ct = enc.get("ciphertext")
        nonce = enc.get("nonce")
        ad = str(enc.get("associated_data") or "certificate")
        if not isinstance(ct, str) or not isinstance(nonce, str):
            continue
        try:
            plain = _aes_gcm_decrypt(cfg.api_v3_key, ad, nonce, ct)
        except Exception as e:
            logger.warning("WeChat cert serial=%s decrypt skip: %s", sn, e)
            continue
        text = plain.decode("utf-8")
        if "BEGIN CERTIFICATE" not in text:
            continue
        out = d / f"{sn.upper()}.pem"
        _atomic_write(out, text.encode("utf-8"))
        n += 1
        logger.info("WeChat platform cert cached: %s", out.name)

    if n == 0:
        raise WeChatPayError("未能解密并保存任何平台证书，请核对 APIv3 密钥与商户权限")
    return n


def ensure_platform_certs_cached(cfg: WeChatPaySettings) -> None:
    """目录模式且目录内尚无 *.pem 时，调用 *sync_platform_certificates*。"""
    if cfg.platform_cert_dir is None:
        return
    d = cfg.platform_cert_dir
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise WeChatPayError(f"无法创建平台证书目录: {e}") from e
    if any(d.glob("*.pem")):
        return
    sync_platform_certificates(cfg)


def _pem_serial_upper(pem: bytes) -> str:
    try:
        cert = x509.load_pem_x509_certificate(pem, default_backend())
    except ValueError as e:
        raise WeChatPayError(
            "平台 X.509 证书 PEM 无效（须含 BEGIN CERTIFICATE）。"
            "若为腾讯提供的 BEGIN PUBLIC KEY 公钥文件，无需改为证书格式，保持当前文件即可（新版本已支持）。"
        ) from e
    return format(cert.serial_number, "X").upper()


def resolve_platform_public_key_for_notify(cfg: WeChatPaySettings, serial_header: str):
    """解析用于回调验签的公钥：X.509 证书（按序列号匹配）、SPKI 公钥 PEM、或目录缓存证书。"""
    serial = serial_header.strip()
    if not serial:
        raise WeChatPayError("缺少 Wechatpay-Serial")
    want = serial.upper()

    if cfg.platform_spki_public_pem:
        try:
            return serialization.load_pem_public_key(
                cfg.platform_spki_public_pem, backend=default_backend()
            )
        except ValueError as e:
            raise WeChatPayError("WECHAT_PAY_PLATFORM_CERT_PATH 中公钥 PEM（BEGIN PUBLIC KEY）无法解析") from e

    if cfg.platform_cert_pem:
        got = _pem_serial_upper(cfg.platform_cert_pem)
        if got != want:
            raise WeChatPayError(
                f"回调证书序列号与本地 PEM 不一致（回调={want} 本地={got}），请改用证书目录或更新 PEM"
            )
        return x509.load_pem_x509_certificate(cfg.platform_cert_pem, default_backend()).public_key()

    if cfg.platform_cert_dir is None:
        raise WeChatPayError("未配置平台证书")

    d = cfg.platform_cert_dir

    def _find_in_dir() -> bytes | None:
        for p in sorted(d.glob("*.pem")):
            try:
                data = p.read_bytes()
                if not _looks_like_x509_cert_pem(data):
                    continue
                if _pem_serial_upper(data) == want:
                    return data
            except (WeChatPayError, ValueError, Exception):
                continue
        return None

    hit = _find_in_dir()
    if hit:
        return x509.load_pem_x509_certificate(hit, default_backend()).public_key()
    sync_platform_certificates(cfg)
    hit = _find_in_dir()
    if hit:
        return x509.load_pem_x509_certificate(hit, default_backend()).public_key()
    raise WeChatPayError(f"无平台证书可验签 serial={want}，已尝试 GET /v3/certificates 刷新缓存")


def _load_private_key(pem: bytes):
    return serialization.load_pem_private_key(pem, password=None, backend=default_backend())


def _sign_authorization(
    *,
    mchid: str,
    serial: str,
    private_key_pem: bytes,
    method: str,
    url_path: str,
    body: str,
) -> str:
    ts = str(int(time.time()))
    nonce = uuid.uuid4().hex
    sign_text = f"{method}\n{url_path}\n{ts}\n{nonce}\n{body}\n"
    key = _load_private_key(private_key_pem)
    sig = key.sign(
        sign_text.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    sig_b64 = base64.b64encode(sig).decode("ascii")
    return (
        f'{SIGN_TYPE} mchid="{mchid}",nonce_str="{nonce}",'
        f'timestamp="{ts}",serial_no="{serial}",signature="{sig_b64}"'
    )


def native_prepay(
    cfg: WeChatPaySettings,
    *,
    out_trade_no: str,
    description: str,
    amount_yuan: Decimal,
) -> str:
    """Call WeChat Native unified order API; return code_url."""
    if not cfg.ready_for_prepay():
        raise WeChatPayError("微信支付未完整配置")

    ensure_platform_certs_cached(cfg)

    total = yuan_to_fen(amount_yuan)
    if total < 1:
        raise WeChatPayError("支付金额无效")

    desc = (description or "账户充值").strip()
    if len(desc.encode("utf-8")) > 120:
        desc = desc.encode("utf-8")[:120].decode("utf-8", errors="ignore")

    body_obj = {
        "appid": cfg.appid,
        "mchid": cfg.mchid,
        "description": desc,
        "out_trade_no": out_trade_no,
        "notify_url": cfg.notify_url,
        "amount": {"total": total, "currency": "CNY"},
    }
    body_str = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))
    url_path = "/v3/pay/transactions/native"
    auth = _sign_authorization(
        mchid=cfg.mchid,
        serial=cfg.mch_cert_serial,
        private_key_pem=cfg.mch_private_key_pem,
        method="POST",
        url_path=url_path,
        body=body_str,
    )

    req = urllib.request.Request(
        NATIVE_URL,
        data=body_str.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "Authorization": auth,
            "User-Agent": "hipp-manager-WeChatPay/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as resp:
            raw = resp.read().decode("utf-8")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        logger.warning("WeChat Native HTTPError %s: %s", e.code, raw[:500])
        try:
            err_j = json.loads(raw)
            msg = err_j.get("message") or err_j.get("detail") or raw[:200]
        except json.JSONDecodeError:
            msg = raw[:200] or str(e)
        raise WeChatPayError(f"微信下单失败: {msg}") from e
    except urllib.error.URLError as e:
        logger.exception("WeChat Native URLError")
        raise WeChatPayError(f"微信下单网络错误: {e.reason}") from e

    if code != 200:
        raise WeChatPayError(f"微信下单异常 HTTP {code}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise WeChatPayError("微信返回非 JSON") from e

    code_url = data.get("code_url")
    if not isinstance(code_url, str) or not code_url.strip():
        raise WeChatPayError("微信未返回 code_url")
    return code_url.strip()


def verify_notify_and_decrypt(
    cfg: WeChatPaySettings,
    *,
    headers: dict[str, str],
    body_text: str,
) -> dict:
    """Verify WeChat signature and decrypt resource; return plaintext JSON dict."""
    if not cfg.api_v3_key:
        raise WeChatPayError("缺少 APIv3 密钥，无法验签/解密")

    sig_b64 = headers.get("Wechatpay-Signature") or headers.get("wechatpay-signature")
    ts = headers.get("Wechatpay-Timestamp") or headers.get("wechatpay-timestamp")
    nonce = headers.get("Wechatpay-Nonce") or headers.get("wechatpay-nonce")
    serial = headers.get("Wechatpay-Serial") or headers.get("wechatpay-serial") or ""
    if not sig_b64 or not ts or not nonce:
        raise WeChatPayError("缺少 Wechatpay 签名头")

    pub = resolve_platform_public_key_for_notify(cfg, serial)

    message = f"{ts}\n{nonce}\n{body_text}\n".encode("utf-8")
    try:
        signature = base64.b64decode(sig_b64)
    except Exception as e:
        raise WeChatPayError("签名 Base64 无效") from e
    try:
        pub.verify(
            signature,
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as e:
        logger.warning("WeChat notify signature verify failed: %s", e)
        raise WeChatPayError("回调验签失败") from e

    try:
        outer = json.loads(body_text)
    except json.JSONDecodeError as e:
        raise WeChatPayError("回调 Body 非 JSON") from e

    resource = outer.get("resource")
    if not isinstance(resource, dict):
        raise WeChatPayError("回调缺少 resource")

    algo = resource.get("algorithm")
    if algo != "AEAD_AES_256_GCM":
        raise WeChatPayError(f"不支持的加密算法: {algo}")

    ciphertext = resource.get("ciphertext")
    n = resource.get("nonce")
    ad = resource.get("associated_data") or ""
    if not isinstance(ciphertext, str) or not isinstance(n, str):
        raise WeChatPayError("回调 resource 字段不完整")

    try:
        plain = _aes_gcm_decrypt(cfg.api_v3_key, ad, n, ciphertext)
        inner = json.loads(plain.decode("utf-8"))
    except Exception as e:
        logger.warning("WeChat notify decrypt failed: %s", e)
        raise WeChatPayError("回调解密失败") from e

    if not isinstance(inner, dict):
        raise WeChatPayError("解密后非对象")
    return inner


def parse_trade_result(inner: dict) -> tuple[str, str, str, int]:
    """Returns (out_trade_no, transaction_id, trade_state, payer_total_fen)."""
    out_no = str(inner.get("out_trade_no") or "").strip()
    txn_id = str(inner.get("transaction_id") or "").strip()
    state = str(inner.get("trade_state") or "").strip()
    amt = inner.get("amount") or {}
    total = 0
    if isinstance(amt, dict):
        total = int(amt.get("payer_total") or amt.get("total") or 0)
    if not out_no:
        raise WeChatPayError("缺少 out_trade_no")
    return out_no, txn_id, state, total
