"""
Bar-to-elapsed-time conversion utility.

Converts raw bar counts to human-readable elapsed time based on timeframe.

Timeframe rules:
  - "1h"  / "60"   → 1 bar = 1 hour
  - "4h"  / "240"  → 1 bar = 4 hours
  - "15m" / "15"   → 1 bar = 15 minutes
  - "1d"  / "D"    → 1 bar = 1 day

Usage:
  bars_to_duration(5, "1h")     → "5 hours"
  bars_to_duration(3, "1d")     → "3 days"
  bars_to_duration(8, "15m")    → "2 hours"
  format_bars(5, "1h")          → "5 bars (5 hours)"
  format_bars(20, "1h")         → "20 bars (20 hours)"
"""
from __future__ import annotations


# Timeframe → minutes per bar
_TIMEFRAME_MINUTES: dict[str, int] = {
    "1m":  1,
    "5m":  5,
    "15m": 15,
    "15":  15,
    "30m": 30,
    "30":  30,
    "1h":  60,
    "60":  60,
    "4h":  240,
    "240": 240,
    "1d":  1440,
    "D":   1440,
}

# Default timeframe for the BTC/Bybit system
DEFAULT_TIMEFRAME = "1h"


def timeframe_minutes(timeframe: str) -> int | None:
    """Return the number of minutes per bar for a given timeframe string.
    Returns None if the timeframe is not recognized."""
    return _TIMEFRAME_MINUTES.get(timeframe)


def bars_to_minutes(bars: int, timeframe: str = DEFAULT_TIMEFRAME) -> int | None:
    """Convert bar count to total minutes. Returns None if timeframe unknown."""
    m = timeframe_minutes(timeframe)
    if m is None:
        return None
    return bars * m


def bars_to_duration(bars: int, timeframe: str = DEFAULT_TIMEFRAME) -> str:
    """
    Convert bar count to a human-readable duration string.

    Examples:
        bars_to_duration(5, "1h")   → "5 hours"
        bars_to_duration(3, "1d")   → "3 days"
        bars_to_duration(8, "15m")  → "2 hours"
        bars_to_duration(36, "1h")  → "1 day 12 hours"
        bars_to_duration(0, "1h")   → "0 hours"
    """
    total_minutes = bars_to_minutes(bars, timeframe)
    if total_minutes is None:
        return f"{bars} bars (timeframe '{timeframe}' unknown)"

    if total_minutes == 0:
        return "0 hours" if timeframe in ("1h", "60") else "0 minutes"

    days = total_minutes // 1440
    remaining = total_minutes % 1440
    hours = remaining // 60
    minutes = remaining % 60

    parts: list[str] = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    return " ".join(parts) if parts else "0 minutes"


def format_bars(bars: int, timeframe: str = DEFAULT_TIMEFRAME) -> str:
    """
    Format bar count with elapsed time in parentheses.

    Examples:
        format_bars(5, "1h")    → "5 bars (5 hours)"
        format_bars(20, "1h")   → "20 bars (20 hours)"
        format_bars(3, "1d")    → "3 bars (3 days)"
        format_bars(8, "15m")   → "8 bars (2 hours)"
        format_bars(1, "1h")    → "1 bar (1 hour)"
    """
    bar_word = "bar" if bars == 1 else "bars"
    duration = bars_to_duration(bars, timeframe)
    return f"{bars} {bar_word} ({duration})"
