import asyncio
import time

import httpx
import respx

from app.domain.labels import LABELS
from app.services.signature import sign_body

CALLBACK_URL = "http://callback.test/provider/callback"


def _one_frame(media_id: str) -> dict:
    return {"media_id": media_id, "frames": [{"explicit": 0.02}]}


def _many_frames(media_id: str, count: int) -> dict:
    return {"media_id": media_id, "frames": [{"explicit": 0.02} for _ in range(count)]}


async def _control(
    client: httpx.AsyncClient,
    mode: str,
    delay_ms: int = 0,
    error_kind: str | None = None,
) -> None:
    body: dict = {"mode": mode, "delay_ms": delay_ms}
    if error_kind is not None:
        body["error_kind"] = error_kind
    response = await client.post("/_control", json=body)
    assert response.status_code == 200


async def _wait_until_counted(client: httpx.AsyncClient, media_id: str) -> None:
    deadline = time.perf_counter() + 1
    while time.perf_counter() < deadline:
        stats = await client.get("/_stats")
        if stats.json()["calls"].get(media_id) == 1:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"{media_id} was not counted")


async def test_slow_waits_then_scores(client: httpx.AsyncClient) -> None:
    await _control(client, "slow", 200)
    started = time.perf_counter()
    response = await client.post("/score", json=_one_frame("demo-slow"))
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert elapsed >= 0.15
    frame = response.json()["frames"][0]
    assert list(frame) == list(LABELS)
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-slow": 1}}


async def test_ok_with_zero_delay_does_not_wait(client: httpx.AsyncClient) -> None:
    await _control(client, "ok", 0)
    started = time.perf_counter()
    response = await client.post("/score", json=_one_frame("demo-ok"))
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert elapsed < 0.5


async def test_timeout_returns_504_after_hold(client: httpx.AsyncClient) -> None:
    await _control(client, "timeout")
    started = time.perf_counter()
    response = await client.post("/score", json=_one_frame("demo-timeout"))
    elapsed = time.perf_counter() - started
    assert response.status_code == 504
    assert elapsed >= 0.15
    assert response.json() == {"detail": "provider timeout"}
    assert "frames" not in response.json()
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-timeout": 1}}


async def test_timeout_counts_while_still_open(client: httpx.AsyncClient) -> None:
    await _control(client, "timeout")
    score_task = asyncio.create_task(client.post("/score", json=_one_frame("demo-open")))
    try:
        await _wait_until_counted(client, "demo-open")
        assert not score_task.done()
    finally:
        response = await score_task
    assert response.status_code == 504


async def test_timeout_does_not_callback(client: httpx.AsyncClient, app) -> None:
    await _control(client, "timeout")
    with respx.mock(assert_all_called=False):
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        response = await client.post("/score", json=_many_frames("demo-timeout", 31))
        await app.state.dispatcher.drain()
        assert response.status_code == 504
        assert route.call_count == 0


async def test_error_defaults_to_500(client: httpx.AsyncClient, app) -> None:
    await _control(client, "error")
    with respx.mock(assert_all_called=False):
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        response = await client.post("/score", json=_one_frame("demo-error"))
        await app.state.dispatcher.drain()
        assert response.status_code == 500
        assert response.json() == {"detail": "provider error"}
        assert route.call_count == 0
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-error": 1}}


async def test_error_429_sets_retry_after(client: httpx.AsyncClient) -> None:
    await _control(client, "error", error_kind="http_429")
    response = await client.post("/score", json=_one_frame("demo-busy"))
    assert response.status_code == 429
    assert response.json() == {"detail": "provider busy"}
    assert response.headers["Retry-After"] == "2"
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-busy": 1}}


async def test_error_malformed_omits_labels(client: httpx.AsyncClient, app) -> None:
    await _control(client, "error", error_kind="malformed")
    with respx.mock(assert_all_called=False):
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        response = await client.post("/score", json=_one_frame("demo-bad"))
        await app.state.dispatcher.drain()
        assert response.status_code == 200
        frames = response.json()["frames"]
        assert len(frames) == 1
        assert list(frames[0]) == ["explicit"]
        assert frames[0]["explicit"] == 0.0
        assert route.call_count == 0
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-bad": 1}}


async def test_error_on_long_video_does_not_callback(client: httpx.AsyncClient, app) -> None:
    await _control(client, "error")
    with respx.mock(assert_all_called=False):
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        response = await client.post("/score", json=_many_frames("demo-long", 31))
        await app.state.dispatcher.drain()
        assert response.status_code == 500
        assert route.call_count == 0
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-long": 1}}


async def test_slow_long_video_delays_callback(client: httpx.AsyncClient, app) -> None:
    await _control(client, "slow", 200)
    with respx.mock:
        route = respx.post(CALLBACK_URL).mock(return_value=httpx.Response(200))
        started = time.perf_counter()
        response = await client.post("/score", json=_many_frames("demo-long", 31))
        assert response.status_code == 202
        assert time.perf_counter() - started < 0.15
        assert route.call_count == 0
        await app.state.dispatcher.drain()
        assert route.call_count == 1
        assert time.perf_counter() - started >= 0.15
        raw = route.calls[0].request.content
        assert route.calls[0].request.headers["X-Signature"] == sign_body(raw, "test-secret")


async def test_mode_change_does_not_affect_in_flight_call(client: httpx.AsyncClient) -> None:
    await _control(client, "slow", 200)
    score_task = asyncio.create_task(client.post("/score", json=_one_frame("demo-inflight")))
    try:
        await _wait_until_counted(client, "demo-inflight")
        assert not score_task.done()
        changed = await client.post("/_control", json={"mode": "error", "delay_ms": 0})
        assert changed.status_code == 200
    finally:
        response = await score_task
    assert response.status_code == 200
    frame = response.json()["frames"][0]
    assert list(frame) == list(LABELS)
