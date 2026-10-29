import asyncio


class MemoryProviderStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._mode = "ok"
        self._delay_ms = 0
        self._error_kind = "http_500"
        self._calls: dict[str, int] = {}

    async def set_control(self, mode: str, delay_ms: int, error_kind: str) -> dict:
        async with self._lock:
            self._mode = mode
            self._delay_ms = delay_ms
            self._error_kind = error_kind
            return self._control_snapshot()

    async def get_control(self) -> dict:
        async with self._lock:
            return self._control_snapshot()

    async def get_calls(self) -> dict[str, int]:
        async with self._lock:
            return dict(self._calls)

    async def increment_call(self, media_id: str) -> int:
        async with self._lock:
            count = self._calls.get(media_id, 0) + 1
            self._calls[media_id] = count
            return count

    async def begin_score(self, media_id: str) -> dict:
        async with self._lock:
            self._calls[media_id] = self._calls.get(media_id, 0) + 1
            return self._control_snapshot()

    def _control_snapshot(self) -> dict:
        return {
            "mode": self._mode,
            "delay_ms": self._delay_ms,
            "error_kind": self._error_kind,
        }
