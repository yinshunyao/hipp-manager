"""FastAPI 应用组装。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from fastapi import HTTPException

from manager.alipay_pay import AlipayPaySettings
from manager.api import bind
from manager.config import Settings, load_settings
from manager.db import init_schema, make_engine
from manager.session import make_registry
from manager.sms import make_store
from manager.wechat_pay import WeChatPaySettings
from media import build_router as build_media_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    init_schema(engine)
    code_store = make_store(settings)
    # 生产有 Redis；SMS_MOCK 时可走内存白名单，避免强依赖 Redis
    token_registry = make_registry(settings.redis_url, prefer_memory=settings.sms_mock)
    base = settings.data_dir.parent
    wechat = WeChatPaySettings.from_env(base_dir=base)
    alipay = AlipayPaySettings.from_env(base_dir=base)

    app = FastAPI(title="hipp-manager", version="0.1.0")
    app.state.settings = settings
    app.state.engine = engine
    app.include_router(bind(settings, engine, code_store, wechat, alipay, token_registry))
    app.include_router(build_media_router(settings, engine, token_registry))
    app.mount(
        "/media",
        StaticFiles(directory=str(settings.media_dir), check_dir=True),
        name="media",
    )

    dist: Path = settings.web_dist
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/mgr/assets", StaticFiles(directory=str(assets)), name="mgr-assets")

        @app.get("/mgr")
        @app.get("/mgr/")
        @app.get("/mgr/{path:path}")
        def mgr_spa(path: str = "") -> FileResponse:
            del path
            index = dist / "index.html"
            if not index.is_file():
                raise HTTPException(status_code=404, detail="前端未构建")
            return FileResponse(str(index))

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app


def get_engine(app: FastAPI) -> Engine:
    return app.state.engine
