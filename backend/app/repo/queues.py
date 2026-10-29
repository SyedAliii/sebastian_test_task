from redis.asyncio import Redis


class Queues:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def enqueue(self, workspace_id: str, job_id: str) -> None:
        await self._client.rpush(f"queue:{workspace_id}", job_id)

    async def length(self, workspace_id: str) -> int:
        return int(await self._client.llen(f"queue:{workspace_id}"))

    async def pop(self, workspace_id: str) -> str | None:
        value = await self._client.lpop(f"queue:{workspace_id}")
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode()
        return str(value)
