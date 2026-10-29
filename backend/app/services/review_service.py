import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db.models import Media
from app.repo.decision_repo import insert_decision
from app.repo.media_repo import list_review


class ReviewService:
    def __init__(self, session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def list_held(self, workspace_id: str) -> list[dict]:
        try:
            return await list_review(self._session, workspace_id)
        except SQLAlchemyError:
            if self._settings.screening_mode == "broken":
                return []
            raise

    async def resolve(self, workspace_id: str, media_id: str, admin_id: str, status: str) -> str:
        try:
            parsed = uuid.UUID(media_id)
        except ValueError:
            return "not_found"
        row = await self._session.scalar(select(Media).where(Media.id == parsed))
        if row is None or row.workspace_id != workspace_id:
            return "not_found"
        if row.status != "held" or row.hold_reason != "review":
            return "conflict"
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            update(Media)
            .where(
                Media.id == parsed,
                Media.workspace_id == workspace_id,
                Media.hold_reason == "review",
            )
            .values(status=status, hold_reason=None, updated_at=now)
        )
        if result.rowcount == 0:
            return "conflict"
        await insert_decision(
            self._session,
            media_id=parsed,
            source="admin",
            scores=None,
            outcome=status,
            reasons=[],
            decided_by=admin_id,
            created_at=now,
        )
        await self._session.commit()
        return "ok"
