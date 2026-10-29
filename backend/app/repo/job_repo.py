import uuid
from datetime import datetime

from sqlalchemy import bindparam, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
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
    clear_lease: bool = False,
) -> int:
    values: dict = {"state": state, "updated_at": updated_at}
    if clear_lease:
        values["lease_owner"] = None
        values["lease_until"] = None
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


async def apply_failure(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    park: bool,
    wait_seconds: float,
    worker_id: str,
) -> int:
    if park:
        statement = """
            update jobs
            set state = 'parked',
                needs_enqueue = false,
                lease_owner = null,
                lease_until = null,
                updated_at = now()
            where id = :job_id and lease_owner = :worker
        """
    else:
        statement = """
            update jobs
            set state = 'retry_wait',
                available_at = now() + make_interval(secs => :wait_seconds),
                needs_enqueue = false,
                lease_owner = null,
                lease_until = null,
                updated_at = now()
            where id = :job_id and lease_owner = :worker
        """
    result = await session.execute(
        text(statement),
        {"job_id": job_id, "worker": worker_id, "wait_seconds": wait_seconds},
    )
    return result.rowcount or 0


async def release_parked_jobs(session: AsyncSession) -> list[uuid.UUID]:
    result = await session.execute(
        text(
            """
            update jobs
            set state = 'queued',
                attempts_used = 0,
                needs_enqueue = true,
                available_at = now(),
                lease_owner = null,
                lease_until = null
            where state = 'parked'
            returning id
            """
        )
    )
    ids = [row[0] for row in result]
    if not ids:
        return []
    await session.execute(
        text(
            """
            update media
            set status = 'pending', hold_reason = null, reasons = '[]'::jsonb, updated_at = now()
            where id in (select media_id from jobs where id = any(:released_ids))
              and status = 'held' and hold_reason = 'no_decision'
            """
        ).bindparams(bindparam("released_ids", type_=ARRAY(PG_UUID(as_uuid=True)))),
        {"released_ids": ids},
    )
    return ids


async def requeue_due_jobs(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            update jobs
            set state = 'queued', needs_enqueue = true, lease_owner = null, lease_until = null
            where (state = 'retry_wait' and available_at <= now())
               or (state = 'running' and lease_until < now())
               or (state = 'awaiting_callback' and available_at <= now())
            """
        )
    )


async def jobs_needing_enqueue(session: AsyncSession) -> list[tuple[uuid.UUID, str]]:
    rows = (
        await session.execute(text("select id, workspace_id from jobs where needs_enqueue = true"))
    ).all()
    return [(row[0], row[1]) for row in rows]


async def clear_needs_enqueue_ids(session: AsyncSession, job_ids: list[uuid.UUID]) -> None:
    if not job_ids:
        return
    await session.execute(
        text("update jobs set needs_enqueue = false where id = any(:ids)").bindparams(
            bindparam("ids", type_=ARRAY(PG_UUID(as_uuid=True)))
        ),
        {"ids": job_ids},
    )


async def probe_parked_job(session: AsyncSession) -> tuple[uuid.UUID, str] | None:
    result = await session.execute(
        text(
            """
            update jobs
            set state = 'queued', attempts_used = 0, needs_enqueue = true, available_at = now(),
                lease_owner = null, lease_until = null
            where id = (
                select id from jobs where state = 'parked' order by updated_at limit 1
            )
              and not exists (
                select 1 from jobs
                where state in ('queued', 'running', 'retry_wait', 'awaiting_callback')
              )
            returning id, workspace_id
            """
        )
    )
    row = result.first()
    if row is None:
        return None
    await session.execute(
        text(
            """
            update media
            set status = 'pending', hold_reason = null, reasons = '[]'::jsonb, updated_at = now()
            where id = (select media_id from jobs where id = :job_id)
            """
        ),
        {"job_id": row[0]},
    )
    return row[0], row[1]


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
