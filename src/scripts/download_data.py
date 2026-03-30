#!/usr/bin/env python3
"""
Download 1h OHLCV kline data from the Bybit V5 public API (no API key required).

Fetches the same date range as btcusdt_1h_2024_2025.csv:
  2023-12-01T00:00:00Z  →  2025-12-31T23:00:00Z  (~18,288 bars)

Output format (matches existing BTC CSV):
  timestamp,open,high,low,close,volume,volume_usd

Usage:
  python src/scripts/download_data.py ETHUSDT
  python src/scripts/download_data.py BNBUSDT
  python src/scripts/download_data.py ETHUSDT BNBUSDT   # both at once

Output:
  analysis/historical_eval/data/ethusdt_1h_2024_2025.csv
  analysis/historical_eval/data/bnbusdt_1h_2024_2025.csv
"""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BYBIT_KLINES   = "https://api.bybit.com/v5/market/kline"
INTERVAL       = "60"           # 1h bars
START_MS       = 1701388800000  # 2023-12-01T00:00:00Z
END_MS         = 1767225600000  # 2026-01-01T00:00:00Z (exclusive)
PAGE_LIMIT     = 1000           # Bybit V5 max per request
REQUEST_DELAY  = 1.2            # seconds between pages (Bybit public rate limit ~60 req/min)
MAX_RETRIES    = 5              # retries on rate-limit (10006) with exponential backoff

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
DATA_DIR = os.path.join(
    _PROJECT_ROOT, "analysis", "historical_eval", "data"
)


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _fetch_page(client: httpx.Client, symbol: str, end_ms: int) -> list[list]:
    """Fetch one page of klines ending at end_ms.  Returns newest-first list.
    Retries up to MAX_RETRIES times on rate-limit errors (retCode 10006).
    """
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


def download(symbol: str, out_path: str) -> int:
    """
    Paginate backwards through klines for *symbol* and write a CSV.

    Returns the number of bars written.
    """
    symbol = symbol.upper()
    print(f"\n{'='*60}")
    print(f"Downloading {symbol} 1h bars")
    print(f"  Range : 2023-12-01 → 2025-12-31")
    print(f"  Output: {out_path}")
    print(f"{'='*60}")

    all_rows: list[list] = []
    end_ms = END_MS

    with httpx.Client(timeout=30) as client:
        while True:
            rows = _fetch_page(client, symbol, end_ms)
            if not rows:
                break

            # rows[0] = newest, rows[-1] = oldest
            oldest_ms = int(rows[-1][0])
            newest_ms = int(rows[0][0])

            # Keep only bars within [START_MS, END_MS)
            in_range = [r for r in rows if START_MS <= int(r[0]) < END_MS]
            all_rows.extend(in_range)

            oldest_dt = datetime.fromtimestamp(oldest_ms / 1000, tz=timezone.utc)
            print(
                f"  page: {len(rows)} bars  "
                f"oldest={oldest_dt.strftime('%Y-%m-%d %H:%M')}  "
                f"kept={len(in_range)}  total={len(all_rows)}"
            )

            # Stop when we've passed the start of the desired range
            if oldest_ms <= START_MS:
                break

            # Next page ends at the oldest bar's timestamp (exclusive)
            end_ms = oldest_ms
            time.sleep(REQUEST_DELAY)

    if not all_rows:
        print("ERROR: no bars fetched — check symbol or API connectivity")
        return 0

    # Sort oldest-first and deduplicate by timestamp
    seen: set[int] = set()
    unique: list[list] = []
    for row in sorted(all_rows, key=lambda r: int(r[0])):
        ts_ms = int(row[0])
        if ts_ms not in seen:
            seen.add(ts_ms)
            unique.append(row)

    # Write CSV in the same format as btcusdt_1h_2024_2025.csv
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "volume_usd"])
        for row in unique:
            ts_ms_val, open_, high, low, close, volume, volume_usd = row
            ts_iso = datetime.fromtimestamp(
                int(ts_ms_val) / 1000, tz=timezone.utc
            ).isoformat()
            writer.writerow([ts_iso, open_, high, low, close, volume, volume_usd])

    print(f"\n✓ Saved {len(unique):,} bars → {out_path}")
    return len(unique)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    symbols = [s.upper() for s in sys.argv[1:]] if len(sys.argv) > 1 else ["ETHUSDT"]
    results: dict[str, int] = {}

    for sym in symbols:
        fname = f"{sym.lower()}_1h_2024_2025.csv"
        path  = os.path.join(DATA_DIR, fname)
        n     = download(sym, path)
        results[sym] = n

    print("\n" + "="*60)
    print("SUMMARY")
    for sym, n in results.items():
        status = "OK" if n > 15000 else "WARNING: fewer bars than expected"
        print(f"  {sym}: {n:,} bars  [{status}]")
    print("="*60)
