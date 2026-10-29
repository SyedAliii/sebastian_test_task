import asyncio
import contextlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.clients.provider_client import ProviderClient, ProviderReply
from app.config import Settings
from app.core.logging.logger import logger
from app.db.models import Job
from app.domain.decide import decide
from app.domain.policy import frames_for_provider, timeout_publishes
from app.domain.retry import retry_delay_seconds, should_park
from app.repo.attempt_repo import finish_attempt, insert_attempt
from app.repo.decision_repo import insert_decision
from app.repo.job_repo import apply_failure, claim_job, load_job, refresh_lease, release_parked_jobs, save_job_state
from app.repo.media_repo import apply_media_status
from app.repo.queues import Queues

_RESULTS = {
    "scored": "success",
    "accepted": "accepted_async",
    "timeout": "timeout",
    "http_429": "http_429",
    "http_500": "http_500",
    "malformed": "malformed",
}


class FairCursor:
    def __init__(self) -> None:
        self.prefer: str | None = None


async def process_one(
    session_factory,
    queues: Queues,
    provider: ProviderClient,
    settings: Settings,
    after_provider_reply=None,
    cursor=None,
) -> bool:
    prefer = None if cursor is None else cursor.prefer
    popped = await queues.pop_fair(prefer)
    if popped is None:
        return False
    workspace_id, job_raw = popped
    if cursor is not None:
        cursor.prefer = "ws_unverified" if workspace_id == "ws_verified" else "ws_verified"
    try:
        job_id = uuid.UUID(job_raw)
    except ValueError:
        return True

    if settings.screening_mode == "fixed":
        async with session_factory() as session:
            claimed = await claim_job(session, job_id, settings.worker_id, settings.lease_seconds)
            await session.commit()
        if not claimed:
            logger.warning(f"job_id={job_id} step=claim_missed")
            return True

    async with session_factory() as session:
        loaded = await load_job(session, job_id)
        if loaded is None:
            return True
        snapshot = {
            "job_id": loaded.id,
            "media_id": loaded.media_id,
            "workspace_id": loaded.workspace_id,
            "frames": list(loaded.frames),
            "verified": loaded.verified,
        }
        attempt_id = await _start_attempt(session, snapshot, settings.worker_id)
        await session.commit()

    sent = frames_for_provider(snapshot["frames"], settings.screening_mode)
    correlation_id = logger.job_start(
        f"workspace_id={snapshot['workspace_id']} media_id={snapshot['media_id']} "
        f"job_id={snapshot['job_id']} attempt={attempt_id}"
    )
    refresh_task = None
    if settings.screening_mode == "fixed":
        refresh_task = asyncio.create_task(
            _keep_lease(session_factory, snapshot["job_id"], settings.worker_id, settings.lease_seconds)
        )
    try:
        reply = await provider.post_score(str(snapshot["media_id"]), sent, correlation_id=correlation_id)
        if after_provider_reply is not None:
            after_provider_reply(reply)
    finally:
        if refresh_task is not None:
            refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await refresh_task
    await _save_reply(session_factory, snapshot, attempt_id, reply, settings)
    logger.job_end(
        f"workspace_id={snapshot['workspace_id']} media_id={snapshot['media_id']} "
        f"job_id={snapshot['job_id']} attempt={attempt_id} kind={reply.kind}",
        status="ok" if reply.kind in {"scored", "accepted"} else "failed",
        correlation_id=correlation_id,
    )
    return True


async def _start_attempt(session, snapshot: dict, worker_id: str) -> uuid.UUID:
    attempt_id = uuid.uuid4()
    try:
        async with session.begin_nested():
            await insert_attempt(
                session,
                attempt_id=attempt_id,
                job_id=snapshot["job_id"],
                media_id=snapshot["media_id"],
                workspace_id=snapshot["workspace_id"],
                worker_id=worker_id,
            )
    except IntegrityError:
        attempt_id = uuid.uuid4()
        await insert_attempt(
            session,
            attempt_id=attempt_id,
            job_id=snapshot["job_id"],
            media_id=snapshot["media_id"],
            workspace_id=snapshot["workspace_id"],
            worker_id=worker_id,
        )
    return attempt_id


