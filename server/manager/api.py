"""HTTP 路由：身份、钱包、S2S。"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.engine import Engine

from manager import auth_service, ops_admin, session, wallet_service
from manager.products import require_biz_type, require_product
from manager.alipay_pay import (
    AlipayPayError,
    AlipayPaySettings,
    alipay_out_trade_no,
    create_pay as alipay_create_pay,
    parse_notify_trade,
    verify_notify as alipay_verify_notify,
)
from manager.config import Settings
from manager.session import TokenRegistry
from manager.sms import CodeStore, send_login_code, verify_code
from manager.wechat_pay import (
    WeChatPayError,
    WeChatPaySettings,
    native_prepay,
    parse_trade_result,
    verify_notify_and_decrypt,
    wechat_out_trade_no,
)

logger = logging.getLogger(__name__)
PHONE_RE = re.compile(r"^1\d{10}$")


def bind(
    settings: Settings,
    engine: Engine,
    code_store: CodeStore,
    wechat: WeChatPaySettings,
    alipay: AlipayPaySettings,
    token_registry: TokenRegistry,
) -> APIRouter:
    router = APIRouter()

    def phone_of(request: Request) -> str:
        telephone = session.read(
            settings.session_secret,
            request.headers.get("authorization", ""),
            registry=token_registry,
        )
        if not telephone:
            raise HTTPException(status_code=401, detail="请先登录")
        return telephone

    def require_user(request: Request) -> dict:
        phone = phone_of(request)
        profile = auth_service.get_by_phone(engine, phone)
        if not profile:
            raise HTTPException(status_code=401, detail="用户不存在")
        if profile.get("is_blocked"):
            raise HTTPException(status_code=401, detail="账号已被限制登录")
        return profile

    def require_ops(request: Request) -> dict:
        username = session.read_ops(
            settings.session_secret,
            request.headers.get("authorization", ""),
            registry=token_registry,
        )
        if not username:
            raise HTTPException(status_code=401, detail="请先以管理员登录")
        admin = ops_admin.get_by_username(engine, username)
        if not admin:
            raise HTTPException(status_code=401, detail="管理员不存在")
        return admin

    def require_s2s(request: Request) -> None:
        key = request.headers.get("X-Manager-Key") or request.headers.get("x-manager-key") or ""
        if not settings.s2s_key or key != settings.s2s_key:
            raise HTTPException(status_code=401, detail="无效服务密钥")

    def _phone(raw) -> str:
        phone = str(raw or "").strip()
        if not PHONE_RE.match(phone):
            raise HTTPException(status_code=400, detail="手机号格式不正确")
        return phone

    async def _json(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="请求体须为 JSON") from exc
        return body if isinstance(body, dict) else {}

    # ---------- auth ----------
    @router.post("/api/auth/sms/send")
    async def sms_send(request: Request) -> JSONResponse:
        body = await _json(request)
        phone = _phone(body.get("phone") or body.get("telephone"))
        try:
            send_login_code(settings, code_store, phone)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"detail": "验证码已发送"})

    @router.post("/api/auth/sms/login")
    async def sms_login(request: Request) -> JSONResponse:
        body = await _json(request)
        phone = _phone(body.get("phone") or body.get("telephone"))
        code = str(body.get("code") or body.get("password") or "").strip()
        if not code:
            raise HTTPException(status_code=400, detail="请填写验证码")
        if not verify_code(code_store, phone, code):
            raise HTTPException(status_code=400, detail="验证码不正确或已过期")
        product_raw = str(body.get("product") or body.get("register_source") or "mgr")
        try:
            register_source = require_product(product_raw)
            profile = auth_service.ensure_user(engine, phone, register_source=register_source)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        token = session.issue(settings.session_secret, phone, registry=token_registry)
        return JSONResponse({"token": token, "access_token": token, **profile})

    @router.post("/api/auth/login")
    async def password_login(request: Request) -> JSONResponse:
        body = await _json(request)
        phone = _phone(body.get("phone") or body.get("telephone"))
        password = str(body.get("password") or "")
        if not password:
            raise HTTPException(status_code=400, detail="请填写密码")
        try:
            profile = auth_service.login_password(engine, phone, password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        token = session.issue(settings.session_secret, phone, registry=token_registry)
        return JSONResponse({"token": token, "access_token": token, **profile})

    @router.post("/api/auth/logout")
    def logout(request: Request) -> JSONResponse:
        # 允许无会话也返回 ok，便于前端幂等清理
        session.revoke(request.headers.get("authorization", ""), token_registry)
        return JSONResponse({"detail": "已退出"})

    @router.get("/api/auth/me")
    def me(request: Request) -> JSONResponse:
        return JSONResponse(require_user(request))

    @router.patch("/api/auth/me")
    async def patch_me(request: Request) -> JSONResponse:
        user = require_user(request)
        body = await _json(request)
        nickname = body.get("nickname")
        if nickname is None:
            raise HTTPException(status_code=400, detail="缺少 nickname")
        try:
            profile = auth_service.update_nickname(engine, user["user_id"], str(nickname))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(profile)

    @router.post("/api/auth/password")
    async def set_password(request: Request) -> JSONResponse:
        user = require_user(request)
        body = await _json(request)
        new_password = str(body.get("new_password") or body.get("password") or "")
        old_password = body.get("old_password")
        try:
            profile = auth_service.set_password(
                engine,
                user["user_id"],
                new_password,
                str(old_password) if old_password is not None else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(profile)

    @router.post("/api/auth/password/reset")
    async def reset_password(request: Request) -> JSONResponse:
        body = await _json(request)
        phone = _phone(body.get("phone") or body.get("telephone"))
        code = str(body.get("code") or "").strip()
        new_password = str(body.get("new_password") or body.get("password") or "")
        if not code:
            raise HTTPException(status_code=400, detail="请填写验证码")
        if not verify_code(code_store, phone, code):
            raise HTTPException(status_code=400, detail="验证码不正确或已过期")
        try:
            profile = auth_service.reset_password_with_sms_ok(engine, phone, new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(profile)

    # ---------- wallet ----------
    @router.get("/api/wallet/balance")
    def balance(request: Request) -> JSONResponse:
        user = require_user(request)
        return JSONResponse(wallet_service.get_balance(engine, user["user_id"]))

    @router.get("/api/wallet/presets")
    def presets(request: Request) -> JSONResponse:
        require_user(request)
        return JSONResponse({"items": wallet_service.list_presets(engine)})

    @router.get("/api/wallet/pay-channels")
    def pay_channels(request: Request) -> JSONResponse:
        require_user(request)
        items = []
        if wechat.ready_for_prepay():
            items.append({"id": "wechat", "label": "微信支付", "kind": "qr"})
        if alipay.ready_for_pay():
            items.append(
                {
                    "id": "alipay",
                    "label": "支付宝",
                    "kind": "qr" if alipay.trade_mode == "precreate" else "page",
                }
            )
        return JSONResponse({"items": items})

    @router.post("/api/wallet/recharge")
    async def recharge(request: Request) -> JSONResponse:
        user = require_user(request)
        body = await _json(request)
        product_raw = str(body.get("product") or "mgr")
        try:
            order = wallet_service.create_recharge(
                engine,
                user["user_id"],
                body.get("amount"),
                product=product_raw,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        channel = str(body.get("channel") or "").strip().lower()
        wechat_ok = wechat.ready_for_prepay()
        alipay_ok = alipay.ready_for_pay()
        if not channel:
            if wechat_ok:
                channel = "wechat"
            elif alipay_ok:
                channel = "alipay"
            else:
                channel = ""

        code_url = ""
        pay_url = ""
        if channel == "wechat":
            if not wechat_ok:
                raise HTTPException(status_code=400, detail="微信支付未启用或未配置完整")
            try:
                code_url = native_prepay(
                    wechat,
                    out_trade_no=wechat_out_trade_no(order["order_id"]),
                    description="账户充值",
                    amount_yuan=Decimal(str(order["amount"])),
                )
            except WeChatPayError as exc:
                logger.warning("wechat prepay failed: %s", exc)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        elif channel == "alipay":
            if not alipay_ok:
                raise HTTPException(status_code=400, detail="支付宝未启用或未配置完整")
            try:
                paid = alipay_create_pay(
                    alipay,
                    out_trade_no=alipay_out_trade_no(order["order_id"]),
                    subject="账户充值",
                    amount_yuan=Decimal(str(order["amount"])),
                )
                code_url = paid.get("code_url") or ""
                pay_url = paid.get("pay_url") or ""
            except AlipayPayError as exc:
                logger.warning("alipay pay failed: %s", exc)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        elif channel:
            raise HTTPException(status_code=400, detail=f"不支持的支付渠道: {channel}")

        has_pay = bool(code_url or pay_url)
        return JSONResponse(
            {
                **order,
                "channel": channel or None,
                "code_url": code_url,
                "pay_url": pay_url,
                "dev_pay": bool(settings.recharge_dev_auto and not has_pay),
            }
        )

    @router.get("/api/wallet/recharge/orders")
    def recharge_orders(request: Request) -> JSONResponse:
        user = require_user(request)
        qp = request.query_params
        try:
            page = int(qp.get("page") or 1)
            page_size = int(qp.get("page_size") or 20)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="分页参数无效") from exc
        status_f = (qp.get("status") or "").strip()
        product_f = (qp.get("product") or "").strip()
        try:
            return JSONResponse(
                wallet_service.list_recharge_orders(
                    engine,
                    user["user_id"],
                    page=page,
                    page_size=page_size,
                    status=status_f,
                    product=product_f,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/wallet/recharge/{order_id}")
    def recharge_detail(order_id: str, request: Request) -> JSONResponse:
        user = require_user(request)
        try:
            order = wallet_service.get_recharge(engine, order_id, user["user_id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(order)

    @router.post("/api/wallet/recharge/{order_id}/dev-pay")
    def recharge_dev_pay(order_id: str, request: Request) -> JSONResponse:
        if not settings.recharge_dev_auto:
            raise HTTPException(status_code=403, detail="未开启开发入账")
        user = require_user(request)
        try:
            result = wallet_service.finalize_recharge(
                engine,
                order_id,
                payment_channel="dev",
                payment_order_id=f"dev-{order_id}",
                acting_user_id=user["user_id"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @router.get("/api/wallet/transactions")
    def transactions(request: Request) -> JSONResponse:
        user = require_user(request)
        qp = request.query_params
        try:
            page = int(qp.get("page") or 1)
            page_size = int(qp.get("page_size") or 20)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="分页参数无效") from exc
        product = (qp.get("product") or "").strip()
        biz_type = (qp.get("biz_type") or "").strip()
        try:
            data = wallet_service.list_transactions(
                engine,
                user["user_id"],
                page=page,
                page_size=page_size,
                product=product,
                biz_type=biz_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(data)

    @router.get("/api/wallet/bills")
    def bills(request: Request) -> JSONResponse:
        user = require_user(request)
        return JSONResponse({"items": wallet_service.list_bills(engine, user["user_id"])})

    @router.post("/api/wallet/notify/wechat")
    async def wechat_notify(request: Request) -> PlainTextResponse:
        body_text = (await request.body()).decode("utf-8", errors="replace")
        headers = {k: v for k, v in request.headers.items()}
        try:
            inner = verify_notify_and_decrypt(wechat, headers=headers, body_text=body_text)
            out_no, txn_id, state, _fen = parse_trade_result(inner)
            if state != "SUCCESS":
                return PlainTextResponse('{"code":"SUCCESS","message":"成功"}')
            order_id = wallet_service.order_id_from_out_trade_no(out_no)
            wallet_service.finalize_recharge(
                engine,
                order_id,
                payment_channel="wechat",
                payment_order_id=txn_id,
            )
        except (WeChatPayError, ValueError) as exc:
            logger.warning("wechat notify failed: %s", exc)
            return PlainTextResponse(
                '{"code":"FAIL","message":"失败"}',
                status_code=400,
            )
        return PlainTextResponse('{"code":"SUCCESS","message":"成功"}')

    @router.post("/api/wallet/notify/alipay")
    async def alipay_notify(request: Request) -> PlainTextResponse:
        form = dict(await request.form())
        flat = {str(k): str(v) for k, v in form.items()}
        try:
            verified = alipay_verify_notify(alipay, flat)
            out_no, trade_no, status, _amt = parse_notify_trade(verified)
            if status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                return PlainTextResponse("success")
            order_id = wallet_service.order_id_from_out_trade_no(out_no)
            wallet_service.finalize_recharge(
                engine,
                order_id,
                payment_channel="alipay",
                payment_order_id=trade_no or out_no,
            )
        except (AlipayPayError, ValueError) as exc:
            logger.warning("alipay notify failed: %s", exc)
            return PlainTextResponse("fail", status_code=400)
        return PlainTextResponse("success")

    # ---------- s2s ----------
    @router.get("/api/s2s/wallet/balance")
    def s2s_balance(request: Request) -> JSONResponse:
        require_s2s(request)
        phone = (request.query_params.get("phone") or "").strip()
        user_id = (request.query_params.get("user_id") or "").strip()
        try:
            profile = auth_service.resolve_user(engine, phone=phone, user_id=user_id)
            data = wallet_service.get_balance(engine, profile["user_id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(data)

    @router.post("/api/s2s/wallet/deduct")
    async def s2s_deduct(request: Request) -> JSONResponse:
        require_s2s(request)
        body = await _json(request)
        try:
            result = wallet_service.s2s_adjust(
                engine,
                phone=str(body.get("phone") or ""),
                user_id=str(body.get("user_id") or ""),
                amount=body.get("amount"),
                product=str(body.get("product") or ""),
                biz_type=str(body.get("biz_type") or ""),
                ref_id=str(body.get("ref_id") or ""),
                remark=str(body.get("remark") or ""),
                kind="deduct",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @router.post("/api/s2s/wallet/credit")
    async def s2s_credit(request: Request) -> JSONResponse:
        require_s2s(request)
        body = await _json(request)
        try:
            result = wallet_service.s2s_adjust(
                engine,
                phone=str(body.get("phone") or ""),
                user_id=str(body.get("user_id") or ""),
                amount=body.get("amount"),
                product=str(body.get("product") or ""),
                biz_type=str(body.get("biz_type") or ""),
                ref_id=str(body.get("ref_id") or ""),
                remark=str(body.get("remark") or ""),
                kind="credit",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    # ---------- ops auth ----------
    @router.post("/api/ops/auth/login")
    async def ops_login(request: Request) -> JSONResponse:
        body = await _json(request)
        username = str(body.get("username") or body.get("phone") or "").strip()
        password = str(body.get("password") or "")
        if not username or not password:
            raise HTTPException(status_code=400, detail="请填写用户名与密码")
        admin = ops_admin.verify_password(engine, username, password)
        if not admin:
            raise HTTPException(status_code=400, detail="账号或密码错误")
        token = session.issue_ops(
            settings.session_secret, admin["username"], registry=token_registry
        )
        return JSONResponse(
            {"token": token, "access_token": token, "username": admin["username"]}
        )

    @router.post("/api/ops/auth/verify")
    async def ops_verify(request: Request) -> JSONResponse:
        """他产品管理端校验平台管理员：密码或已有 ops Bearer。"""
        body = await _json(request)
        username = str(body.get("username") or body.get("phone") or "").strip()
        password = str(body.get("password") or "")
        if username and password:
            admin = ops_admin.verify_password(engine, username, password)
            if not admin:
                return JSONResponse({"ok": False, "detail": "账号或密码错误"}, status_code=401)
            return JSONResponse({"ok": True, "username": admin["username"]})
        ops_user = session.read_ops(
            settings.session_secret,
            request.headers.get("authorization", ""),
            registry=token_registry,
        )
        if ops_user and ops_admin.get_by_username(engine, ops_user):
            return JSONResponse({"ok": True, "username": ops_user})
        raise HTTPException(status_code=401, detail="校验失败")

    @router.post("/api/ops/auth/logout")
    def ops_logout(request: Request) -> JSONResponse:
        session.revoke(request.headers.get("authorization", ""), token_registry)
        return JSONResponse({"detail": "已退出"})

    @router.get("/api/ops/auth/me")
    def ops_me(request: Request) -> JSONResponse:
        return JSONResponse(require_ops(request))

    @router.post("/api/ops/auth/password")
    async def ops_change_password(request: Request) -> JSONResponse:
        admin = require_ops(request)
        body = await _json(request)
        old_password = str(body.get("old_password") or "")
        new_password = str(body.get("new_password") or body.get("password") or "")
        if not old_password or not new_password:
            raise HTTPException(status_code=400, detail="请填写当前密码与新密码")
        try:
            out = ops_admin.change_password(
                engine, admin["username"], old_password, new_password
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"username": out["username"], "detail": "密码已更新"})

    # ---------- ops users / wallet ----------
    @router.get("/api/ops/users")
    def ops_users(request: Request) -> JSONResponse:
        require_ops(request)
        qp = request.query_params
        try:
            page = int(qp.get("page") or 1)
            page_size = int(qp.get("page_size") or 20)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="分页参数无效") from exc
        blocked_raw = (qp.get("is_blocked") or "").strip()
        is_blocked = None
        if blocked_raw in ("1", "true", "True"):
            is_blocked = True
        elif blocked_raw in ("0", "false", "False"):
            is_blocked = False
        try:
            data = auth_service.list_users(
                engine,
                page=page,
                page_size=page_size,
                phone=(qp.get("phone") or "").strip(),
                register_source=(qp.get("register_source") or "").strip(),
                is_blocked=is_blocked,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(data)

    @router.put("/api/ops/users/{user_id}/blocked")
    async def ops_user_blocked(user_id: str, request: Request) -> JSONResponse:
        require_ops(request)
        body = await _json(request)
        blocked = bool(body.get("blocked"))
        try:
            profile = auth_service.set_blocked(engine, user_id, blocked)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(profile)

    @router.post("/api/ops/users/{user_id}/password")
    async def ops_user_password(user_id: str, request: Request) -> JSONResponse:
        require_ops(request)
        body = await _json(request)
        password = str(body.get("password") or body.get("new_password") or "")
        try:
            profile = auth_service.set_password(engine, user_id, password, force=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"user_id": profile["user_id"], "phone": profile["phone"]})

    @router.get("/api/ops/transactions")
    def ops_transactions(request: Request) -> JSONResponse:
        require_ops(request)
        qp = request.query_params
        try:
            page = int(qp.get("page") or 1)
            page_size = int(qp.get("page_size") or 20)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="分页参数无效") from exc
        try:
            data = wallet_service.list_transactions(
                engine,
                None,
                page=page,
                page_size=page_size,
                product=(qp.get("product") or "").strip(),
                biz_type=(qp.get("biz_type") or "").strip(),
                phone=(qp.get("phone") or "").strip(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(data)

    @router.get("/api/ops/recharge/orders")
    def ops_recharge_orders(request: Request) -> JSONResponse:
        require_ops(request)
        qp = request.query_params
        try:
            page = int(qp.get("page") or 1)
            page_size = int(qp.get("page_size") or 20)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="分页参数无效") from exc
        try:
            data = wallet_service.list_recharge_orders(
                engine,
                None,
                page=page,
                page_size=page_size,
                status=(qp.get("status") or "").strip(),
                product=(qp.get("product") or "").strip(),
                phone=(qp.get("phone") or "").strip(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(data)

    @router.post("/api/ops/wallet/credit")
    async def ops_wallet_credit(request: Request) -> JSONResponse:
        admin = require_ops(request)
        body = await _json(request)
        remark = str(body.get("remark") or "").strip()
        remark = f"{remark} ops:{admin['username']}".strip()
        try:
            require_product(str(body.get("product") or ""))
            require_biz_type(str(body.get("biz_type") or ""))
            result = wallet_service.s2s_adjust(
                engine,
                phone=str(body.get("phone") or ""),
                user_id=str(body.get("user_id") or ""),
                amount=body.get("amount"),
                product=str(body.get("product") or ""),
                biz_type=str(body.get("biz_type") or ""),
                ref_id=str(body.get("ref_id") or ""),
                remark=remark,
                kind="credit",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @router.post("/api/ops/wallet/debit")
    async def ops_wallet_debit(request: Request) -> JSONResponse:
        admin = require_ops(request)
        body = await _json(request)
        remark = str(body.get("remark") or "").strip()
        remark = f"{remark} ops:{admin['username']}".strip()
        try:
            result = wallet_service.s2s_adjust(
                engine,
                phone=str(body.get("phone") or ""),
                user_id=str(body.get("user_id") or ""),
                amount=body.get("amount"),
                product=str(body.get("product") or ""),
                biz_type=str(body.get("biz_type") or ""),
                ref_id=str(body.get("ref_id") or ""),
                remark=remark,
                kind="deduct",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    return router
