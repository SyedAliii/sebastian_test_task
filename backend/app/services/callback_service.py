import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging.logger import logger
from app.db.models import Job, Media, Workspace
from app.domain.decide import decide
from app.domain.labels import LABELS
from app.repo.decision_repo import insert_decision, provider_decision_exists
from app.repo.job_repo import release_parked_jobs, save_job_state
from app.repo.media_repo import apply_media_status


@dataclass(frozen=True)
class CallbackResult:
    status_code: int
    body: dict


class CallbackService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply(self, raw: bytes, correlation_id: str | None = None) -> CallbackResult:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return CallbackResult(400, {"detail": "malformed callback"})
        if not isinstance(payload, dict):
            return CallbackResult(400, {"detail": "malformed callback"})
        try:
            media_id = uuid.UUID(str(payload.get("media_id")))
        except (TypeError, ValueError):
            return CallbackResult(404, {"detail": "not found"})
        row = (
            await self._session.execute(
                select(
                    Media.frame_count,
                    Workspace.verified,
                    Job.id.label("job_id"),
                )
                .join(Workspace, Workspace.id == Media.workspace_id)
                .outerjoin(Job, Job.media_id == Media.id)
                .where(Media.id == media_id)
            )
        ).one_or_none()
        if row is None:
            return CallbackResult(404, {"detail": "not found"})
        if await provider_decision_exists(self._session, media_id):
            return CallbackResult(200, {"status": "ok"})
        frames = payload.get("frames")
        if not _frames_ok(frames, row.frame_count):
            return CallbackResult(400, {"detail": "malformed callback"})
        decision = decide(frames, row.verified)
        now = datetime.now(timezone.utc)
        await insert_decision(
            self._session,
            media_id=media_id,
            source="provider",
            scores=frames,
            outcome=decision.status,
            reasons=decision.reasons,
            decided_by=None,
            created_at=now,
        )
        await apply_media_status(
            self._session,
            media_id,
            status=decision.status,
            hold_reason=decision.hold_reason,
            reasons=decision.reasons,
            updated_at=now,
        )
        if row.job_id is not None:
            await save_job_state(self._session, row.job_id, state="succeeded", updated_at=now, clear_lease=True)
        await release_parked_jobs(self._session)
        await self._session.commit()
        logger.webhook_in("provider", source="provider")
        return CallbackResult(200, {"status": "ok"})


def _frames_ok(frames: object, frame_count: int) -> bool:
    if not isinstance(frames, list) or len(frames) != frame_count:
        return False
    for frame in frames:
        if not isinstance(frame, dict) or any(label not in frame for label in LABELS):
            return False
    return True
