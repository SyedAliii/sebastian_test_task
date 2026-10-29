import time

from app.config import Settings
from app.core.logging.logger import apply_log_settings, log_level_banner, logger


def main() -> None:
    settings = Settings()
    apply_log_settings(settings)
    log_level_banner("moderation-scheduler")
    logger.system_info("process=scheduler")
    while True:
        time.sleep(5)


if __name__ == "__main__":
    main()
