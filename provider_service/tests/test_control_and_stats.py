import httpx


async def test_stats_starts_empty(client: httpx.AsyncClient) -> None:
    response = await client.get("/_stats")
    assert response.status_code == 200
    assert response.json() == {"calls": {}}


async def test_control_ok(client: httpx.AsyncClient) -> None:
    response = await client.post("/_control", json={"mode": "ok", "delay_ms": 0})
    assert response.status_code == 200
    assert response.json() == {"mode": "ok", "delay_ms": 0, "error_kind": "http_500"}


async def test_control_defaults_delay(client: httpx.AsyncClient) -> None:
    response = await client.post("/_control", json={"mode": "slow"})
    assert response.status_code == 200
    assert response.json()["delay_ms"] == 0
    assert response.json()["mode"] == "slow"


async def test_control_rejects_bad_mode(client: httpx.AsyncClient) -> None:
    saved = await client.post("/_control", json={"mode": "ok", "delay_ms": 1})
    assert saved.status_code == 200

    rejected = await client.post("/_control", json={"mode": "nope", "delay_ms": 0})
    assert rejected.status_code == 422

    again = await client.post("/_control", json={"mode": "ok", "delay_ms": 1})
    assert again.status_code == 200
    assert again.json()["mode"] == "ok"
    assert again.json()["delay_ms"] == 1


async def test_control_rejects_negative_delay(client: httpx.AsyncClient) -> None:
    response = await client.post("/_control", json={"mode": "ok", "delay_ms": -1})
    assert response.status_code == 422


async def test_control_saves_error_kind(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/_control",
        json={"mode": "error", "delay_ms": 0, "error_kind": "http_429"},
    )
    assert response.status_code == 200
    assert response.json()["error_kind"] == "http_429"
    assert response.json()["mode"] == "error"


async def test_control_does_not_count_as_a_call(client: httpx.AsyncClient) -> None:
    first = await client.post("/_control", json={"mode": "ok", "delay_ms": 0})
    second = await client.post("/_control", json={"mode": "timeout", "delay_ms": 5})
    assert first.status_code == 200
    assert second.status_code == 200

    stats = await client.get("/_stats")
    assert stats.status_code == 200
    assert stats.json() == {"calls": {}}
