"""
Binance REST API adapter for OHLCV data ingestion.

Phase 2: REST polling (daily bars). No WebSocket in Phase 2.
Phase 3: Migrate to WebSocket for live streaming.

Responsibilities:
  - Fetch historical OHLCV from Binance REST /klines endpoint.
  - Normalize Binance response format into OHLCVBar objects.
  - Validate OHLCVBar invariants (enforced in OHLCVBar.__post_init__).
  - Detect and log data gaps.
  - Apply rate limiting (Binance: 1200 weight/min; klines = 1 weight each).

Source: /docs/agent_registry/group_registry.md (MARKET_DATA phase_2_deliverable)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.schemas import OHLCVBar

logger = logging.getLogger(__name__)

BINANCE_KLINES_ENDPOINT = "https://api.binance.com/api/v3/klines"
RATE_LIMIT_WEIGHT_PER_MIN = 1200
KLINES_WEIGHT = 1


class BinanceAdapter:
    """
    Binance OHLCV data fetcher.

    Phase 2: HTTP polling (asyncio httpx).
    No API key required for public market data endpoints.
    """

    def __init__(self, base_url: str = BINANCE_KLINES_ENDPOINT) -> None:
        self._base_url = base_url
        self._session = None   # httpx.AsyncClient, initialized in setup()

    async def setup(self) -> None:
        """Initialize async HTTP client."""
        raise NotImplementedError("BinanceAdapter.setup() — Phase 2 implementation pending")

    async def teardown(self) -> None:
        """Close HTTP client."""
        raise NotImplementedError("Phase 2 pending")

    async def fetch_bars(
        self,
        symbol: str,
        timeframe: str,          # "1d", "4h", "1h" (Binance interval strings)
        limit: int = 250,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[OHLCVBar]:
        """
        Fetch up to 'limit' OHLCV bars from Binance.

        Binance kline format (index → field):
          0: open_time (ms), 1: open, 2: high, 3: low, 4: close,
          5: volume (base), 6: close_time (ms), 7: quote_volume (USD)

        All returned bars have is_closed=True (except possibly the last).
        """
        raise NotImplementedError("BinanceAdapter.fetch_bars() — Phase 2 implementation pending")

    def _normalize_kline(self, symbol: str, timeframe: str, kline: list) -> OHLCVBar:
        """
        Convert Binance kline list → OHLCVBar.
        Raises ValueError if invariants violated (passed through from OHLCVBar.__post_init__).
        """
        raise NotImplementedError("Phase 2 pending")

    async def _rate_limit_wait(self) -> None:
        """Simple token-bucket rate limiter. Waits if weight budget exceeded."""
        raise NotImplementedError("Phase 2 pending")
