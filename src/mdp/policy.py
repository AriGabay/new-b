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
from traders.panel_constants import (
    PANEL_REGIME_THRESHOLDS,
    PANEL_SYMBOL_THRESHOLD_OFFSET,
)

logger = logging.getLogger(__name__)

# Rule thresholds (named constants for auditability)
# Sweep-optimal: T=15 across all regimes (optimization_result.json)
# T=14 was below breakeven — do not lower below 15
# hc_offset=2 → HC requires min(20, 15+2)=17 approvals for high-conviction entry
# defer_offset=-3 → DEFER fires at max(8, 15-3)=12 approvals
_REGIME_THRESHOLDS = {
    "bull":     {"base": 15, "hc_offset": 2, "defer_offset": -3},
    "trending": {"base": 15, "hc_offset": 2, "defer_offset": -3},
    "ranging":  {"base": 15, "hc_offset": 2, "defer_offset": -3},
    "bear":     {"base": 15, "hc_offset": 2, "defer_offset": -3},
}
# Sweep-optimal: T=15 across all regimes (optimization_result.json)
# T=14 was below breakeven — do not lower below 15
_DEFAULT_REGIME = {"base": PANEL_REGIME_THRESHOLDS.get("ranging", 15), "hc_offset": 2, "defer_offset": -3}

# Task 11H: non-BTC symbols need tighter consensus (panel calibrated on BTC)
_SYMBOL_THRESHOLD_OFFSET: dict[str, int] = PANEL_SYMBOL_THRESHOLD_OFFSET  # from panel_constants

HC_MIN_AVG_SCORE    = 7.0
HC_MAX_STD_DEV      = 1.5
# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
HC_MAX_DRAWDOWN     = 0.15
# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
HC_MIN_WIN_RATE     = 0.48

# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
MED_MIN_AVG_SCORE   = 5.8
# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
MED_MIN_RR          = 1.5

# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
SMALL_MIN_AVG_SCORE = 5.8

DEFER_MIN_AVG_SCORE = 5.5
DEFER_MIN_COMPOSITE = 0.65
DEFER_MAX_STD_DEV   = 2.0

# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
REDUCE_MAX_STREAK   = -10
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

    def _get_regime_thresholds(self, state: MDPState) -> dict:
        """Return per-regime approval thresholds derived from state.btc_macro.

        Non-BTC symbols (ETH, BNB) receive +1 on all thresholds because the
        panel was calibrated on BTC price action (Task 11H).
        """
        regime = getattr(state, "btc_macro", "ranging")
        rt = _REGIME_THRESHOLDS.get(regime, _DEFAULT_REGIME)
        if getattr(state, "trending", False) and regime == "ranging":
            rt = _REGIME_THRESHOLDS["trending"]
        symbol_offset = _SYMBOL_THRESHOLD_OFFSET.get(
            getattr(state, "symbol", "BTCUSDT"), 0
        )
        base = rt["base"] + symbol_offset
        return {
            "hc_min_approvals":    min(20, base + rt["hc_offset"]),
            "med_min_approvals":   base,
            "small_min_approvals": base,
            "defer_min_approvals": max(8, base + rt["defer_offset"]),
            "regime":              regime,
            "base_threshold":      base,
            "symbol_offset":       symbol_offset,
        }

    def decide(self, state: MDPState) -> tuple[MDPAction, dict]:
        """
        Evaluate rules in priority order. Returns (action, reasoning).

        reasoning keys:
          rule_fired: str       — which rule triggered
          rule_number: int      — 0-5
          factors: dict         — relevant state values that drove the decision
          size_multiplier: float — position size modifier
        """
        rt = self._get_regime_thresholds(state)
        logger.info(
            "MDPPolicy: regime=%s symbol=%s base_threshold=%d offset=%d "
            "(HC=%d MED=%d SMALL=%d DEFER=%d)",
            rt["regime"], getattr(state, "symbol", "BTCUSDT"),
            rt["base_threshold"], rt.get("symbol_offset", 0),
            rt["hc_min_approvals"], rt["med_min_approvals"],
            rt["small_min_approvals"], rt["defer_min_approvals"],
        )

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
            state.approve_count >= rt["hc_min_approvals"]
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
            state.approve_count >= rt["med_min_approvals"]
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
            state.approve_count >= rt["small_min_approvals"]
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
            state.approve_count >= rt["defer_min_approvals"]
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
