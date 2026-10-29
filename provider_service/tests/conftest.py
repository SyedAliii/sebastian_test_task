import httpx
import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        provider_hmac_secret="test-secret",
        callback_base_url="http://callback.test",
        callback_path="/provider/callback",
        timeout_hold_seconds=0.2,
        retry_after_seconds=2,
    )


@pytest.fixture
def app(test_settings: Settings):
    return create_app(test_settings)


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
