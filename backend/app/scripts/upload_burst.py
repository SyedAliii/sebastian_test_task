import argparse
import threading
import time

import httpx

HEADERS_U = {"X-User-Id": "member_u", "X-Workspace-Id": "ws_unverified"}
HEADERS_V = {"X-User-Id": "member_v", "X-Workspace-Id": "ws_verified"}


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
    parser.add_argument("--images", type=int, default=5)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    image_ids: list[str] = []

    def post_images() -> None:
        for index in range(args.images):
            if index:
                time.sleep(2)
            media_id = _post_media(
                args.api,
                HEADERS_V,
                {"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]},
            )
            image_ids.append(media_id)
            print(f"image={media_id}")

    first_video = _post_media(args.api, HEADERS_U, _video_body(args.frames))
    print(f"video={first_video}")
    image_thread = threading.Thread(target=post_images)
    image_thread.start()
    for _ in range(args.videos - 1):
        media_id = _post_media(args.api, HEADERS_U, _video_body(args.frames))
        print(f"video={media_id}")
    image_thread.join()
    print(f"uploaded videos={args.videos} images={len(image_ids)}")


if __name__ == "__main__":
    main()
