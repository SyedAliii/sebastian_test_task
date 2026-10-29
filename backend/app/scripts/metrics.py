import argparse
import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine, text

from app.config import Settings

_UNCHECKED = """
select count(*)
from media m
where m.status = 'published'
  and m.created_at >= :since
  and not exists (
    select 1 from screening_decisions d
    where d.media_id = m.id and d.source = 'provider'
  )
"""

_OLDEST = """
select extract(epoch from (now() - min(j.created_at)))
from jobs j
join media m on m.id = j.media_id
where j.state <> 'succeeded'
  and m.created_at >= :since
"""

_MEDIA_IDS = """
select id::text
from media
where created_at >= :since
"""


def collect_metrics(since: datetime, settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    engine = create_engine(settings.alembic_database_url)
    with engine.connect() as connection:
        unchecked = connection.execute(text(_UNCHECKED), {"since": since}).scalar_one()
        oldest = connection.execute(text(_OLDEST), {"since": since}).scalar_one()
        media_ids = [row[0] for row in connection.execute(text(_MEDIA_IDS), {"since": since})]
    engine.dispose()
    if not media_ids:
        calls_per_upload = 0
    else:
        stats = httpx.get(f"{settings.provider_base_url.rstrip('/')}/_stats", timeout=5).json()
        counts = stats.get("calls", {})
        calls_per_upload = sum(int(counts.get(media_id, 0)) for media_id in media_ids) / len(media_ids)
    if oldest is None:
        oldest_waiting = 0
    else:
        oldest_waiting = float(oldest)
        if oldest_waiting == int(oldest_waiting):
            oldest_waiting = int(oldest_waiting)
    if isinstance(calls_per_upload, float) and calls_per_upload == int(calls_per_upload):
        calls_per_upload = int(calls_per_upload)
    return {
        "published_unchecked": int(unchecked or 0),
        "provider_calls_per_upload": calls_per_upload,
        "oldest_waiting_seconds": oldest_waiting,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True)
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since)
    print(json.dumps(collect_metrics(since)))


if __name__ == "__main__":
    main()
