"""
MDPPolicy: maps MDPState → MDPAction.

Phase 1: Deterministic rule-based policy.

Rules are evaluated in priority order; the first matching rule wins.
Each rule returns the action AND a reasoning dict that explains why it fired.
The reasoning dict is stored in the transition log for auditability.

Phase 2 plan: Replace or augment this with a learned policy (e.g. tabular Q,
contextual bandit, or small neural net). The interface (decide → action + reasoning)
stays the same regardless of policy implementation.

Rule hierarchy (in priority order):
  R0. REDUCE_RISK   — streak or drawdown breach (portfolio protection)
  R1. HIGH_CONVICTION — strong consensus + healthy account
  R2. ENTER_MEDIUM  — standard qualifying entry
  R3. ENTER_SMALL   — qualifying entry but risk factors present
  R4. DEFER         — promising but insufficient consensus; wait one bar
  R5. NO_TRADE      — default fallback
"""
from __future__ import annotations

import logging

from mdp.state import MDPState
from mdp.actions import MDPAction

logger = logging.getLogger(__name__)

# Rule thresholds (named constants for auditability)
# Phase 5: thresholds aligned with panel APPROVE_THRESHOLD=15
HC_MIN_APPROVALS    = 18    # threshold + 3 (capped at 20)
HC_MIN_AVG_SCORE    = 7.0
HC_MAX_STD_DEV      = 1.5
HC_MAX_DRAWDOWN     = 0.10
HC_MIN_WIN_RATE     = 0.50

MED_MIN_APPROVALS   = 15    # = panel threshold
MED_MIN_AVG_SCORE   = 5.8
MED_MIN_RR          = 2.0

SMALL_MIN_APPROVALS = 15    # = panel threshold
SMALL_MIN_AVG_SCORE = 5.8

DEFER_MIN_APPROVALS = 12    # threshold - 3
DEFER_MIN_AVG_SCORE = 5.5
DEFER_MIN_COMPOSITE = 0.65
DEFER_MAX_STD_DEV   = 2.0

# Phase 4: relaxed from -4/0.25 to prevent premature trade blocking
# With 56% WR, 8 consecutive losses has only 0.15% probability
REDUCE_MAX_STREAK   = -8
REDUCE_MAX_DRAWDOWN = 0.38


