import asyncio
import json
from collections.abc import Awaitable, Callable

from app.config import Settings
from app.services.signature import sign_body

Sender = Callable[[str, bytes, str, str], Awaitable[None]]


class CallbackDispatcher:
    def __init__(self, settings: Settings, sender: Sender) -> None:
        self._settings = settings
        self._sender = sender
        self._tasks: set[asyncio.Task] = set()

    def dispatch(self, media_id: str, payload: dict, delay_seconds: float = 0.0) -> None:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = sign_body(raw, self._settings.provider_hmac_secret)
        task = asyncio.create_task(
            self._run(self._settings.callback_url(), raw, signature, media_id, delay_seconds)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks))

    async def _run(
        self,
        url: str,
        raw: bytes,
        signature: str,
        media_id: str,
        delay_seconds: float,
    ) -> None:
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        await self._sender(url, raw, signature, media_id)
