"""
News & Macro Group (Group 2 — always_on=False, implementation_priority=5).

Responsibilities:
  - Load static event calendar (JSON). No live news feed.
  - Compute position_size_modifier based on proximity to high-impact events.
  - Classify BTC macro regime from EMA stack (bull/bear/ranging).
  - Load Fear & Greed index from data/sentiment.json.
  - Update SystemState.macro_position_modifier and fear_greed_index each bar.
  - Publish GroupSignalEvent with macro metadata for EntryGroup.

Position modifier schedule (high-impact events only):
  4h before:  0.50  (reduced size — approaching event)
  1h before:  0.00  (block new entries — too close)
  1h after:   0.50  (reduced size — absorbing reaction)
  Otherwise:  1.00  (normal)

Fear & Greed modifier (applied multiplicatively):
  Extreme fear (<20): × 0.70
  Extreme greed (>80): × 0.70
  Otherwise: no change

BTC macro classification (from FeatureVector EMAs):
  EMA20 > EMA50 > EMA200 → "bull"
  EMA20 < EMA50 < EMA200 → "bear"
  else                    → "ranging"

LLM: NOT used (Phase 2: deterministic calendar only).
Always-on: NO — triggered once per BarCloseEvent.

Source: /docs/agent_registry/group_registry.md (NEWS_MACRO entry)
        /research/hypotheses/hypothesis_registry.md (H4-002)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from agents.base.group import BaseGroup
from core.events import BarCloseEvent, EventBus, FeatureReadyEvent, GroupSignalEvent, SystemEvent
from core.registry import GroupID
from core.schemas import GroupSignalBundle, RegimeContext
from core.state import SystemState

logger = logging.getLogger(__name__)


def _parse_event_datetime(entry: dict) -> datetime:
    """Parse an event calendar entry into a naive UTC datetime."""
    date_str = entry.get("date", "")
    time_str = entry.get("time", "00:00")
    # Support both "HH:MM" and "HH:MM:SS"
    if len(time_str) == 5:
        time_str = time_str + ":00"
    return datetime.fromisoformat(f"{date_str}T{time_str}")


class NewsMacroGroup(BaseGroup):
    """
    Macro event risk and BTC regime context provider.

    Cross-bar state:
    -   _event_calendar: list[dict]       — loaded from JSON at startup
    -   _latest_features: dict[str, Any]  — most recent FeatureVector per symbol
    -   _fear_greed_value: float          — from sentiment.json (default 50)
    """

    group_id = GroupID.NEWS_MACRO

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)
        self._event_calendar: list = []
        self._latest_features: dict = {}   # symbol → FeatureVector
        self._fear_greed_value: float = 50.0

    async def _setup(self) -> None:
        await self.bus.subscribe(BarCloseEvent, self.handle_event)
        await self.bus.subscribe(FeatureReadyEvent, self.handle_event)
        await self._load_event_calendar()
        self._fear_greed_value = self._load_sentiment()
        logger.info(
            "NewsMacroGroup ready: %d events loaded, F&G=%.0f",
            len(self._event_calendar),
            self._fear_greed_value,
        )

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, FeatureReadyEvent) and event.features is not None:
            # Cache latest features per symbol for use in the next bar close.
            self._latest_features[event.features.symbol] = event.features
        elif isinstance(event, BarCloseEvent):
            await self._process_bar_close(event)

    async def _process_bar_close(self, event: BarCloseEvent) -> None:
        """
        On each bar close:
        1. Check calendar for high-impact events → compute position_size_modifier.
        2. Apply Fear & Greed modifier.
        3. Classify BTC macro from cached FeatureVector (or fallback to regime).
        4. Update SystemState.
        5. Publish GroupSignalEvent with macro metadata.
        """
        bar = event.bar
        reference_ts = bar.timestamp if bar is not None else event.timestamp
        symbol = bar.symbol if bar is not None else "BTCUSDT"
        timeframe = bar.timeframe if bar is not None else "1h"

        # Step 1: event calendar modifier
        modifier = self._compute_position_modifier(reference_ts)

        # Step 2: Fear & Greed modifier
        fg = self._fear_greed_value
        if fg < 20 or fg > 80:
            modifier *= 0.70
        modifier = max(0.0, min(1.0, modifier))

        # Step 3: BTC macro classification
        features = self._latest_features.get(symbol)
        if features is not None:
            btc_macro = self._classify_btc_macro(features)
        else:
            # Fallback: use whatever IndicatorsGroup already set on the shared regime
            btc_macro = getattr(self.state.regime, "btc_macro", "ranging") or "ranging"

        # Step 4: update SystemState
        await self.state.update_macro_state(modifier, fg)

        # Step 5: publish
        has_event_48h = self._has_high_impact_event_next_48h(reference_ts)
        bundle = GroupSignalBundle(
            group_id=self.group_id.value,
            symbol=symbol,
            timeframe=timeframe,
            timestamp=reference_ts,
            metadata={
                "macro_position_modifier": modifier,
                "fear_greed_index": fg,
                "btc_macro": btc_macro,
                "has_high_impact_event_48h": has_event_48h,
            },
        )
        await self.bus.publish(GroupSignalEvent(
            source=self.group_id.value,
            bundle=bundle,
        ))
        logger.debug(
            "NewsMacroGroup: bar %s symbol=%s modifier=%.2f fg=%.0f macro=%s event48h=%s",
            reference_ts, symbol, modifier, fg, btc_macro, has_event_48h,
        )

    # ------------------------------------------------------------------
    # Calendar loading
    # ------------------------------------------------------------------

    async def _load_event_calendar(self) -> None:
        """
        Load static event calendar from config path (JSON).
        Schema: [{"date":"2024-03-20","time":"18:00","event":"FOMC Decision",
                  "impact":"high","asset":"all"}]
        Missing file → log warning and continue with empty calendar.
        """
        calendar_path = self.config.get("event_calendar_path")
        if not calendar_path:
            logger.warning(
                "NewsMacroGroup: no event_calendar_path configured. "
                "Calendar-based event risk disabled."
            )
            return
        try:
            path = Path(calendar_path)
            if not path.exists():
                logger.warning(
                    "NewsMacroGroup: event calendar not found at %s. "
                    "Calendar-based event risk disabled.",
                    calendar_path,
                )
                return
            with open(path) as f:
                self._event_calendar = json.load(f)
            logger.info(
                "NewsMacroGroup: loaded %d events from %s",
                len(self._event_calendar),
                calendar_path,
            )
        except Exception as exc:
            logger.warning(
                "NewsMacroGroup: failed to load event calendar from %s: %s",
                calendar_path,
                exc,
            )
            self._event_calendar = []

    def _load_sentiment(self) -> float:
        """
        Load Fear & Greed index from sentiment_path config (or data/sentiment.json).
        Returns 50.0 (neutral) on any error or missing file.
        Schema: {"value": 50, "label": "neutral", "updated": "..."}
        """
        sentiment_path = self.config.get("sentiment_path", "data/sentiment.json")
        try:
            path = Path(sentiment_path)
            if not path.exists():
                return 50.0
            with open(path) as f:
                data = json.load(f)
            value = float(data.get("value", 50.0))
            logger.debug("NewsMacroGroup: F&G index=%.0f from %s", value, sentiment_path)
            return value
        except Exception as exc:
            logger.debug("NewsMacroGroup: could not load sentiment (%s), defaulting to 50", exc)
            return 50.0

    # ------------------------------------------------------------------
    # Event calendar helpers
    # ------------------------------------------------------------------

    def _has_high_impact_event_next_48h(self, reference_ts: datetime) -> bool:
        """Return True if any high-impact event falls within 48h of reference_ts."""
        window_end = reference_ts + timedelta(hours=48)
        for entry in self._event_calendar:
            if entry.get("impact", "").lower() != "high":
                continue
            try:
                event_dt = _parse_event_datetime(entry)
            except Exception:
                continue
            if reference_ts <= event_dt <= window_end:
                return True
        return False

    def _compute_position_modifier(self, reference_ts: datetime) -> float:
        """
        Scan the event calendar and return the most restrictive size modifier:
          1h before  → 0.00 (block — too close to event)
          4h before  → 0.50 (reduce — approaching event)
          1h after   → 0.50 (reduce — absorbing reaction)
          Otherwise  → 1.00 (no restriction)

        Only high-impact events are considered.
        Multiple events: returns the minimum (most restrictive) modifier.
        """
        modifier = 1.0
        for entry in self._event_calendar:
            if entry.get("impact", "").lower() != "high":
                continue
            try:
                event_dt = _parse_event_datetime(entry)
            except Exception:
                continue

            diff_seconds = (event_dt - reference_ts).total_seconds()
            hours_ahead = diff_seconds / 3600.0   # positive = event in the future
            hours_after = -hours_ahead             # positive = event already passed

            if 0 < hours_ahead <= 1:
                # Within 1h before event — block
                modifier = 0.0
                break   # can't get more restrictive
            elif 0 < hours_ahead <= 4:
                # 1–4h before event — half size
                modifier = min(modifier, 0.50)
            elif 0 < hours_after <= 1:
                # Within 1h after event — half size (absorbing reaction)
                modifier = min(modifier, 0.50)
            # else: outside all windows → no effect

        return modifier

    # ------------------------------------------------------------------
    # BTC macro classification
    # ------------------------------------------------------------------

    def _classify_btc_macro(self, features) -> str:
        """
        Classify BTC macro regime from EMA stack.
          EMA20 > EMA50 > EMA200 → 'bull'
          EMA20 < EMA50 < EMA200 → 'bear'
          else                    → 'ranging'
        """
        ema20 = float(features.ema20)
        ema50 = float(features.ema50)
        ema200 = float(features.ema200)
        if ema20 > ema50 > ema200:
            return "bull"
        elif ema20 < ema50 < ema200:
            return "bear"
        else:
            return "ranging"
