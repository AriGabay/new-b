"""
ScenarioLoader — builds BTCSetupPackets and FeatureVector sequences for validation.

Provides deterministic, labelled scenarios covering:
  - Bull trend LONG (ideal conditions)
  - Bear trend SHORT (ideal conditions)
  - Bear macro + LONG (triggers Rail 5)
  - High volatility (triggers Rail 6 if borderline)
  - Poor R:R (triggers Rail 3)
  - Ranging / weak confluence
  - Mean reversion extreme
  - Overbought LONG (RSI 80+)
  - All-reject (every evaluator rejects)
  - Walk-forward bar sequences for replay testing

These scenarios are used in:
  - Panel behavior measurement (PanelBatchRunner)
  - Threshold sensitivity analysis
  - Risk gate validation

Source tag: these are constructed scenarios, NOT real market data.
When used in PanelBatchRunner with real panel logic = event_driven_runtime_simulation.
When used with forced approvals = synthetic_control_scenarios.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.schemas import Direction, FeatureVector, RegimeContext
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


def _make_macd(trend: str = "neutral") -> MACDValues:
    return MACDValues(
        macd_line=Decimal("0"),
        signal_line=Decimal("0"),
        histogram=Decimal("0"),
        trend=trend,
    )


def _empty_chart_pattern() -> ChartPatternSnapshot:
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


# ---------------------------------------------------------------------------
# Scenario descriptor
# ---------------------------------------------------------------------------

@dataclass
class ScenarioDescriptor:
    """Metadata attached to each BTCSetupPacket scenario."""
    scenario_id: str
    label: str
    description: str
    expected_panel_outcome: str   # "approve" | "hold" | "uncertain"
    expected_enter_blockers: list[str]  # which rails or reasons are expected to block
    direction: str   # "long" or "short"


@dataclass
class LabelledPacket:
    """BTCSetupPacket + scenario metadata."""
    packet: BTCSetupPacket
    descriptor: ScenarioDescriptor


# ---------------------------------------------------------------------------
# Core scenario builders
# ---------------------------------------------------------------------------

def make_indicator_snapshot(
    close: float = 65000,
    ema_alignment: str = "full_bull",
    adx14: float = 28.0,
    rsi14: float = 58.0,
    prev_rsi14: float = 54.0,
    rsi_direction: str = "rising",
    volume_ratio: float = 1.6,
    volume_character: str = "above_avg",
    volatility_regime: str = "normal",
    atr14_vs_sma20: float = 1.0,
    bb_position: str = "middle",
    bb_width_pct: float = 45.0,
) -> IndicatorSnapshot:
    p = Decimal(str(close))
    atr = Decimal(str(close * 0.012))   # 1.2% ATR typical for BTC
    bb_mid = p
    bb_width = p * Decimal("0.04")
    return IndicatorSnapshot(
        close=p,
        ema20=p * Decimal("0.995"),
        ema50=p * Decimal("0.985"),
        ema200=p * Decimal("0.960"),
        ema_alignment=ema_alignment,
        rsi14=rsi14,
        prev_rsi14=prev_rsi14,
        rsi_direction=rsi_direction,
        macd=_make_macd("neutral"),
        bb_upper=bb_mid + bb_width,
        bb_middle=bb_mid,
        bb_lower=bb_mid - bb_width,
        bb_width_pct=bb_width_pct,
        bb_position=bb_position,
        atr14=atr,
        atr14_vs_sma20=atr14_vs_sma20,
        volatility_regime=volatility_regime,
        adx14=adx14,
        trend_strength="strong" if adx14 >= 25 else ("moderate" if adx14 >= 20 else "weak"),
        volume_ratio=volume_ratio,
        volume_character=volume_character,
    )


def make_structural_snapshot(
    at_support: bool = True,
    at_resistance: bool = False,
    structure_quality: str = "strong",
    trend_direction: str = "uptrend",
    higher_highs: bool = True,
    higher_lows: bool = True,
    support_distance_pct: Optional[float] = 0.5,
    resistance_distance_pct: Optional[float] = None,
) -> StructuralSnapshot:
    return StructuralSnapshot(
        at_support=at_support,
        at_resistance=at_resistance,
        nearest_support=None,
        nearest_resistance=None,
        support_distance_pct=support_distance_pct,
        resistance_distance_pct=resistance_distance_pct,
        structure_quality=structure_quality,
        trend_direction=trend_direction,
        higher_highs=higher_highs,
        higher_lows=higher_lows,
    )


def make_candlestick_snapshot(
    primary_pattern: Optional[str] = None,
    pattern_direction: Optional[str] = None,
    pattern_at_structure: bool = False,
) -> CandlestickSnapshot:
    patterns = [primary_pattern] if primary_pattern else []
    return CandlestickSnapshot(
        patterns_detected=patterns,
        primary_pattern=primary_pattern,
        pattern_direction=pattern_direction,
        pattern_at_structure=pattern_at_structure,
        raw_signals=[],
    )


def make_setup_proposal(
    direction: Direction = Direction.LONG,
    entry_price: float = 65000,
    stop_distance_pct: float = 2.0,
    r_r_ratio: float = 2.5,
    setup_quality: str = "B",
    proposed_leverage: float = 1.5,
    confirming_signals: Optional[list[str]] = None,
    primary_thesis: str = "",
) -> SetupProposal:
    ep = Decimal(str(entry_price))
    stop_dist = ep * Decimal(str(stop_distance_pct / 100))
    if direction == Direction.LONG:
        stop_price = ep - stop_dist
        target_price = ep + stop_dist * Decimal(str(r_r_ratio))
    else:
        stop_price = ep + stop_dist
        target_price = ep - stop_dist * Decimal(str(r_r_ratio))
    target_dist = abs(target_price - ep)
    target_pct = float(target_dist / ep * 100)
    return SetupProposal(
        direction=direction,
        entry_price=ep,
        stop_price=stop_price,
        target_price=target_price,
        r_r_ratio=r_r_ratio,
        stop_distance_pct=stop_distance_pct,
        target_distance_pct=target_pct,
        proposed_leverage=proposed_leverage,
        proposed_risk_pct=0.01,
        setup_quality=setup_quality,
        confirming_signals=confirming_signals or ["ema_crossover"],
        conflicting_signals=[],
        primary_thesis=primary_thesis or f"{direction.value} on BTCUSDT",
    )


def _make_regime(
    btc_macro: str = "bull",
    volatility_regime: str = "normal",
    adx14: float = 28.0,
    trending: bool = True,
) -> RegimeContext:
    return RegimeContext(
        btc_macro=btc_macro,
        trending=trending,
        volatility_regime=volatility_regime,
        adx14=adx14,
        atr14=Decimal("780"),
        atr14_vs_sma20=1.0,
    )


def _make_packet(
    indicators: IndicatorSnapshot,
    structure: StructuralSnapshot,
    candlestick: CandlestickSnapshot,
    proposal: SetupProposal,
    regime: RegimeContext,
    chart_pattern: Optional[ChartPatternSnapshot] = None,
) -> BTCSetupPacket:
    return BTCSetupPacket(
        packet_id=str(uuid.uuid4()),
        symbol="BTCUSDT",
        timeframe="1h",
        bar_timestamp=_utcnow(),
        assembled_at=_utcnow(),
        indicators=indicators,
        structure=structure,
        candlestick=candlestick,
        chart_pattern=chart_pattern or _empty_chart_pattern(),
        regime=regime,
        proposal=proposal,
        groups_contributed=["indicators", "candlestick", "technical_structure"],
        packet_valid=True,
    )


# ---------------------------------------------------------------------------
# Named scenarios (10 standard scenarios for panel validation)
# ---------------------------------------------------------------------------

def scenario_ideal_bull_long() -> LabelledPacket:
    """
    Best-case LONG setup in a bull market.
    Expectation: borderline panel approval (~14-17/20 depending on avg_score).
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="full_bull", adx14=28.0,
            rsi14=58.0, prev_rsi14=54.0, rsi_direction="rising",
            volume_ratio=1.65, volume_character="above_avg",
            volatility_regime="normal", atr14_vs_sma20=1.0,
            bb_position="middle", bb_width_pct=45.0,
        ),
        structure=make_structural_snapshot(
            at_support=True, structure_quality="strong",
            trend_direction="uptrend", higher_highs=True, higher_lows=True,
            support_distance_pct=0.5,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern="bullish_engulfing",
            pattern_direction="bullish",
            pattern_at_structure=True,
        ),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=2.0, r_r_ratio=2.5,
            setup_quality="B", proposed_leverage=1.5,
            confirming_signals=["ema_crossover", "rsi_momentum", "candlestick"],
            primary_thesis="LONG on BTCUSDT: strong bull trend, EMA aligned, at support",
        ),
        regime=_make_regime(btc_macro="bull", volatility_regime="normal", adx14=28.0),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s01_ideal_bull_long",
            label="Ideal Bull LONG",
            description="Full bull EMA alignment, RSI 58 rising, at strong support, bull macro, R:R=2.5",
            expected_panel_outcome="uncertain",
            expected_enter_blockers=[],
            direction="long",
        ),
    )


