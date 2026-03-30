"""
Group and Agent Role Registries.
Provides runtime discovery of groups and their active hypotheses.

Source: /docs/agent_registry/group_registry.md
        /docs/agent_registry/role_registry.md
        /research/hypotheses/hypothesis_registry.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Group Registry
# ---------------------------------------------------------------------------

class GroupID(str, Enum):
    MARKET_DATA              = "market_data"
    NEWS_MACRO               = "news_macro"
    INDICATORS               = "indicators"
    CANDLESTICK              = "candlestick"
    CHART_PATTERN            = "chart_pattern"
    TECHNICAL_STRUCTURE      = "technical_structure"
    ENTRY                    = "entry"
    EXIT                     = "exit"
    RISK_LEVERAGE            = "risk_leverage"
    PERFORMANCE_JOURNAL      = "performance_journal_learning"
    HISTORIAN                = "historian"


@dataclass
class GroupRegistryEntry:
    group_id:                GroupID
    responsibility:          str
    always_on:               bool
    llm_permitted:           bool
    implementation_priority: int
    dependencies:            list[GroupID] = field(default_factory=list)
    active_hypotheses:       list[str] = field(default_factory=list)   # H-IDs
    blocked_patterns:        list[str] = field(default_factory=list)   # rejection IDs
    phase_2_deliverable:     str = ""


GROUP_REGISTRY: dict[GroupID, GroupRegistryEntry] = {
    GroupID.MARKET_DATA: GroupRegistryEntry(
        group_id=GroupID.MARKET_DATA,
        responsibility="Ingest, normalize, validate, and distribute OHLCV for all symbols.",
        always_on=True,
        llm_permitted=False,
        implementation_priority=1,
        dependencies=[],
        phase_2_deliverable=(
            "Binance REST polling (daily bars), gap detection, "
            "ATR/EMA/RSI/BB/ADX feature computation."
        ),
    ),
    GroupID.NEWS_MACRO: GroupRegistryEntry(
        group_id=GroupID.NEWS_MACRO,
        responsibility="Monitor macro events and scheduled risk calendar.",
        always_on=False,
        llm_permitted=True,
        implementation_priority=5,
        dependencies=[],
        phase_2_deliverable="Static event calendar (CSV). No live news in Phase 2.",
    ),
    GroupID.INDICATORS: GroupRegistryEntry(
        group_id=GroupID.INDICATORS,
        responsibility="Compute indicator signals (EMA crossover, RSI divergence, BB squeeze, regime).",
        always_on=False,
        llm_permitted=False,
        implementation_priority=2,
        dependencies=[GroupID.MARKET_DATA],
        active_hypotheses=["H3-001", "H3-002", "H3-004"],
        phase_2_deliverable="EMA crossover (20/50), RSI divergence with impulse filter, BB squeeze.",
    ),
    GroupID.CANDLESTICK: GroupRegistryEntry(
        group_id=GroupID.CANDLESTICK,
        responsibility="Detect candlestick patterns respecting hypothesis registry.",
        always_on=False,
        llm_permitted=False,
        implementation_priority=3,
        dependencies=[GroupID.MARKET_DATA, GroupID.TECHNICAL_STRUCTURE],
        active_hypotheses=["H2-001", "H2-002", "H2-003", "H2-004", "H2-005"],
        blocked_patterns=["RJ-001", "RJ-002", "RJ-009", "RJ-010"],
        phase_2_deliverable="Bearish/Bullish Engulfing, Morning Star, Evening Star, Three Black Crows, Doji.",
    ),
    GroupID.CHART_PATTERN: GroupRegistryEntry(
        group_id=GroupID.CHART_PATTERN,
        responsibility="Track chart pattern state machines; detect confirmed breakouts.",
        always_on=False,
        llm_permitted=False,
        implementation_priority=2,
        dependencies=[GroupID.MARKET_DATA],
        active_hypotheses=["H1-001", "H1-002", "H1-003", "H1-004", "H1-005"],
        blocked_patterns=["RJ-007", "RJ-008", "RJ-009"],
        phase_2_deliverable="State machines for H1-001 through H1-005 (5 critical patterns).",
    ),
    GroupID.TECHNICAL_STRUCTURE: GroupRegistryEntry(
        group_id=GroupID.TECHNICAL_STRUCTURE,
        responsibility="Identify S/R levels, trend direction, and structural context.",
        always_on=False,
        llm_permitted=False,
        implementation_priority=2,
        dependencies=[GroupID.MARKET_DATA],
        phase_2_deliverable="Swing high/low detection, horizontal S/R (min 2 touches), at_resistance/at_support flags.",
    ),
    GroupID.ENTRY: GroupRegistryEntry(
        group_id=GroupID.ENTRY,
        responsibility="Aggregate signals, apply confirmation gate, resolve conflicts, produce CandidateTradeProposal.",
        always_on=False,
        llm_permitted=True,
        implementation_priority=4,
        dependencies=[
            GroupID.INDICATORS, GroupID.CANDLESTICK,
            GroupID.CHART_PATTERN, GroupID.TECHNICAL_STRUCTURE,
            GroupID.NEWS_MACRO,
        ],
        phase_2_deliverable="Signal aggregation, confirmation gate, conflict detection, composite scoring.",
    ),
    GroupID.EXIT: GroupRegistryEntry(
        group_id=GroupID.EXIT,
        responsibility="Monitor open positions for stop hits, target hits, time stops.",
        always_on=False,
        llm_permitted=False,
        implementation_priority=3,
        dependencies=[GroupID.MARKET_DATA, GroupID.INDICATORS, GroupID.CHART_PATTERN],
        phase_2_deliverable="Stop loss exit, target exit, time stop exit.",
    ),
    GroupID.RISK_LEVERAGE: GroupRegistryEntry(
        group_id=GroupID.RISK_LEVERAGE,
        responsibility="Final non-overridable gate: applies all 9 Phase 1 risk rules.",
        always_on=False,
        llm_permitted=False,
        implementation_priority=1,
        dependencies=[GroupID.MARKET_DATA, GroupID.ENTRY],
        phase_2_deliverable="All 9 Phase 1 risk rules as deterministic checks.",
    ),
    GroupID.PERFORMANCE_JOURNAL: GroupRegistryEntry(
        group_id=GroupID.PERFORMANCE_JOURNAL,
        responsibility="Log all events; compute performance metrics; detect edge decay.",
        always_on=True,
        llm_permitted=True,
        implementation_priority=3,
        dependencies=[],  # Subscribes to all events
        phase_2_deliverable="SQLite journal, trade outcome logging, basic performance metrics.",
    ),
}


# ---------------------------------------------------------------------------
# Hypothesis Registry (mirrors /research/hypotheses/hypothesis_registry.md)
# ---------------------------------------------------------------------------

class HypothesisStatus(str, Enum):
    UNTESTED    = "untested"
    IN_SAMPLE   = "in_sample_tested"
    OOS_PASSED  = "oos_passed"
    SHADOW      = "shadow_live"
    VALIDATED   = "validated"
    REJECTED    = "rejected"


@dataclass
class HypothesisEntry:
    hypothesis_id:   str
    claim:           str
    signal_type:     str   # "chart_pattern" | "candlestick" | "indicator" | "macro"
    direction_bias:  str   # "long" | "short" | "both"
    sprint:          str   # "S1" | "S2" | "S3" | "S4" | "S5"
    priority:        str   # "CRITICAL" | "HIGH" | "MEDIUM"
    status:          HypothesisStatus = HypothesisStatus.UNTESTED
    equity_baseline: Optional[str] = None   # Bulkowski stats if available
    acceptance_criteria: str = ""
    known_failure_modes: list[str] = field(default_factory=list)


HYPOTHESIS_REGISTRY: dict[str, HypothesisEntry] = {
    "H1-001": HypothesisEntry(
        hypothesis_id="H1-001",
        claim="H&S Top post-neckline short entry yields positive expectancy.",
        signal_type="chart_pattern",
        direction_bias="short",
        sprint="S2",
        priority="CRITICAL",
        equity_baseline="~7% failure rate, 93% break downward (Bulkowski equities)",
        acceptance_criteria="Failure rate < 20% in crypto; profit factor > 1.2 after fees",
        known_failure_modes=["Strong macro bull market", "Neckline manipulation in thin markets"],
    ),
    "H1-002": HypothesisEntry(
        hypothesis_id="H1-002",
        claim="Inverse H&S post-neckline long entry yields positive expectancy.",
        signal_type="chart_pattern",
        direction_bias="long",
        sprint="S2",
        priority="CRITICAL",
        equity_baseline="High reliability, commonly studied",
        acceptance_criteria="Failure rate < 20%; profit factor > 1.2",
    ),
    "H1-003": HypothesisEntry(
        hypothesis_id="H1-003",
        claim="Confirmed double bottoms have < 15% failure rate; unconfirmed > 40%.",
        signal_type="chart_pattern",
        direction_bias="long",
        sprint="S2",
        priority="CRITICAL",
        equity_baseline="Confirmed: 3% failure; Unconfirmed: 64% failure (Bulkowski)",
        acceptance_criteria="Confirmed < 15%; Unconfirmed > 40%; statistically significant difference",
    ),
    "H1-004": HypothesisEntry(
        hypothesis_id="H1-004",
        claim="Descending triangle confirmed breakout yields positive expectancy short.",
        signal_type="chart_pattern",
        direction_bias="short",
        sprint="S2",
        priority="CRITICAL",
        equity_baseline="4% failure rate with confirmed downside breakout (Bulkowski)",
        acceptance_criteria="Failure rate < 15% in crypto",
    ),
    "H1-005": HypothesisEntry(
        hypothesis_id="H1-005",
        claim="Triple bottom long entry yields positive expectancy.",
        signal_type="chart_pattern",
        direction_bias="long",
        sprint="S2",
        priority="CRITICAL",
        equity_baseline="4% failure rate, 38% average rise (Bulkowski)",
        acceptance_criteria="Failure rate < 15%; average gain > 15%",
    ),
    "H1-006": HypothesisEntry(
        hypothesis_id="H1-006",
        claim="Bull flags in crypto have acceptable failure rates with 50%-discounted targets.",
        signal_type="chart_pattern",
        direction_bias="long",
        sprint="S3",
        priority="HIGH",
        equity_baseline="12-13% failure rate, 52-63% target achievement (Bulkowski)",
        acceptance_criteria="Failure rate < 20%; positive expectancy with 50% target discount",
    ),
    "H1-007": HypothesisEntry(
        hypothesis_id="H1-007",
        claim="High & Tight Flags outperform standard flags in crypto.",
        signal_type="chart_pattern",
        direction_bias="long",
        sprint="S3",
        priority="HIGH",
        equity_baseline="17% failure rate with breakout (Bulkowski)",
    ),
    "H1-008": HypothesisEntry(
        hypothesis_id="H1-008",
        claim="Confirmed falling wedge breakouts yield positive expectancy longs.",
        signal_type="chart_pattern",
        direction_bias="long",
        sprint="S3",
        priority="HIGH",
        equity_baseline="10% failure rate, 43% average rise (Bulkowski)",
        acceptance_criteria="Failure rate < 20%; average gain > 10%",
    ),
    "H1-009": HypothesisEntry(
        hypothesis_id="H1-009",
        claim="Pipe bottoms in downtrend yield positive expectancy longs.",
        signal_type="chart_pattern",
        direction_bias="long",
        sprint="S3",
        priority="HIGH",
        equity_baseline="12% failure rate, 47% average rise (Bulkowski)",
    ),
    "H2-001": HypothesisEntry(
        hypothesis_id="H2-001",
        claim="Bearish/Bullish Engulfing at structural levels has directional edge.",
        signal_type="candlestick",
        direction_bias="both",
        sprint="S4",
        priority="HIGH",
        acceptance_criteria="Average next-5-bar return < -2% (bearish) or > +2% (bullish) after fees",
    ),
    "H2-002": HypothesisEntry(
        hypothesis_id="H2-002",
        claim="Morning/Evening Stars at structural levels have directional edge.",
        signal_type="candlestick",
        direction_bias="both",
        sprint="S4",
        priority="HIGH",
    ),
    "H2-003": HypothesisEntry(
        hypothesis_id="H2-003",
        claim="Three Black Crows in uptrend yields reliable downside continuation.",
        signal_type="candlestick",
        direction_bias="short",
        sprint="S4",
        priority="HIGH",
    ),
    "H2-004": HypothesisEntry(
        hypothesis_id="H2-004",
        claim="Inverted Hammer is bearish continuation in crypto (per Bulkowski, not textbook).",
        signal_type="candlestick",
        direction_bias="short",
        sprint="S4",
        priority="MEDIUM",
        equity_baseline="~60% bearish continuation (Bulkowski equities; contradicts textbook)",
    ),
    "H2-005": HypothesisEntry(
        hypothesis_id="H2-005",
        claim="Doji after 2+ trend candles has elevated reversal probability.",
        signal_type="candlestick",
        direction_bias="both",
        sprint="S4",
        priority="MEDIUM",
    ),
    "H3-001": HypothesisEntry(
        hypothesis_id="H3-001",
        claim="RSI divergence in established trend, no impulse candle, yields positive expectancy.",
        signal_type="indicator",
        direction_bias="both",
        sprint="S3",
        priority="HIGH",
        acceptance_criteria="Win rate > 55% with R:R >= 1.5:1 (context filters required)",
    ),
    "H3-002": HypothesisEntry(
        hypothesis_id="H3-002",
        claim="Simple 20/50 EMA crossover on daily BTC has positive expectancy (baseline benchmark).",
        signal_type="indicator",
        direction_bias="both",
        sprint="S1",
        priority="HIGH",
        acceptance_criteria="Profit factor > 1.2; max drawdown < 40%; used as minimum bar for all strategies",
    ),
    "H3-003": HypothesisEntry(
        hypothesis_id="H3-003",
        claim="ATR-scaled stops (2×ATR) improve Sharpe vs fixed % stops on same signals.",
        signal_type="indicator",
        direction_bias="both",
        sprint="S1",
        priority="HIGH",
        acceptance_criteria="Sharpe improvement > 0.1; max drawdown reduction > 5%",
    ),
    "H3-004": HypothesisEntry(
        hypothesis_id="H3-004",
        claim="BB squeeze followed by breakout yields higher-magnitude moves than average.",
        signal_type="indicator",
        direction_bias="both",
        sprint="S5",
        priority="MEDIUM",
    ),
    "H4-001": HypothesisEntry(
        hypothesis_id="H4-001",
        claim="Patterns from high-volume assets (>$10M/day) have lower failure rates.",
        signal_type="macro",
        direction_bias="both",
        sprint="S1",
        priority="HIGH",
        acceptance_criteria="Failure rate difference > 10pp between high- and low-volume universes",
    ),
    "H4-002": HypothesisEntry(
        hypothesis_id="H4-002",
        claim="BTC MVRV > 3.0 predicts significantly lower 90-day forward returns.",
        signal_type="macro",
        direction_bias="both",
        sprint="S5",
        priority="MEDIUM",
    ),
    "H4-003": HypothesisEntry(
        hypothesis_id="H4-003",
        claim="After >15% drop, bounce+bearish signal yields profitable short continuation.",
        signal_type="macro",
        direction_bias="short",
        sprint="S5",
        priority="HIGH",
    ),
    "H4-004": HypothesisEntry(
        hypothesis_id="H4-004",
        claim="Inside bar closing bottom 25% of prior range → 60%+ downside breakout.",
        signal_type="candlestick",
        direction_bias="short",
        sprint="S5",
        priority="MEDIUM",
        equity_baseline="70% downside breakout (Bulkowski equities)",
    ),
    "H5-001": HypothesisEntry(
        hypothesis_id="H5-001",
        claim="Fading round-number stop hunts has positive expectancy.",
        signal_type="macro",
        direction_bias="both",
        sprint="S5",
        priority="MEDIUM",
    ),
    "H5-002": HypothesisEntry(
        hypothesis_id="H5-002",
        claim="Pump/volume-anomaly filter removes blowup events and improves Sharpe.",
        signal_type="macro",
        direction_bias="both",
        sprint="S1",
        priority="HIGH",
    ),
}


def get_active_hypotheses(sprint: Optional[str] = None) -> list[HypothesisEntry]:
    """Return hypotheses that are UNTESTED (i.e., candidates for next sprint)."""
    result = [h for h in HYPOTHESIS_REGISTRY.values()
              if h.status == HypothesisStatus.UNTESTED]
    if sprint:
        result = [h for h in result if h.sprint == sprint]
    return result


def get_validated_hypotheses() -> list[HypothesisEntry]:
    """Return hypotheses that have passed OOS validation."""
    return [h for h in HYPOTHESIS_REGISTRY.values()
            if h.status == HypothesisStatus.VALIDATED]