class MDPPolicy:
    """
    Phase 1: Rule-based policy (deterministic, no learning).
    Maps MDPState → (MDPAction, reasoning_dict).

    Deliberately uses MORE information than the old threshold system:
      - Evaluator disagreement (score_std_dev)
      - Account health (drawdown_pct, current_streak, recent_win_rate)
      - Risk context (volatility_regime, trades_last_24_bars)
      - Not just approve_count and avg_score

    The interface is stable: Phase 2 replaces the rule body while keeping
    decide(state) → (action, reasoning).
    """

    def decide(self, state: MDPState) -> tuple[MDPAction, dict]:
        """
        Evaluate rules in priority order. Returns (action, reasoning).

        reasoning keys:
          rule_fired: str       — which rule triggered
          rule_number: int      — 0-5
          factors: dict         — relevant state values that drove the decision
          size_multiplier: float — position size modifier
        """
        # ------------------------------------------------------------------
        # R0: Portfolio protection — always evaluated first
        # ------------------------------------------------------------------
        if state.current_streak <= REDUCE_MAX_STREAK or state.drawdown_pct > REDUCE_MAX_DRAWDOWN:
            reasoning = {
                "rule_fired": "REDUCE_RISK",
                "rule_number": 0,
                "factors": {
                    "current_streak": state.current_streak,
                    "drawdown_pct": state.drawdown_pct,
                    "reduce_max_streak": REDUCE_MAX_STREAK,
                    "reduce_max_drawdown": REDUCE_MAX_DRAWDOWN,
                },
                "size_multiplier": 0.0,
            }
            logger.debug(
                "MDPPolicy R0 REDUCE_RISK: streak=%d drawdown=%.1f%%",
                state.current_streak, state.drawdown_pct * 100,
            )
            return MDPAction.REDUCE_RISK, reasoning

        # ------------------------------------------------------------------
        # R1: High conviction — strong consensus + healthy account
        # ------------------------------------------------------------------
        if (
            state.approve_count >= HC_MIN_APPROVALS
            and state.avg_score >= HC_MIN_AVG_SCORE
            and state.score_std_dev < HC_MAX_STD_DEV
            and state.drawdown_pct < HC_MAX_DRAWDOWN
            and state.recent_win_rate >= HC_MIN_WIN_RATE
        ):
            reasoning = {
                "rule_fired": "ENTER_HIGH_CONVICTION",
                "rule_number": 1,
                "factors": {
                    "approve_count": state.approve_count,
                    "avg_score": state.avg_score,
                    "score_std_dev": state.score_std_dev,
                    "drawdown_pct": state.drawdown_pct,
                    "recent_win_rate": state.recent_win_rate,
                },
                "size_multiplier": 1.5,
            }
            logger.debug(
                "MDPPolicy R1 ENTER_HIGH_CONVICTION: approve=%d avg=%.1f std=%.2f",
                state.approve_count, state.avg_score, state.score_std_dev,
            )
            return MDPAction.ENTER_HIGH_CONVICTION, reasoning

        # ------------------------------------------------------------------
        # R2: Standard entry — qualifying consensus + adequate R:R
        # ------------------------------------------------------------------
        if (
            state.approve_count >= MED_MIN_APPROVALS
            and state.avg_score >= MED_MIN_AVG_SCORE
            and state.r_r_ratio >= MED_MIN_RR
        ):
            reasoning = {
                "rule_fired": "ENTER_MEDIUM",
                "rule_number": 2,
                "factors": {
                    "approve_count": state.approve_count,
                    "avg_score": state.avg_score,
                    "r_r_ratio": state.r_r_ratio,
                },
                "size_multiplier": 1.0,
            }
            logger.debug(
                "MDPPolicy R2 ENTER_MEDIUM: approve=%d avg=%.1f r_r=%.2f",
                state.approve_count, state.avg_score, state.r_r_ratio,
            )
            return MDPAction.ENTER_MEDIUM, reasoning

        # ------------------------------------------------------------------
        # R3: Cautious entry — qualifying consensus but risk factors present
        # ------------------------------------------------------------------
        risk_factor_triggered = (
            state.drawdown_pct > 0.10
            or state.current_streak < -2
            or state.volatility_regime == "high"
        )
        if (
            state.approve_count >= SMALL_MIN_APPROVALS
            and state.avg_score >= SMALL_MIN_AVG_SCORE
            and risk_factor_triggered
        ):
            triggered = []
            if state.drawdown_pct > 0.10:
                triggered.append(f"drawdown={state.drawdown_pct:.1%}")
            if state.current_streak < -2:
                triggered.append(f"streak={state.current_streak}")
            if state.volatility_regime == "high":
                triggered.append("high_volatility")

            reasoning = {
                "rule_fired": "ENTER_SMALL",
                "rule_number": 3,
                "factors": {
                    "approve_count": state.approve_count,
                    "avg_score": state.avg_score,
                    "risk_factors_triggered": triggered,
                },
                "size_multiplier": 0.5,
            }
            logger.debug(
                "MDPPolicy R3 ENTER_SMALL: approve=%d avg=%.1f risk=%s",
                state.approve_count, state.avg_score, triggered,
            )
            return MDPAction.ENTER_SMALL, reasoning

        # ------------------------------------------------------------------
        # R4: Defer — promising setup, near threshold; wait one bar
        # ------------------------------------------------------------------
        if (
            state.approve_count >= DEFER_MIN_APPROVALS
            and state.avg_score >= DEFER_MIN_AVG_SCORE
            and state.composite_score >= DEFER_MIN_COMPOSITE
            and state.score_std_dev < DEFER_MAX_STD_DEV
        ):
            reasoning = {
                "rule_fired": "DEFER",
                "rule_number": 4,
                "factors": {
                    "approve_count": state.approve_count,
                    "avg_score": state.avg_score,
                    "composite_score": state.composite_score,
                    "score_std_dev": state.score_std_dev,
                    "note": "near threshold — re-evaluate next bar",
                },
                "size_multiplier": 0.0,
            }
            logger.debug(
                "MDPPolicy R4 DEFER: approve=%d composite=%.2f std=%.2f",
                state.approve_count, state.composite_score, state.score_std_dev,
            )
            return MDPAction.DEFER, reasoning

        # ------------------------------------------------------------------
        # R5: No trade — no rule matched
        # ------------------------------------------------------------------
        reasoning = {
            "rule_fired": "NO_TRADE",
            "rule_number": 5,
            "factors": {
                "approve_count": state.approve_count,
                "avg_score": state.avg_score,
                "r_r_ratio": state.r_r_ratio,
                "composite_score": state.composite_score,
            },
            "size_multiplier": 0.0,
        }
        logger.debug(
            "MDPPolicy R5 NO_TRADE: approve=%d avg=%.1f",
            state.approve_count, state.avg_score,
        )
        return MDPAction.NO_TRADE, reasoning