def scenario_ideal_bear_short() -> LabelledPacket:
    """
    Best-case SHORT setup in a bear market.
    Expectation: borderline panel approval for SHORT.
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="full_bear", adx14=27.0,
            rsi14=42.0, prev_rsi14=46.0, rsi_direction="falling",
            volume_ratio=1.55, volume_character="above_avg",
            volatility_regime="normal", atr14_vs_sma20=1.0,
            bb_position="middle", bb_width_pct=42.0,
        ),
        structure=make_structural_snapshot(
            at_support=False, at_resistance=True, structure_quality="strong",
            trend_direction="downtrend", higher_highs=False, higher_lows=False,
            resistance_distance_pct=0.5,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern="bearish_engulfing",
            pattern_direction="bearish",
            pattern_at_structure=True,
        ),
        proposal=make_setup_proposal(
            direction=Direction.SHORT, entry_price=65000,
            stop_distance_pct=2.0, r_r_ratio=2.5,
            setup_quality="B", proposed_leverage=1.5,
            confirming_signals=["ema_crossover", "rsi_momentum"],
            primary_thesis="SHORT on BTCUSDT: full bear EMA, RSI falling, at resistance",
        ),
        regime=_make_regime(btc_macro="bear", volatility_regime="normal", adx14=27.0),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s02_ideal_bear_short",
            label="Ideal Bear SHORT",
            description="Full bear EMA alignment, RSI 42 falling, at strong resistance, bear macro, R:R=2.5",
            expected_panel_outcome="uncertain",
            expected_enter_blockers=[],
            direction="short",
        ),
    )


def scenario_bear_macro_long() -> LabelledPacket:
    """
    LONG in bear macro environment.
    Rail 5 (bear + long) fires regardless of panel votes.
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="full_bull", adx14=22.0,
            rsi14=55.0, prev_rsi14=51.0, rsi_direction="rising",
            volume_ratio=1.3, volume_character="above_avg",
            volatility_regime="normal", atr14_vs_sma20=1.0,
            bb_position="middle", bb_width_pct=38.0,
        ),
        structure=make_structural_snapshot(
            at_support=True, structure_quality="moderate",
            trend_direction="uptrend", higher_highs=True, higher_lows=True,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern="hammer", pattern_direction="bullish",
            pattern_at_structure=True,
        ),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=2.0, r_r_ratio=2.2,
            setup_quality="C", proposed_leverage=1.5,
        ),
        regime=_make_regime(btc_macro="bear", volatility_regime="normal", adx14=22.0),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s03_bear_macro_long",
            label="Bear Macro LONG (Rail 5)",
            description="LONG in bear macro — Rail 5 (bear+long blocked) fires unconditionally",
            expected_panel_outcome="hold",
            expected_enter_blockers=["Rail 5: long in bear regime"],
            direction="long",
        ),
    )


