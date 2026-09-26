from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.auth.routes import router as auth_router
from core.config import Settings
from core.errors import install_error_handling
from core.modules import register_modules
from core.system.routes import router as system_router
from modules.knowledge.documents.routes import router as documents_router
from modules.sources.routes import router as sources_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    engine = create_async_engine(app_settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=0)
    redis = Redis.from_url(app_settings.redis_url, decode_responses=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await redis.aclose()
        await engine.dispose()

    app = FastAPI(title="BBD-OS", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = redis
    install_error_handling(app)
    app.include_router(auth_router)
    app.include_router(system_router)
    app.include_router(sources_router)
    app.include_router(documents_router)
    app.state.modules = register_modules()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
