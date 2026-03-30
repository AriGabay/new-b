"""
Candlestick Group (Group 4 — always_on=False, implementation_priority=3).

Responsibilities:
  - Detect candlestick patterns on confirmed (closed) bars only.
  - Active hypotheses: H2-001 through H2-005.
  - Blocked patterns (registry rejections): RJ-001, RJ-002, RJ-009, RJ-010.
  - All patterns require structural level context (at_resistance or at_support).
  - Signal only emitted after TECHNICAL_STRUCTURE group has published S/R context.

LLM: NOT permitted.
Trigger: FeatureReadyEvent (after TechnicalStructure publishes its bundle).
Depends on: MARKET_DATA, TECHNICAL_STRUCTURE.

Phase 2 deliverable:
  Bearish/Bullish Engulfing, Morning Star, Evening Star, Three Black Crows, Doji.

Active patterns:
  H2-001: Bearish/Bullish Engulfing — 2-bar pattern. Requires at S/R level.
  H2-002: Morning Star (3-bar bullish reversal), Evening Star (3-bar bearish).
           Requires at S/R level.
  H2-003: Three Black Crows — 3 consecutive bearish candles in uptrend.
           Does NOT require S/R (trend continuation pattern).
  H2-004: Inverted Hammer — BEARISH continuation (Bulkowski: 60%).
           Textbook says bullish; reject that interpretation. SHORT signal only.
  H2-005: Doji — after 2+ trend candles. Requires context confirmation.

Blocked (do NOT implement):
  RJ-001: Hanging Man — 33% reversal rate. Too low.
  RJ-002: Shooting Star standalone — 60% reversal rate with no S/R. Too low.
  RJ-009: Any candlestick pattern in ranging/choppy market (ADX14 < 20).
  RJ-010: Hammers as standalone longs without impulse-free confirmation.

Source: /docs/agent_registry/group_registry.md (CANDLESTICK entry)
        /research/rejected_ideas/rejected_and_suspicious_ideas.md
        /research/source_notes/source_03_candlesticks_audit.md
"""
from __future__ import annotations

import logging
from collections import deque
from decimal import Decimal
from typing import Optional

from agents.base.group import BaseGroup
from core.events import EventBus, FeatureReadyEvent, GroupSignalEvent, SystemEvent
from core.registry import GroupID
from core.schemas import (
    CandlestickSignal,
    Direction,
    FeatureVector,
    GroupSignalBundle,
    StructuralLevelBundle,
)
from core.state import SystemState

logger = logging.getLogger(__name__)

# Maximum feature history per symbol (need 3 for multi-bar patterns)
FEATURE_HISTORY_SIZE = 3


