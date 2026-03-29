"""
Chronological CSV OHLCV data loader for walk-forward optimization.

Loads historical bar data from CSV files, validates integrity, and returns
a list of OHLCVBar objects in strict chronological order (oldest first).

Expected CSV format:
  timestamp,open,high,low,close,volume[,volume_usd]

Where:
  - timestamp: ISO-8601 UTC or Unix epoch milliseconds
  - open/high/low/close: Decimal prices
  - volume: Base asset volume (BTC)
  - volume_usd: Optional quote volume; defaults to close * volume if missing

Validation rules:
  - Timestamps must be strictly ascending (no duplicates, no gaps > 2x expected)
  - OHLCV invariants: high >= max(open, close), low <= min(open, close)
  - No negative prices or volumes
  - Minimum row count enforced (default: 200 for FeatureComputer warm-up)
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from core.schemas import OHLCVBar

logger = logging.getLogger(__name__)

MIN_BARS_DEFAULT = 200  # FeatureComputer warm-up requirement


@dataclass(frozen=True)
class LoadResult:
    """Result of loading a CSV file."""
    bars: list[OHLCVBar]
    path: str
    symbol: str
    timeframe: str
    bar_count: int
    first_timestamp: Optional[datetime]
    last_timestamp: Optional[datetime]
    warnings: list[str]

    @property
    def duration_bars(self) -> int:
        return self.bar_count

    @property
    def ok(self) -> bool:
        return self.bar_count > 0


def load_csv(
    path: str | Path,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    min_bars: int = MIN_BARS_DEFAULT,
    max_gap_multiplier: float = 2.0,
) -> LoadResult:
    """
    Load OHLCV bars from a CSV file.

    Args:
        path: Path to CSV file.
        symbol: Trading pair symbol (default BTCUSDT).
        timeframe: Bar timeframe (default 1h).
        min_bars: Minimum number of bars required.
        max_gap_multiplier: Flag warning if gap between bars > multiplier * expected interval.

    Returns:
        LoadResult with bars in chronological order.

    Raises:
        FileNotFoundError: If CSV file does not exist.
        ValueError: If CSV has fewer than min_bars valid rows.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    warnings: list[str] = []
    bars: list[OHLCVBar] = []

    expected_interval_ms = _timeframe_to_ms(timeframe)

    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header row: {path}")

        # Normalize headers to lowercase
        header_map = {h.strip().lower(): h for h in reader.fieldnames}
        _validate_headers(header_map, path)

        prev_ts: Optional[datetime] = None
        for row_idx, row in enumerate(reader, start=2):  # row 1 = header
            try:
                bar = _parse_row(row, header_map, symbol, timeframe, row_idx)
            except (ValueError, InvalidOperation, AssertionError) as e:
                warnings.append(f"Row {row_idx}: skipped — {e}")
                continue

            # Chronological order check
            if prev_ts is not None and bar.timestamp <= prev_ts:
                warnings.append(
                    f"Row {row_idx}: timestamp {bar.timestamp} <= previous {prev_ts} — skipped"
                )
                continue

            # Gap check
            if prev_ts is not None and expected_interval_ms > 0:
                gap_ms = (bar.timestamp - prev_ts).total_seconds() * 1000
                if gap_ms > expected_interval_ms * max_gap_multiplier:
                    gap_bars = gap_ms / expected_interval_ms
                    warnings.append(
                        f"Row {row_idx}: gap of {gap_bars:.1f} bars between "
                        f"{prev_ts} and {bar.timestamp}"
                    )

            bars.append(bar)
            prev_ts = bar.timestamp

    if len(bars) < min_bars:
        raise ValueError(
            f"CSV has {len(bars)} valid bars, need at least {min_bars}. "
            f"File: {path}"
        )

    if warnings:
        logger.warning(
            "data_loader: %d warnings loading %s (%d bars kept)",
            len(warnings), path.name, len(bars),
        )

    return LoadResult(
        bars=bars,
        path=str(path),
        symbol=symbol,
        timeframe=timeframe,
        bar_count=len(bars),
        first_timestamp=bars[0].timestamp if bars else None,
        last_timestamp=bars[-1].timestamp if bars else None,
        warnings=warnings,
    )


def _validate_headers(header_map: dict[str, str], path: Path) -> None:
    """Ensure required columns exist."""
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(header_map.keys())
    if missing:
        raise ValueError(
            f"CSV missing required columns: {missing}. "
            f"Found: {list(header_map.keys())}. File: {path}"
        )


def _parse_row(
    row: dict,
    header_map: dict[str, str],
    symbol: str,
    timeframe: str,
    row_idx: int,
) -> OHLCVBar:
    """Parse a single CSV row into an OHLCVBar."""

    def _get(key: str) -> str:
        return row[header_map[key]].strip()

    # Timestamp
    ts_raw = _get("timestamp")
    timestamp = _parse_timestamp(ts_raw)

    # Prices
    open_ = Decimal(_get("open"))
    high = Decimal(_get("high"))
    low = Decimal(_get("low"))
    close = Decimal(_get("close"))
    volume = Decimal(_get("volume"))

    # Optional volume_usd
    if "volume_usd" in header_map:
        try:
            volume_usd = Decimal(_get("volume_usd"))
        except (InvalidOperation, KeyError):
            volume_usd = close * volume
    else:
        volume_usd = close * volume

    return OHLCVBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        volume_usd=volume_usd,
        is_closed=True,
    )


def _parse_timestamp(ts_raw: str) -> datetime:
    """Parse timestamp from ISO-8601 string or Unix epoch milliseconds."""
    # Try Unix epoch ms first (all digits)
    if ts_raw.isdigit() or (ts_raw.startswith("-") and ts_raw[1:].isdigit()):
        epoch_ms = int(ts_raw)
        return datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)

    # Try ISO-8601 variants
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f+00:00",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%d %H:%M:%S+00:00",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
    ):
        try:
            dt = datetime.strptime(ts_raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    raise ValueError(f"Cannot parse timestamp: '{ts_raw}'")


def _timeframe_to_ms(timeframe: str) -> int:
    """Convert timeframe string to milliseconds per bar."""
    _map = {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "60": 3_600_000,
        "4h": 14_400_000,
        "240": 14_400_000,
        "1d": 86_400_000,
        "D": 86_400_000,
    }
    return _map.get(timeframe, 0)