async def _keep_lease(session_factory, job_id: uuid.UUID, worker_id: str, lease_seconds: float) -> None:
    while True:
        await asyncio.sleep(lease_seconds / 3)
        async with session_factory() as session:
            await refresh_lease(session, job_id, worker_id, lease_seconds)
            await session.commit()


async def _save_reply(session_factory, snapshot: dict, attempt_id: uuid.UUID, reply: ProviderReply, settings: Settings) -> None:
    now = datetime.now(timezone.utc)
    bump = settings.screening_mode == "broken"
    lease_owner = settings.worker_id if settings.screening_mode == "fixed" else None
    async with session_factory() as session:
        await finish_attempt(session, attempt_id, _RESULTS.get(reply.kind, "http_500"), reply.kind)
        if settings.screening_mode == "fixed" and reply.kind in {"timeout", "http_429", "http_500", "malformed"}:
            await _fail_or_park(session, snapshot["job_id"], snapshot["media_id"], reply, settings)
            return
        if reply.kind == "timeout" and timeout_publishes(settings.screening_mode):
            await apply_media_status(
                session,
                snapshot["media_id"],
                status="published",
                hold_reason=None,
                reasons=[],
                updated_at=now,
            )
            job_rows = await save_job_state(
                session,
                snapshot["job_id"],
                state="succeeded",
                updated_at=now,
                bump_attempts=bump,
                lease_owner=lease_owner,
            )
        elif reply.kind == "scored" and reply.body is not None:
            decision = decide(reply.body["frames"], snapshot["verified"])
            await insert_decision(
                session,
                media_id=snapshot["media_id"],
                source="provider",
                scores=reply.body["frames"],
                outcome=decision.status,
                reasons=decision.reasons,
                decided_by=None,
                created_at=now,
            )
            await apply_media_status(
                session,
                snapshot["media_id"],
                status=decision.status,
                hold_reason=decision.hold_reason,
                reasons=decision.reasons,
                updated_at=now,
            )
            job_rows = await save_job_state(
                session,
                snapshot["job_id"],
                state="succeeded",
                updated_at=now,
                bump_attempts=bump,
                lease_owner=lease_owner,
            )
            await release_parked_jobs(session)
        elif reply.kind == "accepted":
            job_rows = await save_job_state(
                session,
                snapshot["job_id"],
                state="awaiting_callback",
                updated_at=now,
                available_at=now + timedelta(seconds=settings.callback_deadline_seconds),
                bump_attempts=bump,
                lease_owner=lease_owner,
                clear_lease=True,
            )
        else:
            job_rows = await save_job_state(
                session,
                snapshot["job_id"],
                state="retry_wait",
                updated_at=now,
                available_at=now + timedelta(seconds=1),
                needs_enqueue=False,
                bump_attempts=bump,
                lease_owner=lease_owner,
            )
        if lease_owner is not None and job_rows == 0:
            await session.rollback()
            return
        await session.commit()


async def _fail_or_park(session, job_id: uuid.UUID, media_id: uuid.UUID, reply: ProviderReply, settings: Settings) -> None:
    used = int(await session.scalar(select(Job.attempts_used).where(Job.id == job_id)) or 0)
    park = should_park(reply.kind, used, settings)
    wait = 0.0 if park else retry_delay_seconds(reply.kind, used, reply.retry_after, settings)
    rows = await apply_failure(session, job_id, park=park, wait_seconds=wait, worker_id=settings.worker_id)
    if rows == 0:
        await session.rollback()
        return
    if park:
        await apply_media_status(
            session,
            media_id,
            status="held",
            hold_reason="no_decision",
            reasons=["no_decision"],
            updated_at=datetime.now(timezone.utc),
        )
    await session.commit()
