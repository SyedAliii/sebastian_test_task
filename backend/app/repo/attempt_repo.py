import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def insert_attempt(
    session: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    job_id: uuid.UUID,
    media_id: uuid.UUID,
    workspace_id: str,
    worker_id: str,
) -> None:
    await session.execute(
        text(
            """
            insert into attempts (id, job_id, media_id, workspace_id, n, worker_id, started_at)
            select :id, :job_id, :media_id, :workspace_id, coalesce(max(n), 0) + 1, :worker, now()
            from attempts
            where job_id = :job_id
            """
        ),
        {
            "id": attempt_id,
            "job_id": job_id,
            "media_id": media_id,
            "workspace_id": workspace_id,
            "worker": worker_id,
        },
    )


async def finish_attempt(
    session: AsyncSession,
    attempt_id: uuid.UUID,
    result: str,
    detail: str | None,
) -> None:
    await session.execute(
        text(
            """
            update attempts
            set finished_at = now(), result = :result, detail = :detail
            where id = :id
            """
        ),
        {"id": attempt_id, "result": result, "detail": detail},
    )
