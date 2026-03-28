"""
Technical Structure Group (Group 6 — always_on=False, implementation_priority=2).

BTC/Bybit focused. Detects swing highs/lows and builds horizontal S/R levels.

10 sub-agents (methods):
  1.  _parse_bars            — extract highs/lows/closes from bar history
  2.  _detect_swing_highs    — 5-bar fractal swing high detection
  3.  _detect_swing_lows     — 5-bar fractal swing low detection
  4.  _cluster_levels        — cluster nearby pivots into S/R levels
  5.  _count_touches         — count bars that touched a level
  6.  _classify_trend        — determine HH/HL and trend direction
  7.  _prune_broken_levels   — remove decisively broken levels
  8.  _proximity_flags       — at_resistance, at_support flags
  9.  _build_structural_bundle — assemble StructuralLevelBundle
  10. _publish_structural_update — store in cache + publish event

LLM: NOT permitted.
Trigger: FeatureReadyEvent.
Depends on: MARKET_DATA.

Source: /docs/agent_registry/group_registry.md (TECHNICAL_STRUCTURE entry)
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Optional

from agents.base.group import BaseGroup
from core.events import EventBus, FeatureReadyEvent, GroupSignalEvent, SystemEvent
from core.registry import GroupID
from core.schemas import (
    Direction, FeatureVector, GroupSignalBundle,
    StructuralLevel, StructuralLevelBundle,
)
from core.state import SystemState

logger = logging.getLogger(__name__)

# Rolling bar history per symbol
BAR_HISTORY_SIZE = 60
# Max S/R levels per side (resistance/support)
MAX_LEVELS = 10
# Minimum touches for a level to qualify
MIN_TOUCHES = 2
# ATR multiplier for "at level" proximity flag
AT_LEVEL_ATR_MULT = 1.0
# Cluster tolerance: pivots within this fraction of ATR are merged
CLUSTER_ATR_MULT = 0.5
# Break tolerance: level broken if close exceeds it by this pct
BREAK_TOLERANCE_PCT = Decimal("0.01")


class TechnicalStructureGroup(BaseGroup):
    """
    Swing pivot and S/R level tracker for BTC/Bybit.

    Cross-bar state (per symbol):
    -   _bar_history:       dict[str, list[FeatureVector]] — rolling 60-bar window
    -   _resistance_levels: dict[str, list[StructuralLevel]]
    -   _support_levels:    dict[str, list[StructuralLevel]]
    -   _structural_cache:  dict[str, StructuralLevelBundle] — latest published bundle
    """

    group_id = GroupID.TECHNICAL_STRUCTURE

    def __init__(
        self,
        state: SystemState,
        bus: EventBus,
        config: Optional[dict] = None,
    ) -> None:
        super().__init__(state, bus, config)
        self._bar_history:       dict[str, list[FeatureVector]]    = {}
        self._resistance_levels: dict[str, list[StructuralLevel]]  = {}
        self._support_levels:    dict[str, list[StructuralLevel]]  = {}
        self._structural_cache:  dict[str, StructuralLevelBundle]  = {}

    async def _setup(self) -> None:
        await self.bus.subscribe(FeatureReadyEvent, self.handle_event)
        logger.info("TechnicalStructureGroup subscribed to FeatureReadyEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, FeatureReadyEvent) and event.features is not None:
            await self._process_features(event.features)

    async def _process_features(self, fv: FeatureVector) -> None:
        """
        Per-bar pipeline:
        1. Update bar_history (rolling 60 bars).
        2. Detect new swing pivots on the confirmed bar (index -3 of history).
        3. Cluster new pivots into S/R levels.
        4. Prune broken levels.
        5. Build StructuralLevelBundle.
        6. Store in cache and publish GroupSignalEvent.
        """
        symbol = fv.symbol

        # 1. Update bar history
        if symbol not in self._bar_history:
            self._bar_history[symbol] = []
            self._resistance_levels[symbol] = []
            self._support_levels[symbol] = []

        self._bar_history[symbol].append(fv)
        if len(self._bar_history[symbol]) > BAR_HISTORY_SIZE:
            self._bar_history[symbol] = self._bar_history[symbol][-BAR_HISTORY_SIZE:]

        bars = self._bar_history[symbol]

        # Need at least 5 bars for fractal detection (2 look-back + 1 + 2 look-forward)
        if len(bars) < 5:
            return

        atr14 = fv.atr14

        # 2. Detect new swing pivots (sub-agents 2 & 3)
        # Confirm bar at index len-3 (2 bars of look-forward available)
        swing_highs = self._detect_swing_highs(bars)
        swing_lows = self._detect_swing_lows(bars)

        # 3. Cluster new pivots into levels (sub-agents 4 & 5)
        for ts, price in swing_highs:
            self._resistance_levels[symbol] = self._cluster_levels(
                self._resistance_levels[symbol], price, ts, "swing_high", atr14, bars
            )

        for ts, price in swing_lows:
            self._support_levels[symbol] = self._cluster_levels(
                self._support_levels[symbol], price, ts, "swing_low", atr14, bars
            )

        # 4. Prune broken levels (sub-agent 7)
        self._resistance_levels[symbol] = self._prune_broken_levels(
            self._resistance_levels[symbol], fv.close, atr14, level_type="resistance"
        )
        self._support_levels[symbol] = self._prune_broken_levels(
            self._support_levels[symbol], fv.close, atr14, level_type="support"
        )

        # Keep only top MAX_LEVELS per side (strongest by touches)
        self._resistance_levels[symbol] = sorted(
            self._resistance_levels[symbol], key=lambda l: l.touches, reverse=True
        )[:MAX_LEVELS]
        self._support_levels[symbol] = sorted(
            self._support_levels[symbol], key=lambda l: l.touches, reverse=True
        )[:MAX_LEVELS]

        # 5. Build bundle (sub-agent 9)
        bundle = self._build_structural_bundle(
            symbol=symbol,
            timeframe=fv.timeframe,
            fv=fv,
            resistance=self._resistance_levels[symbol],
            support=self._support_levels[symbol],
        )

        # 6. Store and publish (sub-agent 10)
        await self._publish_structural_update(symbol, bundle)

    # ------------------------------------------------------------------
    # Sub-agent 1: _parse_bars
    # ------------------------------------------------------------------

    def _parse_bars(
        self, bars: list[FeatureVector]
    ) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
        """Extract highs, lows, closes from bar history."""
        highs  = [b.high  for b in bars]
        lows   = [b.low   for b in bars]
        closes = [b.close for b in bars]
        return highs, lows, closes

    # ------------------------------------------------------------------
    # Sub-agent 2: _detect_swing_highs
    # ------------------------------------------------------------------

    def _detect_swing_highs(
        self, bars: list[FeatureVector]
    ) -> list[tuple[datetime, Decimal]]:
        """
        5-bar fractal swing high detection.
        bar[i] is a swing high if:
            bars[i].high > bars[i-2].high AND
            bars[i].high > bars[i-1].high AND
            bars[i].high > bars[i+1].high AND
            bars[i].high > bars[i+2].high

        We only check the bar at index len(bars)-3 to ensure the 2 look-forward
        bars are available (confirmed 2 bars ago).
        """
        swing_highs = []
        n = len(bars)
        if n < 5:
            return swing_highs

        # Only check the newly-confirmable pivot (bars[-3])
        i = n - 3
        candidate = bars[i]
        h = candidate.high

        neighbors = [bars[i-2].high, bars[i-1].high, bars[i+1].high, bars[i+2].high]
        if all(h > nh for nh in neighbors):
            swing_highs.append((candidate.timestamp, h))

        return swing_highs

    # ------------------------------------------------------------------
    # Sub-agent 3: _detect_swing_lows
    # ------------------------------------------------------------------

    def _detect_swing_lows(
        self, bars: list[FeatureVector]
    ) -> list[tuple[datetime, Decimal]]:
        """
        5-bar fractal swing low detection.
        bar[i] is a swing low if bars[i].low < all of [i-2, i-1, i+1, i+2].
        Confirmed at bars[-3].
        """
        swing_lows = []
        n = len(bars)
        if n < 5:
            return swing_lows

        i = n - 3
        candidate = bars[i]
        lo = candidate.low

        neighbors = [bars[i-2].low, bars[i-1].low, bars[i+1].low, bars[i+2].low]
        if all(lo < nl for nl in neighbors):
            swing_lows.append((candidate.timestamp, lo))

        return swing_lows

    # ------------------------------------------------------------------
    # Sub-agent 4: _cluster_levels
    # ------------------------------------------------------------------

    def _cluster_levels(
        self,
        levels: list[StructuralLevel],
        price: Decimal,
        timestamp: datetime,
        level_type: str,
        atr14: Decimal,
        bars: list[FeatureVector],
    ) -> list[StructuralLevel]:
        """
        Cluster a new pivot into the existing level list.
        - If pivot within CLUSTER_ATR_MULT × ATR14 of existing level → update level
          (recalculate price as median, increment strength, update last_tested).
        - Otherwise create a new StructuralLevel.
        - Count touches from bar history.
        """
        cluster_tol = atr14 * Decimal(str(CLUSTER_ATR_MULT))

        # Find if this pivot is near any existing level
        for level in levels:
            if abs(level.price - price) <= cluster_tol:
                # Merge: update level price to be median of constituent prices
                # We approximate by averaging old price and new pivot
                merged_price = (level.price + price) / Decimal("2")
                touches = self._count_touches(merged_price, bars, tolerance=cluster_tol)
                level.price = merged_price
                level.touches = max(touches, level.touches + 1)
                level.strength = min(1.0, level.strength + 0.2)
                level.last_tested = timestamp
                return levels

        # No nearby level found — create new
        touches = self._count_touches(price, bars, tolerance=cluster_tol)
        if touches >= 1:  # At least touched once (the pivot itself)
            new_level = StructuralLevel(
                price=price,
                touches=touches,
                strength=min(1.0, touches * 0.2),
                first_tested=timestamp,
                last_tested=timestamp,
                level_type=level_type,
            )
            levels.append(new_level)

        return levels

    # ------------------------------------------------------------------
    # Sub-agent 5: _count_touches
    # ------------------------------------------------------------------

    def _count_touches(
        self,
        level_price: Decimal,
        bars: list[FeatureVector],
        tolerance: Decimal,
    ) -> int:
        """
        Count bars that touched this level.
        A bar "touches" if:
            high >= level_price - tolerance  AND  low <= level_price + tolerance
        i.e. the bar's range overlaps the level zone.
        """
        count = 0
        tol = tolerance if tolerance > Decimal("0") else level_price * Decimal("0.001")
        for bar in bars:
            if bar.high >= level_price - tol and bar.low <= level_price + tol:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Sub-agent 6: _classify_trend
    # ------------------------------------------------------------------

    def _classify_trend(
        self, bars: list[FeatureVector], fv: FeatureVector
    ) -> tuple[bool, bool, str]:
        """
        Determine higher_highs, higher_lows, and trend_direction from recent bars.
        Uses last 10 bars minimum.
        Returns (higher_highs, higher_lows, trend_direction).
        """
        if len(bars) < 6:
            return False, False, "sideways"

        recent = bars[-10:] if len(bars) >= 10 else bars

        # Find local highs and lows by scanning pairs
        highs = [b.high for b in recent]
        lows  = [b.low  for b in recent]

        # Simple: compare first half to second half
        mid = len(recent) // 2
        first_half_high  = max(highs[:mid])
        second_half_high = max(highs[mid:])
        first_half_low   = min(lows[:mid])
        second_half_low  = min(lows[mid:])

        higher_highs = second_half_high > first_half_high
        higher_lows  = second_half_low  > first_half_low

        # Also use EMA alignment from feature vector
        ema_bull = fv.ema20 > fv.ema50
        ema_bear = fv.ema20 < fv.ema50

        if higher_highs and higher_lows and ema_bull:
            trend_direction = "uptrend"
        elif not higher_highs and not higher_lows and ema_bear:
            trend_direction = "downtrend"
        else:
            trend_direction = "sideways"

        return higher_highs, higher_lows, trend_direction

    # ------------------------------------------------------------------
    # Sub-agent 7: _prune_broken_levels
    # ------------------------------------------------------------------

    def _prune_broken_levels(
        self,
        levels: list[StructuralLevel],
        current_close: Decimal,
        atr14: Decimal,
        level_type: str,
    ) -> list[StructuralLevel]:
        """
        Remove decisively broken levels.
        - Resistance broken: close > level_price × (1 + BREAK_TOLERANCE_PCT)
          AND the break is more than 1 ATR above the level (decisive).
        - Support broken: close < level_price × (1 - BREAK_TOLERANCE_PCT)
          AND the break is more than 1 ATR below the level.
        """
        result = []
        for level in levels:
            if level_type == "resistance":
                # Level broken if price is decisively above it
                break_threshold = level.price * (Decimal("1") + BREAK_TOLERANCE_PCT)
                if current_close > break_threshold and (current_close - level.price) > atr14:
                    logger.debug(
                        "Pruning broken resistance level %.2f (close=%.2f)",
                        float(level.price), float(current_close),
                    )
                    continue
            elif level_type == "support":
                # Level broken if price is decisively below it
                break_threshold = level.price * (Decimal("1") - BREAK_TOLERANCE_PCT)
                if current_close < break_threshold and (level.price - current_close) > atr14:
                    logger.debug(
                        "Pruning broken support level %.2f (close=%.2f)",
                        float(level.price), float(current_close),
                    )
                    continue
            result.append(level)
        return result

    # ------------------------------------------------------------------
    # Sub-agent 8: _proximity_flags
    # ------------------------------------------------------------------

    def _proximity_flags(
        self,
        resistance_levels: list[StructuralLevel],
        support_levels: list[StructuralLevel],
        current_close: Decimal,
        atr14: Decimal,
    ) -> tuple[bool, bool, Optional[StructuralLevel], Optional[StructuralLevel]]:
        """
        Determine at_resistance and at_support flags.
        at_resistance: price within AT_LEVEL_ATR_MULT × ATR14 BELOW nearest resistance
        at_support:    price within AT_LEVEL_ATR_MULT × ATR14 ABOVE nearest support

        Returns (at_resistance, at_support, nearest_resistance_level, nearest_support_level).
        """
        proximity_band = atr14 * Decimal(str(AT_LEVEL_ATR_MULT))

        # Nearest resistance: lowest resistance level above current close
        above_resistances = [
            lvl for lvl in resistance_levels
            if lvl.price >= current_close and lvl.touches >= MIN_TOUCHES
        ]
        nearest_resistance: Optional[StructuralLevel] = None
        if above_resistances:
            nearest_resistance = min(above_resistances, key=lambda l: l.price)

        at_resistance = (
            nearest_resistance is not None
            and (nearest_resistance.price - current_close) <= proximity_band
        )

        # Nearest support: highest support level below current close
        below_supports = [
            lvl for lvl in support_levels
            if lvl.price <= current_close and lvl.touches >= MIN_TOUCHES
        ]
        nearest_support: Optional[StructuralLevel] = None
        if below_supports:
            nearest_support = max(below_supports, key=lambda l: l.price)

        at_support = (
            nearest_support is not None
            and (current_close - nearest_support.price) <= proximity_band
        )

        return at_resistance, at_support, nearest_resistance, nearest_support

    # ------------------------------------------------------------------
    # Sub-agent 9: _build_structural_bundle
    # ------------------------------------------------------------------

    def _build_structural_bundle(
        self,
        symbol: str,
        timeframe: str,
        fv: FeatureVector,
        resistance: list[StructuralLevel],
        support: list[StructuralLevel],
    ) -> StructuralLevelBundle:
        """Assemble StructuralLevelBundle for current bar."""
        at_resistance, at_support, nearest_res, nearest_sup = self._proximity_flags(
            resistance, support, fv.close, fv.atr14
        )

        return StructuralLevelBundle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=fv.timestamp,
            resistance_levels=list(resistance),
            support_levels=list(support),
            at_resistance=at_resistance,
            at_support=at_support,
            nearest_resistance=nearest_res,
            nearest_support=nearest_sup,
        )

    # ------------------------------------------------------------------
    # Sub-agent 10: _publish_structural_update
    # ------------------------------------------------------------------

    async def _publish_structural_update(
        self, symbol: str, bundle: StructuralLevelBundle
    ) -> None:
        """Store bundle in cache and publish GroupSignalEvent."""
        self._structural_cache[symbol] = bundle

        gsb = GroupSignalBundle(
            group_id=self.group_id.value,
            symbol=bundle.symbol,
            timeframe=bundle.timeframe,
            timestamp=bundle.timestamp,
            signals=[],
            regime=None,
            structural=bundle,
            metadata={
                "at_resistance": bundle.at_resistance,
                "at_support": bundle.at_support,
                "resistance_count": len(bundle.resistance_levels),
                "support_count": len(bundle.support_levels),
            },
        )

        await self.bus.publish(
            GroupSignalEvent(source=self.group_id.value, bundle=gsb)
        )

        logger.debug(
            "TechnicalStructureGroup: %s — R=%d S=%d at_R=%s at_S=%s",
            symbol,
            len(bundle.resistance_levels),
            len(bundle.support_levels),
            bundle.at_resistance,
            bundle.at_support,
        )

    # ------------------------------------------------------------------
    # Public accessor for inter-group use
    # ------------------------------------------------------------------

    def get_structural_bundle(self, symbol: str) -> Optional[StructuralLevelBundle]:
        """Return the latest StructuralLevelBundle for a symbol, or None."""
        return self._structural_cache.get(symbol)
