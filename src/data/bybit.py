"""
Bybit V5 REST API adapter for OHLCV data ingestion.

Fetches closed OHLCV bars from the Bybit V5 /v5/market/kline endpoint.
No API key required for public market data.

Timeframe mapping:
  "60"  -> "1h"
  "240" -> "4h"
  "D"   -> "1d"

Source: BYBIT_KLINES_PATH = "/v5/market/kline"
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from core.schemas import OHLCVBar

logger = logging.getLogger(__name__)

BYBIT_BASE_URL = "https://api.bybit.com"
BYBIT_KLINES_PATH = "/v5/market/kline"

# Bybit interval string -> our Timeframe string
_INTERVAL_TO_TIMEFRAME: dict[str, str] = {
    "60":  "1h",
    "240": "4h",
    "D":   "1d",
}


class BybitAdapter:
    """
    Bybit V5 OHLCV data fetcher.

    Async HTTP adapter using httpx.AsyncClient.
    Call setup() before use; call teardown() when done.

    Bybit returns klines newest-first; fetch_bars() reverses to oldest-first.
    """

    def __init__(self, base_url: str = BYBIT_BASE_URL) -> None:
        self._base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def setup(self) -> None:
        """Initialize the async HTTP client with a 10-second timeout."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(10.0),
        )
        logger.info("BybitAdapter: HTTP client initialized (base_url=%s)", self._base_url)

    async def teardown(self) -> None:
        """Close and release the async HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("BybitAdapter: HTTP client closed")

    async def fetch_bars(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        end_time_ms: Optional[int] = None,
    ) -> list[OHLCVBar]:
        """
        Fetch up to `limit` closed OHLCV bars from Bybit.

        Args:
            symbol:      Trading pair, e.g. "BTCUSDT"
            interval:    Bybit interval string: "60", "240", or "D"
            limit:       Number of bars to fetch (max 200 per Bybit V5 API)
            end_time_ms: Optional end timestamp in milliseconds UTC (exclusive).
                         If None, fetches the most recent bars.

        Returns:
            List of OHLCVBar objects ordered oldest-first.

        Raises:
            RuntimeError: On HTTP error or non-zero Bybit retCode.
        """
        if self._client is None:
            raise RuntimeError("BybitAdapter.setup() must be called before fetch_bars()")

        params: dict[str, str | int] = {
            "category": "linear",
            "symbol":   symbol,
            "interval": interval,
            "limit":    limit,
        }
        if end_time_ms is not None:
            params["end"] = end_time_ms

        logger.debug(
            "BybitAdapter: GET %s params=%s", BYBIT_KLINES_PATH, params
        )

        try:
            response = await self._client.get(BYBIT_KLINES_PATH, params=params)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Bybit HTTP request failed: {exc}") from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"Bybit API returned HTTP {response.status_code}: {response.text}"
            )

        payload = response.json()
        ret_code = payload.get("retCode", -1)
        if ret_code != 0:
            ret_msg = payload.get("retMsg", "unknown error")
            raise RuntimeError(
                f"Bybit API error retCode={ret_code} retMsg={ret_msg!r}"
            )

        timeframe = _INTERVAL_TO_TIMEFRAME.get(str(interval))
        if timeframe is None:
            raise RuntimeError(
                f"Unknown Bybit interval {interval!r}. "
                f"Supported: {list(_INTERVAL_TO_TIMEFRAME)}"
            )

        raw_list: list[list] = payload["result"]["list"]

        # Bybit returns newest-first; reverse to oldest-first
        raw_list = list(reversed(raw_list))

        bars: list[OHLCVBar] = []
        for kline_row in raw_list:
            try:
                bar = self._normalize_kline(symbol, timeframe, kline_row)
                bars.append(bar)
            except (AssertionError, ValueError, IndexError) as exc:
                logger.warning(
                    "BybitAdapter: skipping malformed kline row %s — %s",
                    kline_row, exc,
                )

        logger.debug(
            "BybitAdapter: fetched %d bars for %s/%s", len(bars), symbol, interval
        )
        return bars

    def _normalize_kline(
        self,
        symbol: str,
        timeframe: str,
        kline_row: list,
    ) -> OHLCVBar:
        """
        Convert a single Bybit kline row to an OHLCVBar.

        kline_row format (Bybit V5):
            [startTime_ms, open_str, high_str, low_str, close_str, volume_str, turnover_str]

        Args:
            symbol:     Trading symbol, e.g. "BTCUSDT"
            timeframe:  Normalised timeframe string: "1h", "4h", or "1d"
            kline_row:  Raw kline list from the API response

        Returns:
            OHLCVBar with all fields populated. is_closed=True.
        """
        start_time_ms = int(kline_row[0])
        open_str      = kline_row[1]
        high_str      = kline_row[2]
        low_str       = kline_row[3]
        close_str     = kline_row[4]
        volume_str    = kline_row[5]   # base asset volume (BTC)
        turnover_str  = kline_row[6]   # quote volume (USD)

        timestamp = datetime.fromtimestamp(start_time_ms / 1000.0, tz=timezone.utc)

        return OHLCVBar(
            symbol     = symbol,
            timeframe  = timeframe,
            timestamp  = timestamp,
            open       = Decimal(open_str),
            high       = Decimal(high_str),
            low        = Decimal(low_str),
            close      = Decimal(close_str),
            volume     = Decimal(volume_str),
            volume_usd = Decimal(turnover_str),
            is_closed  = True,
        )
