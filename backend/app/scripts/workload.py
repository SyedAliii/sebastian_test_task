import argparse
import json
import threading
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine, text

from app.config import Settings
from app.scripts.metrics import collect_metrics

HEADERS_U = {"X-User-Id": "member_u", "X-Workspace-Id": "ws_unverified"}
HEADERS_V = {"X-User-Id": "member_v", "X-Workspace-Id": "ws_verified"}


def _sync_engine(settings: Settings):
    return create_engine(settings.alembic_database_url)


def _pending_videos(settings: Settings, since: datetime) -> int:
    engine = _sync_engine(settings)
    with engine.connect() as connection:
        count = connection.execute(
            text(
                """
                select count(*)
                from media
                where workspace_id = 'ws_unverified'
                  and status = 'pending'
                  and created_at >= :since
                """
            ),
            {"since": since},
        ).scalar_one()
    engine.dispose()
    return int(count)


def _still_recovering(settings: Settings, since: datetime) -> int:
    engine = _sync_engine(settings)
    with engine.connect() as connection:
        count = connection.execute(
            text(
                """
                select count(*)
                from media
                where created_at >= :since
                  and (
                    status = 'pending'
                    or (status = 'held' and hold_reason = 'no_decision')
                  )
                """
            ),
            {"since": since},
        ).scalar_one()
    engine.dispose()
    return int(count)


def _post_media(api: str, headers: dict, body: dict) -> str:
    response = httpx.post(f"{api}/media", headers=headers, json=body, timeout=30)
    response.raise_for_status()
    return response.json()["id"]


def _video_body(frame_count: int) -> dict:
    frames = [{"explicit": 0.1} for _ in range(frame_count - 1)]
    frames.append({"explicit": 0.95})
    return {"type": "video", "source": "upload", "frames": frames}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", type=int, default=200)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--outage", action="store_true")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    settings = Settings()
    provider = settings.provider_base_url.rstrip("/")
    start = datetime.now(timezone.utc)
    mode = "timeout" if args.outage else "ok"
    httpx.post(f"{provider}/_control", json={"mode": mode, "delay_ms": 0}, timeout=10).raise_for_status()

    images: list[dict] = []

    def post_images() -> None:
        for index in range(5):
            if index:
                time.sleep(2)
            images.append(
                {
                    "id": _post_media(args.api, HEADERS_V, {"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]}),
                    "started": time.monotonic(),
                    "status": "pending",
                    "seconds": None,
                    "videos_pending": None,
                }
            )

    first = _post_media(args.api, HEADERS_U, _video_body(args.frames))
    image_thread = threading.Thread(target=post_images)
    image_thread.start()
    for _ in range(args.videos - 1):
        _post_media(args.api, HEADERS_U, _video_body(args.frames))
    image_thread.join()

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        pending_videos = _pending_videos(settings, start)
        still_pending = False
        for image in images:
            if image["status"] != "pending":
                continue
            response = httpx.get(f"{args.api}/media/{image['id']}", headers=HEADERS_V, timeout=10)
            response.raise_for_status()
            status = response.json()["status"]
            if status == "pending":
                still_pending = True
                continue
            image["status"] = status
            image["seconds"] = round(time.monotonic() - image["started"], 1)
            image["videos_pending"] = pending_videos
        if images and not still_pending:
            break
        time.sleep(1)

    for image in images:
        print(
            f"image={image['id']} status={image['status']} seconds={image['seconds']} "
            f"videos_pending={image['videos_pending']}"
        )
    print(json.dumps(collect_metrics(start, settings)))
    if args.outage:
        httpx.post(f"{provider}/_control", json={"mode": "ok", "delay_ms": 0}, timeout=10).raise_for_status()
        recover_until = time.monotonic() + 180
        while time.monotonic() < recover_until and _still_recovering(settings, start):
            time.sleep(1)
        print(json.dumps(collect_metrics(start, settings)))
    if not first:
        return


if __name__ == "__main__":
    main()
