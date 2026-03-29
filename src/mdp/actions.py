"""
MDPAction: the action space for the MDP decision policy.

Phase 1 actions map directly to position sizing decisions.
DEFER is a temporal action — re-evaluate on next bar.
REDUCE_RISK is a portfolio management action.

Size multipliers affect the position_size_usd computed by RiskLeverageGroup.
They are stored in FinalDecision.size_multiplier and will be consumed by
RiskLeverageGroup in Phase 2 (currently logged but not yet wired to sizing).
"""
from __future__ import annotations

from enum import Enum


class MDPAction(Enum):
    NO_TRADE             = "no_trade"
    ENTER_SMALL          = "enter_small"    # 50% of normal size
    ENTER_MEDIUM         = "enter_medium"   # 100% of normal size
    ENTER_HIGH_CONVICTION = "enter_high"   # 150% of normal size
    DEFER                = "defer"          # skip this bar, re-evaluate next
    REDUCE_RISK          = "reduce_risk"    # close/reduce existing positions


# Maps action → position size multiplier (relative to base R sizing)
ACTION_SIZE_MULTIPLIERS: dict[MDPAction, float] = {
    MDPAction.NO_TRADE:              0.0,
    MDPAction.ENTER_SMALL:           0.5,
    MDPAction.ENTER_MEDIUM:          1.0,
    MDPAction.ENTER_HIGH_CONVICTION: 1.5,
    MDPAction.DEFER:                 0.0,
    MDPAction.REDUCE_RISK:           0.0,
}

# Actions that result in entering a trade
ENTER_ACTIONS = frozenset([
    MDPAction.ENTER_SMALL,
    MDPAction.ENTER_MEDIUM,
    MDPAction.ENTER_HIGH_CONVICTION,
])
