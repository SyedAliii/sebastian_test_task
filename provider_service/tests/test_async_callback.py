import asyncio
import hashlib
import hmac
import json

import httpx
import respx

from app.domain.labels import LABELS
from app.services.signature import sign_body

CALLBACK_URL = "http://callback.test/provider/callback"


def _frames(count: int, explicit: float = 0.02) -> list[dict]:
    return [{"explicit": explicit} for _ in range(count)]


def test_sign_body_known_value() -> None:
    raw = b'{"a":1}'
    signed = sign_body(raw, "test-secret")
    expected = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    assert signed == expected
    assert len(signed) == 64
    assert signed == signed.lower()
    assert all(character in "0123456789abcdef" for character in signed)


async def test_long_video_returns_202(client: httpx.AsyncClient, app) -> None:
    with respx.mock:
        respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        response = await client.post("/score", json={"media_id": "demo-long", "frames": _frames(31)})
        await app.state.dispatcher.drain()
    assert response.status_code == 202
    body = response.json()
    assert body == {"media_id": "demo-long", "status": "accepted"}
    assert "frames" not in body


async def test_long_video_posts_signed_callback(client: httpx.AsyncClient, app) -> None:
    with respx.mock:
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        response = await client.post("/score", json={"media_id": "demo-long", "frames": _frames(31)})
        assert response.status_code == 202
        await app.state.dispatcher.drain()
        assert route.call_count == 1
        raw = route.calls[0].request.content
        payload = json.loads(raw)
        assert len(payload["frames"]) == 31
        for frame in payload["frames"]:
            assert set(frame) == set(LABELS)
        assert route.calls[0].request.headers["X-Signature"] == sign_body(raw, "test-secret")


async def test_callback_uses_sent_bytes(client: httpx.AsyncClient, app) -> None:
    with respx.mock:
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        await client.post("/score", json={"media_id": "demo-long", "frames": _frames(31)})
        await app.state.dispatcher.drain()
        raw = route.calls[0].request.content
        changed = bytes([raw[0] ^ 0x01]) + raw[1:]
        assert sign_body(changed, "test-secret") != route.calls[0].request.headers["X-Signature"]


async def test_thirty_frames_does_not_callback(client: httpx.AsyncClient, app) -> None:
    with respx.mock(assert_all_called=False):
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        response = await client.post("/score", json={"media_id": "demo-30", "frames": _frames(30)})
        await app.state.dispatcher.drain()
        assert response.status_code == 200
        assert route.call_count == 0


async def test_long_video_is_counted(client: httpx.AsyncClient, app) -> None:
    with respx.mock:
        respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        response = await client.post("/score", json={"media_id": "demo-long", "frames": _frames(31)})
        await app.state.dispatcher.drain()
    assert response.status_code == 202
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-long": 1}}


async def test_second_long_call_counts_again(client: httpx.AsyncClient, app) -> None:
    body = {"media_id": "demo-long", "frames": _frames(31)}
    with respx.mock:
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        first = await client.post("/score", json=body)
        second = await client.post("/score", json=body)
        await app.state.dispatcher.drain()
        assert first.status_code == 202
        assert second.status_code == 202
        assert route.call_count == 2
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-long": 2}}


async def test_callback_failure_still_counts(client: httpx.AsyncClient, app) -> None:
    with respx.mock:
        respx.post(CALLBACK_URL).mock(return_value=httpx.Response(500))
        response = await client.post("/score", json={"media_id": "demo-long", "frames": _frames(31)})
        assert response.status_code == 202
        await app.state.dispatcher.drain()
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-long": 1}}


async def test_callback_network_error_does_not_raise(client: httpx.AsyncClient, app) -> None:
    with respx.mock:
        respx.post(CALLBACK_URL).mock(side_effect=httpx.ConnectError)
        response = await client.post("/score", json={"media_id": "demo-long", "frames": _frames(31)})
        assert response.status_code == 202
        await app.state.dispatcher.drain()


async def test_returns_202_before_callback_finishes(client: httpx.AsyncClient, app) -> None:
    release = asyncio.Event()

    async def wait_for_release(request: httpx.Request) -> httpx.Response:
        await release.wait()
        return httpx.Response(200)

    with respx.mock:
        route = respx.post(CALLBACK_URL).mock(side_effect=wait_for_release)
        response = await client.post("/score", json={"media_id": "demo-long", "frames": _frames(31)})
        assert response.status_code == 202
        assert not release.is_set()
        release.set()
        await app.state.dispatcher.drain()
        assert route.call_count == 1
