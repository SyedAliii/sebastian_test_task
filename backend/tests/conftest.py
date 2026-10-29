"""Tests need Compose Postgres and Redis running.

Postgres must be accepting connections on 127.0.0.1:5432, with databases
moderation and moderation_test. Redis must be on 127.0.0.1:6379.
Schema changes belong in Alembic. These tests migrate moderation_test only.
"""

import os
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_session
from app.config import Settings
from app.db.seed import seed
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated_test_db():
    settings = Settings()
    os.environ["ALEMBIC_URL"] = settings.alembic_database_url_test
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")
    yield
    os.environ.pop("ALEMBIC_URL", None)


@pytest.fixture
def test_settings() -> Settings:
    loaded = Settings()
    return loaded.model_copy(
        update={
            "database_url": loaded.database_url_test,
            "alembic_database_url": loaded.alembic_database_url_test,
            "redis_url": loaded.redis_url_test,
            "screening_mode": "fixed",
        }
    )


@pytest.fixture
async def db_session(migrated_test_db):
    settings = Settings()
    engine = create_async_engine(settings.database_url_test)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("TRUNCATE attempts, screening_decisions, jobs, media, users, workspaces CASCADE")
        )
        await seed(session)
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
async def redis_client():
    url = Settings().redis_url_test
    if not url.rstrip("/").endswith("/1"):
        raise RuntimeError("REDIS_URL_TEST must use Redis database 1")
    client = Redis.from_url(url)
    await client.flushdb()
    yield client
    await client.aclose()


@pytest.fixture
def app(test_settings: Settings, db_session, redis_client):
    application = create_app(test_settings, session_factory=db_session, redis_client=redis_client)

    async def override_session():
        async with db_session() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    return application


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
