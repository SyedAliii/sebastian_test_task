import uuid
from datetime import datetime, timedelta, timezone

import httpx
import respx

from app.config import Settings
from app.db.models import Media, ScreeningDecision
from app.scripts.metrics import collect_metrics


async def test_published_unchecked_ignores_older_rows(db_session) -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=5)
    old = uuid.uuid4()
    unchecked = uuid.uuid4()
    checked = uuid.uuid4()
    async with db_session() as session:
        session.add_all(
            [
                _published(old, "member_v", "ws_verified", since - timedelta(minutes=10)),
                _published(unchecked, "member_v", "ws_verified", since + timedelta(minutes=1)),
                _published(checked, "member_u", "ws_unverified", since + timedelta(minutes=1)),
            ]
        )
        await session.flush()
        session.add(
            ScreeningDecision(
                id=uuid.uuid4(),
                media_id=checked,
                source="provider",
                scores=[{"explicit": 0.1}],
                outcome="published",
                reasons=[],
                decided_by=None,
                created_at=now,
            )
        )
        await session.commit()
    settings = Settings().model_copy(
        update={
            "alembic_database_url": Settings().alembic_database_url_test,
            "provider_base_url": "http://provider.test",
        }
    )
    with respx.mock:
        respx.get("http://provider.test/_stats").mock(
            return_value=httpx.Response(200, json={"calls": {str(unchecked): 1, str(checked): 1}})
        )
        metrics = collect_metrics(since, settings)
    assert metrics["published_unchecked"] == 1
    assert metrics["provider_calls_per_upload"] == 1


def _published(media_id: uuid.UUID, user_id: str, workspace_id: str, created_at: datetime) -> Media:
    return Media(
        id=media_id,
        workspace_id=workspace_id,
        submitted_by=user_id,
        type="image",
        source="upload",
        prompt=None,
        frames=[{"explicit": 0.1}],
        frame_count=1,
        status="published",
        hold_reason=None,
        reasons=[],
        created_at=created_at,
        updated_at=created_at,
    )
