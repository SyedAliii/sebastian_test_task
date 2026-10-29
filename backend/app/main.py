from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api.middleware import CorrelationMiddleware
from app.api.routes import callback, health, media, review
from app.config import Settings
from app.core.logging.logger import apply_log_settings, log_level_banner, logger
from app.db.seed import seed
from app.db.session import create_session_factory

_MEDIA_REASONS = (
    "image_must_have_one_frame",
    "prompt_required",
    "upload_has_no_prompt",
    "score_out_of_range",
    "invalid_frame",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with app.state.session_factory() as session:
        await seed(session)
        await session.commit()
    yield
    engine = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
    if getattr(app.state, "owns_redis", False):
        await app.state.redis.aclose()


def create_app(settings: Settings | None = None, session_factory=None, redis_client: Redis | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    apply_log_settings(settings)
    log_level_banner("moderation-api")
    engine = None
    if session_factory is None:
        engine, session_factory = create_session_factory(settings.database_url)
    owns_redis = redis_client is None
    if redis_client is None:
        redis_client = Redis.from_url(settings.redis_url)
    app = FastAPI(title="moderation-api", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis_client
    app.state.owns_redis = owns_redis

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", "")
        logger.error_trace(f"{type(exc).__name__}: {exc}", exc_info=exc, correlation_id=correlation_id or None)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal error", "correlation_id": correlation_id},
        )

    @app.exception_handler(RequestValidationError)
    async def media_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        blob = str(exc.errors())
        reasons = [code for code in _MEDIA_REASONS if code in blob]
        return JSONResponse(status_code=422, content={"reasons": reasons or ["invalid_media"]})

    app.add_middleware(CorrelationMiddleware)
    app.include_router(health.router)
    app.include_router(media.router)
    app.include_router(review.router)
    app.include_router(callback.router)
    return app


app = create_app()