def scenario_poor_rr() -> LabelledPacket:
    """
    Otherwise reasonable setup with R:R = 1.2 (below 1.5 minimum).
    Rail 3 fires. RiskParityEvaluator also rejects.
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="full_bull", adx14=26.0,
            rsi14=56.0, prev_rsi14=52.0, rsi_direction="rising",
            volume_ratio=1.4, volume_character="above_avg",
            volatility_regime="normal",
        ),
        structure=make_structural_snapshot(
            at_support=True, structure_quality="strong",
            trend_direction="uptrend", higher_highs=True, higher_lows=True,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern="bullish_engulfing", pattern_direction="bullish",
            pattern_at_structure=True,
        ),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=2.0, r_r_ratio=1.2,  # ← Too low
            setup_quality="B", proposed_leverage=1.5,
        ),
        regime=_make_regime(btc_macro="bull"),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s04_poor_rr",
            label="Poor R:R LONG (Rail 3)",
            description="Good setup but R:R=1.2 < 1.5 minimum. Rail 3 fires unconditionally.",
            expected_panel_outcome="hold",
            expected_enter_blockers=["Rail 3: R:R 1.20 < 1.5"],
            direction="long",
        ),
    )


def scenario_high_volatility_moderate_consensus() -> LabelledPacket:
    """
    High volatility with only ~14/20 approvals.
    Rail 6 requires 16+ approvals in high vol → fires.
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="full_bull", adx14=30.0,
            rsi14=60.0, prev_rsi14=55.0, rsi_direction="rising",
            volume_ratio=2.1, volume_character="surge",
            volatility_regime="high", atr14_vs_sma20=1.8,
            bb_position="near_upper", bb_width_pct=75.0,
        ),
        structure=make_structural_snapshot(
            at_support=True, structure_quality="strong",
            trend_direction="uptrend", higher_highs=True, higher_lows=True,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern="hammer", pattern_direction="bullish",
            pattern_at_structure=True,
        ),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=3.0, r_r_ratio=2.0,  # wider stop for high vol
            setup_quality="B", proposed_leverage=1.2,
        ),
        regime=_make_regime(btc_macro="bull", volatility_regime="high", adx14=30.0),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s05_high_vol_moderate_consensus",
            label="High Vol + Moderate Consensus (Rail 6)",
            description="High volatility: needs 16/20 approve. At ~14 → Rail 6 fires.",
            expected_panel_outcome="hold",
            expected_enter_blockers=["Rail 6: high vol requires 16/20"],
            direction="long",
        ),
    )


