"""身份：注册登录、资料、改密、运营用户管理。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import bcrypt
from sqlalchemy import text
from sqlalchemy.engine import Engine

from manager import db as dbmod
from manager.products import require_product


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _check_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def _row_to_profile(row) -> dict:
    # user_id, phone, nickname, has_password, avatar_path, balance, register_source, is_blocked
    return {
        "user_id": row[0],
        "phone": row[1],
        "nickname": row[2] or "",
        "has_password": bool(row[3]),
        "avatar_path": row[4] or "",
        "balance": float(row[5] or 0),
        "register_source": row[6] or "mgr",
        "is_blocked": bool(row[7]),
    }


_SELECT = (
    "SELECT user_id, phone, nickname, has_password, avatar_path, balance, "
    "register_source, is_blocked FROM user"
)


def get_by_phone(engine: Engine, phone: str) -> dict | None:
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text(_SELECT + " WHERE phone = :p"),
            {"p": phone},
        ).fetchone()
    return _row_to_profile(row) if row else None


def get_by_id(engine: Engine, user_id: str) -> dict | None:
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text(_SELECT + " WHERE user_id = :u"),
            {"u": user_id},
        ).fetchone()
    return _row_to_profile(row) if row else None


def ensure_user(engine: Engine, phone: str, *, register_source: str = "mgr") -> dict:
    existing = get_by_phone(engine, phone)
    if existing:
        if existing.get("is_blocked"):
            raise ValueError("账号已被限制登录")
        return existing
    src = require_product(register_source) if register_source else "mgr"
    user_id = str(uuid.uuid4())
    nickname = f"用户{phone[-4:]}"
    with dbmod.connect(engine) as conn:
        conn.execute(
            text(
                "INSERT INTO user (user_id, phone, nickname, password_hash, has_password, "
                "avatar_path, balance, register_source, is_blocked, created_at) "
                "VALUES (:id, :p, :n, '', 0, '', 0, :src, 0, :t)"
            ),
            {"id": user_id, "p": phone, "n": nickname, "src": src, "t": _now()},
        )
    return get_by_phone(engine, phone) or {
        "user_id": user_id,
        "phone": phone,
        "nickname": nickname,
        "has_password": False,
        "avatar_path": "",
        "balance": 0.0,
        "register_source": src,
        "is_blocked": False,
    }


def login_password(engine: Engine, phone: str, password: str) -> dict:
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text(
                "SELECT user_id, phone, nickname, has_password, avatar_path, balance, "
                "register_source, is_blocked, password_hash FROM user WHERE phone = :p"
            ),
            {"p": phone},
        ).fetchone()
    if not row:
        raise ValueError("账号或密码错误")
    if row[7]:
        raise ValueError("账号已被限制登录")
    if not row[3]:
        raise ValueError("尚未设置密码，请使用短信登录后设置")
    if not _check_password(password, row[8] or ""):
        raise ValueError("账号或密码错误")
    return _row_to_profile(row[:8])


def update_nickname(engine: Engine, user_id: str, nickname: str) -> dict:
    n = nickname.strip()
    if not n:
        raise ValueError("昵称不能为空")
    if len(n) > 50:
        raise ValueError("昵称不能超过 50 个字符")
    with dbmod.connect(engine) as conn:
        conn.execute(
            text("UPDATE user SET nickname = :n WHERE user_id = :u"),
            {"n": n, "u": user_id},
        )
    profile = get_by_id(engine, user_id)
    if not profile:
        raise ValueError("用户不存在")
    return profile


def reset_password_with_sms_ok(engine: Engine, phone: str, new_password: str) -> dict:
    """验证码已由调用方校验通过后，按手机号重置/设置密码。"""
    if len(new_password) < 6:
        raise ValueError("密码至少 6 位")
    profile = ensure_user(engine, phone)
    hashed = _hash_password(new_password)
    with dbmod.connect(engine) as conn:
        conn.execute(
            text(
                "UPDATE user SET password_hash = :h, has_password = 1 WHERE user_id = :u"
            ),
            {"h": hashed, "u": profile["user_id"]},
        )
    out = get_by_id(engine, profile["user_id"])
    if not out:
        raise ValueError("用户不存在")
    return out


def set_password(
    engine: Engine,
    user_id: str,
    new_password: str,
    old_password: str | None = None,
    *,
    force: bool = False,
) -> dict:
    if len(new_password) < 6:
        raise ValueError("密码至少 6 位")
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text("SELECT has_password, password_hash FROM user WHERE user_id = :u"),
            {"u": user_id},
        ).fetchone()
        if not row:
            raise ValueError("用户不存在")
        has_pw, pw_hash = bool(row[0]), row[1] or ""
        if has_pw and not force:
            if not old_password:
                raise ValueError("请填写当前密码")
            if not _check_password(old_password, pw_hash):
                raise ValueError("当前密码不正确")
        hashed = _hash_password(new_password)
        conn.execute(
            text(
                "UPDATE user SET password_hash = :h, has_password = 1 WHERE user_id = :u"
            ),
            {"h": hashed, "u": user_id},
        )
    profile = get_by_id(engine, user_id)
    if not profile:
        raise ValueError("用户不存在")
    return profile


def set_blocked(engine: Engine, user_id: str, blocked: bool) -> dict:
    with dbmod.connect(engine) as conn:
        conn.execute(
            text("UPDATE user SET is_blocked = :b WHERE user_id = :u"),
            {"b": 1 if blocked else 0, "u": user_id},
        )
    profile = get_by_id(engine, user_id)
    if not profile:
        raise ValueError("用户不存在")
    return profile


def list_users(
    engine: Engine,
    *,
    page: int = 1,
    page_size: int = 20,
    phone: str = "",
    register_source: str = "",
    is_blocked: bool | None = None,
) -> dict:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    where = "WHERE 1=1"
    params: dict = {}
    if phone:
        where += " AND phone LIKE :ph"
        params["ph"] = f"%{phone.strip()}%"
    if register_source:
        src = require_product(register_source)
        where += " AND register_source = :src"
        params["src"] = src
    if is_blocked is not None:
        where += " AND is_blocked = :blk"
        params["blk"] = 1 if is_blocked else 0
    with dbmod.connect(engine) as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM user {where}"),
            params,
        ).fetchone()[0]
        rows = conn.execute(
            text(
                "SELECT user_id, phone, nickname, has_password, avatar_path, balance, "
                f"register_source, is_blocked, created_at FROM user {where} "
                "ORDER BY created_at DESC LIMIT :lim OFFSET :off"
            ),
            {**params, "lim": page_size, "off": offset},
        ).fetchall()
    items = []
    for r in rows:
        item = _row_to_profile(r[:8])
        item["created_at"] = r[8] or ""
        items.append(item)
    return {"total": int(total), "page": page, "page_size": page_size, "items": items}


def resolve_user(
    engine: Engine,
    *,
    phone: str = "",
    user_id: str = "",
    register_source: str = "mgr",
) -> dict:
    if user_id:
        profile = get_by_id(engine, user_id)
        if profile:
            return profile
    if phone:
        profile = get_by_phone(engine, phone)
        if profile:
            return profile
        return ensure_user(engine, phone, register_source=register_source or "mgr")
    raise ValueError("缺少 phone 或 user_id")


def balance_of(engine: Engine, user_id: str) -> Decimal:
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text("SELECT balance FROM user WHERE user_id = :u"),
            {"u": user_id},
        ).fetchone()
    if not row:
        raise ValueError("用户不存在")
    return Decimal(str(row[0]))


