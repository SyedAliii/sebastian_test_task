from redis.asyncio import Redis


class Queues:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def enqueue(self, workspace_id: str, job_id: str) -> None:
        await self._client.rpush(f"queue:{workspace_id}", job_id)

    async def length(self, workspace_id: str) -> int:
        return int(await self._client.llen(f"queue:{workspace_id}"))

    async def enqueue_many(self, jobs: list[tuple[str, str]]) -> None:
        pipe = self._client.pipeline(transaction=False)
        for job_id, workspace_id in jobs:
            pipe.rpush(f"queue:{workspace_id}", job_id)
        await pipe.execute()

    async def pop_fair(self, prefer: str | None) -> tuple[str, str] | None:
        if prefer == "ws_unverified":
            order = ("ws_unverified", "ws_verified")
        else:
            order = ("ws_verified", "ws_unverified")
        for workspace_id in order:
            job_id = await self.pop(workspace_id)
            if job_id is not None:
                return workspace_id, job_id
        return None

    async def pop(self, workspace_id: str) -> str | None:
        value = await self._client.lpop(f"queue:{workspace_id}")
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode()
        return str(value)
