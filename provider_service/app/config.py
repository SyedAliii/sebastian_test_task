from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    provider_host: str = "0.0.0.0"
    provider_port: int = 8001
    provider_hmac_secret: str = "test-secret"
    callback_base_url: str = "http://127.0.0.1:9000"
    callback_path: str = "/provider/callback"
    timeout_hold_seconds: float = 120
    retry_after_seconds: int = 2
    log_level: str = "INFO"

    def callback_url(self) -> str:
        base = self.callback_base_url.rstrip("/")
        path = self.callback_path.lstrip("/")
        return f"{base}/{path}"
