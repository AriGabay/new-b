"""
SetupPacketBuilder: constructs a BTCSetupPacket from runtime state.

Called by PanelDecisionGroup when a CandidateTradeProposal arrives.
Maps FeatureVector + CandidateTradeProposal + SystemState → BTCSetupPacket.

Fields that cannot be fully computed from FeatureVector are filled with
safe defaults and documented. MACD is not in FeatureVector — zeros used.
ChartPatternSnapshot is built from ChartPatternGroup._signals_cache and
_active_cache (injected via runner._wire_caches); empty snapshot only when
no chart pattern signals or active patterns are present for the symbol.

Source: /docs/runtime_runner_design.md
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.schemas import (
    CandidateTradeProposal,
    Direction,
    FeatureVector,
    StructuralLevelBundle,
)
from core.setup_packet import (
    BTCSetupPacket,
    CandlestickSnapshot,
    ChartPatternSnapshot,
    IndicatorSnapshot,
    MACDValues,
    SetupProposal,
    StructuralSnapshot,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ema_alignment(close: Decimal, ema20: Decimal, ema50: Decimal, ema200: Decimal) -> str:
    """Classify EMA alignment from price position."""
    above200 = close > ema200
    above50 = close > ema50
    above20 = close > ema20
    if above200 and above50 and above20:
        return "full_bull"
    if not above200 and not above50 and not above20:
        return "full_bear"
    if above200 and above50:
        return "partial_bull"
    if not above200 and not above50:
        return "partial_bear"
    return "mixed"


def _bb_position(close: Decimal, bb_upper: Decimal, bb_middle: Decimal, bb_lower: Decimal) -> str:
    if close > bb_upper:
        return "above_upper"
    if close >= bb_middle + (bb_upper - bb_middle) * Decimal("0.7"):
        return "near_upper"
    if close <= bb_lower:
        return "below_lower"
    if close <= bb_lower + (bb_middle - bb_lower) * Decimal("0.3"):
        return "near_lower"
    return "middle"


def _volatility_regime(atr14: Decimal, atr14_sma20: Decimal) -> str:
    if atr14_sma20 <= 0:
        return "normal"
    ratio = float(atr14 / atr14_sma20)
    if ratio > 1.5:
        return "high"
    if ratio < 0.7:
        return "low"
    return "normal"


def _trend_strength(adx14: float) -> str:
    if adx14 >= 25:
        return "strong"
    if adx14 >= 20:
        return "moderate"
    return "weak"


def _volume_character(volume_ratio: float) -> str:
    if volume_ratio >= 2.0:
        return "surge"
    if volume_ratio >= 1.2:
        return "above_avg"
    if volume_ratio >= 0.8:
        return "normal"
    return "below_avg"


def _rsi_direction(rsi14: float, prev_rsi14: float) -> str:
    diff = rsi14 - prev_rsi14
    if diff > 1.0:
        return "rising"
    if diff < -1.0:
        return "falling"
    return "flat"


def _setup_quality(composite_score: float) -> str:
    if composite_score >= 0.75:
        return "A"
    if composite_score >= 0.60:
        return "B"
    if composite_score >= 0.50:
        return "C"
    return "invalid"


def build_indicator_snapshot(fv: FeatureVector) -> IndicatorSnapshot:
    """Map FeatureVector → IndicatorSnapshot. MACD defaults to zeros (not in FeatureVector)."""
    atr14_sma20 = fv.atr14_sma20 if hasattr(fv, "atr14_sma20") and fv.atr14_sma20 > 0 else fv.atr14
    return IndicatorSnapshot(
        close=fv.close,
        ema20=fv.ema20,
        ema50=fv.ema50,
        ema200=fv.ema200,
        ema_alignment=_ema_alignment(fv.close, fv.ema20, fv.ema50, fv.ema200),
        rsi14=fv.rsi14,
        prev_rsi14=fv.prev_rsi14,
        rsi_direction=_rsi_direction(fv.rsi14, fv.prev_rsi14),
        macd=MACDValues(
            macd_line=Decimal("0"),
            signal_line=Decimal("0"),
            histogram=Decimal("0"),
            trend="neutral",
        ),
        bb_upper=fv.bb_upper,
        bb_middle=fv.bb_middle,
        bb_lower=fv.bb_lower,
        bb_width_pct=fv.bb_width_pct,
        bb_position=_bb_position(fv.close, fv.bb_upper, fv.bb_middle, fv.bb_lower),
        atr14=fv.atr14,
        atr14_vs_sma20=float(fv.atr14 / atr14_sma20) if atr14_sma20 > 0 else 1.0,
        volatility_regime=_volatility_regime(fv.atr14, atr14_sma20),
        adx14=fv.adx14,
        trend_strength=_trend_strength(fv.adx14),
        volume_ratio=fv.volume_ratio,
        volume_character=_volume_character(fv.volume_ratio),
    )


def build_structural_snapshot(
    structural_bundle: Optional[StructuralLevelBundle],
) -> StructuralSnapshot:
    """Map TechnicalStructureGroup output → StructuralSnapshot. Defaults if None."""
    if structural_bundle is None:
        return StructuralSnapshot(
            at_resistance=False,
            at_support=False,
            nearest_resistance=None,
            nearest_support=None,
            resistance_distance_pct=None,
            support_distance_pct=None,
            structure_quality="none",
            trend_direction="sideways",
            higher_highs=False,
            higher_lows=False,
        )
    return StructuralSnapshot(
        at_resistance=getattr(structural_bundle, "at_resistance", False),
        at_support=getattr(structural_bundle, "at_support", False),
        nearest_resistance=getattr(structural_bundle, "nearest_resistance", None),
        nearest_support=getattr(structural_bundle, "nearest_support", None),
        resistance_distance_pct=getattr(structural_bundle, "resistance_distance_pct", None),
        support_distance_pct=getattr(structural_bundle, "support_distance_pct", None),
        structure_quality=getattr(structural_bundle, "structure_quality", "none"),
        trend_direction=getattr(structural_bundle, "trend_direction", "sideways"),
        higher_highs=getattr(structural_bundle, "higher_highs", False),
        higher_lows=getattr(structural_bundle, "higher_lows", False),
    )


def build_candlestick_snapshot(
    signals: list,
    structural_bundle: Optional[StructuralLevelBundle] = None,
) -> CandlestickSnapshot:
    """Build CandlestickSnapshot from raw CandlestickSignal list."""
    from core.schemas import CandlestickSignal
    cs_signals = [s for s in signals if isinstance(s, CandlestickSignal)]
    patterns = [getattr(s, "signal_subtype", "") for s in cs_signals if getattr(s, "signal_subtype", "")]
    primary = cs_signals[0].signal_subtype if cs_signals else None
    direction = None
    if cs_signals:
        d = getattr(cs_signals[0], "direction", None)
        if d is not None:
            direction = "bullish" if str(d).upper() in ("LONG", "DIRECTION.LONG") else "bearish"
    at_structure = bool(
        structural_bundle is not None and (
            getattr(structural_bundle, "at_resistance", False) or
            getattr(structural_bundle, "at_support", False)
        )
    )
    return CandlestickSnapshot(
        patterns_detected=patterns,
        primary_pattern=primary,
        pattern_direction=direction,
        pattern_at_structure=at_structure,
        raw_signals=cs_signals,
    )


def build_empty_chart_pattern_snapshot() -> ChartPatternSnapshot:
    """ChartPatternGroup is stubbed — always returns empty snapshot."""
    return ChartPatternSnapshot(
        active_patterns=[],
        confirmed_patterns=[],
        primary_confirmed=None,
        pattern_direction=None,
        measured_move=None,
        conservative_target=None,
        breakout_level=None,
        raw_signals=[],
    )


def build_chart_pattern_snapshot(
    confirmed_signals: list,
    active_pattern_names: list,
) -> ChartPatternSnapshot:
    """Build ChartPatternSnapshot from ChartPatternGroup caches."""
    from core.schemas import ChartPatternSignal as _CPS
    cp_signals = [s for s in confirmed_signals if isinstance(s, _CPS)]

    confirmed_names = [getattr(s, "signal_subtype", "") for s in cp_signals]
    primary = confirmed_names[0] if confirmed_names else None

    primary_signal = cp_signals[0] if cp_signals else None
    measured_move = getattr(primary_signal, "measured_move", None)
    conservative_target = getattr(primary_signal, "conservative_target", None)
    breakout_level = getattr(primary_signal, "breakout_level", None)
    direction = None
    if primary_signal:
        d = getattr(primary_signal, "direction", None)
        if d is not None:
            direction = (
                "bullish"
                if str(d).upper() in ("LONG", "DIRECTION.LONG")
                else "bearish"
            )

    return ChartPatternSnapshot(
        active_patterns=list(active_pattern_names),
        confirmed_patterns=confirmed_names,
        primary_confirmed=primary,
        pattern_direction=direction,
        measured_move=measured_move,
        conservative_target=conservative_target,
        breakout_level=breakout_level,
        raw_signals=cp_signals,
    )


def build_setup_proposal(
    proposal: CandidateTradeProposal,
    fv: FeatureVector,
) -> SetupProposal:
    """Derive SetupProposal from CandidateTradeProposal + FeatureVector."""
    entry_price = proposal.entry_price
    # stop_price from proposal if available, else use 2×ATR14 from entry
    stop_price = getattr(proposal, "stop_price", None)
    if stop_price is None or stop_price == 0:
        if proposal.direction == Direction.LONG:
            stop_price = entry_price - 2 * fv.atr14
        else:
            stop_price = entry_price + 2 * fv.atr14

    stop_dist = abs(entry_price - stop_price)
    target_price = getattr(proposal, "raw_target", None)
    if target_price is None or target_price == 0:
        if proposal.direction == Direction.LONG:
            target_price = entry_price + 2 * stop_dist
        else:
            target_price = entry_price - 2 * stop_dist

    target_dist = abs(target_price - entry_price)
    r_r = float(target_dist / stop_dist) if stop_dist > 0 else 0.0
    stop_dist_pct = float(stop_dist / entry_price) * 100 if entry_price > 0 else 0.0
    target_dist_pct = float(target_dist / entry_price) * 100 if entry_price > 0 else 0.0

    return SetupProposal(
        direction=proposal.direction,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        r_r_ratio=r_r,
        stop_distance_pct=stop_dist_pct,
        target_distance_pct=target_dist_pct,
        proposed_leverage=min(float(entry_price / stop_dist), 3.0)
            if stop_dist > 0 else 1.0,
        proposed_risk_pct=0.01,
        setup_quality=_setup_quality(proposal.composite_score),
        confirming_signals=getattr(proposal, "setup_refs", []) or [],
        conflicting_signals=[],
        primary_thesis=getattr(proposal, "thesis", f"{proposal.direction} on {proposal.symbol}"),
        composite_score=proposal.composite_score,
    )


def build_btc_setup_packet(
    proposal: CandidateTradeProposal,
    fv: FeatureVector,
    structural_bundle: Optional[StructuralLevelBundle] = None,
    candlestick_signals: Optional[list] = None,
    chart_pattern_signals: Optional[list] = None,
    active_chart_patterns: Optional[list] = None,
) -> BTCSetupPacket:
    """
    Build a BTCSetupPacket from runtime state.
    Called by PanelDecisionGroup after CandidateTradeEvent arrives.

    Notes:
    - MACD values default to zero (not in FeatureVector; to be added Phase 5)
    - ChartPatternSnapshot is always empty (group stubbed)
    - StructuralSnapshot uses defaults if TechnicalStructureGroup not wired
    # ChartPatternSnapshot built from cache when chart_pattern_signals or active_chart_patterns present
    """
    from core.schemas import RegimeContext
    regime = RegimeContext(
        btc_macro=getattr(proposal, "regime_context", None) and
                  getattr(proposal.regime_context, "btc_macro", "ranging") or "ranging",
        trending=fv.adx14 >= 20,
        volatility_regime=_volatility_regime(
            fv.atr14,
            fv.atr14_sma20 if hasattr(fv, "atr14_sma20") else fv.atr14,
        ),
        adx14=fv.adx14,
        atr14=fv.atr14,
        atr14_vs_sma20=float(fv.atr14 / fv.atr14_sma20)
            if hasattr(fv, "atr14_sma20") and fv.atr14_sma20 > 0 else 1.0,
    )
    # Prefer regime from proposal if available
    if hasattr(proposal, "regime_context") and proposal.regime_context is not None:
        regime = proposal.regime_context

    return BTCSetupPacket(
        packet_id=str(uuid.uuid4()),
        symbol=proposal.symbol,
        timeframe=getattr(proposal, "timeframe", "1h"),
        bar_timestamp=fv.timestamp,
        assembled_at=_utcnow(),
        indicators=build_indicator_snapshot(fv),
        structure=build_structural_snapshot(structural_bundle),
        candlestick=build_candlestick_snapshot(candlestick_signals or [], structural_bundle),
        chart_pattern=build_chart_pattern_snapshot(
            chart_pattern_signals or [],
            active_chart_patterns or [],
        ) if (chart_pattern_signals or active_chart_patterns) else build_empty_chart_pattern_snapshot(),
        regime=regime,
        proposal=build_setup_proposal(proposal, fv),
        groups_contributed=(
            ["indicators", "candlestick", "technical_structure", "chart_pattern"]
            if (chart_pattern_signals or active_chart_patterns)
            else ["indicators", "candlestick", "technical_structure"]
        ),
        packet_valid=True,
    )
