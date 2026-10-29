import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.clients.provider_client import ProviderClient, ProviderReply
from app.config import Settings
from app.core.logging.logger import logger
from app.domain.decide import decide
from app.domain.policy import frames_for_provider, timeout_publishes
from app.repo.attempt_repo import finish_attempt, insert_attempt
from app.repo.decision_repo import insert_decision
from app.repo.job_repo import load_job, save_job_state
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


async def process_one(session_factory, queues: Queues, provider: ProviderClient, settings: Settings) -> bool:
    job_raw = await queues.pop("ws_verified")
    if job_raw is None:
        job_raw = await queues.pop("ws_unverified")
    if job_raw is None:
        return False
    try:
        job_id = uuid.UUID(job_raw)
    except ValueError:
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
        f"job_id={snapshot['job_id']} attempt=-"
    )
    reply = await provider.post_score(str(snapshot["media_id"]), sent, correlation_id=correlation_id)
    await _save_reply(session_factory, snapshot, attempt_id, reply, settings)
    logger.job_end(
        f"workspace_id={snapshot['workspace_id']} media_id={snapshot['media_id']} "
        f"job_id={snapshot['job_id']} attempt=- kind={reply.kind}",
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


async def _save_reply(session_factory, snapshot: dict, attempt_id: uuid.UUID, reply: ProviderReply, settings: Settings) -> None:
    now = datetime.now(timezone.utc)
    bump = settings.screening_mode == "broken"
    async with session_factory() as session:
        await finish_attempt(session, attempt_id, _RESULTS.get(reply.kind, "http_500"), reply.kind)
        if reply.kind == "timeout" and timeout_publishes(settings.screening_mode):
            await apply_media_status(
                session,
                snapshot["media_id"],
                status="published",
                hold_reason=None,
                reasons=[],
                updated_at=now,
            )
            await save_job_state(session, snapshot["job_id"], state="succeeded", updated_at=now, bump_attempts=bump)
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
            await save_job_state(session, snapshot["job_id"], state="succeeded", updated_at=now, bump_attempts=bump)
        elif reply.kind == "accepted":
            await save_job_state(
                session,
                snapshot["job_id"],
                state="awaiting_callback",
                updated_at=now,
                available_at=now + timedelta(seconds=settings.callback_deadline_seconds),
                bump_attempts=bump,
            )
        else:
            await save_job_state(
                session,
                snapshot["job_id"],
                state="retry_wait",
                updated_at=now,
                available_at=now + timedelta(seconds=1),
                needs_enqueue=False,
                bump_attempts=bump,
            )
        await session.commit()
