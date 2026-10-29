import socket
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql+asyncpg://moderation:moderation@127.0.0.1:5432/moderation"
    alembic_database_url: str = "postgresql+psycopg://moderation:moderation@127.0.0.1:5432/moderation"
    redis_url: str = "redis://127.0.0.1:6379/0"
    provider_base_url: str = "http://127.0.0.1:8001"
    provider_hmac_secret: str = "test-secret"
    provider_http_timeout_seconds: float = 10
    screening_mode: Literal["broken", "fixed"] = "fixed"
    lease_seconds: float = 30
    callback_deadline_seconds: float = 30
    worker_id: str = ""
    scheduler_interval_seconds: float = 1
    probe_interval_seconds: float = 10
    retry_timeout_max: int = 3
    retry_429_max: int = 3
    retry_500_max: int = 2
    retry_malformed_max: int = 2
    retry_base_seconds: float = 1
    retry_429_min_seconds: float = 5
    database_url_test: str = "postgresql+asyncpg://moderation:moderation@127.0.0.1:5432/moderation_test"
    alembic_database_url_test: str = "postgresql+psycopg://moderation:moderation@127.0.0.1:5432/moderation_test"
    redis_url_test: str = "redis://127.0.0.1:6379/1"
    log_detail_level: Literal["none", "high", "mid", "low"] = "mid"
    log_enable_emojis: bool = True
    log_json_max_size: int = 50000
    log_json_max_depth: int = 10

    @field_validator("worker_id", mode="after")
    @classmethod
    def empty_worker_id_uses_hostname(cls, value: str) -> str:
        if value.strip() == "":
            return socket.gethostname()
        return value
