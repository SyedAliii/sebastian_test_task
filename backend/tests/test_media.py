from sqlalchemy import func, select

from app.db.models import Media

HEADERS_V = {"X-User-Id": "member_v", "X-Workspace-Id": "ws_verified"}
HEADERS_U = {"X-User-Id": "member_u", "X-Workspace-Id": "ws_unverified"}
IMAGE = {"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]}


async def test_upload_returns_pending(client) -> None:
    response = await client.post("/media", json=IMAGE, headers=HEADERS_V)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["id"]


async def test_owner_can_read(client) -> None:
    created = await client.post("/media", json=IMAGE, headers=HEADERS_V)
    media_id = created.json()["id"]
    response = await client.get(f"/media/{media_id}", headers=HEADERS_V)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["id"] == media_id


async def test_other_workspace_is_404(client) -> None:
    created = await client.post("/media", json=IMAGE, headers=HEADERS_V)
    media_id = created.json()["id"]
    response = await client.get(f"/media/{media_id}", headers=HEADERS_U)
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}


async def test_missing_header_is_401(client) -> None:
    response = await client.post("/media", json=IMAGE)
    assert response.status_code == 401
    assert response.json() == {"detail": "missing caller"}


async def test_user_in_wrong_workspace_is_401(client) -> None:
    response = await client.post(
        "/media",
        json=IMAGE,
        headers={"X-User-Id": "member_v", "X-Workspace-Id": "ws_unverified"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "unknown caller"}


async def test_generation_is_stored(client, db_session) -> None:
    response = await client.post(
        "/media",
        json={
            "type": "image",
            "source": "generation",
            "prompt": "two adults on a beach at sunset",
            "frames": [{"explicit": 0.1}],
        },
        headers=HEADERS_V,
    )
    assert response.status_code == 202
    async with db_session() as session:
        prompt = await session.scalar(select(Media.prompt).where(Media.id == response.json()["id"]))
    assert prompt == "two adults on a beach at sunset"


async def test_image_with_two_frames_is_422(client, db_session) -> None:
    response = await client.post(
        "/media",
        json={"type": "image", "source": "upload", "frames": [{"explicit": 0.1}, {"explicit": 0.2}]},
        headers=HEADERS_V,
    )
    assert response.status_code == 422
    assert "image_must_have_one_frame" in response.json()["reasons"]
    async with db_session() as session:
        count = await session.scalar(select(func.count()).select_from(Media))
    assert count == 0


async def test_job_is_pushed(client, redis_client) -> None:
    response = await client.post("/media", json=IMAGE, headers=HEADERS_V)
    assert response.status_code == 202
    assert await redis_client.llen("queue:ws_verified") == 1
    assert await redis_client.llen("queue:ws_unverified") == 0
