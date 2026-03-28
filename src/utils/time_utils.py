"""Time utilities. All times in UTC. No naive datetimes in the system."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


def bar_open_time(close_time: datetime, timeframe: str) -> datetime:
    """
    Compute bar open time from close time and timeframe string.
    timeframe: "1d" | "4h" | "1h"
    """
    from datetime import timedelta
    offsets = {
        "1d": timedelta(days=1),
        "4h": timedelta(hours=4),
        "1h": timedelta(hours=1),
    }
    offset = offsets.get(timeframe)
    if offset is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")
    return close_time - offset
