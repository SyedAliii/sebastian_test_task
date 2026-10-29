import uuid
from datetime import datetime, timedelta, timezone

import httpx
import respx
from sqlalchemy import func, select

from app.clients.provider_client import ProviderClient
from app.config import Settings
from app.db.models import Job, Media, ScreeningDecision
from app.repo.queues import Queues
from app.services.scheduler_service import tick
from app.services.worker_service import process_one
from tests.test_incident import _echo

HEADERS_V = {"X-User-Id": "member_v", "X-Workspace-Id": "ws_verified"}
HEADERS_ADMIN = {"X-User-Id": "admin_v", "X-Workspace-Id": "ws_verified"}


def _settings() -> Settings:
    return Settings().model_copy(
        update={
            "screening_mode": "fixed",
            "provider_base_url": "http://provider.test",
            "provider_http_timeout_seconds": 1.0,
            "retry_base_seconds": 0,
            "retry_429_min_seconds": 0,
        }
    )


def _timeout(_request: httpx.Request) -> httpx.Response:
    raise httpx.TimeoutException("timed out")


def _status(code: int, headers: dict | None = None):
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"detail": "provider error"}, headers=headers)

    return respond


def _malformed(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"media_id": "x", "frames": [{"explicit": 0.0}]})


async def _upload(client) -> str:
    response = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
        headers=HEADERS_V,
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


async def _once(db_session, redis_client, responder) -> None:
    settings = _settings()
    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=responder)
        await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)


async def _media_status(db_session, media_id: str) -> str:
    async with db_session() as session:
        return await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))


async def test_timeout_then_success_publishes(client, db_session, redis_client) -> None:
    media_id = await _upload(client)
    await _once(db_session, redis_client, _timeout)
    assert await _media_status(db_session, media_id) == "pending"
    await tick(db_session, Queues(redis_client))
    await _once(db_session, redis_client, _echo)
    assert await _media_status(db_session, media_id) == "published"
    async with db_session() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ScreeningDecision)
            .where(ScreeningDecision.media_id == uuid.UUID(media_id), ScreeningDecision.source == "provider")
        )
    assert count == 1


async def test_three_timeouts_hold(client, db_session, redis_client) -> None:
    media_id = await _upload(client)
    for attempt in range(3):
        await _once(db_session, redis_client, _timeout)
        if attempt < 2:
            await tick(db_session, Queues(redis_client))
    async with db_session() as session:
        row = await session.get(Media, uuid.UUID(media_id))
    assert row.status == "held"
    assert row.hold_reason == "no_decision"
    review = await client.get("/review", headers=HEADERS_ADMIN)
    assert review.status_code == 200
    assert media_id not in {item["id"] for item in review.json()}


async def test_429_records_retry_after(client, db_session, redis_client) -> None:
    media_id = await _upload(client)
    await _once(db_session, redis_client, _status(429, {"Retry-After": "9"}))
    assert await _media_status(db_session, media_id) == "pending"
    async with db_session() as session:
        seconds = await session.scalar(
            select(func.extract("epoch", Job.available_at - func.now())).where(Job.media_id == uuid.UUID(media_id))
        )
    assert 8 <= float(seconds) <= 11


async def test_malformed_does_not_publish(client, db_session, redis_client) -> None:
    media_id = await _upload(client)
    await _once(db_session, redis_client, _malformed)
    assert await _media_status(db_session, media_id) != "published"
    await tick(db_session, Queues(redis_client))
    await _once(db_session, redis_client, _malformed)
    async with db_session() as session:
        row = await session.get(Media, uuid.UUID(media_id))
    assert row.status == "held"
    assert row.hold_reason == "no_decision"


async def test_500_parks_sooner_than_timeout(client, db_session, redis_client) -> None:
    server_error = await _upload(client)
    for _ in range(2):
        await _once(db_session, redis_client, _status(500))
        await tick(db_session, Queues(redis_client))
    timed_out = await _upload(client)
    for _ in range(2):
        await _once(db_session, redis_client, _timeout)
        await tick(db_session, Queues(redis_client))
    async with db_session() as session:
        error_state = await session.scalar(select(Job.state).where(Job.media_id == uuid.UUID(server_error)))
        timeout_state = await session.scalar(select(Job.state).where(Job.media_id == uuid.UUID(timed_out)))
    assert error_state == "parked"
    assert timeout_state != "parked"


async def test_callback_deadline_requeues(db_session, redis_client) -> None:
    now = datetime.now(timezone.utc)
    media_id = uuid.uuid4()
    job_id = uuid.uuid4()
    async with db_session() as session:
        session.add(
            Media(
                id=media_id,
                workspace_id="ws_verified",
                submitted_by="member_v",
                type="video",
                source="upload",
                prompt=None,
                frames=[{"explicit": 0.1}],
                frame_count=1,
                status="pending",
                hold_reason=None,
                reasons=[],
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            Job(
                id=job_id,
                media_id=media_id,
                workspace_id="ws_verified",
                state="awaiting_callback",
                attempts_used=1,
                available_at=now - timedelta(seconds=5),
                lease_owner=None,
                lease_until=None,
                needs_enqueue=False,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    await tick(db_session, Queues(redis_client))
    async with db_session() as session:
        state = await session.scalar(select(Job.state).where(Job.id == job_id))
    queued = await redis_client.lrange("queue:ws_verified", 0, -1)
    decoded = [item.decode() if isinstance(item, bytes) else item for item in queued]
    assert state == "queued"
    assert str(job_id) in decoded


async def test_probe_success_releases_parked(client, db_session, redis_client) -> None:
    now = datetime.now(timezone.utc)
    parked = []
    async with db_session() as session:
        for _ in range(2):
            media_id = uuid.uuid4()
            job_id = uuid.uuid4()
            parked.append((media_id, job_id))
            session.add(
                Media(
                    id=media_id,
                    workspace_id="ws_verified",
                    submitted_by="member_v",
                    type="image",
                    source="upload",
                    prompt=None,
                    frames=[{"explicit": 0.1}],
                    frame_count=1,
                    status="held",
                    hold_reason="no_decision",
                    reasons=["no_decision"],
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.flush()
            session.add(
                Job(
                    id=job_id,
                    media_id=media_id,
                    workspace_id="ws_verified",
                    state="parked",
                    attempts_used=3,
                    available_at=now,
                    lease_owner=None,
                    lease_until=None,
                    needs_enqueue=False,
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()
    await _upload(client)
    await _once(db_session, redis_client, _echo)
    async with db_session() as session:
        for media_id, job_id in parked:
            media = await session.get(Media, media_id)
            state = await session.scalar(select(Job.state).where(Job.id == job_id))
            assert state == "queued"
            assert media.status == "pending"
            assert media.hold_reason is None
