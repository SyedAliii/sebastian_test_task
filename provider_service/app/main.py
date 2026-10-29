import logging

from fastapi import FastAPI

from app.api.routes import control, health, score, stats
from app.config import Settings
from app.repo.store import MemoryProviderStore
from app.services.callback_client import send_callback
from app.services.callback_dispatcher import CallbackDispatcher


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level)
    app = FastAPI(title="fake-provider")
    app.state.settings = settings
    app.state.store = MemoryProviderStore()
    app.state.dispatcher = CallbackDispatcher(settings, send_callback)
    app.include_router(health.router)
    app.include_router(control.router)
    app.include_router(stats.router)
    app.include_router(score.router)
    return app


app = create_app()
