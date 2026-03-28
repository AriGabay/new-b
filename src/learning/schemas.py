"""
Learning-layer dataclasses.

These mirror the SQLite tables in journal_extension.py and are used
throughout the calibration, tracking, and recommendation systems.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from learning.outcome_source import OutcomeSource


@dataclass
class StoredSetupPacket:
    """A BTCSetupPacket archived at decision time."""
    packet_id: str
    symbol: str
    timeframe: str
    bar_timestamp: datetime
    stored_at: datetime
    outcome_source: OutcomeSource
    # JSON-serialized full BTCSetupPacket
    packet_json: str
    # Linked trade (populated when trade closes)
    trade_id: Optional[str] = None


@dataclass
class StoredTraderReview:
    """One TraderVerdict from one evaluator for one setup."""
    review_id: str
    packet_id: str
    trader_name: str
    outcome_source: OutcomeSource
    vote: str               # approve / reject / abstain
    score: float            # 1-10
    confidence: float       # 0.0-1.0
    pro_reason: str
    anti_reason: str
    execution_concern: str
    risk_concern: str
    explanation: str
    reviewed_at: datetime
    # Linked trade for outcome attribution
    trade_id: Optional[str] = None


@dataclass
class StoredPanelSummary:
    """PanelResult summary for one setup."""
    panel_id: str
    packet_id: str
    outcome_source: OutcomeSource
    approve_count: int
    reject_count: int
    abstain_count: int
    avg_score: float
    weighted_score: float
    panel_recommendation: str   # enter / hold
    key_risks: str              # JSON list
    key_strengths: str          # JSON list
    evaluated_at: datetime
    trade_id: Optional[str] = None


@dataclass
class StoredFinalDecision:
    """FinalDecisionGroup output for one setup."""
    decision_id: str
    packet_id: str
    panel_id: str
    outcome_source: OutcomeSource
    decision: str               # enter / hold
    safety_rails_triggered: str # JSON list of rail names
    rationale: str
    decided_at: datetime
    trade_id: Optional[str] = None


@dataclass
class OutcomeAttribution:
    """
    Links a closed trade back to the decision trace that created it.
    Populated when trade closes.
    """
    attribution_id: str
    trade_id: str
    packet_id: str
    panel_id: str
    decision_id: str
    outcome_source: OutcomeSource
    outcome: str                # win / loss / breakeven
    pnl_r: float
    exit_reason: str
    bars_held: int
    # Setup family (e.g. "ema_crossover", "bb_squeeze")
    setup_family: str
    attributed_at: datetime


@dataclass
class TraderCalibrationRecord:
    """
    Running calibration record for one trader evaluator.
    Updated after each closed trade that the trader reviewed.
    Minimum 30 samples before drawing conclusions.
    """
    trader_name: str
    outcome_source: OutcomeSource
    total_reviews: int = 0
    # Approve accuracy: of trades approved, what % were wins
    approvals_given: int = 0
    approvals_that_won: int = 0
    # Reject accuracy: of trades rejected, what % would have won
    rejections_given: int = 0
    # Brier score components (probability calibration)
    brier_score_sum: float = 0.0
    brier_score_count: int = 0
    # Overconfidence flag: high confidence + wrong outcome
    high_conf_wrong_count: int = 0
    # Average score on winning vs losing trades
    avg_score_on_wins: float = 0.0
    avg_score_on_losses: float = 0.0
    win_score_sum: float = 0.0
    win_score_count: int = 0
    loss_score_sum: float = 0.0
    loss_score_count: int = 0
    last_updated: Optional[datetime] = None

    @property
    def approval_win_rate(self) -> Optional[float]:
        if self.approvals_given < 30:
            return None  # insufficient sample size
        return self.approvals_that_won / self.approvals_given

    @property
    def brier_score(self) -> Optional[float]:
        if self.brier_score_count < 30:
            return None
        return self.brier_score_sum / self.brier_score_count

    @property
    def is_overconfident(self) -> bool:
        if self.total_reviews < 30:
            return False
        return (self.high_conf_wrong_count / self.total_reviews) > 0.30

    @property
    def has_sufficient_samples(self) -> bool:
        return self.total_reviews >= 30


@dataclass
class SetupFamilyRecord:
    """Per-setup-family performance. Min 30 samples before conclusions."""
    setup_family: str
    outcome_source: OutcomeSource
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    total_pnl_r: float = 0.0
    avg_bars_held: float = 0.0
    bars_held_sum: float = 0.0
    last_updated: Optional[datetime] = None

    @property
    def win_rate(self) -> Optional[float]:
        if self.total_trades < 30:
            return None
        return self.wins / self.total_trades

    @property
    def avg_pnl_r(self) -> Optional[float]:
        if self.total_trades < 30:
            return None
        return self.total_pnl_r / self.total_trades

    @property
    def has_sufficient_samples(self) -> bool:
        return self.total_trades >= 30


@dataclass
class SpecialistGroupRecord:
    """
    Per-specialist-group signal contribution.
    Tracks how often each group's signals lead to winning trades.
    Min 30 samples before conclusions.
    """
    group_id: str
    outcome_source: OutcomeSource
    signals_contributed: int = 0
    signals_on_winning_trades: int = 0
    signals_on_losing_trades: int = 0
    avg_quality_score_wins: float = 0.0
    avg_quality_score_losses: float = 0.0
    last_updated: Optional[datetime] = None

    @property
    def win_contribution_rate(self) -> Optional[float]:
        total = self.signals_on_winning_trades + self.signals_on_losing_trades
        if total < 30:
            return None
        return self.signals_on_winning_trades / total

    @property
    def has_sufficient_samples(self) -> bool:
        total = self.signals_on_winning_trades + self.signals_on_losing_trades
        return total >= 30


@dataclass
class LearningRecommendation:
    """A generated recommendation from the RecommendationEngine."""
    recommendation_id: str
    created_at: datetime
    outcome_source: OutcomeSource
    recommendation_type: str   # reweight / quarantine / caution / none
    target: str                # trader name, setup family, or group_id
    reason: str
    evidence: str              # summary of supporting data
    sample_size: int
    confidence: str            # low / medium / high
    # Status
    applied: bool = False
    applied_at: Optional[datetime] = None