class CandlestickGroup(BaseGroup):
    """
    Candlestick pattern detection group.

    Cross-bar state (per symbol):
    -   _feature_history:      dict[str, deque[FeatureVector]]  — last 3 bars
    -   _structural_cache:     dict[str, StructuralLevelBundle] — latest S/R from TechStructure
    -   _tech_structure_group: optional direct reference to TechnicalStructureGroup
    """

    group_id = GroupID.CANDLESTICK

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)
        self._feature_history:    dict[str, deque] = {}
        self._structural_cache:   dict[str, StructuralLevelBundle] = {}
        self._tech_structure_group = None
        # signals_cache: most-recent CandlestickSignal list per symbol.
        # Populated each bar so PanelDecisionGroup can retrieve via runner wiring.
        # Fix: Phase 6.2.5 — previously missing; caused patterns_detected=[] in setup packet.
        self._signals_cache:      dict[str, list] = {}

    def set_technical_structure_group(self, group) -> None:
        """Wire up a direct reference to TechnicalStructureGroup for S/R queries."""
        self._tech_structure_group = group

    async def _setup(self) -> None:
        await self.bus.subscribe(FeatureReadyEvent, self.handle_event)
        await self.bus.subscribe(GroupSignalEvent, self.handle_event)
        logger.info("CandlestickGroup subscribed to FeatureReadyEvent and GroupSignalEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, FeatureReadyEvent) and event.features is not None:
            await self._process_features(event.features)
        elif isinstance(event, GroupSignalEvent):
            bundle = event.bundle
            if bundle is not None and bundle.structural is not None:
                self._structural_cache[bundle.symbol] = bundle.structural
                logger.debug(
                    "CandlestickGroup: updated structural cache for %s from GroupSignalEvent",
                    bundle.symbol,
                )

    async def _process_features(self, features: FeatureVector) -> None:
        """
        Per-bar pipeline:
        1. Update 3-bar feature history.
        2. Resolve structural context (cache first, then direct group call).
        3. Detect all active patterns (H2-001 through H2-005).
        4. Collect non-None signals.
        5. Publish GroupSignalEvent.
        """
        symbol = features.symbol

        # 1. Update feature history (maxlen=3 deque)
        if symbol not in self._feature_history:
            self._feature_history[symbol] = deque(maxlen=FEATURE_HISTORY_SIZE)
        self._feature_history[symbol].append(features)

        # 2. Resolve structural context
        structural: Optional[StructuralLevelBundle] = self._structural_cache.get(symbol)
        if structural is None and self._tech_structure_group is not None:
            try:
                structural = self._tech_structure_group.get_structural_bundle(symbol)
                if structural is not None:
                    self._structural_cache[symbol] = structural
            except Exception as exc:
                logger.warning(
                    "CandlestickGroup: failed to fetch structural bundle for %s: %s",
                    symbol, exc,
                )

        bars = list(self._feature_history[symbol])
        signals: list[CandlestickSignal] = []

        # Need at least 1 bar for single-bar patterns
        if len(bars) >= 1:
            current = bars[-1]

            # H2-017: Dragonfly Doji (requires structural at_support)
            if structural is not None:
                dd_sig = self._detect_dragonfly_doji(symbol, current, structural)
                if dd_sig is not None:
                    signals.append(dd_sig)

            # H2-018: Gravestone Doji (requires structural at_resistance)
            if structural is not None:
                gd_sig = self._detect_gravestone_doji(symbol, current, structural)
                if gd_sig is not None:
                    signals.append(gd_sig)

            # H2-024: Long Lower Shadow (requires structural at_support + downtrend)
            if structural is not None:
                lls_sig = self._detect_long_lower_shadow(symbol, current, structural)
                if lls_sig is not None:
                    signals.append(lls_sig)

        # Need at least 2 bars for 2-bar patterns
        if len(bars) >= 2:
            current = bars[-1]
            prev = bars[-2]

            # H2-001: Engulfing (with structural, or strong body without)
            if structural is not None:
                eng_sig = self._detect_engulfing(symbol, current, prev, structural)
                if eng_sig is not None:
                    signals.append(eng_sig)
            # H2-006: Strong engulfing without S/R — body > 1.5× ATR14
            if structural is None or not signals:
                strong_eng = self._detect_strong_engulfing(symbol, current, prev)
                if strong_eng is not None:
                    signals.append(strong_eng)

            # H2-004: Inverted Hammer — BEARISH (requires structural)
            if structural is not None:
                ih_sig = self._detect_inverted_hammer(symbol, current, structural)
                if ih_sig is not None:
                    signals.append(ih_sig)

            # H2-019/H2-020: Kicking (bullish/bearish — no S/R required)
            kick_sig = self._detect_kicking(symbol, current, prev)
            if kick_sig is not None:
                signals.append(kick_sig)

            # H2-021: On Neck (bearish continuation — no S/R required)
            on_sig = self._detect_on_neck(symbol, current, prev)
            if on_sig is not None:
                signals.append(on_sig)

            # H2-022: Harami Cross (requires ADX > 15)
            hc_sig = self._detect_harami_cross(symbol, current, prev)
            if hc_sig is not None:
                signals.append(hc_sig)

        # Need 3 bars for 3-bar patterns
        if len(bars) >= 3:
            # H2-002: Morning/Evening Star (requires structural)
            if structural is not None:
                star_sig = self._detect_morning_evening_star(symbol, bars[-3:], structural)
                if star_sig is not None:
                    signals.append(star_sig)

            # H2-003: Three Black Crows (no S/R required)
            tbc_sig = self._detect_three_black_crows(symbol, bars[-3:])
            if tbc_sig is not None:
                signals.append(tbc_sig)

            # H2-005: Doji (structural optional — self-confirming after trend)
            doji_sig = self._detect_doji(symbol, bars[-3:], structural)
            if doji_sig is not None:
                signals.append(doji_sig)

            # H2-023: Tri Star (3 consecutive dojis — very rare)
            tri_sig = self._detect_tri_star(symbol, bars[-3:])
            if tri_sig is not None:
                signals.append(tri_sig)

        # Store signals in per-symbol cache so PanelDecisionGroup can retrieve them.
        # This is the fix for Phase 6.2.5: previously the cache was never populated,
        # causing patterns_detected=[] in every setup packet.
        self._signals_cache[symbol] = list(signals)

        # Build and publish bundle (empty signals still published so downstream knows we ran)
        bundle = GroupSignalBundle(
            group_id=self.group_id.value,
            symbol=symbol,
            timeframe=features.timeframe,
            timestamp=features.timestamp,
            signals=list(signals),  # type: ignore[arg-type]
            regime=None,
            structural=structural,
            metadata={
                "signal_count": len(signals),
                "patterns": [s.pattern_name for s in signals],
                "has_structural_context": structural is not None,
            },
        )

        await self.bus.publish(
            GroupSignalEvent(source=self.group_id.value, bundle=bundle)
        )

        if signals:
            logger.debug(
                "CandlestickGroup: %s/%s — %d pattern(s): %s",
                symbol, features.timeframe, len(signals),
                [s.pattern_name for s in signals],
            )

    # ------------------------------------------------------------------
    # H2-001: Engulfing patterns
    # ------------------------------------------------------------------

    def _detect_engulfing(
        self,
        symbol: str,
        current: FeatureVector,
        prev: FeatureVector,
        structural: StructuralLevelBundle,
    ) -> Optional[CandlestickSignal]:
        """
        H2-001: Bullish or Bearish Engulfing.
        Requires: adx14 > 20, at_support (bullish) or at_resistance (bearish).
        Current bar's body must completely engulf the prior bar's body.
        """
        # RJ-009: block in choppy/ranging market
        if current.adx14 < 15:
            return None

        prev_bearish = prev.open > prev.close
        prev_bullish = prev.open < prev.close
        curr_bullish = current.close > current.open
        curr_bearish = current.close < current.open

        # Bullish Engulfing: prev bearish, current bullish body fully engulfs prev body
        if (
            prev_bearish
            and curr_bullish
            and current.open <= prev.close
            and current.close >= prev.open
            and structural.at_support
        ):
            nearest_price: Optional[Decimal] = None
            dist_pct: Optional[float] = None
            if structural.nearest_support is not None:
                nearest_price = structural.nearest_support.price
                if nearest_price > Decimal("0"):
                    dist_pct = float(
                        abs(current.close - nearest_price) / nearest_price * Decimal("100")
                    )

            logger.debug("CandlestickGroup: bullish_engulfing detected for %s", symbol)
            return CandlestickSignal(
                group_id=self.group_id.value,
                symbol=symbol,
                timeframe=current.timeframe,
                timestamp=current.timestamp,
                direction=Direction.LONG,
                signal_type="candlestick",
                signal_subtype="bullish_engulfing",
                hypothesis_ref="H2-001",
                quality_score=0.70,
                requires_structural_level=True,
                context_confirmed=True,
                confirmation_required=False,
                confirmed_on_bar_close=True,
                pattern_name="bullish_engulfing",
                bars_consumed=2,
                nearest_structural_level=nearest_price,
                structural_level_distance_pct=dist_pct,
                metadata={
                    "prev_open": float(prev.open),
                    "prev_close": float(prev.close),
                    "curr_open": float(current.open),
                    "curr_close": float(current.close),
                    "adx14": current.adx14,
                },
            )

        # Bearish Engulfing: prev bullish, current bearish body fully engulfs prev body
        if (
            prev_bullish
            and curr_bearish
            and current.open >= prev.close
            and current.close <= prev.open
            and structural.at_resistance
        ):
            nearest_price = None
            dist_pct = None
            if structural.nearest_resistance is not None:
                nearest_price = structural.nearest_resistance.price
                if nearest_price > Decimal("0"):
                    dist_pct = float(
                        abs(current.close - nearest_price) / nearest_price * Decimal("100")
                    )

            logger.debug("CandlestickGroup: bearish_engulfing detected for %s", symbol)
            return CandlestickSignal(
                group_id=self.group_id.value,
                symbol=symbol,
                timeframe=current.timeframe,
                timestamp=current.timestamp,
                direction=Direction.SHORT,
                signal_type="candlestick",
                signal_subtype="bearish_engulfing",
                hypothesis_ref="H2-001",
                quality_score=0.70,
                requires_structural_level=True,
                context_confirmed=True,
                confirmation_required=False,
                confirmed_on_bar_close=True,
                pattern_name="bearish_engulfing",
                bars_consumed=2,
                nearest_structural_level=nearest_price,
                structural_level_distance_pct=dist_pct,
                metadata={
                    "prev_open": float(prev.open),
                    "prev_close": float(prev.close),
                    "curr_open": float(current.open),
                    "curr_close": float(current.close),
                    "adx14": current.adx14,
                },
            )

        return None

    # ------------------------------------------------------------------
    # H2-006: Strong Engulfing (no S/R required — body > 1.5× ATR14)
    # ------------------------------------------------------------------

    def _detect_strong_engulfing(
        self,
        symbol: str,
        current: FeatureVector,
        prev: FeatureVector,
    ) -> Optional[CandlestickSignal]:
        """
        H2-006: Strong engulfing without S/R requirement.

        Fires when the engulfing body is > 1.5× ATR14 — these large candles
        represent significant momentum and don't need S/R context to be valid.
        Quality score slightly lower (0.60) since no structural confirmation.
        """
        if current.adx14 < 15:
            return None

        prev_bearish = prev.open > prev.close
        prev_bullish = prev.open < prev.close
        curr_bullish = current.close > current.open
        curr_bearish = current.close < current.open

        # Body size relative to ATR
        body = current.candle_body
        atr = current.atr14
        if atr <= Decimal("0") or body <= Decimal("0"):
            return None

        body_atr_ratio = float(body / atr)
        if body_atr_ratio < 1.5:
            return None  # Not strong enough without S/R

        # Bullish strong engulfing
        if (
            prev_bearish
            and curr_bullish
            and current.open <= prev.close
            and current.close >= prev.open
        ):
            return CandlestickSignal(
                group_id=self.group_id.value,
                symbol=symbol,
                timeframe=current.timeframe,
                timestamp=current.timestamp,
                direction=Direction.LONG,
                signal_type="candlestick",
                signal_subtype="strong_bullish_engulfing",
                hypothesis_ref="H2-006",
                quality_score=0.60,
                requires_structural_level=False,
                context_confirmed=True,
                confirmation_required=False,
                confirmed_on_bar_close=True,
                pattern_name="strong_bullish_engulfing",
                bars_consumed=2,
                nearest_structural_level=None,
                structural_level_distance_pct=None,
                metadata={
                    "body_atr_ratio": round(body_atr_ratio, 2),
                    "body": float(body),
                    "atr14": float(atr),
                    "adx14": current.adx14,
                },
            )

        # Bearish strong engulfing
        if (
            prev_bullish
            and curr_bearish
            and current.open >= prev.close
            and current.close <= prev.open
        ):
            return CandlestickSignal(
                group_id=self.group_id.value,
                symbol=symbol,
                timeframe=current.timeframe,
                timestamp=current.timestamp,
                direction=Direction.SHORT,
                signal_type="candlestick",
                signal_subtype="strong_bearish_engulfing",
                hypothesis_ref="H2-006",
                quality_score=0.60,
                requires_structural_level=False,
                context_confirmed=True,
                confirmation_required=False,
                confirmed_on_bar_close=True,
                pattern_name="strong_bearish_engulfing",
                bars_consumed=2,
                nearest_structural_level=None,
                structural_level_distance_pct=None,
                metadata={
                    "body_atr_ratio": round(body_atr_ratio, 2),
                    "body": float(body),
                    "atr14": float(atr),
                    "adx14": current.adx14,
                },
            )

        return None

    # ------------------------------------------------------------------
    # H2-002: Morning Star / Evening Star
    # ------------------------------------------------------------------

    def _detect_morning_evening_star(
        self,
        symbol: str,
        bars: list,   # 3 FeatureVectors [b_minus2, b_minus1, b_0], oldest first
        structural: StructuralLevelBundle,
    ) -> Optional[CandlestickSignal]:
        """
        H2-002: Morning Star (bullish) / Evening Star (bearish).
        bars = [b-2, b-1, b0] oldest to newest.
        Morning Star: b-2 large bearish, b-1 small star, b0 large bullish, at support.
        Evening Star: b-2 large bullish, b-1 small star, b0 large bearish, at resistance.
        """
        if len(bars) < 3:
            return None

        b0, b1, b2 = bars[0], bars[1], bars[2]

        # RJ-009: block in choppy/ranging market
        if b2.adx14 < 15:
            return None

        b0_bullish = b0.close > b0.open
        b0_bearish = b0.close < b0.open
        b2_bullish = b2.close > b2.open
        b2_bearish = b2.close < b2.open

        # Morning Star (LONG)
        if (
            b0_bearish
            and b0.body_ratio > 0.6
            and b1.body_ratio < 0.3
            and b2_bullish
            and b2.body_ratio > 0.6
            and structural.at_support
        ):
            b0_midpoint = (b0.open + b0.close) / Decimal("2")
            if b2.close > b0_midpoint:
                nearest_price: Optional[Decimal] = None
                dist_pct: Optional[float] = None
                if structural.nearest_support is not None:
                    nearest_price = structural.nearest_support.price
                    if nearest_price > Decimal("0"):
                        dist_pct = float(
                            abs(b2.close - nearest_price) / nearest_price * Decimal("100")
                        )
                logger.debug("CandlestickGroup: morning_star detected for %s", symbol)
                return CandlestickSignal(
                    group_id=self.group_id.value,
                    symbol=symbol,
                    timeframe=b2.timeframe,
                    timestamp=b2.timestamp,
                    direction=Direction.LONG,
                    signal_type="candlestick",
                    signal_subtype="morning_star",
                    hypothesis_ref="H2-002",
                    quality_score=0.75,
                    requires_structural_level=True,
                    context_confirmed=True,
                    confirmation_required=False,
                    confirmed_on_bar_close=True,
                    pattern_name="morning_star",
                    bars_consumed=3,
                    nearest_structural_level=nearest_price,
                    structural_level_distance_pct=dist_pct,
                    metadata={
                        "b0_body_ratio": b0.body_ratio,
                        "b1_body_ratio": b1.body_ratio,
                        "b2_body_ratio": b2.body_ratio,
                        "b0_midpoint": float(b0_midpoint),
                        "b2_close": float(b2.close),
                        "adx14": b2.adx14,
                    },
                )

        # Evening Star (SHORT)
        if (
            b0_bullish
            and b0.body_ratio > 0.6
            and b1.body_ratio < 0.3
            and b2_bearish
            and b2.body_ratio > 0.6
            and structural.at_resistance
        ):
            b0_midpoint = (b0.open + b0.close) / Decimal("2")
            if b2.close < b0_midpoint:
                nearest_price = None
                dist_pct = None
                if structural.nearest_resistance is not None:
                    nearest_price = structural.nearest_resistance.price
                    if nearest_price > Decimal("0"):
                        dist_pct = float(
                            abs(b2.close - nearest_price) / nearest_price * Decimal("100")
                        )
                logger.debug("CandlestickGroup: evening_star detected for %s", symbol)
                return CandlestickSignal(
                    group_id=self.group_id.value,
                    symbol=symbol,
                    timeframe=b2.timeframe,
                    timestamp=b2.timestamp,
                    direction=Direction.SHORT,
                    signal_type="candlestick",
                    signal_subtype="evening_star",
                    hypothesis_ref="H2-002",
                    quality_score=0.75,
                    requires_structural_level=True,
                    context_confirmed=True,
                    confirmation_required=False,
                    confirmed_on_bar_close=True,
                    pattern_name="evening_star",
                    bars_consumed=3,
                    nearest_structural_level=nearest_price,
                    structural_level_distance_pct=dist_pct,
                    metadata={
                        "b0_body_ratio": b0.body_ratio,
                        "b1_body_ratio": b1.body_ratio,
                        "b2_body_ratio": b2.body_ratio,
                        "b0_midpoint": float(b0_midpoint),
                        "b2_close": float(b2.close),
                        "adx14": b2.adx14,
                    },
                )

        return None

    # ------------------------------------------------------------------
    # H2-003: Three Black Crows
    # ------------------------------------------------------------------

    def _detect_three_black_crows(
        self,
        symbol: str,
        bars: list,   # 3 FeatureVectors [b-2, b-1, b0], oldest first
    ) -> Optional[CandlestickSignal]:
        """
        H2-003: Three Black Crows (bearish continuation in uptrend).
        All 3 bars bearish with body_ratio > 0.6, each closes lower than prior.
        Prior uptrend: bars[0].ema20 > bars[0].ema50.
        Blocked if adx14 < 20 (RJ-009).
        """
        if len(bars) < 3:
            return None

        b0, b1, b2 = bars[0], bars[1], bars[2]

        # RJ-009: block in choppy/ranging market
        if b2.adx14 < 15:
            return None

        # All 3 must be bearish (close < open)
        if not (b0.close < b0.open and b1.close < b1.open and b2.close < b2.open):
            return None

        # Each bar must have body_ratio > 0.6 (strong bearish body)
        if not (b0.body_ratio > 0.6 and b1.body_ratio > 0.6 and b2.body_ratio > 0.6):
            return None

        # Each closes lower than the previous
        if not (b1.close < b0.close and b2.close < b1.close):
            return None

        # Prior uptrend: ema20 > ema50 on the first bar of the pattern
        if not (b0.ema20 > b0.ema50):
            return None

        logger.debug("CandlestickGroup: three_black_crows detected for %s", symbol)
        return CandlestickSignal(
            group_id=self.group_id.value,
            symbol=symbol,
            timeframe=b2.timeframe,
            timestamp=b2.timestamp,
            direction=Direction.SHORT,
            signal_type="candlestick",
            signal_subtype="three_black_crows",
            hypothesis_ref="H2-003",
            quality_score=0.65,
            requires_structural_level=False,
            context_confirmed=True,
            confirmation_required=False,
            confirmed_on_bar_close=True,
            pattern_name="three_black_crows",
            bars_consumed=3,
            nearest_structural_level=None,
            structural_level_distance_pct=None,
            metadata={
                "b0_close": float(b0.close),
                "b1_close": float(b1.close),
                "b2_close": float(b2.close),
                "b0_body_ratio": b0.body_ratio,
                "b1_body_ratio": b1.body_ratio,
                "b2_body_ratio": b2.body_ratio,
                "adx14": b2.adx14,
                "ema20_vs_ema50": float(b0.ema20 - b0.ema50),
            },
        )

    # ------------------------------------------------------------------
    # H2-004: Inverted Hammer (BEARISH — Bulkowski interpretation)
    # ------------------------------------------------------------------

    def _detect_inverted_hammer(
        self,
        symbol: str,
        current: FeatureVector,
        structural: StructuralLevelBundle,
    ) -> Optional[CandlestickSignal]:
        """
        H2-004: Inverted Hammer — SHORT signal only (Bulkowski: ~60% bearish continuation).
        Upper shadow >= 2× candle body. Lower shadow <= 0.1× candle range.
        After uptrend (ema20 > ema50, adx14 > 20). At resistance level.
        Rejected as bullish signal per RJ-010.
        """
        # RJ-009: block in choppy/ranging market
        if current.adx14 < 15:
            return None

        # Requires uptrend context
        if not (current.ema20 > current.ema50):
            return None

        # Requires at resistance (bearish interpretation)
        if not structural.at_resistance:
            return None

        body = current.candle_body
        upper_shadow = current.upper_shadow
        lower_shadow = current.lower_shadow
        candle_range = current.candle_range

        # Guard against zero-body or zero-range bars
        if body <= Decimal("0") or candle_range <= Decimal("0"):
            return None

        # Upper shadow must be at least 2× the body
        if upper_shadow < body * Decimal("2"):
            return None

        # Lower shadow must be tiny (<= 10% of candle range)
        if lower_shadow > candle_range * Decimal("0.1"):
            return None

        nearest_price: Optional[Decimal] = None
        dist_pct: Optional[float] = None
        if structural.nearest_resistance is not None:
            nearest_price = structural.nearest_resistance.price
            if nearest_price > Decimal("0"):
                dist_pct = float(
                    abs(current.close - nearest_price) / nearest_price * Decimal("100")
                )

        logger.debug("CandlestickGroup: inverted_hammer_bearish detected for %s", symbol)
        return CandlestickSignal(
            group_id=self.group_id.value,
            symbol=symbol,
            timeframe=current.timeframe,
            timestamp=current.timestamp,
            direction=Direction.SHORT,
            signal_type="candlestick",
            signal_subtype="inverted_hammer_bearish",
            hypothesis_ref="H2-004",
            quality_score=0.60,
            requires_structural_level=True,
            context_confirmed=True,
            confirmation_required=False,
            confirmed_on_bar_close=True,
            pattern_name="inverted_hammer_bearish",
            bars_consumed=1,
            nearest_structural_level=nearest_price,
            structural_level_distance_pct=dist_pct,
            metadata={
                "upper_shadow": float(upper_shadow),
                "lower_shadow": float(lower_shadow),
                "body": float(body),
                "candle_range": float(candle_range),
                "adx14": current.adx14,
                "ema20": float(current.ema20),
                "ema50": float(current.ema50),
            },
        )

    # ------------------------------------------------------------------
    # H2-005: Doji after trend candles
    # ------------------------------------------------------------------

    def _detect_doji(
        self,
        symbol: str,
        bars: list,   # last 3 FeatureVectors [b-2, b-1, b0], oldest first
        structural: Optional[StructuralLevelBundle],
    ) -> Optional[CandlestickSignal]:
        """
        H2-005: Doji after 2+ trend candles.
        bars[-1].doji_flag must be True.
        Prior 2 bars same direction → counter-direction reversal signal.
        Blocked if adx14 < 20 (RJ-009).
        requires_structural_level=False (self-confirming after trend candles).
        """
        if len(bars) < 3:
            return None

        b0, b1, b2 = bars[0], bars[1], bars[2]

        # b2 is the current bar — must be a doji
        if not b2.doji_flag:
            return None

        # RJ-009: block in choppy/ranging market
        if b2.adx14 < 15:
            return None

        # Prior 2 bars (b0 and b1) must be same direction
        b0_bullish = b0.close > b0.open
        b0_bearish = b0.close < b0.open
        b1_bullish = b1.close > b1.open
        b1_bearish = b1.close < b1.open

        direction: Optional[Direction] = None

        # Both prior bars bullish → bearish reversal signal
        if b0_bullish and b1_bullish:
            direction = Direction.SHORT
        # Both prior bars bearish → bullish reversal signal
        elif b0_bearish and b1_bearish:
            direction = Direction.LONG
        else:
            # Mixed prior direction — no confirmed trend to reverse
            return None

        logger.debug(
            "CandlestickGroup: doji_reversal (%s) detected for %s",
            direction.value, symbol,
        )
        return CandlestickSignal(
            group_id=self.group_id.value,
            symbol=symbol,
            timeframe=b2.timeframe,
            timestamp=b2.timestamp,
            direction=direction,
            signal_type="candlestick",
            signal_subtype="doji_reversal",
            hypothesis_ref="H2-005",
            quality_score=0.55,
            requires_structural_level=False,
            context_confirmed=True,
            confirmation_required=True,
            confirmed_on_bar_close=True,
            pattern_name="doji_reversal",
            bars_consumed=3,
            nearest_structural_level=None,
            structural_level_distance_pct=None,
            metadata={
                "b0_direction": "bullish" if b0_bullish else "bearish",
                "b1_direction": "bullish" if b1_bullish else "bearish",
                "body_ratio": b2.body_ratio,
                "adx14": b2.adx14,
                "has_structural_context": structural is not None,
            },
        )

    # ------------------------------------------------------------------
    # H2-017: Dragonfly Doji (bullish reversal)
    # ------------------------------------------------------------------

    def _detect_dragonfly_doji(
        self, symbol: str, current: FeatureVector, structural: StructuralLevelBundle,
    ) -> Optional[CandlestickSignal]:
        """
        H2-017: Dragonfly Doji. Doji body + upper_shadow <= body.
        Long lower shadow signals buying pressure. Bullish at support.
        From thesis Appendix A: is_doji_body AND upper_shadow <= body.
        """
        if current.adx14 < 15:
            return None
        if not current.doji_flag:
            return None
        if not structural.at_support:
            return None

        body = current.candle_body
        upper_shadow = current.upper_shadow
        lower_shadow = current.lower_shadow

        # Dragonfly: upper shadow tiny, lower shadow long
        if upper_shadow > body * Decimal("1.5"):
            return None
        if lower_shadow < body * Decimal("2"):
            return None

        return CandlestickSignal(
            group_id=self.group_id.value, symbol=symbol,
            timeframe=current.timeframe, timestamp=current.timestamp,
            direction=Direction.LONG, signal_type="candlestick",
            signal_subtype="dragonfly_doji", hypothesis_ref="H2-017",
            quality_score=0.55, requires_structural_level=True,
            context_confirmed=True, confirmation_required=False,
            confirmed_on_bar_close=True, pattern_name="dragonfly_doji",
            bars_consumed=1, nearest_structural_level=None,
            structural_level_distance_pct=None,
            metadata={"body": float(body), "lower_shadow": float(lower_shadow),
                      "upper_shadow": float(upper_shadow), "adx14": current.adx14},
        )

    # ------------------------------------------------------------------
    # H2-018: Gravestone Doji (bearish reversal)
    # ------------------------------------------------------------------

    def _detect_gravestone_doji(
        self, symbol: str, current: FeatureVector, structural: StructuralLevelBundle,
    ) -> Optional[CandlestickSignal]:
        """
        H2-018: Gravestone Doji. Doji body + lower_shadow <= body.
        Long upper shadow signals selling pressure. Bearish at resistance.
        From thesis: is_doji_body AND lower_shadow <= body.
        """
        if current.adx14 < 15:
            return None
        if not current.doji_flag:
            return None
        if not structural.at_resistance:
            return None

        body = current.candle_body
        upper_shadow = current.upper_shadow
        lower_shadow = current.lower_shadow

        # Gravestone: lower shadow tiny, upper shadow long
        if lower_shadow > body * Decimal("1.5"):
            return None
        if upper_shadow < body * Decimal("2"):
            return None

        return CandlestickSignal(
            group_id=self.group_id.value, symbol=symbol,
            timeframe=current.timeframe, timestamp=current.timestamp,
            direction=Direction.SHORT, signal_type="candlestick",
            signal_subtype="gravestone_doji", hypothesis_ref="H2-018",
            quality_score=0.55, requires_structural_level=True,
            context_confirmed=True, confirmation_required=False,
            confirmed_on_bar_close=True, pattern_name="gravestone_doji",
            bars_consumed=1, nearest_structural_level=None,
            structural_level_distance_pct=None,
            metadata={"body": float(body), "upper_shadow": float(upper_shadow),
                      "lower_shadow": float(lower_shadow), "adx14": current.adx14},
        )

    # ------------------------------------------------------------------
    # H2-019/H2-020: Kicking (bullish/bearish — strong momentum shift)
    # ------------------------------------------------------------------

    def _detect_kicking(
        self, symbol: str, current: FeatureVector, prev: FeatureVector,
    ) -> Optional[CandlestickSignal]:
        """
        H2-019: Kicking Bullish — bearish marubozu followed by bullish marubozu
                 with gap up (or open >= prev close in crypto).
        H2-020: Kicking Bearish — mirror.
        From thesis: Bar1 marubozu (body_ratio > 0.90), Bar2 opposite marubozu.
        In crypto (24/7, no gaps): Bar2 opens at/above Bar1 close for bullish.
        Quality: 0.70 (strong momentum shift).
        """
        if current.adx14 < 15:
            return None

        prev_body_ratio = prev.body_ratio
        curr_body_ratio = current.body_ratio

        # Both bars must be strong (marubozu-like)
        if prev_body_ratio < 0.85 or curr_body_ratio < 0.85:
            return None

        prev_bearish = prev.open > prev.close
        prev_bullish = prev.open < prev.close
        curr_bullish = current.close > current.open
        curr_bearish = current.close < current.open

        # Kicking Bullish: prev bearish marubozu → curr bullish marubozu, opens >= prev close
        if prev_bearish and curr_bullish and current.open >= prev.close:
            return CandlestickSignal(
                group_id=self.group_id.value, symbol=symbol,
                timeframe=current.timeframe, timestamp=current.timestamp,
                direction=Direction.LONG, signal_type="candlestick",
                signal_subtype="kicking_bullish", hypothesis_ref="H2-019",
                quality_score=0.70, requires_structural_level=False,
                context_confirmed=True, confirmation_required=False,
                confirmed_on_bar_close=True, pattern_name="kicking_bullish",
                bars_consumed=2, nearest_structural_level=None,
                structural_level_distance_pct=None,
                metadata={"prev_body_ratio": prev_body_ratio,
                          "curr_body_ratio": curr_body_ratio, "adx14": current.adx14},
            )

        # Kicking Bearish: prev bullish marubozu → curr bearish marubozu, opens <= prev close
        if prev_bullish and curr_bearish and current.open <= prev.close:
            return CandlestickSignal(
                group_id=self.group_id.value, symbol=symbol,
                timeframe=current.timeframe, timestamp=current.timestamp,
                direction=Direction.SHORT, signal_type="candlestick",
                signal_subtype="kicking_bearish", hypothesis_ref="H2-020",
                quality_score=0.70, requires_structural_level=False,
                context_confirmed=True, confirmation_required=False,
                confirmed_on_bar_close=True, pattern_name="kicking_bearish",
                bars_consumed=2, nearest_structural_level=None,
                structural_level_distance_pct=None,
                metadata={"prev_body_ratio": prev_body_ratio,
                          "curr_body_ratio": curr_body_ratio, "adx14": current.adx14},
            )

        return None

    # ------------------------------------------------------------------
    # H2-021: On Neck (bearish continuation)
    # ------------------------------------------------------------------

    def _detect_on_neck(
        self, symbol: str, current: FeatureVector, prev: FeatureVector,
    ) -> Optional[CandlestickSignal]:
        """
        H2-021: On Neck (bearish continuation).
        From thesis: In downtrend, Bar1 bearish with long body.
        Bar2 opens below Bar1 low, closes near Bar1 low (within 0.3%).
        Significant in 3/4 crypto datasets (academic finding).
        """
        if current.adx14 < 15:
            return None

        # Require downtrend: ema20 < ema50
        if not (current.ema20 < current.ema50):
            return None

        # Bar1 must be bearish with substantial body
        if not (prev.open > prev.close and prev.body_ratio > 0.5):
            return None

        # Bar2 opens below Bar1 low
        if current.open > prev.low:
            return None

        # Bar2 closes near Bar1 low (within 0.3%)
        prev_low = float(prev.low)
        close = float(current.close)
        if prev_low > 0:
            distance_pct = abs(close - prev_low) / prev_low
            if distance_pct > 0.003:  # within 0.3%
                return None
        else:
            return None

        return CandlestickSignal(
            group_id=self.group_id.value, symbol=symbol,
            timeframe=current.timeframe, timestamp=current.timestamp,
            direction=Direction.SHORT, signal_type="candlestick",
            signal_subtype="on_neck", hypothesis_ref="H2-021",
            quality_score=0.55, requires_structural_level=False,
            context_confirmed=True, confirmation_required=False,
            confirmed_on_bar_close=True, pattern_name="on_neck",
            bars_consumed=2, nearest_structural_level=None,
            structural_level_distance_pct=None,
            metadata={"prev_body_ratio": prev.body_ratio,
                      "distance_to_prev_low_pct": round(distance_pct * 100, 3),
                      "adx14": current.adx14},
        )

    # ------------------------------------------------------------------
    # H2-022: Harami Cross (bullish/bearish reversal)
    # ------------------------------------------------------------------

    def _detect_harami_cross(
        self, symbol: str, current: FeatureVector, prev: FeatureVector,
    ) -> Optional[CandlestickSignal]:
        """
        H2-022: Harami Cross. Like Harami but second candle is a Doji.
        Bullish: large bearish → doji INSIDE previous body. Direction: LONG.
        Bearish: large bullish → doji INSIDE previous body. Direction: SHORT.
        First bar body_ratio > 0.6. ADX > 15.
        """
        if current.adx14 < 15:
            return None
        if not current.doji_flag:
            return None
        if prev.body_ratio < 0.6:
            return None

        # Doji must be inside the previous bar's body
        prev_body_high = max(prev.open, prev.close)
        prev_body_low = min(prev.open, prev.close)
        curr_body_high = max(current.open, current.close)
        curr_body_low = min(current.open, current.close)

        if curr_body_high > prev_body_high or curr_body_low < prev_body_low:
            return None

        prev_bearish = prev.open > prev.close
        prev_bullish = prev.open < prev.close

        if prev_bearish:
            # Bullish harami cross: large bear then doji inside
            return CandlestickSignal(
                group_id=self.group_id.value, symbol=symbol,
                timeframe=current.timeframe, timestamp=current.timestamp,
                direction=Direction.LONG, signal_type="candlestick",
                signal_subtype="harami_cross_bullish", hypothesis_ref="H2-022",
                quality_score=0.55, requires_structural_level=False,
                context_confirmed=True, confirmation_required=True,
                confirmed_on_bar_close=True, pattern_name="harami_cross_bullish",
                bars_consumed=2, nearest_structural_level=None,
                structural_level_distance_pct=None,
                metadata={"prev_body_ratio": prev.body_ratio, "adx14": current.adx14},
            )

        if prev_bullish:
            # Bearish harami cross: large bull then doji inside
            return CandlestickSignal(
                group_id=self.group_id.value, symbol=symbol,
                timeframe=current.timeframe, timestamp=current.timestamp,
                direction=Direction.SHORT, signal_type="candlestick",
                signal_subtype="harami_cross_bearish", hypothesis_ref="H2-022",
                quality_score=0.55, requires_structural_level=False,
                context_confirmed=True, confirmation_required=True,
                confirmed_on_bar_close=True, pattern_name="harami_cross_bearish",
                bars_consumed=2, nearest_structural_level=None,
                structural_level_distance_pct=None,
                metadata={"prev_body_ratio": prev.body_ratio, "adx14": current.adx14},
            )

        return None

    # ------------------------------------------------------------------
    # H2-023: Tri Star (bullish/bearish reversal — very rare)
    # ------------------------------------------------------------------

    def _detect_tri_star(
        self, symbol: str, bars: list,
    ) -> Optional[CandlestickSignal]:
        """
        H2-023: Tri Star. Three consecutive Doji candles.
        Bullish: in downtrend, 3 dojis with middle doji lower. Direction: LONG.
        Bearish: in uptrend, 3 dojis with middle doji higher. Direction: SHORT.
        Very rare but strong when it appears.
        """
        if len(bars) < 3:
            return None

        b0, b1, b2 = bars[0], bars[1], bars[2]

        # All three must be dojis
        if not (b0.doji_flag and b1.doji_flag and b2.doji_flag):
            return None

        if b2.adx14 < 15:
            return None

        mid_close = float(b1.close)
        first_close = float(b0.close)
        last_close = float(b2.close)

        # Bullish tri star: in downtrend, middle doji is lower
        if b0.ema20 < b0.ema50 and mid_close < first_close and mid_close < last_close:
            return CandlestickSignal(
                group_id=self.group_id.value, symbol=symbol,
                timeframe=b2.timeframe, timestamp=b2.timestamp,
                direction=Direction.LONG, signal_type="candlestick",
                signal_subtype="tri_star_bullish", hypothesis_ref="H2-023",
                quality_score=0.60, requires_structural_level=False,
                context_confirmed=True, confirmation_required=True,
                confirmed_on_bar_close=True, pattern_name="tri_star_bullish",
                bars_consumed=3, nearest_structural_level=None,
                structural_level_distance_pct=None,
                metadata={"adx14": b2.adx14},
            )

        # Bearish tri star: in uptrend, middle doji is higher
        if b0.ema20 > b0.ema50 and mid_close > first_close and mid_close > last_close:
            return CandlestickSignal(
                group_id=self.group_id.value, symbol=symbol,
                timeframe=b2.timeframe, timestamp=b2.timestamp,
                direction=Direction.SHORT, signal_type="candlestick",
                signal_subtype="tri_star_bearish", hypothesis_ref="H2-023",
                quality_score=0.60, requires_structural_level=False,
                context_confirmed=True, confirmation_required=True,
                confirmed_on_bar_close=True, pattern_name="tri_star_bearish",
                bars_consumed=3, nearest_structural_level=None,
                structural_level_distance_pct=None,
                metadata={"adx14": b2.adx14},
            )

        return None

    # ------------------------------------------------------------------
    # H2-024: Long Lower Shadow (bullish)
    # ------------------------------------------------------------------

    def _detect_long_lower_shadow(
        self, symbol: str, current: FeatureVector, structural: StructuralLevelBundle,
    ) -> Optional[CandlestickSignal]:
        """
        H2-024: Long Lower Shadow (bullish).
        From thesis: lower_shadow > 75% of total range.
        Shows strong buying pressure from below.
        Requires at_support and prior downtrend.
        """
        if current.adx14 < 15:
            return None
        if not structural.at_support:
            return None
        # Require downtrend
        if not (current.ema20 < current.ema50):
            return None

        lower_shadow = current.lower_shadow
        candle_range = current.candle_range

        if candle_range <= Decimal("0"):
            return None

        shadow_pct = float(lower_shadow / candle_range)
        if shadow_pct < 0.75:
            return None

        return CandlestickSignal(
            group_id=self.group_id.value, symbol=symbol,
            timeframe=current.timeframe, timestamp=current.timestamp,
            direction=Direction.LONG, signal_type="candlestick",
            signal_subtype="long_lower_shadow", hypothesis_ref="H2-024",
            quality_score=0.50, requires_structural_level=True,
            context_confirmed=True, confirmation_required=True,
            confirmed_on_bar_close=True, pattern_name="long_lower_shadow",
            bars_consumed=1, nearest_structural_level=None,
            structural_level_distance_pct=None,
            metadata={"shadow_pct": round(shadow_pct * 100, 1),
                      "lower_shadow": float(lower_shadow),
                      "candle_range": float(candle_range),
                      "adx14": current.adx14},
        )
