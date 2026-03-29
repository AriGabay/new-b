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

        After loading, publishes one FeatureReadyEvent for the 1h timeframe
        if the FeatureComputer has enough data. This ensures all subscribed
        groups (Indicators, Candlestick, TechnicalStructure, Entry, Exit)
        process the current market state immediately at startup rather than
        waiting up to 60 minutes for the next natural bar close.
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
                        "startup_load: %s/%s — loaded %d bars, features=%s, "
                        "last_bar_ts=%s",
                        symbol, tf_label, len(bar_list),
                        "ready" if fv is not None else "warming up",
                        self._last_bar_ts[key],
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

        # Publish FeatureReadyEvent for 1h timeframe so all groups can
        # process the current market state immediately at startup.
        # Without this, groups are silent until the next natural bar close
        # (up to 60 minutes away).
        primary_key = (symbol, "1h")
        fv_1h = self._feature_cache.get(primary_key)
        if fv_1h is not None:
            await self.state.update_last_close(symbol, fv_1h.close)
            await self.bus.publish(
                FeatureReadyEvent(source=f"{self.group_id.value}.startup", features=fv_1h)
            )
            logger.info(
                "startup_load: published initial FeatureReadyEvent for %s/1h "
                "(close=%s, ts=%s). Groups will process current market state.",
                symbol, fv_1h.close, fv_1h.timestamp,
            )
        else:
            logger.warning(
                "startup_load: 1h FeatureVector not ready after startup "
                "(need %d bars, have %d). Will wait for first natural bar close.",
                200, len(list(self._bar_history.get(primary_key, []))),
            )

        logger.info("startup_load complete. BTC eligible.")

    async def fetch_and_process(
        self,
        symbol: str = BTC_SYMBOL,
        interval: str = "60",
    ) -> Optional[FeatureVector]:
        """
        Main method called by the polling loop each bar close.

        Returns:
            FeatureVector if a NEW bar was detected and features were computed.
            None if:
              - No new bar since last poll (most calls — only one new bar per hour).
              - Fetch failed.
              - Not enough history for FeatureComputer yet.

        IMPORTANT: Returns None when there is no new bar, even if the feature
        cache is populated. This is the signal used by run_one_bar() to determine
        whether the downstream chain was triggered. Do NOT return a cached
        FeatureVector on no-new-bar — that causes a false "bar processed" count
        and a completely silent downstream chain.

        Steps:
        1. Fetch latest bars from Bybit (limit=200 to catch up if needed).
        2. For each bar newer than last known, append to bar_history.
        3. Trim bar_history to BAR_HISTORY_SIZE.
        4. Compute FeatureVector from bar_history.
        5. Store in feature_cache.
        6. Publish BarCloseEvent for each new bar.
        7. Publish FeatureReadyEvent with the latest FeatureVector.
        8. Return the new FeatureVector (or None if no new bar / warming up).
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
            # No new bar since last poll — downstream chain should NOT run.
            # Log at DEBUG so the polling silence is visible at high verbosity.
            logger.debug(
                "fetch_and_process: %s/%s — no new bar (last bar: %s). "
                "Downstream chain idle.",
                symbol, tf_label, self._last_bar_ts.get(key),
            )
            # Return None — NOT the cached FeatureVector.
            # Callers that need cached features should call get_feature_cache().
            return None

        # New bar(s) detected — run the full pipeline.
        logger.info(
            "fetch_and_process: %s/%s — NEW BAR detected: %d bar(s) "
            "(newest ts: %s). Triggering downstream chain.",
            symbol, tf_label, len(new_bars),
            new_bars[-1].timestamp if new_bars else None,
        )

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
            logger.info(
                "fetch_and_process: %s/%s — FeatureReadyEvent published "
                "(close=%s, atr14=%s). All subscribed groups triggered.",
                symbol, tf_label, fv.close, fv.atr14,
            )
        else:
            logger.info(
                "fetch_and_process: %s/%s — %d new bar(s) stored, "
                "still warming up (%d/%d bars). No FeatureReadyEvent yet.",
                symbol, tf_label, len(new_bars), len(bar_list), 200,
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
