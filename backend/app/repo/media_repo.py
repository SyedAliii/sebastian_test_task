import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Media


async def insert_media(
    session: AsyncSession,
    *,
    media_id: uuid.UUID,
    workspace_id: str,
    submitted_by: str,
    media_type: str,
    source: str,
    prompt: str | None,
    frames: list,
    created_at: datetime,
) -> None:
    session.add(
        Media(
            id=media_id,
            workspace_id=workspace_id,
            submitted_by=submitted_by,
            type=media_type,
            source=source,
            prompt=prompt,
            frames=frames,
            frame_count=len(frames),
            status="pending",
            hold_reason=None,
            reasons=[],
            created_at=created_at,
            updated_at=created_at,
        )
    )


async def get_media_for_workspace(
    session: AsyncSession,
    media_id: uuid.UUID,
    workspace_id: str,
) -> Media | None:
    return await session.scalar(
        select(Media).where(Media.id == media_id, Media.workspace_id == workspace_id)
    )


async def list_review(session: AsyncSession, workspace_id: str) -> list[dict]:
    rows = (
        await session.execute(
            select(Media.id, Media.status, Media.reasons).where(
                Media.workspace_id == workspace_id,
                Media.status == "held",
                Media.hold_reason == "review",
            )
        )
    ).all()
    return [{"id": str(row.id), "status": row.status, "reasons": row.reasons} for row in rows]


async def apply_media_status(
    session: AsyncSession,
    media_id: uuid.UUID,
    *,
    status: str,
    hold_reason: str | None,
    reasons: list,
    updated_at: datetime,
) -> None:
    await session.execute(
        update(Media)
        .where(Media.id == media_id)
        .values(status=status, hold_reason=hold_reason, reasons=reasons, updated_at=updated_at)
    )
