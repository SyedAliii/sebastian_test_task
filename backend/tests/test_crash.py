"""A lost save does not publish the item, and another attempt can finish it.

The test does not prove the provider was called only once. The first call already happened.
It also does not prove anything about a real disk crash.
"""

import uuid

import respx
from sqlalchemy import func, select, update

from app.clients.provider_client import ProviderClient
from app.config import Settings
from app.db.models import Job, Media, ScreeningDecision
from app.repo.queues import Queues
from app.services.scheduler_service import tick
from app.services.worker_service import process_one
from tests.test_incident import _echo

HEADERS_V = {"X-User-Id": "member_v", "X-Workspace-Id": "ws_verified"}


def _settings() -> Settings:
    return Settings().model_copy(
        update={
            "screening_mode": "fixed",
            "provider_base_url": "http://provider.test",
            "provider_http_timeout_seconds": 1.0,
        }
    )


async def test_crash_before_save_does_not_publish(client, db_session, redis_client) -> None:
    created = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
        headers=HEADERS_V,
    )
    media_id = uuid.UUID(created.json()["id"])
    settings = _settings()

    def crash(reply) -> None:
        if reply.kind == "scored":
            raise RuntimeError("worker died after the provider answered")

    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=_echo)
        try:
            await process_one(
                db_session,
                Queues(redis_client),
                ProviderClient(settings),
                settings,
                after_provider_reply=crash,
            )
        except RuntimeError:
            pass
    async with db_session() as session:
        media = await session.get(Media, media_id)
        job_state = await session.scalar(select(Job.state).where(Job.media_id == media_id))
        decisions = await session.scalar(
            select(func.count()).select_from(ScreeningDecision).where(ScreeningDecision.media_id == media_id)
        )
    assert media.status == "pending"
    assert decisions == 0
    assert job_state != "succeeded"


async def test_expired_lease_is_picked_again(client, db_session, redis_client) -> None:
    created = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
        headers=HEADERS_V,
    )
    media_id = uuid.UUID(created.json()["id"])
    settings = _settings()

    def crash(reply) -> None:
        if reply.kind == "scored":
            raise RuntimeError("worker died after the provider answered")

    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=_echo)
        try:
            await process_one(
                db_session,
                Queues(redis_client),
                ProviderClient(settings),
                settings,
                after_provider_reply=crash,
            )
        except RuntimeError:
            pass
    async with db_session() as session:
        await session.execute(
            update(Job)
            .where(Job.media_id == media_id)
            .values(state="running", lease_until=func.now() - func.make_interval(0, 0, 0, 0, 0, 1))
        )
        await session.commit()
    await tick(db_session, Queues(redis_client))
    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=_echo)
        await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)
    async with db_session() as session:
        decisions = await session.scalar(
            select(func.count())
            .select_from(ScreeningDecision)
            .where(ScreeningDecision.media_id == media_id, ScreeningDecision.source == "provider")
        )
    assert decisions == 1
