import asyncio
import time

from redis.asyncio import Redis

from app.config import Settings
from app.core.logging.logger import apply_log_settings, log_level_banner, logger
from app.db.session import create_session_factory
from app.repo.queues import Queues
from app.services.scheduler_service import run_probe, tick


async def _loop() -> None:
    settings = Settings()
    apply_log_settings(settings)
    log_level_banner("moderation-scheduler")
    logger.system_info("process=scheduler")
    engine, session_factory = create_session_factory(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    queues = Queues(redis)
    last_probe = time.monotonic()
    try:
        while True:
            try:
                await tick(session_factory, queues)
                now = time.monotonic()
                if now - last_probe >= settings.probe_interval_seconds:
                    await run_probe(session_factory)
                    last_probe = now
            except Exception as exc:
                logger.error_trace(f"process=scheduler error={type(exc).__name__}: {exc}", exc_info=exc)
            await asyncio.sleep(settings.scheduler_interval_seconds)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(_loop())


if __name__ == "__main__":
    main()
