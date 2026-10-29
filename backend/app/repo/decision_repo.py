import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScreeningDecision


async def provider_decision_exists(session: AsyncSession, media_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(ScreeningDecision.id).where(
            ScreeningDecision.media_id == media_id,
            ScreeningDecision.source == "provider",
        )
    )
    return found is not None


async def insert_decision(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    source: str,
    scores: list | None,
    outcome: str,
    reasons: list,
    decided_by: str | None,
    created_at: datetime,
) -> None:
    session.add(
        ScreeningDecision(
            id=uuid.uuid4(),
            media_id=media_id,
            source=source,
            scores=scores,
            outcome=outcome,
            reasons=reasons,
            decided_by=decided_by,
            created_at=created_at,
        )
    )
