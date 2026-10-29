import httpx

from app.config import Settings


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_callback_url_joins_one_slash() -> None:
    with_slash = Settings(
        _env_file=None,
        callback_base_url="http://x:9000/",
        callback_path="/provider/callback",
    )
    without_slash = Settings(
        _env_file=None,
        callback_base_url="http://x:9000",
        callback_path="/provider/callback",
    )
    assert with_slash.callback_url() == "http://x:9000/provider/callback"
    assert without_slash.callback_url() == "http://x:9000/provider/callback"
