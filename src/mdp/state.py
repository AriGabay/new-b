"""
MDPState: rich state vector for the MDP decision policy.

Built from: CandidateTradeProposal + PanelResult (20 verdicts) + SystemState.

Design:
  - All 20 evaluator scores/votes/confidences are captured individually.
  - Disagreement (score_std_dev) is a first-class feature.
  - Account health (drawdown, streak, win_rate) shapes action sizing.
  - to_vector() encodes the state for future ML consumption.
  - to_dict() serializes for JSON storage in transition logs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MDPState:
    """
    Rich state vector for MDP decision policy.
    Built from: proposal + panel outputs + account context.
    """

    # ------------------------------------------------------------------
    # Proposal features
    # ------------------------------------------------------------------
    direction: str              # "long" / "short"
    symbol: str
    timeframe: str
    entry_price: float
    stop_price: float
    target_price: float
    r_r_ratio: float
    composite_score: float
    setup_quality: str          # "A" | "B" | "C" | "invalid"

    # ------------------------------------------------------------------
    # Regime context
    # ------------------------------------------------------------------
    btc_macro: str              # "bull" | "bear" | "ranging"
    trending: bool
    volatility_regime: str      # "low" | "normal" | "high"
    adx14: float

    # ------------------------------------------------------------------
    # Structure context
    # ------------------------------------------------------------------
    at_support: bool
    at_resistance: bool

    # ------------------------------------------------------------------
    # Panel outputs — rich, not collapsed to a single number
    # ------------------------------------------------------------------
    approve_count: int
    reject_count: int
    abstain_count: int
    avg_score: float
    weighted_score: float
    panel_confidence: float

    # Individual evaluator data (all 20)
    evaluator_scores: dict       # {evaluator_name: float}
    evaluator_votes: dict        # {evaluator_name: str}
    evaluator_confidences: dict  # {evaluator_name: float}

    # Evaluator agreement metrics
    score_std_dev: float         # disagreement level; 0 = perfect consensus
    bull_bear_split: float       # fraction of trend-following approvers (0–1)

    # Key panel insights
    key_risks: list
    key_strengths: list

    # ------------------------------------------------------------------
    # Account state
    # ------------------------------------------------------------------
    current_equity: float
    drawdown_pct: float
    daily_pnl_pct: float
    open_positions_count: int
    total_exposure_pct: float
    recent_win_rate: float       # last 20 trades (0.5 = unknown)
    current_streak: int          # positive = win streak, negative = loss streak
    trades_last_24_bars: int

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for transition log storage."""
        return {
            "direction": self.direction,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "r_r_ratio": self.r_r_ratio,
            "composite_score": self.composite_score,
            "setup_quality": self.setup_quality,
            "btc_macro": self.btc_macro,
            "trending": self.trending,
            "volatility_regime": self.volatility_regime,
            "adx14": self.adx14,
            "at_support": self.at_support,
            "at_resistance": self.at_resistance,
            "approve_count": self.approve_count,
            "reject_count": self.reject_count,
            "abstain_count": self.abstain_count,
            "avg_score": self.avg_score,
            "weighted_score": self.weighted_score,
            "panel_confidence": self.panel_confidence,
            "evaluator_scores": self.evaluator_scores,
            "evaluator_votes": self.evaluator_votes,
            "evaluator_confidences": self.evaluator_confidences,
            "score_std_dev": self.score_std_dev,
            "bull_bear_split": self.bull_bear_split,
            "key_risks": self.key_risks,
            "key_strengths": self.key_strengths,
            "current_equity": self.current_equity,
            "drawdown_pct": self.drawdown_pct,
            "daily_pnl_pct": self.daily_pnl_pct,
            "open_positions_count": self.open_positions_count,
            "total_exposure_pct": self.total_exposure_pct,
            "recent_win_rate": self.recent_win_rate,
            "current_streak": self.current_streak,
            "trades_last_24_bars": self.trades_last_24_bars,
        }

    def to_vector(self) -> list:
        """
        Encode state as a numerical vector for future ML use.

        Encoding conventions:
          - Categoricals: one-hot or ordinal as described below.
          - Booleans: 0.0 / 1.0.
          - Counts: raw integers.
          - Proportions: 0.0–1.0 already; no normalization needed.
          - Prices: excluded (non-stationary); use r_r_ratio and pct distances.
          - Per-evaluator scores: sorted by name for reproducibility.
        """
        # direction
        dir_enc = 1.0 if self.direction == "long" else -1.0

        # setup_quality ordinal: A=1.0, B=0.75, C=0.5, invalid=0.0
        quality_map = {"A": 1.0, "B": 0.75, "C": 0.5, "invalid": 0.0}
        quality_enc = quality_map.get(self.setup_quality, 0.5)

        # btc_macro: bull=1.0, ranging=0.0, bear=-1.0
        macro_map = {"bull": 1.0, "ranging": 0.0, "bear": -1.0}
        macro_enc = macro_map.get(self.btc_macro, 0.0)

        # volatility_regime: low=0.0, normal=0.5, high=1.0
        vol_map = {"low": 0.0, "normal": 0.5, "high": 1.0}
        vol_enc = vol_map.get(self.volatility_regime, 0.5)

        # per-evaluator scores (sorted by name for reproducibility) — normalized /10
        sorted_names = sorted(self.evaluator_scores.keys())
        eval_scores_enc = [self.evaluator_scores.get(n, 5.0) / 10.0 for n in sorted_names]
        eval_confs_enc = [self.evaluator_confidences.get(n, 0.5) for n in sorted_names]

        base = [
            dir_enc,
            self.r_r_ratio / 5.0,                  # normalize: typical range 1–5
            self.composite_score,                   # already 0–1
            quality_enc,
            macro_enc,
            1.0 if self.trending else 0.0,
            vol_enc,
            self.adx14 / 50.0,                     # ADX rarely exceeds 50
            1.0 if self.at_support else 0.0,
            1.0 if self.at_resistance else 0.0,
            self.approve_count / 20.0,
            self.reject_count / 20.0,
            self.abstain_count / 20.0,
            self.avg_score / 10.0,
            self.weighted_score / 10.0,
            self.panel_confidence,
            self.score_std_dev / 3.0,              # std rarely exceeds 3
            self.bull_bear_split,
            self.drawdown_pct,
            self.daily_pnl_pct + 0.5,              # shift: −0.5 to +0.5 → 0 to 1
            float(self.open_positions_count) / 10.0,
            self.total_exposure_pct,
            self.recent_win_rate,
            (self.current_streak + 10.0) / 20.0,   # shift: −10..+10 → 0..1
            float(self.trades_last_24_bars) / 10.0,
        ]

        return base + eval_scores_enc + eval_confs_enc
