import httpx
import respx

from app.domain.labels import LABELS
from app.services.scoring import normalize_frames


def _score_body(media_id: str, frames: list[dict]) -> dict:
    return {"media_id": media_id, "frames": frames}


async def test_score_fills_missing_labels(client: httpx.AsyncClient) -> None:
    response = await client.post("/score", json=_score_body("demo-1", [{"explicit": 0.02}]))
    assert response.status_code == 200
    frame = response.json()["frames"][0]
    assert list(frame) == list(LABELS)
    assert frame["explicit"] == 0.02
    for label in LABELS:
        if label != "explicit":
            assert frame[label] == 0


async def test_score_keeps_every_frame(client: httpx.AsyncClient) -> None:
    frames = [{} for _ in range(9)]
    frames[8] = {"explicit": 0.95}
    response = await client.post("/score", json=_score_body("demo-nine", frames))
    assert response.status_code == 200
    body = response.json()["frames"]
    assert len(body) == 9
    assert body[8]["explicit"] == 0.95


async def test_score_counts_each_call(client: httpx.AsyncClient) -> None:
    body = _score_body("demo-1", [{"explicit": 0.02}])
    first = await client.post("/score", json=body)
    second = await client.post("/score", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-1": 2}}


async def test_score_counts_separate_ids(client: httpx.AsyncClient) -> None:
    first = await client.post("/score", json=_score_body("a", [{"explicit": 0.1}]))
    second = await client.post("/score", json=_score_body("b", [{"explicit": 0.1}]))
    assert first.status_code == 200
    assert second.status_code == 200
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"a": 1, "b": 1}}


async def test_invalid_body_does_not_count(client: httpx.AsyncClient) -> None:
    response = await client.post("/score", json={"media_id": "demo-1", "frames": []})
    assert response.status_code == 422
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {}}


async def test_score_out_of_range_does_not_count(client: httpx.AsyncClient) -> None:
    response = await client.post("/score", json=_score_body("demo-1", [{"explicit": 1.2}]))
    assert response.status_code == 422
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {}}


async def test_score_bool_does_not_count(client: httpx.AsyncClient) -> None:
    response = await client.post("/score", json=_score_body("demo-1", [{"explicit": True}]))
    assert response.status_code == 422
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {}}


async def test_unknown_label_is_dropped(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/score",
        json=_score_body("demo-1", [{"explicit": 0.2, "extra": 0.9}]),
    )
    assert response.status_code == 200
    frame = response.json()["frames"][0]
    assert list(frame) == list(LABELS)
    assert frame["explicit"] == 0.2


async def test_thirty_frames_is_sync(client: httpx.AsyncClient) -> None:
    frames = [{"explicit": 0.1} for _ in range(30)]
    response = await client.post("/score", json=_score_body("demo-30", frames))
    assert response.status_code == 200
    body = response.json()["frames"]
    assert len(body) == 30
    assert all(list(frame) == list(LABELS) for frame in body)
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-30": 1}}


async def test_thirty_one_frames_not_yet(client: httpx.AsyncClient, app) -> None:
    frames = [{"explicit": 0.1} for _ in range(31)]
    with respx.mock:
        respx.post("http://callback.test/provider/callback").mock(return_value=httpx.Response(200))
        response = await client.post("/score", json=_score_body("demo-31", frames))
        await app.state.dispatcher.drain()
    assert response.status_code == 202
    assert response.json() == {"media_id": "demo-31", "status": "accepted"}
    stats = await client.get("/_stats")
    assert stats.json() == {"calls": {"demo-31": 1}}


async def test_prompt_field_is_ignored(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/score",
        json={
            "media_id": "demo-1",
            "prompt": "a 16-year-old",
            "frames": [{"explicit": 0.02}],
        },
    )
    assert response.status_code == 200
    assert response.json()["frames"][0]["explicit"] == 0.02


def test_normalize_frames_is_pure() -> None:
    original = [{"minor": 0.6}]
    result = normalize_frames(original)
    assert len(result) == 1
    assert list(result[0]) == list(LABELS)
    assert result[0]["minor"] == 0.6
    for label in LABELS:
        if label != "minor":
            assert result[0][label] == 0
    assert original == [{"minor": 0.6}]
