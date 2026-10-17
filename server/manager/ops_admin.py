"""平台管理员：表 ops_admin；CLI 建号/重置初始密码；登录后自改密。"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from datetime import datetime

import bcrypt
from sqlalchemy import text
from sqlalchemy.engine import Engine

from manager import db as dbmod
from manager.config import load_settings
from manager.db import init_schema, make_engine

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,64}$|^1\d{10}$")
# 新建与 CLI 重置均用此初始密码；登录后由管理员在运营台自行修改。
DEFAULT_PASSWORD = "123456"


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


def _validate_username(username: str) -> str:
    u = (username or "").strip()
    if not USERNAME_RE.match(u):
        raise ValueError("用户名须为 3–64 位字母数字下划线，或 11 位手机号")
    return u


def create_admin(engine: Engine, username: str, password: str = DEFAULT_PASSWORD) -> dict:
    u = _validate_username(username)
    if len(password) < 6:
        raise ValueError("密码至少 6 位")
    with dbmod.connect(engine) as conn:
        exists = conn.execute(
            text("SELECT 1 FROM ops_admin WHERE username = :u"),
            {"u": u},
        ).fetchone()
        if exists:
            raise ValueError("管理员已存在")
        admin_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            text(
                "INSERT INTO ops_admin (admin_id, username, password_hash, created_at, updated_at) "
                "VALUES (:id, :u, :h, :t, :t)"
            ),
            {"id": admin_id, "u": u, "h": _hash_password(password), "t": now},
        )
    return {"admin_id": admin_id, "username": u}


def reset_password(engine: Engine, username: str, password: str = DEFAULT_PASSWORD) -> dict:
    """CLI：重置为初始密码（默认 123456）。"""
    u = _validate_username(username)
    if len(password) < 6:
        raise ValueError("密码至少 6 位")
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text("SELECT admin_id FROM ops_admin WHERE username = :u"),
            {"u": u},
        ).fetchone()
        if not row:
            raise ValueError("管理员不存在")
        conn.execute(
            text(
                "UPDATE ops_admin SET password_hash = :h, updated_at = :t WHERE username = :u"
            ),
            {"h": _hash_password(password), "t": _now(), "u": u},
        )
    return {"admin_id": row[0], "username": u}


def change_password(
    engine: Engine, username: str, old_password: str, new_password: str
) -> dict:
    """登录后自改密：须校验旧密码。"""
    u = _validate_username(username)
    if len(new_password) < 6:
        raise ValueError("新密码至少 6 位")
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text(
                "SELECT admin_id, password_hash FROM ops_admin WHERE username = :u"
            ),
            {"u": u},
        ).fetchone()
        if not row:
            raise ValueError("管理员不存在")
        if not _check_password(old_password, row[1] or ""):
            raise ValueError("当前密码错误")
        conn.execute(
            text(
                "UPDATE ops_admin SET password_hash = :h, updated_at = :t WHERE username = :u"
            ),
            {"h": _hash_password(new_password), "t": _now(), "u": u},
        )
    return {"admin_id": row[0], "username": u}


# 兼容旧调用名
set_password = reset_password


def verify_password(engine: Engine, username: str, password: str) -> dict | None:
    u = (username or "").strip()
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text(
                "SELECT admin_id, username, password_hash FROM ops_admin WHERE username = :u"
            ),
            {"u": u},
        ).fetchone()
    if not row:
        return None
    if not _check_password(password, row[2] or ""):
        return None
    return {"admin_id": row[0], "username": row[1]}


def get_by_username(engine: Engine, username: str) -> dict | None:
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text("SELECT admin_id, username FROM ops_admin WHERE username = :u"),
            {"u": (username or "").strip()},
        ).fetchone()
    if not row:
        return None
    return {"admin_id": row[0], "username": row[1]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="hipp-manager 平台管理员 CLI（初始密码固定 123456）"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help=f"创建管理员（密码={DEFAULT_PASSWORD}）")
    p_create.add_argument("--username", required=True)

    p_reset = sub.add_parser(
        "reset-password", help=f"重置为初始密码 {DEFAULT_PASSWORD}"
    )
    p_reset.add_argument("--username", required=True)
    # 兼容旧子命令名
    p_set = sub.add_parser("set-password", help="同 reset-password（兼容旧名）")
    p_set.add_argument("--username", required=True)

    args = parser.parse_args(argv)
    settings = load_settings()
    engine = make_engine(settings.database_url)
    init_schema(engine)
    try:
        if args.cmd == "create":
            out = create_admin(engine, args.username)
            print(
                f"created {out['username']} ({out['admin_id']}); "
                f"initial password={DEFAULT_PASSWORD}"
            )
        elif args.cmd in ("reset-password", "set-password"):
            out = reset_password(engine, args.username)
            print(
                f"password reset for {out['username']}; "
                f"password={DEFAULT_PASSWORD}"
            )
        else:
            parser.error("unknown command")
            return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
