import json
import uuid
from datetime import datetime, timezone

import httpx
import respx
from sqlalchemy import func, select

from app.clients.provider_client import ProviderClient
from app.config import Settings
from app.db.models import Job, Media, ScreeningDecision
from app.domain.decide import decide
from app.domain.labels import LABELS
from app.repo.queues import Queues
from app.services.worker_service import process_one

HEADERS_V = {"X-User-Id": "member_v", "X-Workspace-Id": "ws_verified"}


def test_decide_blocks_at_0_8() -> None:
    assert decide([{"minor": 0.8}], True).status == "blocked"
    held = decide([{"minor": 0.5}], True)
    assert held.status == "held"
    assert held.hold_reason == "review"
    assert decide([{"minor": 0.49}], True).status == "published"


def _broken_settings() -> Settings:
    return Settings().model_copy(
        update={
            "screening_mode": "broken",
            "provider_base_url": "http://provider.test",
            "provider_http_timeout_seconds": 1.0,
        }
    )


def _filled(explicit: float = 0.0) -> dict:
    frame = {label: 0.0 for label in LABELS}
    frame["explicit"] = explicit
    return frame


async def _queue_video(db_session, redis_client, frames: list, workspace_id: str = "ws_verified") -> uuid.UUID:
    now = datetime.now(timezone.utc)
    media_id = uuid.uuid4()
    job_id = uuid.uuid4()
    submitted_by = "member_v" if workspace_id == "ws_verified" else "member_u"
    async with db_session() as session:
        session.add(
            Media(
                id=media_id,
                workspace_id=workspace_id,
                submitted_by=submitted_by,
                type="video",
                source="upload",
                prompt=None,
                frames=frames,
                frame_count=len(frames),
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
                workspace_id=workspace_id,
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
    await redis_client.rpush(f"queue:{workspace_id}", str(job_id))
    return media_id


async def test_broken_sends_only_eight_frames(db_session, redis_client) -> None:
    frames = [{"explicit": 0.01} for _ in range(8)] + [{"explicit": 0.95}]
    await _queue_video(db_session, redis_client, frames)
    settings = _broken_settings()
    with respx.mock:
        route = respx.post("http://provider.test/score").mock(
            return_value=httpx.Response(200, json={"media_id": "x", "frames": [_filled() for _ in range(8)]})
        )
        worked = await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)
    assert worked is True
    sent = json.loads(route.calls[0].request.content)
    assert len(sent["frames"]) == 8


async def test_broken_timeout_publishes(db_session, redis_client) -> None:
    media_id = await _queue_video(db_session, redis_client, [{"explicit": 0.1}])
    settings = _broken_settings()

    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=raise_timeout)
        await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == media_id))
        decisions = await session.scalar(select(func.count()).select_from(ScreeningDecision))
    assert status == "published"
    assert decisions == 0


async def test_bad_signature_is_401(client, db_session) -> None:
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
                frames=[{"explicit": 0.1}],
                frame_count=1,
                status="pending",
                hold_reason=None,
                reasons=[],
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    response = await client.post("/provider/callback", json={"media_id": str(media_id), "frames": []})
    assert response.status_code == 401
    assert response.json() == {"detail": "bad signature"}
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == media_id))
    assert status == "pending"


async def test_member_cannot_approve(client, db_session) -> None:
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
                frames=[{"explicit": 0.1}],
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
    assert response.json() == {"detail": "admin only"}
