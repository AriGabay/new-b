"""
FeatureStore: append-only bar and feature storage.

Phase 2 implementation: Parquet files partitioned by symbol/timeframe.
Phase 3: migrate to TimescaleDB.

Contract (from /docs/data_contracts/data_contracts.md):
  - get_bars(symbol, timeframe, n) → list[OHLCVBar]   (newest-first)
  - get_features(symbol, timeframe, n) → list[FeatureVector]
  - append_bar(bar: OHLCVBar) → None
  - append_features(features: FeatureVector) → None
  - get_latest_bar(symbol, timeframe) → Optional[OHLCVBar]
  - get_latest_features(symbol, timeframe) → Optional[FeatureVector]

Invariants:
  - append_bar() rejects bars with is_closed == False.
  - append_bar() rejects bars older than the most recent bar (gaps are logged, not silently filled).
  - All reads are read-only; the store does NOT modify existing records.
  - The store is the single source of truth for OHLCV history.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.schemas import FeatureVector, OHLCVBar

logger = logging.getLogger(__name__)


class FeatureStore:
    """
    Append-only OHLCV and feature storage.

    Phase 2: Parquet files at data_dir/{symbol}_{timeframe}_bars.parquet
                                    data_dir/{symbol}_{timeframe}_features.parquet
    """

    def __init__(self, data_dir: str = "data/bars") -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # In-memory cache (last 250 bars per symbol/timeframe for fast access)
        self._bar_cache:     dict[tuple, list] = {}
        self._feature_cache: dict[tuple, list] = {}

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        n: int = 250,
    ) -> list[OHLCVBar]:
        """
        Return last n closed bars for symbol/timeframe.
        Newest first (bars[0] = most recent).
        """
        raise NotImplementedError("FeatureStore.get_bars() — Phase 2 implementation pending")

    def get_features(
        self,
        symbol: str,
        timeframe: str,
        n: int = 250,
    ) -> list[FeatureVector]:
        """
        Return last n feature vectors for symbol/timeframe.
        Newest first.
        """
        raise NotImplementedError("FeatureStore.get_features() — Phase 2 implementation pending")

    def append_bar(self, bar: OHLCVBar) -> None:
        """
        Append a closed bar to the store.
        Raises ValueError if bar.is_closed == False.
        Logs warning if gap detected vs previous bar.
        """
        if not bar.is_closed:
            raise ValueError(f"Cannot store unclosed bar: {bar.symbol} {bar.timestamp}")
        raise NotImplementedError("FeatureStore.append_bar() — Phase 2 implementation pending")

    def append_features(self, features: FeatureVector) -> None:
        """Append computed FeatureVector to the store."""
        raise NotImplementedError("FeatureStore.append_features() — Phase 2 implementation pending")

    def get_latest_bar(self, symbol: str, timeframe: str) -> Optional[OHLCVBar]:
        """Return the most recent bar, or None if no data."""
        raise NotImplementedError("FeatureStore.get_latest_bar() — Phase 2 implementation pending")

    def get_latest_features(self, symbol: str, timeframe: str) -> Optional[FeatureVector]:
        """Return the most recent FeatureVector, or None if no data."""
        raise NotImplementedError("FeatureStore.get_latest_features() — Phase 2 implementation pending")