def scenario_ranging_weak_confluence() -> LabelledPacket:
    """
    Ranging market, no clear trend, low confluence score.
    Panel unlikely to approve (consensus < 14/20 expected).
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="mixed", adx14=14.0,
            rsi14=51.0, prev_rsi14=50.0, rsi_direction="flat",
            volume_ratio=0.9, volume_character="normal",
            volatility_regime="low", atr14_vs_sma20=0.75,
            bb_position="middle", bb_width_pct=18.0,  # BB squeeze
        ),
        structure=make_structural_snapshot(
            at_support=False, structure_quality="none",
            trend_direction="sideways", higher_highs=False, higher_lows=False,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern=None,
        ),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=1.5, r_r_ratio=2.0,
            setup_quality="C", proposed_leverage=1.3,
        ),
        regime=_make_regime(btc_macro="ranging", volatility_regime="low", adx14=14.0, trending=False),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s06_ranging_weak_confluence",
            label="Ranging / Weak Confluence",
            description="ADX 14, mixed EMA, no structure, no candle — low confluence, panel should hold",
            expected_panel_outcome="hold",
            expected_enter_blockers=["insufficient_consensus"],
            direction="long",
        ),
    )


def scenario_mean_reversion_extreme_long() -> LabelledPacket:
    """
    Mean reversion setup: RSI < 30, at support, BB below lower.
    MeanReversionEvaluator scores high. TrendFollowingEvaluator may reject.
    Mixed panel expected.
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="partial_bear", adx14=18.0,
            rsi14=28.0, prev_rsi14=32.0, rsi_direction="falling",
            volume_ratio=1.9, volume_character="above_avg",
            volatility_regime="normal", atr14_vs_sma20=1.1,
            bb_position="below_lower", bb_width_pct=62.0,
        ),
        structure=make_structural_snapshot(
            at_support=True, structure_quality="strong",
            trend_direction="downtrend", higher_highs=False, higher_lows=False,
            support_distance_pct=0.2,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern="hammer", pattern_direction="bullish",
            pattern_at_structure=True,
        ),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=1.5, r_r_ratio=3.0,
            setup_quality="B", proposed_leverage=1.3,
        ),
        regime=_make_regime(btc_macro="ranging", volatility_regime="normal", adx14=18.0),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s07_mean_reversion_extreme_long",
            label="Mean Reversion Extreme LONG",
            description="RSI 28 + at support + BB below lower. MeanReversion likes it, TrendFollowing rejects.",
            expected_panel_outcome="hold",
            expected_enter_blockers=["insufficient_consensus"],
            direction="long",
        ),
    )


