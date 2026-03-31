"""
Panel threshold constants — single source of truth.

Imported by:
  - traders/panel.py              (TraderEvaluatorPanel)
  - decision/final_group.py       (FinalDecisionGroup)
  - mdp/policy.py                 (MDPPolicy)

Do NOT duplicate these values elsewhere; always import from here.

Threshold semantics:
  PANEL_APPROVE_THRESHOLD   — default fallback when regime is unknown
  PANEL_MIN_AVG_SCORE       — minimum evaluator avg score to enter
  PANEL_REGIME_THRESHOLDS   — per-regime approval counts (out of 20)
  PANEL_SYMBOL_THRESHOLD_OFFSET — extra approvals required for non-BTC symbols
                                   (panel evaluators are calibrated on BTC)
"""
from __future__ import annotations

# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
PANEL_APPROVE_THRESHOLD: int = 15
# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
PANEL_MIN_AVG_SCORE: float = 5.8

# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
# Sweep-optimal: T=15 across all regimes (optimization_result.json)
# T=14 was below breakeven — do not lower below 15
# NOTE: bull/trending kept at 15 — T=15 is the structural optimum across ALL regimes,
# not just one. Do NOT lower thresholds in bull market.
PANEL_REGIME_THRESHOLDS: dict[str, int] = {
    "bull":     15,
    "trending": 15,
    "ranging":  15,
    "bear":     15,
}

# Task 11H: non-BTC symbols require tighter consensus
PANEL_SYMBOL_THRESHOLD_OFFSET: dict[str, int] = {
    "ETHUSDT": 1,
    "BNBUSDT": 1,
}
