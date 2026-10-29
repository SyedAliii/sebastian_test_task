from dataclasses import dataclass

import httpx

from app.config import Settings
from app.core.logging.logger import logger
from app.domain.labels import LABELS


@dataclass(frozen=True)
class ProviderReply:
    kind: str
    body: dict | None = None
    retry_after: int | None = None


class ProviderClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def post_score(
        self,
        media_id: str,
        frames: list,
        correlation_id: str | None = None,
    ) -> ProviderReply:
        url = f"{self._settings.provider_base_url.rstrip('/')}/score"
        payload = {"media_id": media_id, "frames": frames}
        cid = logger.api_request_out(url, method="POST", payload=payload, correlation_id=correlation_id)
        try:
            async with httpx.AsyncClient(timeout=self._settings.provider_http_timeout_seconds) as client:
                response = await client.post(url, json=payload)
        except httpx.TimeoutException:
            logger.api_response_in(url, status=0, correlation_id=cid)
            return ProviderReply(kind="timeout")
        except httpx.HTTPError:
            logger.api_response_in(url, status=0, correlation_id=cid)
            return ProviderReply(kind="http_500")
        logger.api_response_in(url, status=response.status_code, correlation_id=cid)
        if response.status_code == 202:
            return ProviderReply(kind="accepted")
        if response.status_code == 429:
            return ProviderReply(kind="http_429", retry_after=_retry_after(response))
        if response.status_code == 504:
            return ProviderReply(kind="timeout")
        if response.status_code == 500:
            return ProviderReply(kind="http_500")
        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError:
                return ProviderReply(kind="malformed")
            if not _usable(body, len(frames)):
                return ProviderReply(kind="malformed", body=body if isinstance(body, dict) else None)
            return ProviderReply(kind="scored", body=body)
        return ProviderReply(kind="http_500")


def _retry_after(response: httpx.Response) -> int | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _usable(body: object, sent_count: int) -> bool:
    if not isinstance(body, dict):
        return False
    frames = body.get("frames")
    if not isinstance(frames, list) or len(frames) != sent_count:
        return False
    for frame in frames:
        if not isinstance(frame, dict) or any(label not in frame for label in LABELS):
            return False
    return True
