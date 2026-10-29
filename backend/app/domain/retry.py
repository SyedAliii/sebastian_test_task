def retry_limit(kind: str, settings) -> int:
    limits = {
        "timeout": settings.retry_timeout_max,
        "http_429": settings.retry_429_max,
        "http_500": settings.retry_500_max,
        "malformed": settings.retry_malformed_max,
    }
    return limits.get(kind, settings.retry_500_max)


def retry_delay_seconds(kind: str, attempts_used: int, retry_after: int | None, settings) -> float:
    if kind == "timeout":
        return settings.retry_base_seconds * (2 ** (attempts_used - 1))
    if kind == "http_429":
        stated = retry_after if retry_after is not None else 0
        return max(float(stated), settings.retry_429_min_seconds)
    return settings.retry_base_seconds


def should_park(kind: str, attempts_used: int, settings) -> bool:
    return attempts_used >= retry_limit(kind, settings)
