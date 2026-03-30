"""
Indicators Group (Group 3 — always_on=False, implementation_priority=2).

BTC/Bybit focused. Processes FeatureVector and produces indicator signals.

Active hypotheses:
  H3-001: RSI divergence (impulse-filtered)
  H3-002: EMA 20/50 crossover (golden/death cross) — transition signal
  H3-004: BB squeeze → breakout
  H3-005: EMA trend continuation / pullback-to-EMA — established-trend signal

H3-002 vs H3-005 distinction:
  H3-002 fires at the EXACT crossover bar (EMA20 just crossed EMA50).  At
  that moment EMA alignment is "partial" or "mixed" — the trend is beginning,
  not established.  The panel evaluators (TrendFollowing, Momentum) score
  these transition setups poorly.

  H3-005 fires during ESTABLISHED trends (EMA20 < EMA50 < EMA200 for SHORT;
  EMA20 > EMA50 > EMA200 for LONG) when price pulls back near EMA20.  At
  these bars EMA alignment is "full_bear" or "full_bull", which is what the
  panel evaluators reward.  H3-005 is the primary source of high-quality
  continuation proposals.

11 sub-agent methods:
  1.  _parse_features             — extract and classify all indicator values
  2.  _detect_ema_crossover       — golden/death cross detection (H3-002)
  3.  _detect_trend_continuation  — pullback-to-EMA in established trend (H3-005)
  4.  _detect_rsi_signal          — RSI trend + divergence setup check
  5.  _detect_macd_signal         — MACD cross + histogram momentum
  6.  _detect_bb_signal           — BB squeeze / expansion breakout (H3-004)
  7.  _compute_regime             — compute RegimeContext, update SystemState
  8.  _validate_signals           — remove contradictory signals
  9.  _score_signals              — assign quality_score to each signal
  10. _summarize_indicator_state  — produce text summary for setup packet
  11. _build_bundle               — assemble GroupSignalBundle

LLM: NOT permitted.
Trigger: FeatureReadyEvent.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional

from agents.base.group import BaseGroup
from core.events import EventBus, FeatureReadyEvent, GroupSignalEvent, SystemEvent
from core.registry import GroupID
from core.schemas import (
    Direction, FeatureVector, GroupSignalBundle, IndicatorSignal, RegimeContext
)
from core.state import SystemState
from features.compute import FeatureComputer

logger = logging.getLogger(__name__)

# BB squeeze threshold: bb_width_pct below this → squeeze active
BB_SQUEEZE_THRESHOLD = 35.0  # Relaxed from 25 → 35 for more squeeze detections on 1h
# EMA crossover ADX minimum (relaxed from 20 → 15 for broader signal generation)
EMA_CROSS_ADX_MIN = 15.0
# MACD history kept per symbol (closes for recompute)
MACD_HISTORY_SIZE = 60
# RSI divergence lookback bars
RSI_DIVERGENCE_LOOKBACK = 10


class IndicatorsGroup(BaseGroup):
    """
    Indicator signal generator for BTC/Bybit.

    Cross-bar state (per symbol):
    -   _squeeze_active:    dict[str, bool]    — BB squeeze active
    -   _prev_macd_line:    dict[str, Decimal] — previous MACD line
    -   _prev_signal_line:  dict[str, Decimal] — previous signal line
    -   _closes_cache:      dict[str, list]    — last 60 closes for MACD
    -   _rsi_history:       dict[str, list]    — last RSI_DIVERGENCE_LOOKBACK RSIs
    -   _price_history:     dict[str, list]    — last RSI_DIVERGENCE_LOOKBACK closes
    """

    group_id = GroupID.INDICATORS

    def __init__(
        self,
        state: SystemState,
        bus: EventBus,
        config: Optional[dict] = None,
    ) -> None:
        super().__init__(state, bus, config)
        self._squeeze_active:   dict[str, bool]    = {}
        self._prev_macd_line:   dict[str, Decimal] = {}
        self._prev_signal_line: dict[str, Decimal] = {}
        self._closes_cache:     dict[str, list]    = {}  # list[Decimal], rolling 60
        self._rsi_history:      dict[str, list]    = {}  # list[float]
        self._price_history:    dict[str, list]    = {}  # list[Decimal]
        self._computer = FeatureComputer()

    async def _setup(self) -> None:
        await self.bus.subscribe(FeatureReadyEvent, self.handle_event)
        logger.info("IndicatorsGroup subscribed to FeatureReadyEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, FeatureReadyEvent) and event.features is not None:
            await self._process_features(event.features)

    async def _process_features(self, fv: FeatureVector) -> None:
        """
        Full indicator pipeline for one bar close.
        """
        symbol = fv.symbol

        # 1. Update closes cache for MACD recompute
        if symbol not in self._closes_cache:
            self._closes_cache[symbol] = []
        self._closes_cache[symbol].append(fv.close)
        if len(self._closes_cache[symbol]) > MACD_HISTORY_SIZE:
            self._closes_cache[symbol] = self._closes_cache[symbol][-MACD_HISTORY_SIZE:]

        # 2. Update RSI + price history for divergence
        if symbol not in self._rsi_history:
            self._rsi_history[symbol] = []
            self._price_history[symbol] = []
        self._rsi_history[symbol].append(fv.rsi14)
        self._price_history[symbol].append(fv.close)
        if len(self._rsi_history[symbol]) > RSI_DIVERGENCE_LOOKBACK:
            self._rsi_history[symbol] = self._rsi_history[symbol][-RSI_DIVERGENCE_LOOKBACK:]
            self._price_history[symbol] = self._price_history[symbol][-RSI_DIVERGENCE_LOOKBACK:]

        # 3. Parse feature values (sub-agent 1)
        parsed = self._parse_features(fv)

        # 4. Run all detection sub-agents
        signals: list[IndicatorSignal] = []

        ema_sig = self._detect_ema_crossover(fv)
        if ema_sig is not None:
            signals.append(ema_sig)

        cont_sig = self._detect_trend_continuation(fv)
        if cont_sig is not None:
            signals.append(cont_sig)

        rsi_sig = self._detect_rsi_signal(fv)
        if rsi_sig is not None:
            signals.append(rsi_sig)

        macd_sig = self._detect_macd_signal(fv, self._closes_cache[symbol])
        if macd_sig is not None:
            signals.append(macd_sig)

        bb_sig = self._detect_bb_signal(fv)
        if bb_sig is not None:
            signals.append(bb_sig)

        # H3-006: DISABLED — fires on every trending bar (6,628× in 2yr),
        # overwhelming quality signals and causing 0% WR when combined with
        # active-weight normalization. H3-005 trend continuation (3,230×)
        # is the proper established-trend signal.
        # trend_sig = self._detect_trend_aligned(fv)
        # if trend_sig is not None:
        #     signals.append(trend_sig)

        # H3-007: RSI mean reversion — fires when RSI crosses key levels
        rsi_mr_sig = self._detect_rsi_mean_reversion(fv)
        if rsi_mr_sig is not None:
            signals.append(rsi_mr_sig)

        # H3-008: Volume breakout — fires on high-volume momentum bars
        vol_sig = self._detect_volume_breakout(fv)
        if vol_sig is not None:
            signals.append(vol_sig)

        # 5. Compute regime and update state (sub-agent 6)
        regime = self._compute_regime(fv)
        await self.state.update_regime(regime)

        # 6. Validate + score signals
        signals = self._validate_signals(signals, fv)
        signals = self._score_signals(signals, fv)

        # 7. Build and publish bundle
        bundle = self._build_bundle(
            symbol=fv.symbol,
            timeframe=fv.timeframe,
            timestamp=fv.timestamp,
            signals=signals,
            regime=regime,
        )

        await self.bus.publish(
            GroupSignalEvent(source=self.group_id.value, bundle=bundle)
        )

        logger.debug(
            "IndicatorsGroup: %s/%s — %d signal(s) | regime=%s/%s",
            fv.symbol, fv.timeframe, len(signals),
            regime.btc_macro, regime.volatility_regime,
        )

    # ------------------------------------------------------------------
    # Sub-agent 1: _parse_features
    # ------------------------------------------------------------------

    def _parse_features(self, fv: FeatureVector) -> dict:
        """Extract and classify all indicator values into a structured dict."""
        # EMA alignment
        if fv.ema20 > fv.ema50 > fv.ema200:
            ema_alignment = "full_bull"
        elif fv.ema20 < fv.ema50 < fv.ema200:
            ema_alignment = "full_bear"
        elif fv.ema20 > fv.ema50:
            ema_alignment = "partial_bull"
        elif fv.ema20 < fv.ema50:
            ema_alignment = "partial_bear"
        else:
            ema_alignment = "mixed"

        # RSI direction
        rsi_delta = fv.rsi14 - fv.prev_rsi14
        if rsi_delta > 0.5:
            rsi_direction = "rising"
        elif rsi_delta < -0.5:
            rsi_direction = "falling"
        else:
            rsi_direction = "flat"

        # ATR ratio
        if fv.atr14_sma20 > Decimal("0"):
            atr_vs_sma20 = float(fv.atr14 / fv.atr14_sma20)
        else:
            atr_vs_sma20 = 1.0

        # Volatility regime
        if atr_vs_sma20 > 1.4:
            vol_regime = "high"
        elif atr_vs_sma20 < 0.7:
            vol_regime = "low"
        else:
            vol_regime = "normal"

        # Trend strength
        if fv.adx14 > 25:
            trend_strength = "strong"
        elif fv.adx14 >= 20:
            trend_strength = "moderate"
        else:
            trend_strength = "weak"

        # Volume character
        if fv.volume_ratio > 2.0:
            vol_char = "surge"
        elif fv.volume_ratio > 1.2:
            vol_char = "above_avg"
        elif fv.volume_ratio > 0.7:
            vol_char = "normal"
        else:
            vol_char = "below_avg"

        # BB position
        close = fv.close
        if close > fv.bb_upper:
            bb_position = "above_upper"
        elif close > fv.bb_middle + (fv.bb_upper - fv.bb_middle) * Decimal("0.5"):
            bb_position = "near_upper"
        elif close < fv.bb_lower:
            bb_position = "below_lower"
        elif close < fv.bb_middle - (fv.bb_middle - fv.bb_lower) * Decimal("0.5"):
            bb_position = "near_lower"
        else:
            bb_position = "middle"

        return {
            "ema_alignment": ema_alignment,
            "rsi_direction": rsi_direction,
            "atr_vs_sma20": atr_vs_sma20,
            "vol_regime": vol_regime,
            "trend_strength": trend_strength,
            "vol_char": vol_char,
            "bb_position": bb_position,
        }

    # ------------------------------------------------------------------
    # Sub-agent 2: _detect_ema_crossover (H3-002)
    # ------------------------------------------------------------------

    def _detect_ema_crossover(self, fv: FeatureVector) -> Optional[IndicatorSignal]:
        """
        H3-002: Golden/death cross detection on EMA 20/50.
        - Golden cross: prev_ema20 < prev_ema50 AND ema20 > ema50 → LONG
        - Death cross:  prev_ema20 > prev_ema50 AND ema20 < ema50 → SHORT
        - Context filter: adx14 >= 20 required.
        """
        if fv.adx14 < EMA_CROSS_ADX_MIN:
            return None

        golden_cross = (
            fv.prev_ema20 < fv.prev_ema50
            and fv.ema20 > fv.ema50
        )
        death_cross = (
            fv.prev_ema20 > fv.prev_ema50
            and fv.ema20 < fv.ema50
        )

        if golden_cross:
            direction = Direction.LONG
            subtype = "golden_cross"
        elif death_cross:
            direction = Direction.SHORT
            subtype = "death_cross"
        else:
            return None

        # EMA alignment bonus info
        if fv.ema20 > fv.ema50 > fv.ema200:
            ema_context = "full_bull_alignment"
        elif fv.ema20 < fv.ema50 < fv.ema200:
            ema_context = "full_bear_alignment"
        else:
            ema_context = "partial_alignment"

        return IndicatorSignal(
            group_id=self.group_id.value,
            symbol=fv.symbol,
            timeframe=fv.timeframe,
            timestamp=fv.timestamp,
            direction=direction,
            signal_type="indicator",
            signal_subtype=subtype,
            hypothesis_ref="H3-002",
            quality_score=0.0,  # scored later
            context_confirmed=True,
            confirmation_required=False,
            confirmed_on_bar_close=True,
            indicator_name="ema_crossover",
            indicator_values={
                "ema20": float(fv.ema20),
                "ema50": float(fv.ema50),
                "ema200": float(fv.ema200),
                "prev_ema20": float(fv.prev_ema20),
                "prev_ema50": float(fv.prev_ema50),
                "adx14": fv.adx14,
                "ema_context": ema_context,
            },
            context_filter_passed=True,
            metadata={"cross_type": subtype},
        )

    # ------------------------------------------------------------------
    # Sub-agent 3: _detect_trend_continuation (H3-005)
    # ------------------------------------------------------------------

    def _detect_trend_continuation(self, fv: FeatureVector) -> Optional[IndicatorSignal]:
        """
        H3-005: EMA trend continuation / pullback-to-EMA signal.

        Fires when price is in an ESTABLISHED trend (full EMA alignment with
        meaningful separation between EMA20 and EMA50) and pulls back near
        EMA20, suggesting a high-probability continuation entry.

        This is distinct from H3-002 (EMA crossover):
        - H3-002 fires at the exact transition bar (EMA20 just crosses EMA50).
          At that moment EMA alignment is "partial" or "mixed" and the panel
          evaluators penalise the ambiguous signal quality.
        - H3-005 fires during the established trend phase where EMA alignment
          is "full_bear" / "full_bull" — the bar type that TrendFollowing,
          MacroRegime, and Momentum score positively.

        SHORT conditions (ALL required):
          - full_bear EMA alignment: EMA20 < EMA50 < EMA200
          - EMA separation >= 0.2 % of EMA50 (trend committed, not just crossed)
          - Price within 3 % below EMA20 (pullback retest of short-term EMA)
          - ADX >= 25 (trending market, not ranging)
          - volume_ratio >= 1.0 (at-least-average participation)
          - RSI between 35 and 65 (pulled back from overbought, not yet oversold)

        LONG conditions (mirror of SHORT):
          - full_bull EMA alignment: EMA20 > EMA50 > EMA200
          - EMA separation >= 0.2 %
          - Price within 3 % above EMA20 (pullback to short-term EMA from above)
          - ADX >= 25, volume_ratio >= 1.0, RSI 35–65

        The "within 3 % of EMA20" window captures:
          - Shallow pullbacks that touch or approach EMA20 (prime continuation zone)
          - Excludes deep retracements far below EMA20 (different setup type)
        """
        # Minimum trend strength (relaxed from 25 → 20 for more signals)
        if fv.adx14 < 20.0:
            return None
        if fv.volume_ratio < 0.8:
            return None

        ema20 = float(fv.ema20)
        ema50 = float(fv.ema50)
        ema200 = float(fv.ema200)
        close = float(fv.close)

        # Require meaningful EMA separation so we don't fire near the crossover bar
        ema_separation_pct = abs(ema50 - ema20) / ema50 if ema50 > 0 else 0.0
        if ema_separation_pct < 0.001:   # < 0.1 % — EMAs too close (relaxed from 0.2%)
            return None

        full_bear = fv.ema20 < fv.ema50 and fv.ema50 < fv.ema200
        full_bull = fv.ema20 > fv.ema50 and fv.ema50 > fv.ema200

        if not full_bear and not full_bull:
            return None

        rsi = fv.rsi14

        if full_bear:
            # SHORT continuation: price pulls back to EMA20 from below.
            # close within 5% BELOW EMA20 — wider pullback zone (was 3%)
            price_near_ema20 = (close > ema20 * 0.95) and (close <= ema20 * 1.02)
            # RSI in mid-zone (widened from 35-65 to 30-70)
            rsi_ok = 30.0 < rsi < 70.0
            if not (price_near_ema20 and rsi_ok):
                return None
            direction = Direction.SHORT
            subtype = "trend_continuation_short"
            ema_context = "full_bear_alignment"

        else:  # full_bull
            # LONG continuation: price pulls back to EMA20 from above.
            price_near_ema20 = (close < ema20 * 1.05) and (close >= ema20 * 0.98)
            rsi_ok = 30.0 < rsi < 70.0
            if not (price_near_ema20 and rsi_ok):
                return None
            direction = Direction.LONG
            subtype = "trend_continuation_long"
            ema_context = "full_bull_alignment"

        return IndicatorSignal(
            group_id=self.group_id.value,
            symbol=fv.symbol,
            timeframe=fv.timeframe,
            timestamp=fv.timestamp,
            direction=direction,
            signal_type="indicator",
            signal_subtype=subtype,
            hypothesis_ref="H3-005",
            quality_score=0.0,   # scored later by _score_signals
            context_confirmed=True,
            confirmation_required=False,
            confirmed_on_bar_close=True,
            indicator_name="ema_trend_continuation",
            indicator_values={
                "ema20": ema20,
                "ema50": ema50,
                "ema200": ema200,
                "close": close,
                "ema_separation_pct": round(ema_separation_pct * 100, 3),
                "ema_context": ema_context,
                "adx14": fv.adx14,
                "volume_ratio": fv.volume_ratio,
                "rsi14": rsi,
            },
            context_filter_passed=True,
            metadata={"setup_type": "trend_continuation"},
        )

    # ------------------------------------------------------------------
    # Sub-agent 3b: _detect_trend_aligned (H3-006) — high-frequency trend signal
    # ------------------------------------------------------------------

    def _detect_trend_aligned(self, fv: FeatureVector) -> Optional[IndicatorSignal]:
        """
        H3-006: Trend-aligned bar signal.

        Fires on EVERY bar where:
          - Full EMA alignment (EMA20 > EMA50 > EMA200 for bull, inverse for bear)
          - ADX >= 20 (trending market)
          - Price on the correct side of EMA20 (above for bull, below for bear)

        This is a HIGH-FREQUENCY signal designed to ensure the pipeline has
        enough CandidateTradeEvents. Quality is moderate (0.55) — the panel
        evaluators are responsible for filtering out bad setups.

        Cooldown: only fires if no H3-005 (trend continuation) fired on this bar,
        to avoid duplicate signals.
        """
        if fv.adx14 < 20.0:
            return None

        close = float(fv.close)
        ema20 = float(fv.ema20)
        ema50 = float(fv.ema50)
        ema200 = float(fv.ema200)

        full_bull = ema20 > ema50 > ema200
        full_bear = ema20 < ema50 < ema200

        if not full_bull and not full_bear:
            return None

        if full_bull and close >= ema20:
            direction = Direction.LONG
            ema_context = "full_bull_alignment"
        elif full_bear and close <= ema20:
            direction = Direction.SHORT
            ema_context = "full_bear_alignment"
        else:
            return None

        return IndicatorSignal(
            group_id=self.group_id.value,
            symbol=fv.symbol,
            timeframe=fv.timeframe,
            timestamp=fv.timestamp,
            direction=direction,
            signal_type="indicator",
            signal_subtype="trend_aligned",
            hypothesis_ref="H3-006",
            quality_score=0.0,   # scored later
            context_confirmed=True,
            confirmation_required=False,
            confirmed_on_bar_close=True,
            indicator_name="trend_aligned",
            indicator_values={
                "ema20": ema20, "ema50": ema50, "ema200": ema200,
                "close": close, "adx14": fv.adx14,
                "ema_context": ema_context,
            },
            context_filter_passed=True,
            metadata={"setup_type": "trend_aligned"},
        )

    # ------------------------------------------------------------------
    # Sub-agent 3c: _detect_rsi_mean_reversion (H3-007)
    # ------------------------------------------------------------------

    def _detect_rsi_mean_reversion(self, fv: FeatureVector) -> Optional[IndicatorSignal]:
        """
        H3-007: RSI mean reversion signal.

        Fires when RSI crosses key mean-reversion thresholds:
          - LONG:  RSI crosses above 35 from below (oversold recovery)
          - SHORT: RSI crosses below 65 from above (overbought fade)

        Wider than H3-001 (which requires RSI < 30 / > 70 extremes).
        Should fire 80-150 times over 2 years on 1h BTC.
        """
        if fv.impulse_flag:
            return None

        rsi = fv.rsi14
        prev_rsi = fv.prev_rsi14

        # Bullish: RSI crosses above 35 from below
        if prev_rsi < 35 and rsi >= 35 and rsi < 55:
            direction = Direction.LONG
            subtype = "rsi_mean_reversion_long"
        # Bearish: RSI crosses below 65 from above
        elif prev_rsi > 65 and rsi <= 65 and rsi > 45:
            direction = Direction.SHORT
            subtype = "rsi_mean_reversion_short"
        else:
            return None

        return IndicatorSignal(
            group_id=self.group_id.value,
            symbol=fv.symbol,
            timeframe=fv.timeframe,
            timestamp=fv.timestamp,
            direction=direction,
            signal_type="indicator",
            signal_subtype=subtype,
            hypothesis_ref="H3-007",
            quality_score=0.0,  # scored later
            context_confirmed=True,
            confirmation_required=False,
            confirmed_on_bar_close=True,
            indicator_name="rsi_mean_reversion",
            indicator_values={
                "rsi14": rsi,
                "prev_rsi14": prev_rsi,
                "adx14": fv.adx14,
                "volume_ratio": fv.volume_ratio,
            },
            context_filter_passed=True,
            metadata={"rsi_zone": "mean_reversion"},
        )

    # ------------------------------------------------------------------
    # Sub-agent 3d: _detect_volume_breakout (H3-008)
    # ------------------------------------------------------------------

    def _detect_volume_breakout(self, fv: FeatureVector) -> Optional[IndicatorSignal]:
        """
        H3-008: Volume breakout signal.

        Fires when:
          - volume_ratio > 2.0 (volume > 2× 20-bar SMA)
          - Price move > 0.5× ATR14 in one bar (meaningful momentum)
          - ADX >= 15 (not totally dead market)

        Direction from bar direction (close vs open).
        Should fire 100-200 times over 2 years on 1h BTC.
        """
        if fv.volume_ratio < 2.0:
            return None
        if fv.adx14 < 15.0:
            return None

        # Price move must be significant relative to ATR
        bar_move = abs(float(fv.close - fv.open))
        atr = float(fv.atr14) if fv.atr14 > 0 else 1.0
        if bar_move < 0.5 * atr:
            return None

        if fv.close > fv.open:
            direction = Direction.LONG
            subtype = "volume_breakout_long"
        elif fv.close < fv.open:
            direction = Direction.SHORT
            subtype = "volume_breakout_short"
        else:
            return None

        return IndicatorSignal(
            group_id=self.group_id.value,
            symbol=fv.symbol,
            timeframe=fv.timeframe,
            timestamp=fv.timestamp,
            direction=direction,
            signal_type="indicator",
            signal_subtype=subtype,
            hypothesis_ref="H3-008",
            quality_score=0.0,  # scored later
            context_confirmed=True,
            confirmation_required=False,
            confirmed_on_bar_close=True,
            indicator_name="volume_breakout",
            indicator_values={
                "volume_ratio": fv.volume_ratio,
                "bar_move": bar_move,
                "atr14": atr,
                "move_atr_ratio": round(bar_move / atr, 3),
                "adx14": fv.adx14,
                "rsi14": fv.rsi14,
                "prev_rsi14": fv.prev_rsi14,
            },
            context_filter_passed=True,
            metadata={"breakout_type": "volume"},
        )

    # ------------------------------------------------------------------
    # Sub-agent 4: _detect_rsi_signal (H3-001)
    # ------------------------------------------------------------------

    def _detect_rsi_signal(self, fv: FeatureVector) -> Optional[IndicatorSignal]:
        """
        RSI trend alignment and divergence setup.
        - Overbought warning: rsi14 > 70 and rising → bearish pressure
        - Oversold setup: rsi14 < 30 and rising → bullish setup
        - RSI momentum: rsi14 > 50 and rising → bullish; < 50 falling → bearish
        - Suppress if impulse_flag = True (H3-001 filter)
        """
        if fv.impulse_flag:
            return None  # Never chase impulse candles

        rsi = fv.rsi14
        prev_rsi = fv.prev_rsi14
        rsi_rising = rsi > prev_rsi

        # Oversold bounce setup (H3-001 bullish divergence proxy)
        if rsi < 30 and rsi_rising and fv.adx14 >= 15:
            return IndicatorSignal(
                group_id=self.group_id.value,
                symbol=fv.symbol,
                timeframe=fv.timeframe,
                timestamp=fv.timestamp,
                direction=Direction.LONG,
                signal_type="indicator",
                signal_subtype="rsi_oversold_bounce",
                hypothesis_ref="H3-001",
                quality_score=0.0,
                context_confirmed=True,
                confirmation_required=True,
                confirmed_on_bar_close=True,
                indicator_name="rsi",
                indicator_values={
                    "rsi14": rsi,
                    "prev_rsi14": prev_rsi,
                    "adx14": fv.adx14,
                },
                context_filter_passed=True,
                metadata={"rsi_zone": "oversold"},
            )

        # Overbought warning (bearish pressure)
        if rsi > 70 and not rsi_rising and fv.adx14 >= 15:
            return IndicatorSignal(
                group_id=self.group_id.value,
                symbol=fv.symbol,
                timeframe=fv.timeframe,
                timestamp=fv.timestamp,
                direction=Direction.SHORT,
                signal_type="indicator",
                signal_subtype="rsi_overbought_fade",
                hypothesis_ref="H3-001",
                quality_score=0.0,
                context_confirmed=True,
                confirmation_required=True,
                confirmed_on_bar_close=True,
                indicator_name="rsi",
                indicator_values={
                    "rsi14": rsi,
                    "prev_rsi14": prev_rsi,
                    "adx14": fv.adx14,
                },
                context_filter_passed=True,
                metadata={"rsi_zone": "overbought"},
            )

        # RSI divergence: price lower low but RSI higher low (bullish)
        symbol = fv.symbol
        prices = self._price_history.get(symbol, [])
        rsis = self._rsi_history.get(symbol, [])

        if len(prices) >= 5 and len(rsis) >= 5 and fv.adx14 >= 18:
            # Bullish divergence: recent price lower than 5 bars ago, RSI higher
            price_5ago = prices[-5]
            rsi_5ago = rsis[-5]
            if fv.close < price_5ago and fv.rsi14 > rsi_5ago and rsi_rising:
                return IndicatorSignal(
                    group_id=self.group_id.value,
                    symbol=fv.symbol,
                    timeframe=fv.timeframe,
                    timestamp=fv.timestamp,
                    direction=Direction.LONG,
                    signal_type="indicator",
                    signal_subtype="rsi_bullish_divergence",
                    hypothesis_ref="H3-001",
                    quality_score=0.0,
                    context_confirmed=True,
                    confirmation_required=True,
                    confirmed_on_bar_close=True,
                    indicator_name="rsi_divergence",
                    indicator_values={
                        "rsi14": rsi,
                        "rsi_5bars_ago": rsi_5ago,
                        "close": float(fv.close),
                        "close_5bars_ago": float(price_5ago),
                        "adx14": fv.adx14,
                    },
                    context_filter_passed=True,
                    metadata={"divergence_type": "bullish"},
                )

            # Bearish divergence: recent price higher high, RSI lower high
            if fv.close > price_5ago and fv.rsi14 < rsi_5ago and not rsi_rising:
                return IndicatorSignal(
                    group_id=self.group_id.value,
                    symbol=fv.symbol,
                    timeframe=fv.timeframe,
                    timestamp=fv.timestamp,
                    direction=Direction.SHORT,
                    signal_type="indicator",
                    signal_subtype="rsi_bearish_divergence",
                    hypothesis_ref="H3-001",
                    quality_score=0.0,
                    context_confirmed=True,
                    confirmation_required=True,
                    confirmed_on_bar_close=True,
                    indicator_name="rsi_divergence",
                    indicator_values={
                        "rsi14": rsi,
                        "rsi_5bars_ago": rsi_5ago,
                        "close": float(fv.close),
                        "close_5bars_ago": float(price_5ago),
                        "adx14": fv.adx14,
                    },
                    context_filter_passed=True,
                    metadata={"divergence_type": "bearish"},
                )

        return None

    # ------------------------------------------------------------------
    # Sub-agent 4: _detect_macd_signal
    # ------------------------------------------------------------------

    def _compute_macd_values(
        self, closes: list[Decimal]
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Recompute MACD (12/26/9) from closes. Returns (macd_line, signal_line, histogram)."""
        if len(closes) < 35:
            zero = Decimal("0")
            return zero, zero, zero
        return self._computer._macd(closes, fast=12, slow=26, signal=9)

    def _detect_macd_signal(
        self, fv: FeatureVector, closes: list[Decimal]
    ) -> Optional[IndicatorSignal]:
        """
        MACD cross detection:
        - Bullish cross: macd_line crosses above signal_line → LONG
        - Bearish cross: macd_line crosses below signal_line → SHORT
        - Histogram direction change as early warning (lower quality)
        """
        symbol = fv.symbol
        if len(closes) < 35:
            return None

        macd_line, signal_line, histogram = self._compute_macd_values(closes)
        prev_macd = self._prev_macd_line.get(symbol, macd_line)
        prev_signal = self._prev_signal_line.get(symbol, signal_line)

        # Update state for next bar
        self._prev_macd_line[symbol] = macd_line
        self._prev_signal_line[symbol] = signal_line

        bullish_cross = prev_macd <= prev_signal and macd_line > signal_line
        bearish_cross = prev_macd >= prev_signal and macd_line < signal_line

        if bullish_cross:
            direction = Direction.LONG
            subtype = "macd_bullish_cross"
        elif bearish_cross:
            direction = Direction.SHORT
            subtype = "macd_bearish_cross"
        else:
            # Check histogram momentum change (early warning, lower score)
            prev_hist = prev_macd - prev_signal
            curr_hist = macd_line - signal_line
            if prev_hist < Decimal("0") and curr_hist > prev_hist and curr_hist < Decimal("0"):
                # Histogram turning up while still negative: bullish momentum building
                direction = Direction.LONG
                subtype = "macd_histogram_turn_up"
            elif prev_hist > Decimal("0") and curr_hist < prev_hist and curr_hist > Decimal("0"):
                direction = Direction.SHORT
                subtype = "macd_histogram_turn_down"
            else:
                return None

        return IndicatorSignal(
            group_id=self.group_id.value,
            symbol=fv.symbol,
            timeframe=fv.timeframe,
            timestamp=fv.timestamp,
            direction=direction,
            signal_type="indicator",
            signal_subtype=subtype,
            hypothesis_ref=None,
            quality_score=0.0,
            context_confirmed=False,
            confirmation_required=True,
            confirmed_on_bar_close=True,
            indicator_name="macd",
            indicator_values={
                "macd_line": float(macd_line),
                "signal_line": float(signal_line),
                "histogram": float(histogram),
                "prev_macd_line": float(prev_macd),
                "prev_signal_line": float(prev_signal),
            },
            context_filter_passed=True,
            metadata={"macd_type": subtype},
        )

    # ------------------------------------------------------------------
    # Sub-agent 5: _detect_bb_signal (H3-004)
    # ------------------------------------------------------------------

    def _detect_bb_signal(self, fv: FeatureVector) -> Optional[IndicatorSignal]:
        """
        H3-004: BB squeeze → breakout detection.
        - Squeeze: bb_width_pct < BB_SQUEEZE_THRESHOLD → mark squeeze_active
        - Breakout: squeeze was active AND close > bb_upper → LONG
        - Breakout: squeeze was active AND close < bb_lower → SHORT
        - Clear squeeze_active after emitting breakout signal.
        """
        symbol = fv.symbol
        if symbol not in self._squeeze_active:
            self._squeeze_active[symbol] = False

        is_squeeze = fv.bb_width_pct < BB_SQUEEZE_THRESHOLD

        if is_squeeze:
            self._squeeze_active[symbol] = True
            # Do not emit during squeeze — wait for breakout
            return None

        # Check for breakout after squeeze
        if self._squeeze_active[symbol]:
            close = fv.close
            if close > fv.bb_upper and fv.volume_ratio > 1.2:
                self._squeeze_active[symbol] = False
                return IndicatorSignal(
                    group_id=self.group_id.value,
                    symbol=fv.symbol,
                    timeframe=fv.timeframe,
                    timestamp=fv.timestamp,
                    direction=Direction.LONG,
                    signal_type="indicator",
                    signal_subtype="bb_squeeze_breakout_long",
                    hypothesis_ref="H3-004",
                    quality_score=0.0,
                    context_confirmed=True,
                    confirmation_required=False,
                    confirmed_on_bar_close=True,
                    indicator_name="bollinger_bands",
                    indicator_values={
                        "bb_upper": float(fv.bb_upper),
                        "bb_lower": float(fv.bb_lower),
                        "bb_middle": float(fv.bb_middle),
                        "bb_width_pct": fv.bb_width_pct,
                        "close": float(fv.close),
                        "volume_ratio": fv.volume_ratio,
                    },
                    context_filter_passed=True,
                    metadata={"breakout_side": "upper"},
                )
            elif close < fv.bb_lower and fv.volume_ratio > 1.2:
                self._squeeze_active[symbol] = False
                return IndicatorSignal(
                    group_id=self.group_id.value,
                    symbol=fv.symbol,
                    timeframe=fv.timeframe,
                    timestamp=fv.timestamp,
                    direction=Direction.SHORT,
                    signal_type="indicator",
                    signal_subtype="bb_squeeze_breakout_short",
                    hypothesis_ref="H3-004",
                    quality_score=0.0,
                    context_confirmed=True,
                    confirmation_required=False,
                    confirmed_on_bar_close=True,
                    indicator_name="bollinger_bands",
                    indicator_values={
                        "bb_upper": float(fv.bb_upper),
                        "bb_lower": float(fv.bb_lower),
                        "bb_middle": float(fv.bb_middle),
                        "bb_width_pct": fv.bb_width_pct,
                        "close": float(fv.close),
                        "volume_ratio": fv.volume_ratio,
                    },
                    context_filter_passed=True,
                    metadata={"breakout_side": "lower"},
                )

        return None

    # ------------------------------------------------------------------
    # Sub-agent 6: _compute_regime
    # ------------------------------------------------------------------

    def _compute_regime(self, fv: FeatureVector) -> RegimeContext:
        """
        Classify BTC macro regime.
        - btc_macro: "bull" if close > ema200 AND close > ema50
                     "bear" if close < ema200
                     "ranging" otherwise
        - trending: adx14 > 25
        - volatility_regime: "high" if atr14_vs_sma20 > 1.4, "low" if < 0.7, else "normal"
        """
        close = fv.close

        if close > fv.ema200 and close > fv.ema50:
            btc_macro = "bull"
        elif close < fv.ema200:
            btc_macro = "bear"
        else:
            btc_macro = "ranging"

        trending = fv.adx14 > 25.0

        if fv.atr14_sma20 > Decimal("0"):
            atr_vs_sma20 = float(fv.atr14 / fv.atr14_sma20)
        else:
            atr_vs_sma20 = 1.0

        if atr_vs_sma20 > 1.4:
            volatility_regime = "high"
        elif atr_vs_sma20 < 0.7:
            volatility_regime = "low"
        else:
            volatility_regime = "normal"

        return RegimeContext(
            btc_macro=btc_macro,
            trending=trending,
            volatility_regime=volatility_regime,
            adx14=fv.adx14,
            atr14=fv.atr14,
            atr14_vs_sma20=atr_vs_sma20,
        )

    # ------------------------------------------------------------------
    # Sub-agent 7: _validate_signals
    # ------------------------------------------------------------------

    def _validate_signals(
        self, signals: list[IndicatorSignal], fv: FeatureVector
    ) -> list[IndicatorSignal]:
        """
        Remove contradictory signals.
        Rules:
        - If both LONG and SHORT signals present, keep only highest-scored
          (or drop both if same score — conflicting).
        - Drop any signal where context_filter_passed = False.
        """
        valid = [s for s in signals if s.context_filter_passed]

        long_sigs = [s for s in valid if s.direction == Direction.LONG]
        short_sigs = [s for s in valid if s.direction == Direction.SHORT]

        # If both directions exist, keep the set with more signals (stronger conviction)
        # If equal, drop both sets to avoid false entries
        if long_sigs and short_sigs:
            if len(long_sigs) > len(short_sigs):
                return long_sigs
            elif len(short_sigs) > len(long_sigs):
                return short_sigs
            else:
                # Conflict — return empty (no trade)
                logger.debug(
                    "IndicatorsGroup: %s — conflicting signals, suppressing all",
                    fv.symbol,
                )
                return []

        return valid

    # ------------------------------------------------------------------
    # Sub-agent 8: _score_signals
    # ------------------------------------------------------------------

    def _score_signals(
        self, signals: list[IndicatorSignal], fv: FeatureVector
    ) -> list[IndicatorSignal]:
        """
        Assign quality_score to each signal based on context.
        Score range: 0.0 – 1.0

        Scoring factors:
        - ADX strength bonus: adx14 > 25 → +0.2
        - Volume confirmation: volume_ratio > 1.5 → +0.15
        - EMA alignment with signal direction → +0.2
        - RSI alignment with signal direction → +0.1
        - Hypothesis with higher priority → base score boost
        """
        for sig in signals:
            score = 0.4  # base

            # ADX trend strength
            if fv.adx14 > 25:
                score += 0.2
            elif fv.adx14 >= 20:
                score += 0.1

            # Volume confirmation
            if fv.volume_ratio > 1.5:
                score += 0.15
            elif fv.volume_ratio > 1.2:
                score += 0.05

            # EMA alignment
            ema_bull = fv.ema20 > fv.ema50
            ema_bear = fv.ema20 < fv.ema50
            if sig.direction == Direction.LONG and ema_bull:
                score += 0.2
            elif sig.direction == Direction.SHORT and ema_bear:
                score += 0.2

            # RSI alignment
            rsi = fv.rsi14
            if sig.direction == Direction.LONG and rsi > 50 and rsi < 70:
                score += 0.1
            elif sig.direction == Direction.SHORT and rsi < 50 and rsi > 30:
                score += 0.1

            # Hypothesis priority boost
            # H3-005 gets the same boost as H3-002 and H3-004: it fires in
            # established-trend conditions that are meaningfully different from
            # lower-quality indicator-only signals.
            if sig.hypothesis_ref in ("H3-002", "H3-004", "H3-005", "H3-007", "H3-008"):
                score += 0.05

            # Cap at 1.0
            sig.quality_score = min(score, 1.0)

        return signals

    # ------------------------------------------------------------------
    # Sub-agent 9: _summarize_indicator_state
    # ------------------------------------------------------------------

    def _summarize_indicator_state(
        self, signals: list[IndicatorSignal], fv: FeatureVector
    ) -> str:
        """
        Produce a text summary of the current indicator state for the setup packet.
        """
        parts = []

        # EMA state
        if fv.ema20 > fv.ema50 > fv.ema200:
            parts.append("EMA fully aligned bullish (20>50>200)")
        elif fv.ema20 < fv.ema50 < fv.ema200:
            parts.append("EMA fully aligned bearish (20<50<200)")
        else:
            parts.append(
                f"EMA mixed (20={float(fv.ema20):.0f}, 50={float(fv.ema50):.0f})"
            )

        # RSI state
        rsi = fv.rsi14
        if rsi > 70:
            parts.append(f"RSI overbought ({rsi:.1f})")
        elif rsi < 30:
            parts.append(f"RSI oversold ({rsi:.1f})")
        else:
            direction_word = "rising" if rsi > fv.prev_rsi14 else "falling"
            parts.append(f"RSI {rsi:.1f} {direction_word}")

        # ADX
        parts.append(f"ADX={fv.adx14:.1f} ({'trending' if fv.adx14 > 25 else 'ranging'})")

        # BB
        if fv.bb_width_pct < BB_SQUEEZE_THRESHOLD:
            parts.append("BB squeeze active")

        # Active signals
        if signals:
            sig_names = [s.signal_subtype for s in signals]
            parts.append(f"Signals: {', '.join(sig_names)}")
        else:
            parts.append("No indicator signals this bar")

        return " | ".join(parts)

    # ------------------------------------------------------------------
    # Sub-agent 10: _build_bundle
    # ------------------------------------------------------------------

    def _build_bundle(
        self,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
        signals: list[IndicatorSignal],
        regime: RegimeContext,
    ) -> GroupSignalBundle:
        """Assemble GroupSignalBundle from all processed signals and regime."""
        return GroupSignalBundle(
            group_id=self.group_id.value,
            symbol=symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            signals=list(signals),  # type: ignore[arg-type]
            regime=regime,
            structural=None,
            metadata={
                "signal_count": len(signals),
                "directions": list({s.direction.value for s in signals}),
            },
        )
