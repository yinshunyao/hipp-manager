"""从工程根 .env 加载配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, value = text.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _truthy(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default) or "").strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    session_secret: bytes
    s2s_key: str
    database_url: str
    redis_url: str
    sms_mock: bool
    sms_access_key_id: str
    sms_access_key_secret: str
    sms_sign_name: str
    sms_template_code: str
    sms_send_interval: int
    sms_valid_time: int
    recharge_dev_auto: bool
    data_dir: Path
    media_dir: Path
    media_public_base: str
    media_max_bytes: int
    web_dist: Path


def load_settings() -> Settings:
    root = repo_root()
    _load_dotenv(root / ".env")
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    media_override = (os.environ.get("MEDIA_DIR") or "").strip()
    media_dir = Path(media_override).expanduser() if media_override else (data_dir / "media")
    if not media_dir.is_absolute():
        media_dir = (root / media_dir).resolve()
    media_dir.mkdir(parents=True, exist_ok=True)

    secret = (os.environ.get("MANAGER_SESSION_SECRET") or "dev-manager-secret").encode("utf-8")
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not db_url:
        db_path = (data_dir / "manager.db").resolve()
        db_url = f"sqlite:///{db_path}"

    max_bytes_raw = (os.environ.get("MEDIA_MAX_BYTES") or "").strip()
    try:
        media_max_bytes = int(max_bytes_raw) if max_bytes_raw else 20 * 1024 * 1024
    except ValueError:
        media_max_bytes = 20 * 1024 * 1024

    return Settings(
        host=(os.environ.get("MANAGER_HOST") or "0.0.0.0").strip(),
        port=int((os.environ.get("MANAGER_PORT") or "9100").strip()),
        session_secret=secret,
        s2s_key=(os.environ.get("MANAGER_S2S_KEY") or "").strip(),
        database_url=db_url,
        redis_url=(os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/3").strip(),
        sms_mock=_truthy("SMS_MOCK", "1"),
        sms_access_key_id=(os.environ.get("MANAGER_SMS_ACCESS_KEY_ID") or "").strip(),
        sms_access_key_secret=(os.environ.get("MANAGER_SMS_ACCESS_KEY_SECRET") or "").strip(),
        sms_sign_name=(os.environ.get("MANAGER_SMS_SIGN_NAME") or "").strip(),
        sms_template_code=(os.environ.get("MANAGER_SMS_TEMPLATE_CODE") or "").strip(),
        sms_send_interval=int((os.environ.get("MANAGER_SMS_SEND_INTERVAL") or "60").strip()),
        sms_valid_time=int((os.environ.get("MANAGER_SMS_VALID_TIME") or "300").strip()),
        recharge_dev_auto=_truthy("RECHARGE_DEV_AUTO", "0"),
        data_dir=data_dir,
        media_dir=media_dir,
        media_public_base=(os.environ.get("MEDIA_PUBLIC_BASE") or "").strip().rstrip("/"),
        media_max_bytes=max(1024, media_max_bytes),
        web_dist=root / "web" / "dist",
    )