def scenario_overbought_long() -> LabelledPacket:
    """
    Strong trend but RSI 82 — very overbought.
    Momentum rejects. Multiple evaluators penalize. Expected: hold.
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="full_bull", adx14=40.0,
            rsi14=82.0, prev_rsi14=78.0, rsi_direction="rising",
            volume_ratio=2.5, volume_character="surge",
            volatility_regime="high", atr14_vs_sma20=1.7,
            bb_position="above_upper", bb_width_pct=80.0,
        ),
        structure=make_structural_snapshot(
            at_support=False, structure_quality="moderate",
            trend_direction="uptrend", higher_highs=True, higher_lows=True,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern=None,
        ),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=3.5, r_r_ratio=1.8,
            setup_quality="C", proposed_leverage=1.8,
        ),
        regime=_make_regime(btc_macro="bull", volatility_regime="high", adx14=40.0),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s08_overbought_long",
            label="Overbought LONG (RSI 82)",
            description="Strong trend but RSI 82, above BB upper, high vol — MomentumEval rejects, high vol Rail 6",
            expected_panel_outcome="hold",
            expected_enter_blockers=["Rail 6: high_vol", "avg_score_too_low"],
            direction="long",
        ),
    )


def scenario_excellent_rr_good_setup() -> LabelledPacket:
    """
    High R:R (3.2) + strong setup — ContraryEvaluator threshold met (>3.0).
    Best plausible setup for maximizing approvals.
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="full_bull", adx14=32.0,
            rsi14=56.0, prev_rsi14=50.0, rsi_direction="rising",
            volume_ratio=1.8, volume_character="above_avg",
            volatility_regime="normal", atr14_vs_sma20=1.0,
            bb_position="near_lower", bb_width_pct=40.0,
        ),
        structure=make_structural_snapshot(
            at_support=True, structure_quality="strong",
            trend_direction="uptrend", higher_highs=True, higher_lows=True,
            support_distance_pct=0.3,
        ),
        candlestick=make_candlestick_snapshot(
            primary_pattern="morning_star",
            pattern_direction="bullish",
            pattern_at_structure=True,
        ),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=1.8, r_r_ratio=3.2,
            setup_quality="A", proposed_leverage=1.2,
            confirming_signals=["ema_crossover", "rsi_momentum", "candlestick", "support"],
            primary_thesis="LONG BTCUSDT: all systems aligned, high R:R pullback to support",
        ),
        regime=_make_regime(btc_macro="bull", volatility_regime="normal", adx14=32.0),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s09_excellent_rr_setup",
            label="Excellent R:R Setup (3.2)",
            description="R:R=3.2 triggers ContraryEvaluator + A-grade quality. Best plausible panel score.",
            expected_panel_outcome="uncertain",
            expected_enter_blockers=[],
            direction="long",
        ),
    )


def scenario_invalid_setup_quality() -> LabelledPacket:
    """
    composite_score would be < 0.50 → setup_quality = "invalid".
    Rail 4 fires. Also avg_score low.
    """
    packet = _make_packet(
        indicators=make_indicator_snapshot(
            close=65000, ema_alignment="mixed", adx14=12.0,
            rsi14=48.0, prev_rsi14=49.0, rsi_direction="flat",
            volume_ratio=0.7, volume_character="below_avg",
            volatility_regime="low", atr14_vs_sma20=0.6,
            bb_position="middle", bb_width_pct=12.0,
        ),
        structure=make_structural_snapshot(
            at_support=False, structure_quality="none",
            trend_direction="sideways", higher_highs=False, higher_lows=False,
        ),
        candlestick=make_candlestick_snapshot(primary_pattern=None),
        proposal=make_setup_proposal(
            direction=Direction.LONG, entry_price=65000,
            stop_distance_pct=1.5, r_r_ratio=2.0,
            setup_quality="invalid",  # ← triggers Rail 4
            proposed_leverage=1.5,
        ),
        regime=_make_regime(btc_macro="ranging", volatility_regime="low", adx14=12.0),
    )
    return LabelledPacket(
        packet=packet,
        descriptor=ScenarioDescriptor(
            scenario_id="s10_invalid_setup_quality",
            label="Invalid Setup Quality (Rail 4)",
            description="setup_quality='invalid' — Rail 4 fires unconditionally",
            expected_panel_outcome="hold",
            expected_enter_blockers=["Rail 4: setup_quality=invalid"],
            direction="long",
        ),
    )


# ---------------------------------------------------------------------------
# Batch collection
# ---------------------------------------------------------------------------

def get_all_standard_scenarios() -> list[LabelledPacket]:
    """Return all 10 standard validation scenarios."""
    return [
        scenario_ideal_bull_long(),
        scenario_ideal_bear_short(),
        scenario_bear_macro_long(),
        scenario_poor_rr(),
        scenario_high_volatility_moderate_consensus(),
        scenario_ranging_weak_confluence(),
        scenario_mean_reversion_extreme_long(),
        scenario_overbought_long(),
        scenario_excellent_rr_good_setup(),
        scenario_invalid_setup_quality(),
    ]


# ---------------------------------------------------------------------------
# FeatureVector sequences for replay harness
# ---------------------------------------------------------------------------

