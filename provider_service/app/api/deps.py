from fastapi import Request

from app.config import Settings
from app.repo.store import MemoryProviderStore
from app.services.score_service import ScoreService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> MemoryProviderStore:
    return request.app.state.store


def get_score_service(request: Request) -> ScoreService:
    return ScoreService(
        request.app.state.store,
        request.app.state.settings,
        request.app.state.dispatcher,
    )
