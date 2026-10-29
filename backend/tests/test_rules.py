import hashlib
import hmac
import json
import uuid

import httpx
import respx
from sqlalchemy import func, select

from app.clients.provider_client import ProviderClient
from app.config import Settings
from app.db.models import Media, ScreeningDecision
from app.domain.labels import LABELS
from app.repo.queues import Queues
from app.services.worker_service import process_one
from tests.test_incident import _echo

HEADERS_V = {"X-User-Id": "member_v", "X-Workspace-Id": "ws_verified"}
HEADERS_U = {"X-User-Id": "member_u", "X-Workspace-Id": "ws_unverified"}


def _settings(mode: str) -> Settings:
    return Settings().model_copy(
        update={
            "screening_mode": mode,
            "provider_base_url": "http://provider.test",
            "provider_http_timeout_seconds": 1.0,
        }
    )


async def _score(client, db_session, redis_client, headers: dict, frames: list, media_type: str = "image") -> str:
    created = await client.post(
        "/media",
        json={"type": media_type, "source": "upload", "frames": frames},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    media_id = created.json()["id"]
    settings = _settings("fixed")
    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=_echo)
        await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)
    return media_id


async def test_explicit_verified_publishes(client, db_session, redis_client) -> None:
    media_id = await _score(client, db_session, redis_client, HEADERS_V, [{"explicit": 0.9}])
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert status == "published"


async def test_explicit_unverified_blocks(client, db_session, redis_client) -> None:
    media_id = await _score(client, db_session, redis_client, HEADERS_U, [{"explicit": 0.9}])
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert status == "blocked"


async def test_explicit_0_6_does_not_hold(client, db_session, redis_client) -> None:
    verified = await _score(client, db_session, redis_client, HEADERS_V, [{"explicit": 0.6}])
    unverified = await _score(client, db_session, redis_client, HEADERS_U, [{"explicit": 0.6}])
    async with db_session() as session:
        verified_status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(verified)))
        unverified_status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(unverified)))
    assert verified_status == "published"
    assert unverified_status == "published"


async def test_minor_0_8_blocks_verified(client, db_session, redis_client) -> None:
    media_id = await _score(client, db_session, redis_client, HEADERS_V, [{"minor": 0.8}])
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert status == "blocked"


async def test_incest_prompt_is_422(client, db_session) -> None:
    response = await client.post(
        "/media",
        json={
            "type": "image",
            "source": "generation",
            "prompt": "incest",
            "frames": [{"explicit": 0.01}],
        },
        headers=HEADERS_V,
    )
    assert response.status_code == 422
    assert response.json() == {"reasons": ["incest"]}
    async with db_session() as session:
        count = await session.scalar(select(func.count()).select_from(Media))
    assert count == 0


async def test_upload_has_no_prompt_check(client) -> None:
    response = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
        headers=HEADERS_V,
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"


async def _pending_unverified_video(client) -> str:
    frames = [{"explicit": 0.01} for _ in range(8)] + [{"explicit": 0.95}]
    created = await client.post(
        "/media",
        json={"type": "video", "source": "upload", "frames": frames},
        headers=HEADERS_U,
    )
    assert created.status_code == 202, created.text
    return created.json()["id"]


def _signed_callback(media_id: str) -> tuple[bytes, str]:
    frames = []
    for index in range(9):
        frame = {label: 0.0 for label in LABELS}
        frame["explicit"] = 0.95 if index == 8 else 0.01
        frames.append(frame)
    raw = json.dumps({"media_id": media_id, "frames": frames}, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    return raw, signature


async def test_callback_with_good_signature_blocks(client, db_session) -> None:
    media_id = await _pending_unverified_video(client)
    raw, signature = _signed_callback(media_id)
    response = await client.post(
        "/provider/callback",
        content=raw,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert status == "blocked"


async def test_second_callback_does_not_change_status(client, db_session) -> None:
    media_id = await _pending_unverified_video(client)
    raw, signature = _signed_callback(media_id)
    headers = {"X-Signature": signature, "Content-Type": "application/json"}
    first = await client.post("/provider/callback", content=raw, headers=headers)
    second = await client.post("/provider/callback", content=raw, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    async with db_session() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ScreeningDecision)
            .where(ScreeningDecision.media_id == uuid.UUID(media_id), ScreeningDecision.source == "provider")
        )
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert count == 1
    assert status == "blocked"


async def test_broken_mode_still_publishes_on_timeout(client, db_session, redis_client) -> None:
    created = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
        headers=HEADERS_V,
    )
    media_id = created.json()["id"]
    settings = _settings("broken")

    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    with respx.mock:
        respx.post("http://provider.test/score").mock(side_effect=raise_timeout)
        await process_one(db_session, Queues(redis_client), ProviderClient(settings), settings)
    async with db_session() as session:
        status = await session.scalar(select(Media.status).where(Media.id == uuid.UUID(media_id)))
    assert status == "published"
