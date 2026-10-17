"""从 hipp-or（hipp）与 VoiceFix（voicefix）按手机号合并导入 manager.user。

用法（服务器 /data/hipp-manager）：
  PYTHONPATH=server .venv/bin/python -m manager.import_legacy

环境变量（可选，默认与生产-yin 同机库名）：
  DATABASE_URL          目标 manager 库（须已在 .env）
  LEGACY_HIPP_URL       默认把 DATABASE_URL 的库名换成 hipp
  LEGACY_VOICE_URL      默认换成 voicefix
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from manager.config import load_settings
from manager.db import init_schema

logger = logging.getLogger(__name__)
PHONE_RE = re.compile(r"^1\d{10}$")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _swap_db(url: str, db_name: str) -> str:
    """mysql+pymysql://user:pass@host:port/old -> .../db_name"""
    if "://" not in url:
        raise ValueError("DATABASE_URL 无效")
    scheme, rest = url.split("://", 1)
    # user:pass@host:port/db?q
    if "/" not in rest:
        return f"{scheme}://{rest}/{db_name}"
    authority, path_q = rest.split("/", 1)
    path = path_q.split("?", 1)[0]
    query = path_q.split("?", 1)[1] if "?" in path_q else ""
    new_path = db_name
    out = f"{scheme}://{authority}/{new_path}"
    if query:
        out += f"?{query}"
    return out


def _d(v) -> Decimal:
    try:
        return Decimal(str(v if v is not None else 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _load_voice(engine: Engine) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT user_id, phone, nickname, COALESCE(password_hash, ''), "
                "has_password, balance, COALESCE(avatar_path, ''), created_at "
                "FROM user"
            )
        ).fetchall()
    for r in rows:
        phone = str(r[1] or "").strip()
        if not PHONE_RE.match(phone):
            continue
        out[phone] = {
            "user_id": str(r[0] or "").strip(),
            "phone": phone,
            "nickname": str(r[2] or "").strip()[:64],
            "password_hash": str(r[3] or "").strip()[:255],
            "has_password": bool(r[4]),
            "balance": _d(r[5]),
            "avatar_path": str(r[6] or "").strip()[:512],
            "created_at": str(r[7] or "")[:32] or _now(),
            "source": "vf",
        }
    return out


def _load_hipp(engine: Engine) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT telephone, COALESCE(nickname, ''), COALESCE(name, ''), "
                "COALESCE(password, ''), COALESCE(avatar, ''), COALESCE(wx_avatar, ''), "
                "create_datetime "
                "FROM vadmin_auth_user WHERE COALESCE(is_delete, 0) = 0"
            )
        ).fetchall()
    for r in rows:
        phone = str(r[0] or "").strip()
        if not PHONE_RE.match(phone):
            continue
        nick = str(r[1] or "").strip() or str(r[2] or "").strip()
        pw = str(r[3] or "").strip()
        avatar = str(r[4] or "").strip() or str(r[5] or "").strip()
        out[phone] = {
            "user_id": "",
            "phone": phone,
            "nickname": nick[:64],
            "password_hash": pw[:255] if pw else "",
            "has_password": bool(pw),
            "balance": Decimal("0.00"),
            "avatar_path": avatar[:512],
            "created_at": str(r[6] or "")[:32] or _now(),
            "source": "or",
        }
    return out


def _merge(voice: dict[str, dict], hipp: dict[str, dict]) -> list[dict]:
    phones = sorted(set(voice) | set(hipp))
    merged: list[dict] = []
    for phone in phones:
        v = voice.get(phone)
        h = hipp.get(phone)
        if v and h:
            use_voice_pw = bool(v["has_password"] and v["password_hash"])
            merged.append(
                {
                    "user_id": v["user_id"] or str(uuid.uuid4()),
                    "phone": phone,
                    "nickname": (v["nickname"] or h["nickname"] or f"用户{phone[-4:]}")[:64],
                    "password_hash": v["password_hash"] if use_voice_pw else h["password_hash"],
                    "has_password": 1 if (use_voice_pw or h["has_password"]) else 0,
                    "avatar_path": (v["avatar_path"] or h["avatar_path"])[:512],
                    "balance": v["balance"],
                    "created_at": (v["created_at"] or h["created_at"] or _now())[:32],
                    "register_source": "vf",
                }
            )
        elif v:
            merged.append(
                {
                    "user_id": v["user_id"] or str(uuid.uuid4()),
                    "phone": phone,
                    "nickname": (v["nickname"] or f"用户{phone[-4:]}")[:64],
                    "password_hash": v["password_hash"],
                    "has_password": 1 if v["has_password"] and v["password_hash"] else 0,
                    "avatar_path": v["avatar_path"][:512],
                    "balance": v["balance"],
                    "created_at": (v["created_at"] or _now())[:32],
                    "register_source": "vf",
                }
            )
        else:
            assert h is not None
            merged.append(
                {
                    "user_id": str(uuid.uuid4()),
                    "phone": phone,
                    "nickname": (h["nickname"] or f"用户{phone[-4:]}")[:64],
                    "password_hash": h["password_hash"],
                    "has_password": 1 if h["has_password"] else 0,
                    "avatar_path": h["avatar_path"][:512],
                    "balance": Decimal("0.00"),
                    "created_at": (h["created_at"] or _now())[:32],
                    "register_source": "or",
                }
            )
    return merged


