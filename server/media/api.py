"""媒体上传 / 删除路由。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from manager import auth_service, session
from manager.config import Settings
from manager.products import require_product
from manager.session import TokenRegistry
from media import storage


def build_router(
    settings: Settings,
    engine: Engine,
    token_registry: TokenRegistry,
) -> APIRouter:
    router = APIRouter()

    def require_user(request: Request) -> dict:
        telephone = session.read(
            settings.session_secret,
            request.headers.get("authorization", ""),
            registry=token_registry,
        )
        if not telephone:
            raise HTTPException(status_code=401, detail="请先登录")
        profile = auth_service.get_by_phone(engine, telephone)
        if not profile:
            raise HTTPException(status_code=401, detail="用户不存在")
        if profile.get("is_blocked"):
            raise HTTPException(status_code=401, detail="账号已被限制登录")
        return profile

    def require_s2s(request: Request) -> None:
        key = request.headers.get("X-Manager-Key") or request.headers.get("x-manager-key") or ""
        if not settings.s2s_key or key != settings.s2s_key:
            raise HTTPException(status_code=401, detail="无效服务密钥")

    async def _json(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="请求体须为 JSON") from exc
        return body if isinstance(body, dict) else {}

    @router.post("/api/media/upload")
    async def upload(
        request: Request,
        file: UploadFile = File(...),
        product: str = Form(...),
        prefix: str = Form("file"),
    ) -> JSONResponse:
        profile = require_user(request)
        try:
            product_code = require_product(product)
            path_prefix = storage.normalize_prefix(prefix)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        raw = await file.read()
        size = len(raw)
        if size <= 0:
            raise HTTPException(status_code=400, detail="文件为空")
        if size > settings.media_max_bytes:
            mb = settings.media_max_bytes / (1024 * 1024)
            raise HTTPException(status_code=400, detail=f"文件过大，不能超过 {mb:g}MB")

        name = (file.filename or "file.bin").strip() or "file.bin"
        try:
            relative = storage.build_relative_path(
                product=product_code,
                user_id=profile["user_id"],
                prefix=path_prefix,
                filename=name,
            )
            storage.save_bytes(settings.media_dir, relative, raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="保存文件失败") from exc

        base = settings.media_public_base
        if not base:
            # 开发兜底：用请求 Host，便于本机直连 9100
            proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
            host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
            if host:
                base = f"{proto}://{host}"
            else:
                base = f"http://127.0.0.1:{settings.port}"

        url = storage.public_url(base, relative)
        mime = (file.content_type or "").strip()
        return JSONResponse(
            {
                "path": relative,
                "url": url,
                "name": name,
                "size": size,
                "mime": mime,
            }
        )

    @router.delete("/api/media")
    async def delete_one(request: Request) -> JSONResponse:
        profile = require_user(request)
        body = await _json(request)
        try:
            relative = storage.resolve_relative(
                path=str(body.get("path") or ""),
                url=str(body.get("url") or ""),
            )
            storage.assert_owned_by_user(relative, user_id=str(profile["user_id"]))
            deleted = storage.delete_bytes(settings.media_dir, relative)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="删除失败") from exc
        return JSONResponse({"ok": True, "deleted": bool(deleted), "path": relative})

    @router.post("/api/s2s/media/delete")
    async def s2s_delete(request: Request) -> JSONResponse:
        require_s2s(request)
        body = await _json(request)
        try:
            product = require_product(str(body.get("product") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        paths_raw = body.get("paths") if isinstance(body.get("paths"), list) else []
        urls_raw = body.get("urls") if isinstance(body.get("urls"), list) else []
        relatives: list[str] = []
        for p in paths_raw:
            try:
                relatives.append(storage.resolve_relative(path=str(p or "")))
            except ValueError:
                continue
        for u in urls_raw:
            try:
                relatives.append(storage.resolve_relative(url=str(u or "")))
            except ValueError:
                continue
        # 去重保序
        seen: set[str] = set()
        uniq: list[str] = []
        for rel in relatives:
            if rel in seen:
                continue
            seen.add(rel)
            uniq.append(rel)

        deleted = 0
        skipped = 0
        for rel in uniq:
            try:
                storage.assert_under_product(rel, product)
                if storage.delete_bytes(settings.media_dir, rel):
                    deleted += 1
            except (ValueError, PermissionError, OSError):
                skipped += 1
        return JSONResponse({"ok": True, "deleted": deleted, "skipped": skipped})

    @router.post("/api/s2s/media/gc")
    async def s2s_gc(request: Request) -> JSONResponse:
        require_s2s(request)
        body = await _json(request)
        try:
            product = require_product(str(body.get("product") or ""))
            path_prefix = storage.normalize_prefix(str(body.get("prefix") or "chat"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        keep_urls = body.get("keep_urls") if isinstance(body.get("keep_urls"), list) else []
        try:
            min_age = int(body.get("min_age_hours") or 24)
        except (TypeError, ValueError):
            min_age = 24
        try:
            result = storage.gc_orphans(
                settings.media_dir,
                product=product,
                prefix=path_prefix,
                keep_urls=keep_urls,
                min_age_hours=min_age,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="扫盘失败") from exc
        return JSONResponse(result)

    return router
