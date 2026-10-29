import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Media, User
from app.db.seed import seed


async def test_seed_inserts_four_users(db_session) -> None:
    async with db_session() as session:
        result = await session.execute(select(User.id))
        assert set(result.scalars().all()) == {"admin_v", "member_v", "admin_u", "member_u"}


async def test_seed_is_safe_twice(db_session) -> None:
    async with db_session() as session:
        await seed(session)
        await session.commit()
        result = await session.execute(select(User.id))
        assert set(result.scalars().all()) == {"admin_v", "member_v", "admin_u", "member_u"}


async def test_image_frame_count_check(db_session) -> None:
    now = datetime.now(timezone.utc)
    async with db_session() as session:
        session.add(
            Media(
                id=uuid.uuid4(),
                workspace_id="ws_verified",
                submitted_by="admin_v",
                type="image",
                source="upload",
                prompt=None,
                frames=[{"explicit": 0.1}, {"explicit": 0.2}],
                frame_count=2,
                status="pending",
                hold_reason=None,
                reasons=[],
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
