import httpx

from app.core.logging.logger import log_level_banner


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_has_no_correlation_header(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert "X-Correlation-ID" not in response.headers


def test_banner_function_exists() -> None:
    log_level_banner("moderation-api")
