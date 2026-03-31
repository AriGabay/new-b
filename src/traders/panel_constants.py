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

PANEL_APPROVE_THRESHOLD: int = 12
PANEL_MIN_AVG_SCORE: float = 5.5

PANEL_REGIME_THRESHOLDS: dict[str, int] = {
    "bull":     11,
    "trending": 11,
    "ranging":  12,
    "bear":     12,
}

# Task 11H: non-BTC symbols require tighter consensus
PANEL_SYMBOL_THRESHOLD_OFFSET: dict[str, int] = {
    "ETHUSDT": 1,
    "BNBUSDT": 1,
}
