import logging

import httpx

logger = logging.getLogger("provider")


async def send_callback(url: str, raw: bytes, signature: str, media_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                url,
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": signature,
                },
            )
    except Exception as exc:
        logger.error(
            "media_id=%s outcome=callback_failed error=%s",
            media_id,
            type(exc).__name__,
        )
        return
    if response.status_code != 200:
        logger.error(
            "media_id=%s outcome=callback_failed status_code=%s",
            media_id,
            response.status_code,
        )
        return
    logger.info(
        "media_id=%s outcome=callback_sent status_code=%s",
        media_id,
        response.status_code,
    )
