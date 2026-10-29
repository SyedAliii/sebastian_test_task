import asyncio

from redis.asyncio import Redis

from app.clients.provider_client import ProviderClient
from app.config import Settings
from app.core.logging.logger import apply_log_settings, log_level_banner, logger
from app.db.session import create_session_factory
from app.repo.queues import Queues
from app.services.worker_service import FairCursor, process_one


async def _loop() -> None:
    settings = Settings()
    apply_log_settings(settings)
    log_level_banner("moderation-worker")
    logger.system_info("process=worker")
    engine, session_factory = create_session_factory(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    queues = Queues(redis)
    provider = ProviderClient(settings)
    cursor = FairCursor()
    try:
        while True:
            try:
                worked = await process_one(session_factory, queues, provider, settings, cursor=cursor)
            except Exception as exc:
                logger.error_trace(f"process=worker error={type(exc).__name__}: {exc}", exc_info=exc)
                worked = False
            if not worked:
                await asyncio.sleep(0.2)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(_loop())


if __name__ == "__main__":
    main()
