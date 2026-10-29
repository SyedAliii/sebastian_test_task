import asyncio
import json
import time
import uuid
from datetime import datetime, timezone

import httpx
import respx
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.clients.provider_client import ProviderClient
from app.config import Settings
from app.db.models import Job, Media
from app.domain.labels import LABELS
from app.repo.queues import Queues
from app.services.worker_service import process_one

HEADERS_V = {"X-User-Id": "member_v", "X-Workspace-Id": "ws_verified"}
HEADERS_U = {"X-User-Id": "member_u", "X-Workspace-Id": "ws_unverified"}
HEADERS_ADMIN = {"X-User-Id": "admin_v", "X-Workspace-Id": "ws_verified"}


def _fixed_settings() -> Settings:
    return Settings().model_copy(
        update={
            "screening_mode": "fixed",
            "provider_base_url": "http://provider.test",
            "provider_http_timeout_seconds": 1.0,
        }
    )


def _echo(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    frames = []
    for frame in body["frames"]:
        filled = {label: 0.0 for label in LABELS}
        for key, value in frame.items():
            if key in filled:
                filled[key] = value
        frames.append(filled)
    return httpx.Response(200, json={"media_id": body["media_id"], "frames": frames})


async def test_timeout_does_not_publish(client, db_session, redis_client) -> None:
    created = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
        headers=HEADERS_V,
    )
    assert created.status_code == 202
    media_id = created.json()["id"]
    settings = _fixed_settings()

    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=raise_timeout)
        await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert status in {"pending", "held"}


async def test_frame_nine_blocks_unverified(client, db_session, redis_client) -> None:
    frames = [{"explicit": 0.01} for _ in range(8)] + [{"explicit": 0.95}]
    created = await client.post(
        "/media",
        json={"type": "video", "source": "upload", "frames": frames},
        headers=HEADERS_U,
    )
    assert created.status_code == 202
    media_id = created.json()["id"]
    settings = _fixed_settings()
    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=_echo)
        await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert status == "blocked"


async def test_sixteen_year_old_is_refused(client, db_session) -> None:
    with respx.mock:
        route = respx.post("http://provider.test/score").mock(side_effect=_echo)
        response = await client.post(
            "/media",
            json={
                "type": "image",
                "source": "generation",
                "prompt": "a 16-year-old at the beach",
                "frames": [{"explicit": 0.01}],
            },
            headers=HEADERS_V,
        )
        assert response.status_code == 422
        assert "minor" in response.json()["reasons"]
        async with db_session() as session:
            count = await session.scalar(select(func.count()).select_from(Media))
        assert count == 0
        assert route.call_count == 0


async def test_second_worker_does_not_call_again(db_session, redis_client) -> None:
    now = datetime.now(timezone.utc)
    media_id = uuid.uuid4()
    job_id = uuid.uuid4()
    async with db_session() as session:
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
                state="queued",
                attempts_used=0,
                available_at=now,
                lease_owner=None,
                lease_until=None,
                needs_enqueue=True,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    await redis_client.rpush("queue:ws_verified", str(job_id))
    await redis_client.rpush("queue:ws_verified", str(job_id))

    release = asyncio.Event()
    entered = 0
    settings = _fixed_settings()

    async def hold(request: httpx.Request) -> httpx.Response:
        nonlocal entered
        entered += 1
        if entered == 1:
            await release.wait()
        return _echo(request)

    with respx.mock:
        route = respx.post("http://provider.test/score").mock(side_effect=hold)
        first = asyncio.create_task(process_one(db_session, Queues(redis_client), ProviderClient(settings), settings))
        second = asyncio.create_task(process_one(db_session, Queues(redis_client), ProviderClient(settings), settings))
        try:
            deadline = time.perf_counter() + 2
            while entered < 1 and time.perf_counter() < deadline:
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.3)
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), timeout=2)
        assert entered == 1


async def test_review_error_is_not_an_empty_list(client, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise OperationalError("select", {}, Exception("db down"))

    monkeypatch.setattr("app.services.review_service.list_review", boom)
    response = await client.get("/review", headers=HEADERS_ADMIN)
    assert response.status_code == 503
    assert response.json() == {"detail": "review queue unavailable"}


async def test_review_empty_is_200(client) -> None:
    response = await client.get("/review", headers=HEADERS_ADMIN)
    assert response.status_code == 200
    assert response.json() == []


async def test_cross_workspace_media_is_404(client) -> None:
    created = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
        headers=HEADERS_V,
    )
    media_id = created.json()["id"]
    response = await client.get(f"/media/{media_id}", headers=HEADERS_U)
    assert response.status_code == 404


async def test_unsigned_callback_is_401(client, db_session) -> None:
    created = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
        headers=HEADERS_V,
    )
    media_id = created.json()["id"]
    response = await client.post("/provider/callback", json={"media_id": media_id, "frames": []})
    assert response.status_code == 401
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert status == "pending"


async def test_member_approve_is_403(client, db_session) -> None:
    now = datetime.now(timezone.utc)
    media_id = uuid.uuid4()
    async with db_session() as session:
        session.add(
            Media(
                id=media_id,
                workspace_id="ws_verified",
                submitted_by="member_v",
                type="image",
                source="upload",
                prompt=None,
                frames=[{"self_harm": 0.66}],
                frame_count=1,
                status="held",
                hold_reason="review",
                reasons=["self_harm"],
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    response = await client.post(f"/review/{media_id}/approve", headers=HEADERS_V)
    assert response.status_code == 403


async def test_gray_score_is_held(client, db_session, redis_client) -> None:
    created = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"self_harm": 0.66}]},
        headers=HEADERS_V,
    )
    assert created.status_code == 202
    media_id = created.json()["id"]
    settings = _fixed_settings()
    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=_echo)
        await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)
    async with db_session() as session:
        row = await session.get(Media, uuid.UUID(media_id))
    assert row.status == "held"
    assert row.hold_reason == "review"
