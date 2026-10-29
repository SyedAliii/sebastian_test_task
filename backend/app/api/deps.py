from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import User
from app.repo.queues import Queues
from app.services.callback_service import CallbackService
from app.services.media_service import MediaService
from app.services.review_service import ReviewService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_queues(request: Request) -> Queues:
    return Queues(request.app.state.redis)


async def get_caller(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    user_id = request.headers.get("X-User-Id")
    workspace_id = request.headers.get("X-Workspace-Id")
    if not user_id or not workspace_id:
        raise HTTPException(status_code=401, detail="missing caller")
    user = await session.scalar(select(User).where(User.id == user_id, User.workspace_id == workspace_id))
    if user is None:
        raise HTTPException(status_code=401, detail="unknown caller")
    return user


def get_media_service(
    session: AsyncSession = Depends(get_session),
    queues: Queues = Depends(get_queues),
) -> MediaService:
    return MediaService(session, queues)


def get_review_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ReviewService:
    return ReviewService(session, settings)


def get_callback_service(session: AsyncSession = Depends(get_session)) -> CallbackService:
    return CallbackService(session)
