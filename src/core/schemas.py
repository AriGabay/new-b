"""
Core data schemas for the crypto trading system.
All inter-module communication uses these typed objects.
No raw dicts passed between components.

Source: /docs/data_contracts/data_contracts.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
import uuid


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    LONG  = "long"
    SHORT = "short"


class ModeGate(str, Enum):
    RESEARCH = "research"   # Log signals only — no execution
    SHADOW   = "shadow"     # Paper trade with real-time data
    LIVE     = "live"       # Real order execution


class Timeframe(str, Enum):
    ONE_HOUR  = "1h"
    FOUR_HOUR = "4h"
    ONE_DAY   = "1d"


class RejectionCode(str, Enum):
    DAILY_LOSS_LIMIT       = "daily_loss_limit"
    MAX_DRAWDOWN           = "max_drawdown"
    PORTFOLIO_EXPOSURE     = "portfolio_exposure_limit"
    CORRELATED_EXPOSURE    = "correlated_exposure_limit"
    SPREAD_TOO_WIDE        = "spread_too_wide"
    PUMP_SIGNAL            = "pump_signal_active"
    INCOMPLETE_TRADE_PLAN  = "incomplete_trade_plan"
    MODE_GATE              = "mode_gate"
    CONFIRMATION_REQUIRED  = "confirmation_required"
    NO_STRUCTURAL_LEVEL    = "no_structural_level"
    SCORE_BELOW_THRESHOLD  = "score_below_threshold"
    CONFLICT               = "direction_conflict"
    DATA_QUALITY           = "data_quality_failure"
    UNIVERSE_FILTER        = "universe_filter"
    HYPOTHESIS_NOT_ACTIVE  = "hypothesis_not_active"


class ExitReason(str, Enum):
    STOP_LOSS       = "stop_loss"
    TARGET_REACHED  = "target_reached"
    TRAILING_STOP   = "trailing_stop"
    TIME_STOP       = "time_stop"
    SIGNAL_REVERSAL = "signal_reversal"
    MANUAL          = "manual"


class Outcome(str, Enum):
    WIN       = "win"
    LOSS      = "loss"
    BREAKEVEN = "breakeven"
    OPEN      = "open"


# ---------------------------------------------------------------------------
# Market Data Schemas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OHLCVBar:
    """
    A single OHLCV bar. Immutable after creation.
    Invariants enforced at construction time.
    """
    symbol:     str
    timeframe:  str
    timestamp:  datetime   # UTC, bar OPEN time
    open:       Decimal
    high:       Decimal
    low:        Decimal
    close:      Decimal
    volume:     Decimal    # Base asset volume
    volume_usd: Decimal    # Quote volume (USD)
    is_closed:  bool = True

    def __post_init__(self) -> None:
        assert self.high >= max(self.open, self.close), \
            f"high {self.high} < max(open, close)"
        assert self.low <= min(self.open, self.close), \
            f"low {self.low} > min(open, close)"
        assert self.high >= self.low, "high < low"
        assert self.volume >= 0, "volume < 0"


@dataclass(frozen=True)
class FeatureVector:
    """
    Pre-computed feature set for a single bar. Immutable.
    All features computable from OHLCV history at bar close time only.
    """
    symbol:    str
    timeframe: str
    timestamp: datetime

    # OHLCV passthrough
    open:   Decimal
    high:   Decimal
    low:    Decimal
    close:  Decimal
    volume: Decimal

    # ATR family
    true_range:   Decimal
    atr14:        Decimal   # Wilder's ATR
    atr14_sma20:  Decimal   # 20-bar SMA of ATR14

    # EMA family
    ema20:      Decimal
    ema50:      Decimal
    ema200:     Decimal
    prev_ema20: Decimal
    prev_ema50: Decimal

    # Momentum
    rsi14:      float
    prev_rsi14: float

    # Bollinger Bands
    bb_upper:     Decimal
    bb_middle:    Decimal
    bb_lower:     Decimal
    bb_width:     Decimal
    bb_width_pct: float    # 0-100 percentile rank over 100 bars

    # Trend
    adx14: float

    # Volume
    volume_sma20: Decimal
    volume_ratio: float

    # Candle anatomy
    candle_body:   Decimal
    candle_range:  Decimal
    body_ratio:    float
    upper_shadow:  Decimal
    lower_shadow:  Decimal

    # Derived flags
    impulse_flag: bool   # candle_range > 2.0 × atr14
    doji_flag:    bool   # body_ratio < 0.1


# ---------------------------------------------------------------------------
# Structural Level
# ---------------------------------------------------------------------------

@dataclass
class StructuralLevel:
    price:        Decimal
    touches:      int
    strength:     float
    first_tested: datetime
    last_tested:  datetime
    level_type:   str    # "swing_high" | "swing_low" | "ma"


# ---------------------------------------------------------------------------
# Signal Schemas
# ---------------------------------------------------------------------------

@dataclass
class CandidateSignal:
    """Base class for all group-generated signals."""
    signal_id:               str = field(default_factory=lambda: str(uuid.uuid4()))
    group_id:                str = ""
    symbol:                  str = ""
    timeframe:               str = ""
    timestamp:               datetime = field(default_factory=datetime.utcnow)
    direction:               Direction = Direction.LONG
    signal_type:             str = ""
    signal_subtype:          str = ""
    hypothesis_ref:          Optional[str] = None
    quality_score:           float = 0.0
    requires_structural_level: bool = False
    context_confirmed:       bool = False
    confirmation_required:   bool = True
    confirmed_on_bar_close:  bool = False
    metadata:                dict = field(default_factory=dict)


@dataclass
class ChartPatternSignal(CandidateSignal):
    signal_type:          str = "chart_pattern"
    pattern_state:        str = "CONFIRMED"
    breakout_level:       Decimal = Decimal("0")
    measured_move:        Decimal = Decimal("0")
    conservative_target:  Decimal = Decimal("0")   # Always measured_move × 0.50
    pattern_quality:      float = 0.0
    bars_in_formation:    int = 0
    volume_at_breakout:   Decimal = Decimal("0")
    volume_at_breakout_ok: bool = False
    neckline_price:       Optional[Decimal] = None

    def __post_init__(self) -> None:
        # Enforce Phase 1 hard rule: conservative target = 50% of measured move
        if self.measured_move > 0:
            self.conservative_target = self.measured_move * Decimal("0.50")


@dataclass
class CandlestickSignal(CandidateSignal):
    signal_type:                   str = "candlestick"
    pattern_name:                  str = ""
    bars_consumed:                 int = 1
    nearest_structural_level:      Optional[Decimal] = None
    structural_level_distance_pct: Optional[float] = None


@dataclass
class IndicatorSignal(CandidateSignal):
    signal_type:            str = "indicator"
    indicator_name:         str = ""
    indicator_values:       dict = field(default_factory=dict)
    context_filter_passed:  bool = False


# ---------------------------------------------------------------------------
# Regime and Group Communication
# ---------------------------------------------------------------------------

@dataclass
class RegimeContext:
    btc_macro:        str    # "bull" | "bear" | "ranging"
    trending:         bool   # ADX14 > 25
    volatility_regime: str   # "low" | "normal" | "high"
    adx14:            float
    atr14:            Decimal
    atr14_vs_sma20:   float  # current ATR / SMA of ATR


@dataclass
class StructuralLevelBundle:
    symbol:             str
    timeframe:          str
    timestamp:          datetime
    resistance_levels:  list[StructuralLevel] = field(default_factory=list)
    support_levels:     list[StructuralLevel] = field(default_factory=list)
    at_resistance:      bool = False
    at_support:         bool = False
    nearest_resistance: Optional[StructuralLevel] = None
    nearest_support:    Optional[StructuralLevel] = None


@dataclass
class GroupSignalBundle:
    group_id:              str
    symbol:                str
    timeframe:             str
    timestamp:             datetime
    signals:               list[CandidateSignal] = field(default_factory=list)
    regime:                Optional[RegimeContext] = None
    structural:            Optional[StructuralLevelBundle] = None
    processing_latency_ms: float = 0.0
    metadata:              dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trade Proposal and Decision
# ---------------------------------------------------------------------------

@dataclass
class ConflictReport:
    conflicts:     list[dict] = field(default_factory=list)
    resolution:    str = "none"
    net_direction: Optional[str] = None


@dataclass
class HistoricalAnalog:
    similar_trades_count: int = 0
    win_rate:             float = 0.0
    avg_r_multiple:       float = 0.0
    common_failure_modes: list[str] = field(default_factory=list)
    last_10_outcomes:     list[str] = field(default_factory=list)


@dataclass
class CriticReport:
    """Output of CriticAgent (LLM-optional). Always advisory."""
    trade_id:              str = ""
    bullish_case:          list[str] = field(default_factory=list)
    bearish_case:          list[str] = field(default_factory=list)
    failure_modes:         list[str] = field(default_factory=list)
    confidence_in_critique: float = 0.0
    recommendation:        str = "proceed"   # "proceed" | "reduce_size" | "skip"


@dataclass
class CandidateTradeProposal:
    proposal_id:      str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol:           str = ""
    timeframe:        str = ""
    timestamp:        datetime = field(default_factory=datetime.utcnow)
    direction:        Direction = Direction.LONG
    entry_price:      Decimal = Decimal("0")
    thesis:           str = ""
    setup_refs:       list[str] = field(default_factory=list)
    hypothesis_refs:  list[str] = field(default_factory=list)
    raw_target:       Decimal = Decimal("0")
    composite_score:  float = 0.0
    score_breakdown:  dict = field(default_factory=dict)
    conflict_report:  Optional[ConflictReport] = None
    historian_analog: Optional[HistoricalAnalog] = None
    critic_report:    Optional[CriticReport] = None
    regime_context:   Optional[RegimeContext] = None
    mode_gate:        ModeGate = ModeGate.RESEARCH


@dataclass
class RiskCheckResult:
    approved:          bool
    rejection_code:    Optional[RejectionCode] = None
    rejection_detail:  Optional[str] = None

    @classmethod
    def approved_ok(cls) -> "RiskCheckResult":
        return cls(approved=True)

    @classmethod
    def rejected(cls, code: RejectionCode, detail: str) -> "RiskCheckResult":
        return cls(approved=False, rejection_code=code, rejection_detail=detail)


@dataclass
class RiskApprovedOrder:
    order_id:           str = field(default_factory=lambda: str(uuid.uuid4()))
    proposal_id:        str = ""
    symbol:             str = ""
    direction:          Direction = Direction.LONG
    entry_price:        Decimal = Decimal("0")
    stop_price:         Decimal = Decimal("0")
    target_price:       Decimal = Decimal("0")
    position_size_usd:  Decimal = Decimal("0")
    position_size_base: Decimal = Decimal("0")
    leverage:           float = 1.0
    r_amount:           Decimal = Decimal("0")
    risk_fraction:      float = 0.01
    risk_checks_passed: list[str] = field(default_factory=list)
    max_bars_to_hold:   int = 20
    timestamp:          datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskRejectedEvent:
    proposal_id:      str
    rejection_reason: str
    rejection_detail: str
    timestamp:        datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Position and Exit
# ---------------------------------------------------------------------------

@dataclass
class Position:
    position_id:          str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id:             str = ""
    symbol:               str = ""
    direction:            Direction = Direction.LONG
    entry_price:          Decimal = Decimal("0")
    stop_price:           Decimal = Decimal("0")
    target_price:         Decimal = Decimal("0")
    position_size_usd:    Decimal = Decimal("0")
    leverage:             float = 1.0
    r_amount:             Decimal = Decimal("0")
    opened_at:            datetime = field(default_factory=datetime.utcnow)
    bars_held:            int = 0
    peak_favorable_price: Decimal = Decimal("0")
    trailing_stop_price:  Optional[Decimal] = None
    current_pnl_usd:      Decimal = Decimal("0")
    current_pnl_r:        float = 0.0
    status:               str = "open"
    correlation_cluster:  str = "btc"
    setup_refs:           list[str] = field(default_factory=list)
    hypothesis_refs:      list[str] = field(default_factory=list)
    # Learning layer link fields — populated from PanelApprovedProposalEvent.
    # Empty string when position was opened without panel (direct/legacy path).
    composite_score:      float = 0.0
    packet_id:            str = ""   # links to setup_packets DB row
    panel_id:             str = ""   # links to panel_summaries DB row
    decision_id:          str = ""   # links to final_decisions DB row


@dataclass
class ExitSignal:
    position_id: str
    exit_reason: ExitReason
    exit_price:  Decimal
    bars_held:   int
    pnl_usd:     Decimal
    pnl_r:       float
    timestamp:   datetime = field(default_factory=datetime.utcnow)
