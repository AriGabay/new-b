"""
RewardComputer: risk-adjusted reward signal for closed trades.

Used by the MDP transition logger (Task 3) to evaluate decision quality.
Each closed trade produces a scalar reward that combines:
  - Base P&L in R-multiples
  - Quality bonuses (clean exits above +1.5R)
  - Risk penalties (drawdown breaches, overleverage, overstay, overtrading)

The reward is attached to PositionCloseEvent and consumed by the MDP layer.

Design notes:
  - Reward is intentionally sparse: only non-zero on trade close.
  - NO_TRADE / DEFER actions return 0.0 (neutral) via compute_deferred_reward().
  - All adjustments are additive and bounded to keep reward finite.

Source: /docs/architecture/mdp_design.md (Task 3)
"""
from __future__ import annotations

import logging
from typing import Optional

from core.schemas import ExitSignal, Position

logger = logging.getLogger(__name__)


class RewardComputer:
    """
    Computes risk-adjusted reward for closed trades.
    Used by MDP transition logger (Task 3) to evaluate decision quality.
    """

    # Reward adjustment constants
    EFFICIENCY_BONUS       =  0.1   # clean exit above +1.5R
    DRAWDOWN_PENALTY       = -0.3   # trade pushed drawdown > 10%
    OVERLEVERAGE_PENALTY   = -0.2   # leverage > 20x on a losing trade
    TIME_PENALTY           = -0.1   # overstayed (bars_held > 60)
    OVERTRADE_PENALTY      = -0.1   # > 5 trades in last 24 bars

    # Thresholds
    EFFICIENCY_R_THRESHOLD   = 1.5   # R-multiple above which exit is "clean"
    DRAWDOWN_THRESHOLD       = 0.10  # 10% drawdown threshold
    OVERLEVERAGE_THRESHOLD   = 20.0  # leverage above which penalty applies on losses
    OVERSTAY_BARS_THRESHOLD  = 60    # bars_held above which time penalty applies
    OVERTRADE_COUNT          = 5     # trades in last 24 bars above which penalty applies

    def compute(
        self,
        position: Position,
        exit_signal: ExitSignal,
        account_state: dict,
    ) -> float:
        """
        Compute risk-adjusted reward for a closed trade.

        Reward formula:
          base_reward = pnl_r  (R-multiple: +2.0 for 2R winner, -1.0 for 1R loser)

          Adjustments:
          - efficiency_bonus:      +0.1 if winner exited above +1.5R (clean trade)
          - drawdown_penalty:      -0.3 if this trade pushed drawdown > 10%
          - overleverage_penalty:  -0.2 if leverage was > 20x on a losing trade
          - time_penalty:          -0.1 if bars_held > 60 (overstayed)
          - overtrade_penalty:     -0.1 if > 5 trades in last 24 bars

          final_reward = base_reward + sum(adjustments)

        Args:
            position:      closed Position object (carries entry, leverage, etc.)
            exit_signal:   ExitSignal with pnl_r and bars_held
            account_state: dict with keys:
                           - 'drawdown_pct': float (current portfolio drawdown)
                           - 'recent_trade_count': int (trades in last 24 bars)

        Returns:
            float: scalar reward (can be negative)
        """
        base_reward = exit_signal.pnl_r

        adjustments = 0.0

        # Efficiency bonus: winner exited cleanly above +1.5R
        if exit_signal.pnl_r >= self.EFFICIENCY_R_THRESHOLD:
            adjustments += self.EFFICIENCY_BONUS
            logger.debug(
                "RewardComputer: +%.2f efficiency bonus (pnl_r=%.2f >= %.2f)",
                self.EFFICIENCY_BONUS, exit_signal.pnl_r, self.EFFICIENCY_R_THRESHOLD,
            )

        # Drawdown penalty: this trade contributed to drawdown > 10%
        drawdown_pct = account_state.get("drawdown_pct", 0.0)
        if drawdown_pct > self.DRAWDOWN_THRESHOLD:
            adjustments += self.DRAWDOWN_PENALTY
            logger.debug(
                "RewardComputer: %.2f drawdown penalty (drawdown=%.1f%% > %.1f%%)",
                self.DRAWDOWN_PENALTY, drawdown_pct * 100, self.DRAWDOWN_THRESHOLD * 100,
            )

        # Overleverage penalty: high leverage on a losing trade
        leverage = getattr(position, "leverage", 0.0)
        if leverage > self.OVERLEVERAGE_THRESHOLD and exit_signal.pnl_r < 0:
            adjustments += self.OVERLEVERAGE_PENALTY
            logger.debug(
                "RewardComputer: %.2f overleverage penalty (leverage=%.1fx on loss %.2fR)",
                self.OVERLEVERAGE_PENALTY, leverage, exit_signal.pnl_r,
            )

        # Time penalty: position overstayed
        if exit_signal.bars_held > self.OVERSTAY_BARS_THRESHOLD:
            adjustments += self.TIME_PENALTY
            logger.debug(
                "RewardComputer: %.2f time penalty (bars_held=%d > %d)",
                self.TIME_PENALTY, exit_signal.bars_held, self.OVERSTAY_BARS_THRESHOLD,
            )

        # Overtrade penalty: too many recent trades
        recent_trade_count = account_state.get("recent_trade_count", 0)
        if recent_trade_count > self.OVERTRADE_COUNT:
            adjustments += self.OVERTRADE_PENALTY
            logger.debug(
                "RewardComputer: %.2f overtrade penalty (%d trades in last 24 bars > %d)",
                self.OVERTRADE_PENALTY, recent_trade_count, self.OVERTRADE_COUNT,
            )

        final_reward = base_reward + adjustments
        logger.debug(
            "RewardComputer: base=%.3f adjustments=%.3f final=%.3f | "
            "position=%s bars=%d leverage=%.1fx",
            base_reward, adjustments, final_reward,
            position.position_id, exit_signal.bars_held, leverage,
        )
        return final_reward

    def compute_deferred_reward(self) -> float:
        """
        For NO_TRADE and DEFER actions: reward = 0.0 (neutral).
        In future: could compute opportunity cost of not trading.
        """
        return 0.0
