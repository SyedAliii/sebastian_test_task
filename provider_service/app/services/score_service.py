import asyncio
import logging
from dataclasses import dataclass

from app.config import Settings
from app.domain.schemas import ScoreRequest
from app.repo.store import MemoryProviderStore
from app.services.callback_dispatcher import CallbackDispatcher
from app.services.scoring import normalize_frames

logger = logging.getLogger("provider")


@dataclass(frozen=True)
class ScoreResult:
    status_code: int
    body: dict
    headers: dict[str, str] | None = None


class ScoreService:
    def __init__(
        self,
        store: MemoryProviderStore,
        settings: Settings,
        dispatcher: CallbackDispatcher,
    ) -> None:
        self._store = store
        self._settings = settings
        self._dispatcher = dispatcher

    async def score(self, request: ScoreRequest) -> ScoreResult:
        snapshot = await self._store.begin_score(request.media_id)
        mode = snapshot["mode"]
        delay_ms = snapshot["delay_ms"]
        error_kind = snapshot["error_kind"]
        frame_count = len(request.frames)

        if mode == "timeout":
            await asyncio.sleep(self._settings.timeout_hold_seconds)
            self._log(request.media_id, frame_count, "timeout")
            return ScoreResult(status_code=504, body={"detail": "provider timeout"})

        if mode == "error":
            return self._error_result(request.media_id, frame_count, error_kind)

        frames = normalize_frames(request.frames)
        if len(frames) > 30:
            self._dispatcher.dispatch(
                request.media_id,
                {"media_id": request.media_id, "frames": frames},
                delay_seconds=delay_ms / 1000,
            )
            self._log(request.media_id, frame_count, "accepted_async")
            return ScoreResult(
                status_code=202,
                body={"media_id": request.media_id, "status": "accepted"},
            )

        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)
        self._log(request.media_id, frame_count, "scored")
        return ScoreResult(
            status_code=200,
            body={"media_id": request.media_id, "frames": frames},
        )

    def _error_result(self, media_id: str, frame_count: int, error_kind: str) -> ScoreResult:
        if error_kind == "http_429":
            self._log(media_id, frame_count, "http_429")
            return ScoreResult(
                status_code=429,
                body={"detail": "provider busy"},
                headers={"Retry-After": str(self._settings.retry_after_seconds)},
            )
        if error_kind == "malformed":
            self._log(media_id, frame_count, "malformed")
            return ScoreResult(
                status_code=200,
                body={"media_id": media_id, "frames": [{"explicit": 0.0}]},
            )
        self._log(media_id, frame_count, "http_500")
        return ScoreResult(status_code=500, body={"detail": "provider error"})

    def _log(self, media_id: str, frame_count: int, outcome: str) -> None:
        logger.info(
            "media_id=%s frame_count=%s outcome=%s",
            media_id,
            frame_count,
            outcome,
        )