def _make_fv(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    price: float = 65000,
    price_change: float = 0.0,  # bar-over-bar % change
    bullish: bool = True,
    rsi: float = 55.0,
    adx: float = 22.0,
    volume_ratio: float = 1.2,
) -> FeatureVector:
    from datetime import datetime, timezone
    p = Decimal(str(price))
    atr = p * Decimal("0.012")
    ema20 = p * (Decimal("0.995") if bullish else Decimal("1.005"))
    ema50 = p * (Decimal("0.980") if bullish else Decimal("1.020"))
    ema200 = p * (Decimal("0.950") if bullish else Decimal("1.050"))
    bb_range = p * Decimal("0.04")
    return FeatureVector(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=_utcnow(),
        open=p - p * Decimal("0.003"),
        high=p + atr * Decimal("0.5"),
        low=p - atr * Decimal("0.5"),
        close=p,
        volume=Decimal("1500"),
        true_range=atr,
        atr14=atr,
        atr14_sma20=atr * Decimal("0.95"),
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        prev_ema20=ema20 - Decimal("50"),
        prev_ema50=ema50 - Decimal("100"),
        rsi14=rsi,
        prev_rsi14=rsi - (2.0 if bullish else -2.0),
        bb_upper=p + bb_range,
        bb_middle=p,
        bb_lower=p - bb_range,
        bb_width=bb_range * 2,
        bb_width_pct=40.0,
        adx14=adx,
        volume_sma20=Decimal("1200"),
        volume_ratio=volume_ratio,
        candle_body=atr * Decimal("0.4"),
        candle_range=atr,
        body_ratio=0.4,
        upper_shadow=atr * Decimal("0.3"),
        lower_shadow=atr * Decimal("0.3"),
        impulse_flag=False,
        doji_flag=False,
    )


def make_bull_bar_sequence(n: int = 40, start_price: float = 65000) -> list[FeatureVector]:
    """
    Steady bull trend: price rising, EMA aligned, RSI 55-65, ADX 25-32.
    After ~20 bars, EntryGroup may fire CandidateTradeEvent (regime-dependent).
    """
    bars = []
    price = start_price
    rsi = 52.0
    adx = 20.0
    for i in range(n):
        price *= 1.003  # ~0.3% per bar
        rsi = min(72.0, rsi + 0.4)
        adx = min(35.0, adx + 0.4)
        bars.append(_make_fv(
            price=price, bullish=True,
            rsi=rsi, adx=adx, volume_ratio=1.3 + (i % 5) * 0.1,
        ))
    return bars


def make_bear_bar_sequence(n: int = 40, start_price: float = 65000) -> list[FeatureVector]:
    """
    Steady bear trend: price falling, EMA inverted, RSI 35-45, ADX 25-32.
    """
    bars = []
    price = start_price
    rsi = 52.0
    adx = 20.0
    for i in range(n):
        price *= 0.997  # ~-0.3% per bar
        rsi = max(28.0, rsi - 0.4)
        adx = min(35.0, adx + 0.3)
        bars.append(_make_fv(
            price=price, bullish=False,
            rsi=rsi, adx=adx, volume_ratio=1.2 + (i % 5) * 0.1,
        ))
    return bars


def make_ranging_bar_sequence(n: int = 40, start_price: float = 65000) -> list[FeatureVector]:
    """
    Ranging market: price oscillating, ADX < 20, RSI near 50.
    Entry signals unlikely to fire.
    """
    import math
    bars = []
    for i in range(n):
        price = start_price * (1 + 0.01 * math.sin(i * 0.3))
        rsi = 50.0 + 5.0 * math.sin(i * 0.4)
        adx = 12.0 + 3.0 * math.sin(i * 0.2)
        bars.append(_make_fv(
            price=price, bullish=i % 2 == 0,
            rsi=rsi, adx=adx, volume_ratio=0.85 + 0.1 * (i % 4),
        ))
    return bars


def make_mixed_regime_sequence(n: int = 60, start_price: float = 65000) -> list[FeatureVector]:
    """
    Bull first half, then ranging, then bear.
    Tests regime transition handling.
    """
    bull = make_bull_bar_sequence(n // 3, start_price)
    ranging_start = float(bull[-1].close) if bull else start_price
    ranging = make_ranging_bar_sequence(n // 3, ranging_start)
    bear_start = float(ranging[-1].close) if ranging else ranging_start
    bear = make_bear_bar_sequence(n - 2 * (n // 3), bear_start)
    return bull + ranging + bear