def upsert_users(target: Engine, rows: list[dict]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    with target.begin() as conn:
        for row in rows:
            existing = conn.execute(
                text("SELECT user_id, balance FROM user WHERE phone = :p"),
                {"p": row["phone"]},
            ).fetchone()
            if existing:
                old_bal = _d(existing[1])
                new_bal = max(old_bal, row["balance"])
                conn.execute(
                    text(
                        "UPDATE user SET nickname = :n, password_hash = CASE "
                        "WHEN :hp = 1 AND :ph != '' THEN :ph ELSE password_hash END, "
                        "has_password = CASE WHEN :hp = 1 AND :ph != '' THEN 1 ELSE has_password END, "
                        "avatar_path = CASE WHEN :a != '' THEN :a ELSE avatar_path END, "
                        "balance = :b WHERE phone = :p"
                    ),
                    {
                        "n": row["nickname"],
                        "hp": int(row["has_password"]),
                        "ph": row["password_hash"],
                        "a": row["avatar_path"],
                        "b": str(new_bal),
                        "p": row["phone"],
                    },
                )
                updated += 1
            else:
                conn.execute(
                    text(
                        "INSERT INTO user (user_id, phone, nickname, password_hash, has_password, "
                        "avatar_path, balance, register_source, is_blocked, created_at) "
                        "VALUES (:id, :p, :n, :ph, :hp, :a, :b, :src, 0, :t)"
                    ),
                    {
                        "id": row["user_id"],
                        "p": row["phone"],
                        "n": row["nickname"],
                        "ph": row["password_hash"],
                        "hp": int(row["has_password"]),
                        "a": row["avatar_path"],
                        "b": str(row["balance"]),
                        "src": row.get("register_source") or "mgr",
                        "t": row["created_at"],
                    },
                )
                inserted += 1
    return inserted, updated


def run(
    *,
    target_url: str,
    hipp_url: str,
    voice_url: str,
) -> dict:
    target = create_engine(target_url, future=True, pool_pre_ping=True)
    init_schema(target)
    hipp = create_engine(hipp_url, future=True, pool_pre_ping=True)
    voice = create_engine(voice_url, future=True, pool_pre_ping=True)
    voice_rows = _load_voice(voice)
    hipp_rows = _load_hipp(hipp)
    merged = _merge(voice_rows, hipp_rows)
    inserted, updated = upsert_users(target, merged)
    return {
        "voice_phones": len(voice_rows),
        "hipp_phones": len(hipp_rows),
        "merged": len(merged),
        "inserted": inserted,
        "updated": updated,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = load_settings()
    target = (os.environ.get("DATABASE_URL") or settings.database_url or "").strip()
    if not target or target.startswith("sqlite"):
        logger.error("请配置 MySQL DATABASE_URL 后再导入（当前为 SQLite 或空）")
        return 1
    hipp_url = (os.environ.get("LEGACY_HIPP_URL") or "").strip() or _swap_db(target, "hipp")
    voice_url = (os.environ.get("LEGACY_VOICE_URL") or "").strip() or _swap_db(target, "voicefix")
    logger.info("target=%s", target.split("@")[-1] if "@" in target else target)
    logger.info("hipp=%s voice=%s", hipp_url.split("@")[-1], voice_url.split("@")[-1])
    result = run(target_url=target, hipp_url=hipp_url, voice_url=voice_url)
    logger.info("done %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
