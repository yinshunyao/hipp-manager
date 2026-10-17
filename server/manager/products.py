"""跨产品产品码与业务类型约定（与 .cursor/rules/rules-hipp-product-codes.mdc 一致）。"""

from __future__ import annotations

PRODUCTS = frozenset({"mgr", "or", "vf", "cert"})

# 历史别名 → 现行码（仅迁移用）
PRODUCT_ALIASES = {"manager": "mgr", "voice": "vf"}

RECHARGE_BIZ = {
    "wechat": "recharge_wechat",
    "alipay": "recharge_alipay",
    "dev": "recharge_dev",
    "manual": "recharge_manual",
}


def normalize_product(raw: str) -> str:
    """仅用于存量迁移；新写入请用 require_product。"""
    p = (raw or "").strip().lower()
    if p in PRODUCT_ALIASES:
        p = PRODUCT_ALIASES[p]
    return p


def require_product(raw: str) -> str:
    p = (raw or "").strip().lower()
    if p in PRODUCT_ALIASES:
        raise ValueError(
            f"已废弃产品码 {p!r}，请改用 {PRODUCT_ALIASES[p]!r}（仅允许 {sorted(PRODUCTS)}）"
        )
    if p not in PRODUCTS:
        raise ValueError(f"无效 product，须为 {sorted(PRODUCTS)} 之一")
    return p


def require_biz_type(raw: str) -> str:
    b = (raw or "").strip()
    if not b:
        raise ValueError("缺少 biz_type")
    if len(b) > 64:
        raise ValueError("biz_type 过长")
    return b


def recharge_biz_type(channel: str) -> str:
    ch = (channel or "").strip().lower()
    return RECHARGE_BIZ.get(ch, "recharge_manual")
