import uuid
from datetime import datetime, timezone

from app.core.logging.logger import logger
from app.db.models import User
from app.domain.schemas import MediaCreated, MediaIn, MediaOut
from app.repo.job_repo import clear_needs_enqueue, insert_job
from app.repo.media_repo import get_media_for_workspace, insert_media
from app.repo.queues import Queues


class MediaService:
    def __init__(self, session, queues: Queues) -> None:
        self._session = session
        self._queues = queues

    async def create_media(
        self,
        caller: User,
        body: MediaIn,
        correlation_id: str | None = None,
    ) -> MediaCreated:
        now = datetime.now(timezone.utc)
        media_id = uuid.uuid4()
        job_id = uuid.uuid4()
        await insert_media(
            self._session,
            media_id=media_id,
            workspace_id=caller.workspace_id,
            submitted_by=caller.id,
            media_type=body.type,
            source=body.source,
            prompt=body.prompt,
            frames=body.frames,
            created_at=now,
        )
        await self._session.flush()
        await insert_job(
            self._session,
            job_id=job_id,
            media_id=media_id,
            workspace_id=caller.workspace_id,
            available_at=now,
        )
        await self._session.commit()
        try:
            await self._queues.enqueue(caller.workspace_id, str(job_id))
        except Exception as exc:
            logger.warning(
                f"workspace_id={caller.workspace_id} media_id={media_id} job_id={job_id} step=enqueue_failed error={type(exc).__name__}",
                correlation_id=correlation_id,
            )
            return MediaCreated(id=str(media_id), status="pending")
        await clear_needs_enqueue(self._session, job_id, datetime.now(timezone.utc))
        await self._session.commit()
        logger.pipeline(
            f"workspace_id={caller.workspace_id} media_id={media_id} job_id={job_id} attempt=- step=accepted",
            correlation_id=correlation_id,
        )
        return MediaCreated(id=str(media_id), status="pending")

    async def get_media(self, caller: User, media_id: str) -> MediaOut | None:
        try:
            parsed = uuid.UUID(media_id)
        except ValueError:
            return None
        row = await get_media_for_workspace(self._session, parsed, caller.workspace_id)
        if row is None:
            return None
        return MediaOut(id=str(row.id), status=row.status, reasons=row.reasons)
