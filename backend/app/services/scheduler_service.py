import uuid

from app.core.logging.logger import logger
from app.repo.job_repo import (
    clear_needs_enqueue_ids,
    jobs_needing_enqueue,
    probe_parked_job,
    requeue_due_jobs,
)
from app.repo.queues import Queues


async def tick(session_factory, queues: Queues) -> int:
    async with session_factory() as session:
        await requeue_due_jobs(session)
        await session.commit()
    async with session_factory() as session:
        due = await jobs_needing_enqueue(session)
    if not due:
        return 0
    try:
        await queues.enqueue_many([(str(job_id), workspace_id) for job_id, workspace_id in due])
    except Exception as exc:
        logger.warning(f"step=enqueue_failed error={type(exc).__name__} count={len(due)}")
        return 0
    async with session_factory() as session:
        await clear_needs_enqueue_ids(session, [job_id for job_id, _workspace_id in due])
        await session.commit()
    logger.system_info(f"enqueued={len(due)}")
    return len(due)


async def run_probe(session_factory) -> uuid.UUID | None:
    async with session_factory() as session:
        probed = await probe_parked_job(session)
        await session.commit()
    if probed is None:
        return None
    return probed[0]
