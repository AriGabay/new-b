"""
Market Data Group (Group 1 — always_on=True, implementation_priority=1).

BTC/Bybit focused. Single-symbol architecture.

Responsibilities:
  - Poll Bybit V5 REST API for BTC OHLCV bars.
  - Store bars in memory (rolling 250-bar window per timeframe).
  - Compute FeatureVector using FeatureComputer.
  - Publish BarCloseEvent and FeatureReadyEvent.
  - Manage eligible_symbols (BTC is always eligible unless system halted).

Timeframes: "1h" (primary), "4h" (context), "1d" (regime).
Bybit interval strings: "60" (1h), "240" (4h), "D" (1d).

LLM: NOT permitted (ADR-002).
Always-on: YES.

Source: /docs/agent_registry/group_registry.md (MARKET_DATA entry)
        /docs/data_contracts/data_contracts.md (OHLCVBar, FeatureVector)
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Optional

from agents.base.group import BaseGroup
from core.events import BarCloseEvent, FeatureReadyEvent, EventBus, SystemEvent
from core.registry import GroupID
from core.schemas import FeatureVector, OHLCVBar
from core.state import SystemState
from data.bybit import BybitAdapter
from features.compute import FeatureComputer

logger = logging.getLogger(__name__)

# Rolling window size per timeframe
BAR_HISTORY_SIZE = 250
# BTC is always the only symbol in phase 1
BTC_SYMBOL = "BTCUSDT"
# Bybit interval string -> our timeframe label
INTERVAL_TO_TF: dict[str, str] = {
    "60":  "1h",
    "240": "4h",
    "D":   "1d",
}


class MarketDataGroup(BaseGroup):
    """
    Always-on BTC/Bybit data ingestion and feature computation group.

    Cross-bar state:
    -   _bar_history: dict[(symbol, timeframe), deque[OHLCVBar]] — rolling 250-bar window
    -   _last_bar_ts: dict[(symbol, timeframe), datetime] — newest bar timestamp seen
    -   _feature_cache: dict[(symbol, timeframe), FeatureVector] — latest computed features
    """

    group_id = GroupID.MARKET_DATA

    def __init__(
        self,
        state: SystemState,
        bus: EventBus,
        config: Optional[dict] = None,
    ) -> None:
        super().__init__(state, bus, config)
        self._adapter = BybitAdapter()
        self._computer = FeatureComputer()

        # Keyed by (symbol, timeframe_label) e.g. ("BTCUSDT", "1h")
        self._bar_history: dict[tuple[str, str], deque[OHLCVBar]] = {}
        self._last_bar_ts: dict[tuple[str, str], Optional[datetime]] = {}
        self._feature_cache: dict[tuple[str, str], Optional[FeatureVector]] = {}

        # BTC is eligible immediately
        self._eligible_symbols: set[str] = {BTC_SYMBOL}

    async def _setup(self) -> None:
        """
        Initialize adapter and mark BTC as eligible.
        Polling is driven externally; no EventBus subscriptions needed.
        """
        await self._adapter.setup()
        await self.state.update_universe({BTC_SYMBOL})
        logger.info("MarketDataGroup ready. BTC/Bybit adapter initialized.")

    async def _teardown(self) -> None:
        await self._adapter.teardown()

    async def _handle_event(self, event: SystemEvent) -> None:
        # Polling-driven; no EventBus events to handle.
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def startup_load(self, symbol: str = BTC_SYMBOL) -> None:
        """
        Called once at system startup. Fetches historical bars for all
        timeframes, computes initial FeatureVectors, and marks BTC eligible.

        Fetches 200 bars each for 1d, 4h, and 1h timeframes.
        """
        timeframe_intervals = [
            ("1d", "D"),
            ("4h", "240"),
            ("1h", "60"),
        ]
        for tf_label, interval in timeframe_intervals:
            try:
                bars = await self._adapter.fetch_bars(symbol, interval, limit=200)
                if bars:
                    key = (symbol, tf_label)
                    if key not in self._bar_history:
                        self._bar_history[key] = deque(maxlen=BAR_HISTORY_SIZE)
                        self._last_bar_ts[key] = None
                        self._feature_cache[key] = None

                    for bar in bars:
                        last_ts = self._last_bar_ts[key]
                        if last_ts is None or bar.timestamp > last_ts:
                            self._bar_history[key].append(bar)
                            self._last_bar_ts[key] = bar.timestamp

                    bar_list = list(self._bar_history[key])
                    fv = self._computer.compute(bar_list)
                    self._feature_cache[key] = fv
                    logger.info(
                        "startup_load: %s/%s — loaded %d bars, features=%s",
                        symbol, tf_label, len(bar_list),
                        "ready" if fv is not None else "warming up",
                    )
                else:
                    logger.warning(
                        "startup_load: %s/%s — no bars returned", symbol, tf_label
                    )
            except Exception as exc:
                logger.error(
                    "startup_load: error fetching %s/%s: %s", symbol, tf_label, exc
                )

        await self.state.update_universe({BTC_SYMBOL})
        logger.info("startup_load complete. BTC eligible.")

    async def fetch_and_process(
        self,
        symbol: str = BTC_SYMBOL,
        interval: str = "60",
    ) -> Optional[FeatureVector]:
        """
        Main method called by the polling loop each bar close.

        Steps:
        1. Fetch latest bars from Bybit (limit=200 to catch up if needed).
        2. For each bar newer than last known, append to bar_history.
        3. Trim bar_history to BAR_HISTORY_SIZE.
        4. Compute FeatureVector from bar_history.
        5. Store in feature_cache.
        6. Publish BarCloseEvent for each new bar.
        7. Publish FeatureReadyEvent with the latest FeatureVector.
        8. Return the FeatureVector or None.
        """
        tf_label = INTERVAL_TO_TF.get(interval)
        if tf_label is None:
            logger.error("fetch_and_process: unknown interval %r", interval)
            return None

        key = (symbol, tf_label)
        if key not in self._bar_history:
            self._bar_history[key] = deque(maxlen=BAR_HISTORY_SIZE)
            self._last_bar_ts[key] = None
            self._feature_cache[key] = None

        try:
            bars = await self._adapter.fetch_bars(symbol, interval, limit=200)
        except Exception as exc:
            logger.error(
                "fetch_and_process: failed to fetch %s/%s: %s", symbol, interval, exc
            )
            return None

        new_bars: list[OHLCVBar] = []
        for bar in bars:
            last_ts = self._last_bar_ts[key]
            if last_ts is None or bar.timestamp > last_ts:
                self._bar_history[key].append(bar)
                self._last_bar_ts[key] = bar.timestamp
                new_bars.append(bar)

        if not new_bars:
            # No new data — return cached features
            return self._feature_cache.get(key)

        # Compute FeatureVector from the full rolling window
        bar_list = list(self._bar_history[key])
        fv = self._computer.compute(bar_list)
        self._feature_cache[key] = fv

        # Publish BarCloseEvent for each new bar
        for bar in new_bars:
            await self.bus.publish(
                BarCloseEvent(source=self.group_id.value, bar=bar)
            )

        # Publish FeatureReadyEvent with the latest features
        if fv is not None:
            await self.state.update_last_close(symbol, fv.close)
            await self.bus.publish(
                FeatureReadyEvent(source=self.group_id.value, features=fv)
            )
            logger.debug(
                "fetch_and_process: %s/%s — %d new bar(s), features published",
                symbol, tf_label, len(new_bars),
            )
        else:
            logger.debug(
                "fetch_and_process: %s/%s — %d new bar(s), still warming up (%d bars)",
                symbol, tf_label, len(new_bars), len(bar_list),
            )

        return fv

    def get_feature_cache(
        self, symbol: str, timeframe: str
    ) -> Optional[FeatureVector]:
        """Return the latest FeatureVector for (symbol, timeframe), or None."""
        return self._feature_cache.get((symbol, timeframe))

    def get_bar_history(
        self, symbol: str, timeframe: str
    ) -> list[OHLCVBar]:
        """Return bars oldest-first for (symbol, timeframe)."""
        key = (symbol, timeframe)
        hist = self._bar_history.get(key)
        if hist is None:
            return []
        return list(hist)
