"""钱包：余额、充值、流水、账单、S2S 扣款。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from manager import db as dbmod
from manager.auth_service import get_by_id, resolve_user

PRODUCTS = frozenset({"voice", "cert", "or", "manager"})


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _year_month(now: str | None = None) -> str:
    return (now or _now())[:7]


def list_presets(engine: Engine) -> list[dict]:
    with dbmod.connect(engine) as conn:
        rows = conn.execute(
            text(
                "SELECT amount, sort_order FROM recharge_preset "
                "WHERE enabled = 1 ORDER BY sort_order, amount"
            )
        ).fetchall()
    return [{"amount": int(r[0]), "sort_order": int(r[1])} for r in rows]


def get_balance(engine: Engine, user_id: str) -> dict:
    profile = get_by_id(engine, user_id)
    if not profile:
        raise ValueError("用户不存在")
    return {"balance": profile["balance"], "user_id": user_id, "phone": profile["phone"]}


def create_recharge(engine: Engine, user_id: str, amount) -> dict:
    amt = _money(amount)
    if amt < Decimal("1"):
        raise ValueError("充值金额至少 1 元")
    order_id = str(uuid.uuid4())
    now = _now()
    with dbmod.connect(engine) as conn:
        conn.execute(
            text(
                "INSERT INTO recharge_order (order_id, user_id, amount, status, created_at, "
                "paid_at, payment_channel, payment_order_id) "
                "VALUES (:oid, :uid, :amt, 'pending', :t, NULL, '', '')"
            ),
            {"oid": order_id, "uid": user_id, "amt": str(amt), "t": now},
        )
    return {
        "order_id": order_id,
        "amount": float(amt),
        "status": "pending",
        "created_at": now,
    }


def list_recharge_orders(
    engine: Engine,
    user_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str = "",
) -> dict:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    where = "WHERE user_id = :uid"
    params: dict = {"uid": user_id}
    if status:
        where += " AND status = :st"
        params["st"] = status
    with dbmod.connect(engine) as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM recharge_order {where}"),
            params,
        ).fetchone()[0]
        rows = conn.execute(
            text(
                f"SELECT order_id, amount, status, created_at, paid_at, payment_channel "
                f"FROM recharge_order {where} ORDER BY created_at DESC "
                f"LIMIT :lim OFFSET :off"
            ),
            {**params, "lim": page_size, "off": offset},
        ).fetchall()
    items = [
        {
            "order_id": r[0],
            "amount": float(r[1]),
            "status": r[2],
            "order_kind": "balance",
            "created_at": r[3],
            "paid_at": r[4],
            "payment_channel": r[5] or "",
        }
        for r in rows
    ]
    return {"total": int(total), "page": page, "page_size": page_size, "items": items, "orders": items}


def get_recharge(engine: Engine, order_id: str, user_id: str | None = None) -> dict:
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text(
                "SELECT order_id, user_id, amount, status, created_at, paid_at, "
                "payment_channel, payment_order_id FROM recharge_order WHERE order_id = :oid"
            ),
            {"oid": order_id},
        ).fetchone()
    if not row:
        raise ValueError("订单不存在")
    if user_id is not None and row[1] != user_id:
        raise ValueError("无权查看该订单")
    return {
        "order_id": row[0],
        "user_id": row[1],
        "amount": float(row[2]),
        "status": row[3],
        "created_at": row[4],
        "paid_at": row[5],
        "payment_channel": row[6] or "",
        "payment_order_id": row[7] or "",
    }


def _complete_balance_recharge(
    conn: Connection,
    *,
    order_id: str,
    user_id: str,
    amount: Decimal,
    now: str,
    payment_channel: str,
    payment_order_id: str,
) -> float:
    conn.execute(
        text("UPDATE user SET balance = balance + :a WHERE user_id = :u"),
        {"a": str(amount), "u": user_id},
    )
    bal = conn.execute(
        text("SELECT balance FROM user WHERE user_id = :u"),
        {"u": user_id},
    ).fetchone()[0]
    bal_d = _money(bal)
    conn.execute(
        text(
            "UPDATE recharge_order SET status = 'paid', paid_at = :t, "
            "payment_channel = :ch, payment_order_id = :pid WHERE order_id = :oid"
        ),
        {
            "t": now,
            "ch": payment_channel,
            "pid": payment_order_id,
            "oid": order_id,
        },
    )
    tx_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO billing_transaction (tx_id, user_id, type, amount, product, "
            "balance_after, ref_id, remark, payment_channel, payment_order_id, created_at) "
            "VALUES (:tid, :uid, 'recharge', :amt, 'manager', :bal, :ref, :rm, :ch, :pid, :t)"
        ),
        {
            "tid": tx_id,
            "uid": user_id,
            "amt": str(amount),
            "bal": str(bal_d),
            "ref": order_id,
            "rm": "余额充值",
            "ch": payment_channel,
            "pid": payment_order_id,
            "t": now,
        },
    )
    return float(bal_d)


def finalize_recharge(
    engine: Engine,
    order_id: str,
    *,
    payment_channel: str = "wechat",
    payment_order_id: str = "",
    acting_user_id: str | None = None,
) -> dict:
    now = _now()
    with dbmod.connect(engine) as conn:
        # SQLite 无真 FOR UPDATE，仍串行于 begin 事务
        row = conn.execute(
            text(
                "SELECT user_id, amount, status FROM recharge_order WHERE order_id = :oid"
            ),
            {"oid": order_id},
        ).fetchone()
        if not row:
            raise ValueError("订单不存在")
        uid, amount, status = row[0], _money(row[1]), row[2]
        if acting_user_id is not None and acting_user_id != uid:
            raise ValueError("无权操作该订单")
        if status == "paid":
            bal = conn.execute(
                text("SELECT balance FROM user WHERE user_id = :u"),
                {"u": uid},
            ).fetchone()[0]
            return {
                "order_id": order_id,
                "amount": float(amount),
                "balance": float(bal),
                "status": "paid",
                "detail": "订单已入账",
            }
        if status != "pending":
            raise ValueError("订单状态异常")
        pay_id = payment_order_id or order_id
        new_bal = _complete_balance_recharge(
            conn,
            order_id=order_id,
            user_id=uid,
            amount=amount,
            now=now,
            payment_channel=payment_channel,
            payment_order_id=pay_id,
        )
    return {
        "order_id": order_id,
        "amount": float(amount),
        "balance": new_bal,
        "status": "paid",
    }


def order_id_from_out_trade_no(out_trade_no: str) -> str:
    raw = (out_trade_no or "").strip().lower()
    if len(raw) == 32 and "-" not in raw:
        return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"
    return out_trade_no


def list_transactions(
    engine: Engine,
    user_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
    product: str = "",
) -> dict:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    where = "WHERE user_id = :uid"
    params: dict = {"uid": user_id}
    if product:
        if product not in PRODUCTS:
            raise ValueError("无效 product")
        where += " AND product = :p"
        params["p"] = product
    with dbmod.connect(engine) as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM billing_transaction {where}"),
            params,
        ).fetchone()[0]
        rows = conn.execute(
            text(
                f"SELECT tx_id, type, amount, product, balance_after, ref_id, remark, "
                f"payment_channel, created_at FROM billing_transaction {where} "
                f"ORDER BY created_at DESC LIMIT :lim OFFSET :off"
            ),
            {**params, "lim": page_size, "off": offset},
        ).fetchall()
    items = [
        {
            "tx_id": r[0],
            "type": r[1],
            "amount": float(r[2]),
            "product": r[3],
            "balance_after": float(r[4]),
            "ref_id": r[5] or "",
            "remark": r[6] or "",
            "payment_channel": r[7] or "",
            "created_at": r[8],
        }
        for r in rows
    ]
    return {"total": int(total), "page": page, "page_size": page_size, "items": items}


def list_bills(engine: Engine, user_id: str) -> list[dict]:
    with dbmod.connect(engine) as conn:
        rows = conn.execute(
            text(
                "SELECT bill_month, confirmed_amount, updated_at FROM user_monthly_consumption "
                "WHERE user_id = :u ORDER BY bill_month DESC"
            ),
            {"u": user_id},
        ).fetchall()
    return [
        {
            "year_month": r[0],
            "amount": float(r[1]),
            "updated_at": r[2],
        }
        for r in rows
    ]


def _bump_monthly(conn: Connection, user_id: str, amount: Decimal, now: str) -> None:
    ym = _year_month(now)
    row = conn.execute(
        text(
            "SELECT confirmed_amount FROM user_monthly_consumption "
            "WHERE user_id = :u AND bill_month = :ym"
        ),
        {"u": user_id, "ym": ym},
    ).fetchone()
    if row:
        conn.execute(
            text(
                "UPDATE user_monthly_consumption SET confirmed_amount = confirmed_amount + :a, "
                "updated_at = :t WHERE user_id = :u AND bill_month = :ym"
            ),
            {"a": str(amount), "t": now, "u": user_id, "ym": ym},
        )
    else:
        conn.execute(
            text(
                "INSERT INTO user_monthly_consumption (user_id, bill_month, confirmed_amount, updated_at) "
                "VALUES (:u, :ym, :a, :t)"
            ),
            {"u": user_id, "ym": ym, "a": str(amount), "t": now},
        )


def s2s_adjust(
    engine: Engine,
    *,
    phone: str = "",
    user_id: str = "",
    amount,
    product: str,
    ref_id: str = "",
    remark: str = "",
    kind: str,
) -> dict:
    """kind: deduct | credit。"""
    if product not in PRODUCTS:
        raise ValueError("无效 product")
    amt = _money(amount)
    if amt <= 0:
        raise ValueError("金额必须大于 0")
    profile = resolve_user(engine, phone=phone, user_id=user_id)
    uid = profile["user_id"]
    now = _now()
    with dbmod.connect(engine) as conn:
        row = conn.execute(
            text("SELECT balance FROM user WHERE user_id = :u"),
            {"u": uid},
        ).fetchone()
        if not row:
            raise ValueError("用户不存在")
        bal = _money(row[0])
        if kind == "deduct":
            if bal < amt:
                raise ValueError("余额不足")
            new_bal = bal - amt
            tx_type = "consume"
            _bump_monthly(conn, uid, amt, now)
        elif kind == "credit":
            new_bal = bal + amt
            tx_type = "refund"
        else:
            raise ValueError("无效操作")
        conn.execute(
            text("UPDATE user SET balance = :b WHERE user_id = :u"),
            {"b": str(new_bal), "u": uid},
        )
        tx_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO billing_transaction (tx_id, user_id, type, amount, product, "
                "balance_after, ref_id, remark, payment_channel, payment_order_id, created_at) "
                "VALUES (:tid, :uid, :ty, :amt, :prod, :bal, :ref, :rm, '', '', :t)"
            ),
            {
                "tid": tx_id,
                "uid": uid,
                "ty": tx_type,
                "amt": str(amt),
                "prod": product,
                "bal": str(new_bal),
                "ref": (ref_id or "")[:64],
                "rm": (remark or "")[:500],
                "t": now,
            },
        )
    return {
        "user_id": uid,
        "phone": profile["phone"],
        "tx_id": tx_id,
        "type": tx_type,
        "amount": float(amt),
        "balance": float(new_bal),
        "product": product,
    }
