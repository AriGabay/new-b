"""
BTCSetupPacket: structured output of all 10 specialist groups.

This packet is assembled by the Entry group after all specialist groups
have processed a bar. The 20 trader evaluators receive this packet.

BTC/Bybit focused. Single-symbol architecture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any

from core.schemas import (
    Direction, RegimeContext, StructuralLevelBundle,
    CandidateSignal, IndicatorSignal, CandlestickSignal, ChartPatternSignal,
)


@dataclass
class MACDValues:
    macd_line: Decimal
    signal_line: Decimal
    histogram: Decimal
    trend: str  # "bullish_cross", "bearish_cross", "bullish_above", "bearish_below", "neutral"


@dataclass
class IndicatorSnapshot:
    """Current values of all computed indicators for BTC."""
    # Price
    close: Decimal
    # EMA alignment
    ema20: Decimal
    ema50: Decimal
    ema200: Decimal
    ema_alignment: str  # "full_bull" | "full_bear" | "partial_bull" | "partial_bear" | "mixed"
    # RSI
    rsi14: float
    prev_rsi14: float
    rsi_direction: str  # "rising" | "falling" | "flat"
    # MACD
    macd: MACDValues
    # Bollinger Bands
    bb_upper: Decimal
    bb_middle: Decimal
    bb_lower: Decimal
    bb_width_pct: float  # percentile rank; low = squeeze
    bb_position: str  # "above_upper" | "near_upper" | "middle" | "near_lower" | "below_lower"
    # ATR
    atr14: Decimal
    atr14_vs_sma20: float  # current ATR / SMA of ATR
    volatility_regime: str  # "low" | "normal" | "high"
    # ADX
    adx14: float
    trend_strength: str  # "strong" (>25) | "moderate" (20-25) | "weak" (<20)
    # Volume
    volume_ratio: float  # current / sma20
    volume_character: str  # "surge" (>2x) | "above_avg" | "normal" | "below_avg"


@dataclass
class StructuralSnapshot:
    """S/R levels and structural context."""
    at_resistance: bool
    at_support: bool
    nearest_resistance: Optional[Decimal]
    nearest_support: Optional[Decimal]
    resistance_distance_pct: Optional[float]  # % above current price
    support_distance_pct: Optional[float]     # % below current price
    structure_quality: str  # "strong" | "moderate" | "weak" | "none"
    trend_direction: str    # "uptrend" | "downtrend" | "sideways"
    higher_highs: bool
    higher_lows: bool


@dataclass
class CandlestickSnapshot:
    """Detected candlestick patterns on this bar."""
    patterns_detected: list[str]       # e.g. ["bullish_engulfing", "doji"]
    primary_pattern: Optional[str]     # strongest pattern
    pattern_direction: Optional[str]   # "bullish" | "bearish" | "neutral"
    pattern_at_structure: bool         # pattern at a S/R level
    raw_signals: list[CandlestickSignal] = field(default_factory=list)


@dataclass
class ChartPatternSnapshot:
    """Active chart pattern state machines."""
    active_patterns: list[str]         # pattern names in non-terminal states
    confirmed_patterns: list[str]      # patterns that reached CONFIRMED this bar
    primary_confirmed: Optional[str]
    pattern_direction: Optional[str]   # direction of primary confirmed pattern
    measured_move: Optional[Decimal]
    conservative_target: Optional[Decimal]
    breakout_level: Optional[Decimal]
    raw_signals: list[ChartPatternSignal] = field(default_factory=list)


@dataclass
class SetupProposal:
    """The proposed trade from the Entry group."""
    direction: Direction
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    r_r_ratio: float           # (target - entry) / (entry - stop)
    stop_distance_pct: float   # abs(entry - stop) / entry
    target_distance_pct: float
    proposed_leverage: float
    proposed_risk_pct: float   # fraction of equity at risk (e.g. 0.01 = 1%)
    setup_quality: str         # "A" | "B" | "C" | "invalid"
    confirming_signals: list[str]
    conflicting_signals: list[str]
    primary_thesis: str        # one-sentence thesis
    composite_score: float = 0.0  # from CandidateTradeProposal; drives R4 DEFER in MDP


@dataclass
class BTCSetupPacket:
    """
    Complete setup packet for BTC evaluation by 20 trader agents.

    Assembled by EntryGroup after all specialist groups have processed
    the current bar. Passed to TraderEvaluatorPanel.
    """
    # Identity
    packet_id: str
    symbol: str
    timeframe: str
    bar_timestamp: datetime
    assembled_at: datetime

    # Current market state
    indicators: IndicatorSnapshot
    structure: StructuralSnapshot
    candlestick: CandlestickSnapshot
    chart_pattern: ChartPatternSnapshot
    regime: RegimeContext

    # Proposed trade
    proposal: SetupProposal

    # Supporting context
    recent_closes: list[Decimal] = field(default_factory=list)  # last 20 closes
    market_context_notes: list[str] = field(default_factory=list)

    # Metadata
    groups_contributed: list[str] = field(default_factory=list)
    packet_valid: bool = True
    invalid_reason: Optional[str] = None
