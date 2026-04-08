#!/usr/bin/env python3
"""
Download historical 1h OHLCV kline data from Bybit V5 public API for
offline learning loop training data.

Downloads BTC, ETH, BNB for two key historical periods:
  Period 1: 2020-01-01 → 2021-12-31  (COVID recovery + 2021 bull run)
  Period 2: 2022-01-01 → 2022-12-31  (bear market + FTX collapse)

These periods cover fundamentally different market regimes, providing
diverse training data for the evaluator weight learning system.

Output files:
  analysis/historical_eval/data/btcusdt_1h_2020_2021.csv
  analysis/historical_eval/data/btcusdt_1h_2022.csv
  analysis/historical_eval/data/ethusdt_1h_2020_2021.csv
  analysis/historical_eval/data/ethusdt_1h_2022.csv
  analysis/historical_eval/data/bnbusdt_1h_2020_2021.csv
  analysis/historical_eval/data/bnbusdt_1h_2022.csv

Usage:
  python src/scripts/download_history.py                    # all symbols + periods
  python src/scripts/download_history.py --symbol BTCUSDT   # BTC only
  python src/scripts/download_history.py --period 2022      # 2022 only
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BYBIT_KLINES  = "https://api.bybit.com/v5/market/kline"
INTERVAL      = "60"           # 1h bars
PAGE_LIMIT    = 1000           # Bybit V5 max per request
REQUEST_DELAY = 1.2            # seconds between pages
MAX_RETRIES   = 5              # retries on rate-limit (10006) with exponential backoff

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
DATA_DIR = os.path.join(_PROJECT_ROOT, "analysis", "historical_eval", "data")

# Historical periods for training data
PERIODS: dict[str, tuple[int, int, str]] = {
    # name → (start_ms, end_ms_exclusive, label)
    "2020_2021": (
        1577836800000,   # 2020-01-01T00:00:00Z
        1640995200000,   # 2022-01-01T00:00:00Z (exclusive)
        "2020-01-01 → 2021-12-31",
    ),
    "2022": (
        1640995200000,   # 2022-01-01T00:00:00Z
        1672531200000,   # 2023-01-01T00:00:00Z (exclusive)
        "2022-01-01 → 2022-12-31",
    ),
}

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]


# ---------------------------------------------------------------------------
# Fetch helpers (same pattern as download_data.py)
# ---------------------------------------------------------------------------

def _fetch_page(client: httpx.Client, symbol: str, end_ms: int) -> list[list]:
    """Fetch one page of klines ending at end_ms. Returns newest-first list."""
    params = {
        "category": "linear",
        "symbol":   symbol,
        "interval": INTERVAL,
        "limit":    PAGE_LIMIT,
        "end":      end_ms,
    }
    for attempt in range(MAX_RETRIES):
        resp = client.get(BYBIT_KLINES, params=params)
        resp.raise_for_status()
        payload = resp.json()
        ret_code = payload.get("retCode", -1)
        if ret_code == 0:
            return payload["result"]["list"]
        if ret_code == 10006:
            wait = 2 ** attempt * 3   # 3, 6, 12, 24, 48 seconds
            print(f"  [rate limit] attempt {attempt+1}/{MAX_RETRIES} — sleeping {wait}s ...")
            time.sleep(wait)
            continue
        raise RuntimeError(
            f"Bybit API error retCode={ret_code} retMsg={payload.get('retMsg')}"
        )
    raise RuntimeError(f"Bybit rate limit persists after {MAX_RETRIES} retries")


def download_period(
    symbol: str,
    period_name: str,
    out_path: str,
) -> int:
    """
    Download klines for symbol over a named period and write CSV.

    Uses INSERT OR IGNORE semantics: if the file already exists and has
    data for this period, it will be preserved (re-downloads are deduped).

    Returns the number of bars written.
    """
    start_ms, end_ms, label = PERIODS[period_name]
    symbol = symbol.upper()

    print(f"\n{'='*60}")
    print(f"Downloading {symbol} 1h bars — {label}")
    print(f"  Output: {out_path}")
    print(f"{'='*60}")

    all_rows: list[list] = []
    cur_end_ms = end_ms

    with httpx.Client(timeout=30) as client:
        while True:
            rows = _fetch_page(client, symbol, cur_end_ms)
            if not rows:
                break

            oldest_ms = int(rows[-1][0])

            # Keep only bars within [start_ms, end_ms)
            in_range = [r for r in rows if start_ms <= int(r[0]) < end_ms]
            all_rows.extend(in_range)

            oldest_dt = datetime.fromtimestamp(oldest_ms / 1000, tz=timezone.utc)
            print(
                f"  page: {len(rows)} bars  "
                f"oldest={oldest_dt.strftime('%Y-%m-%d %H:%M')}  "
                f"kept={len(in_range)}  total={len(all_rows)}"
            )

            if oldest_ms <= start_ms:
                break

            cur_end_ms = oldest_ms
            time.sleep(REQUEST_DELAY)

    if not all_rows:
        print(f"WARNING: no bars fetched for {symbol} {period_name}")
        return 0

    # Sort oldest-first and deduplicate by timestamp
    seen: set[int] = set()
    unique: list[list] = []
    for row in sorted(all_rows, key=lambda r: int(r[0])):
        ts_ms = int(row[0])
        if ts_ms not in seen:
            seen.add(ts_ms)
            unique.append(row)

    # Load existing data if file already exists (dedup across re-runs)
    existing_rows: dict[int, list] = {}
    if os.path.exists(out_path):
        with open(out_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    ts_ms = int(ts.timestamp() * 1000)
                    existing_rows[ts_ms] = [
                        ts_ms,
                        row["open"], row["high"], row["low"], row["close"],
                        row["volume"], row["volume_usd"],
                    ]
                except Exception:
                    pass
        print(f"  [dedup] loaded {len(existing_rows)} existing rows from {out_path}")

    # Merge: new data wins if same timestamp
    for row in unique:
        existing_rows[int(row[0])] = row

    final_rows = sorted(existing_rows.values(), key=lambda r: int(r[0]))

    # Write CSV
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "volume_usd"])
        for row in final_rows:
            ts_ms_val = int(row[0])
            ts_iso = datetime.fromtimestamp(ts_ms_val / 1000, tz=timezone.utc).isoformat()
            writer.writerow([ts_iso, row[1], row[2], row[3], row[4], row[5], row[6]])

    print(f"\n✓ Saved {len(final_rows):,} bars → {out_path}")
    return len(final_rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download historical OHLCV data for offline learning."
    )
    parser.add_argument(
        "--symbol", "-s",
        nargs="+",
        default=SYMBOLS,
        help=f"Symbols to download (default: {' '.join(SYMBOLS)})",
    )
    parser.add_argument(
        "--period", "-p",
        nargs="+",
        choices=list(PERIODS.keys()),
        default=list(PERIODS.keys()),
        help=f"Periods to download (default: all). Options: {', '.join(PERIODS.keys())}",
    )
    args = parser.parse_args()

    symbols = [s.upper() for s in args.symbol]
    periods = args.period

    results: dict[str, int] = {}

    for symbol in symbols:
        for period in periods:
            fname = f"{symbol.lower()}_1h_{period}.csv"
            path = os.path.join(DATA_DIR, fname)
            n = download_period(symbol, period, path)
            results[f"{symbol}/{period}"] = n

    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)
    total_bars = 0
    for key, n in results.items():
        expected = 8760 if "2022" in key else 17520
        status = "OK" if n >= expected * 0.9 else "WARNING: fewer bars than expected"
        print(f"  {key:<30}: {n:>7,} bars  [{status}]")
        total_bars += n
    print(f"  {'TOTAL':<30}: {total_bars:>7,} bars")
    print("=" * 60)
    print()
    print("These files feed into the offline learning loop:")
    print("  python scripts/learn_and_test.py")


if __name__ == "__main__":
    main()
