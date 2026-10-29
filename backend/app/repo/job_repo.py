import uuid
from datetime import datetime

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, Media, Workspace


async def insert_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    media_id: uuid.UUID,
    workspace_id: str,
    available_at: datetime,
) -> None:
    session.add(
        Job(
            id=job_id,
            media_id=media_id,
            workspace_id=workspace_id,
            state="queued",
            attempts_used=0,
            available_at=available_at,
            lease_owner=None,
            lease_until=None,
            needs_enqueue=True,
            created_at=available_at,
            updated_at=available_at,
        )
    )


async def clear_needs_enqueue(session: AsyncSession, job_id: uuid.UUID, updated_at: datetime) -> None:
    await session.execute(
        update(Job).where(Job.id == job_id).values(needs_enqueue=False, updated_at=updated_at)
    )


async def load_job(session: AsyncSession, job_id: uuid.UUID):
    return (
        await session.execute(
            select(
                Job.id,
                Job.state,
                Job.media_id,
                Job.workspace_id,
                Media.frames,
                Media.frame_count,
                Workspace.verified,
            )
            .join(Media, Media.id == Job.media_id)
            .join(Workspace, Workspace.id == Job.workspace_id)
            .where(Job.id == job_id)
        )
    ).one_or_none()


async def save_job_state(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    state: str,
    updated_at: datetime,
    available_at: datetime | None = None,
    needs_enqueue: bool | None = None,
    bump_attempts: bool = False,
    lease_owner: str | None = None,
) -> int:
    values: dict = {"state": state, "updated_at": updated_at}
    if available_at is not None:
        values["available_at"] = available_at
    if needs_enqueue is not None:
        values["needs_enqueue"] = needs_enqueue
    if bump_attempts:
        values["attempts_used"] = Job.attempts_used + 1
    statement = update(Job).where(Job.id == job_id)
    if lease_owner is not None:
        statement = statement.where(Job.lease_owner == lease_owner)
    result = await session.execute(statement.values(**values))
    return result.rowcount or 0


async def claim_job(session: AsyncSession, job_id: uuid.UUID, worker_id: str, lease_seconds: float) -> bool:
    result = await session.execute(
        text(
            """
            update jobs
            set state = 'running',
                lease_owner = :worker,
                lease_until = now() + make_interval(secs => :lease_seconds),
                attempts_used = attempts_used + 1,
                needs_enqueue = false
            where id = :job_id
              and (
                (state in ('queued', 'retry_wait') and available_at <= now())
                or (state = 'running' and lease_until < now())
              )
            returning id
            """
        ),
        {"worker": worker_id, "lease_seconds": lease_seconds, "job_id": job_id},
    )
    return result.first() is not None


async def refresh_lease(session: AsyncSession, job_id: uuid.UUID, worker_id: str, lease_seconds: float) -> None:
    await session.execute(
        text(
            """
            update jobs
            set lease_until = now() + make_interval(secs => :lease_seconds)
            where id = :job_id and lease_owner = :worker and state = 'running'
            """
        ),
        {"lease_seconds": lease_seconds, "job_id": job_id, "worker": worker_id},
    )
