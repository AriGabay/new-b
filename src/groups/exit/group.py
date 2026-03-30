"""
Exit Group (Group 8 — always_on=False, implementation_priority=3).

Responsibilities:
  - Monitor all open positions against each new bar.
  - Check stop loss (fixed and trailing), target, time stop.
  - Apply partial profit taking at +1R (30%) and +2R (20%).
  - Apply breakeven time stop if bars_held >= 24 and not at +0.3R.
  - Emit ExitSignal when any exit condition is triggered.
  - Update trailing stop on favorable price movement.
  - Publish PositionCloseEvent (with reward_signal) via EventBus.

LLM: NOT permitted.
Trigger: FeatureReadyEvent (checks open positions on each bar close).
Depends on: MARKET_DATA, INDICATORS, CHART_PATTERN.
Always-on: NO (active only when there are open positions).

Phase 2 deliverable: Stop loss exit, target exit, time stop exit.

Exit priority (first condition triggered wins):
  1. Hard stop loss   — price crosses stop_price (LONG: low ≤ stop; SHORT: high ≥ stop)
  2. Target reached   — price crosses target_price (LONG: high ≥ target; SHORT: low ≤ target)
  3. Trailing stop    — trailing_stop_price set after +0.75R favorable move
  4. Time stop        — bars_held ≥ MAX_BARS_TO_HOLD (72 bars = 3 days on 1h)
  5. Signal reversal  — opposing ChartPattern/Indicator signal (advisory, not forced)

Trailing stop rules:
  - Activate when position reaches +0.75R (favorable).
  - Initial trail distance: 1.5×ATR14.
  - Tighten to 1.0×ATR14 after +1.5R.
  - Tighten to 0.6×ATR14 after +2.5R.
  - Never widen trailing stop.

Partial profit taking:
  - At +1R: close 30% of position (remaining_fraction → 0.70).
  - At +2R: close additional 20% (remaining_fraction → 0.50).
  - Remaining 50% rides trailing stop.

Breakeven time stop:
  - At bars_held >= 24 AND pnl_r < +0.3R: move stop to entry_price (breakeven).
  - Does not exit — just tightens stop.

Source: /docs/agent_registry/group_registry.md (EXIT entry)
        /docs/risk_framework/risk_contract.md
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from agents.base.group import BaseGroup
from core.events import (
    EventBus,
    FeatureReadyEvent,
    PositionCloseEvent,
    SystemEvent,
)
from core.registry import GroupID
from core.schemas import Direction, ExitReason, ExitSignal, FeatureVector, Position
from core.state import SystemState

logger = logging.getLogger(__name__)

MAX_BARS_TO_HOLD = 72   # 72 bars = 3 days on 1h — give trades room to develop

# Trailing stop activation and tightening thresholds (in R-multiples)
TRAIL_ACTIVATE_R     = 1.0   # activate trailing stop at +1.0R (was 0.50 — let winners run)
TRAIL_ATR_INITIAL    = Decimal("1.5")  # initial trail distance ×ATR14 (was 0.6 — too tight)
TRAIL_ATR_TIGHT_1    = Decimal("1.0")  # tighten to ×ATR14 after +1.5R (was 0.4)
TRAIL_ATR_TIGHT_2    = Decimal("0.6")  # tighten further after +2.5R (was 0.3)
TRAIL_TIGHT_1_R      = 1.5   # R-multiple at which first tightening applies
TRAIL_TIGHT_2_R      = 2.5   # R-multiple at which second tightening applies

# Partial profit taking thresholds
PARTIAL_1_R          = 1.0   # take 30% off at +1R
PARTIAL_1_FRACTION   = 0.30
PARTIAL_2_R          = 2.0   # take 20% off at +2R
PARTIAL_2_FRACTION   = 0.20

# Breakeven time stop
BREAKEVEN_BARS       = 24    # apply breakeven stop after 24 bars (was 12 — too aggressive)
BREAKEVEN_MIN_R      = 0.3   # minimum R-multiple to avoid breakeven stop


class ExitGroup(BaseGroup):
    """
    Position exit monitor.

    Cross-bar state:
    -   Reads open positions from SystemState.portfolio.open_positions.
    -   Maintains trailing stop prices locally (mirrors position state).
    """

    group_id = GroupID.EXIT

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)

    async def _setup(self) -> None:
        await self.bus.subscribe(FeatureReadyEvent, self.handle_event)
        logger.info("ExitGroup subscribed to FeatureReadyEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, FeatureReadyEvent) and event.features:
            await self._check_exits(event.features)

    async def _check_exits(self, features: FeatureVector) -> None:
        """
        On each bar close, check all open positions for exit conditions.
        Applies exit priority order: stop → target → trailing → time → reversal.
        For each triggered position: build ExitSignal, publish PositionCloseEvent.
        """
        open_positions = dict(self.state.portfolio.open_positions)  # snapshot
        for position_id, position in open_positions.items():
            if position.symbol != features.symbol:
                continue
            if self._is_entry_bar(position, features):
                # Entry bar: the position was opened at the close of this bar.
                # The bar's low/high occurred BEFORE the entry, so checking them
                # against stop/target would produce false stops.
                #
                # BUG FIX (Phase 7.1): all 42 historical bars_held=0 stop-loss
                # exits were caused by this entry-bar wick check. The V3 fixture
                # trade (double_bottom_long_v1) reached +1.655R MFE but was
                # falsely stopped at -0.184R because the entry bar's wick
                # (low=69289) was 12 points below the stop (69301).
                position.bars_held += 1
                continue
            exit_signal = self._evaluate_position(position, features)
            if exit_signal:
                await self._execute_exit(position, exit_signal)

    def _is_entry_bar(self, position: Position, features: FeatureVector) -> bool:
        """
        Returns True if this FeatureVector is the bar on which the position was
        opened.  In the runtime path, the position opens at bar close during the
        same FeatureReadyEvent cascade that ExitGroup later processes.  The bar's
        low/high occurred before the entry, so exit checks are invalid.

        Detection: bars_held == 0 AND the bar's close matches the entry price.
        This is safe because:
          - entry_price is always set from state.last_close_by_symbol (= bar close)
          - bars_held == 0 means no exit check has run yet
          - the close match ensures we only skip the EXACT entry bar, not a
            subsequent bar that happens to also have bars_held == 0 (e.g. if a
            position was opened via direct CandidateTradeEvent injection in tests)
        """
        if position.bars_held != 0:
            return False
        return float(position.entry_price) == float(features.close)

    def _evaluate_position(
        self,
        position: Position,
        features: FeatureVector,
    ) -> Optional[ExitSignal]:
        """
        Check exit conditions in priority order:
        1. Hard stop loss
        2. Target reached
        3. Trailing stop triggered
        4. Time stop (bars_held >= MAX_BARS_TO_HOLD)

        Before checking, update trailing stop and apply partial profit taking.
        Breakeven time stop: if bars_held >= BREAKEVEN_BARS and pnl_r < BREAKEVEN_MIN_R,
        tighten stop to entry_price (no forced exit — just stops a drawback).

        Note: entry-bar skipping is handled by _check_exits (skip_ids).
        This method is only called for bars AFTER the entry bar.
        """
        # Apply partial profit taking (updates remaining_fraction in-place)
        self._apply_partial_exits(position, features)

        # Update trailing stop (ratchet only — never widens)
        new_trail = self._update_trailing_stop(position, features)
        if new_trail is not None:
            position.trailing_stop_price = new_trail
            logger.debug(
                "Position %s: trailing stop updated to %s",
                position.position_id, new_trail,
            )

        # Breakeven time stop: tighten to entry_price if stalled
        self._apply_breakeven_stop(position, features)

        # 1. Hard stop loss
        if self._check_stop_loss(position, features):
            exit_price = position.stop_price
            pnl_usd, pnl_r = self._compute_pnl(position, exit_price)
            return ExitSignal(
                position_id=position.position_id,
                exit_reason=ExitReason.STOP_LOSS,
                exit_price=exit_price,
                bars_held=position.bars_held,
                pnl_usd=pnl_usd,
                pnl_r=pnl_r,
            )

        # 2. Target reached
        if self._check_target(position, features):
            exit_price = position.target_price
            pnl_usd, pnl_r = self._compute_pnl(position, exit_price)
            return ExitSignal(
                position_id=position.position_id,
                exit_reason=ExitReason.TARGET_REACHED,
                exit_price=exit_price,
                bars_held=position.bars_held,
                pnl_usd=pnl_usd,
                pnl_r=pnl_r,
            )

        # 3. Trailing stop triggered
        if self._check_trailing_stop(position, features):
            exit_price = position.trailing_stop_price
            pnl_usd, pnl_r = self._compute_pnl(position, exit_price)
            return ExitSignal(
                position_id=position.position_id,
                exit_reason=ExitReason.TRAILING_STOP,
                exit_price=exit_price,
                bars_held=position.bars_held,
                pnl_usd=pnl_usd,
                pnl_r=pnl_r,
            )

        # 4. Time stop
        if position.bars_held >= MAX_BARS_TO_HOLD:
            exit_price = features.close
            pnl_usd, pnl_r = self._compute_pnl(position, exit_price)
            return ExitSignal(
                position_id=position.position_id,
                exit_reason=ExitReason.TIME_STOP,
                exit_price=exit_price,
                bars_held=position.bars_held,
                pnl_usd=pnl_usd,
                pnl_r=pnl_r,
            )

        # Increment bars held (mutable position)
        position.bars_held += 1
        return None

    def _apply_partial_exits(self, position: Position, features: FeatureVector) -> None:
        """
        Record partial profit exits at +1R and +2R thresholds.
        Updates position.remaining_fraction and position.partial_exits in-place.
        Does NOT emit events — locked profits are included in final PnL via _compute_pnl.

        LONG:  +nR when high >= entry + n × (entry - stop)
        SHORT: +nR when low  <= entry - n × (stop - entry)
        """
        if position.r_amount <= 0 or position.entry_price <= 0:
            return

        if position.direction == Direction.LONG:
            r_dist = position.entry_price - position.stop_price
            current_r = (
                float((features.high - position.entry_price) / r_dist)
                if r_dist > 0 else 0.0
            )
        else:
            r_dist = position.stop_price - position.entry_price
            current_r = (
                float((position.entry_price - features.low) / r_dist)
                if r_dist > 0 else 0.0
            )

        # Determine which partial exits have already been taken
        taken_partials = {pe["level"] for pe in position.partial_exits}

        # +1R partial: take 30% off
        if current_r >= PARTIAL_1_R and "1R" not in taken_partials:
            if position.remaining_fraction > PARTIAL_1_FRACTION:
                partial_price = (
                    position.entry_price + r_dist
                    if position.direction == Direction.LONG
                    else position.entry_price - r_dist
                )
                size_base = position.position_size_usd / position.entry_price
                partial_size = size_base * Decimal(str(PARTIAL_1_FRACTION))
                if position.direction == Direction.LONG:
                    partial_pnl = (partial_price - position.entry_price) * partial_size
                else:
                    partial_pnl = (position.entry_price - partial_price) * partial_size

                position.partial_exits.append({
                    "level": "1R",
                    "fraction": PARTIAL_1_FRACTION,
                    "price": float(partial_price),
                    "pnl_usd": float(partial_pnl),
                })
                position.remaining_fraction = round(
                    position.remaining_fraction - PARTIAL_1_FRACTION, 6
                )
                logger.debug(
                    "Position %s: partial exit at +1R (%.0f%% → remaining=%.0f%%)",
                    position.position_id,
                    PARTIAL_1_FRACTION * 100,
                    position.remaining_fraction * 100,
                )

        # +2R partial: take 20% off
        if current_r >= PARTIAL_2_R and "2R" not in taken_partials:
            if position.remaining_fraction > PARTIAL_2_FRACTION:
                partial_price = (
                    position.entry_price + 2 * r_dist
                    if position.direction == Direction.LONG
                    else position.entry_price - 2 * r_dist
                )
                size_base = position.position_size_usd / position.entry_price
                partial_size = size_base * Decimal(str(PARTIAL_2_FRACTION))
                if position.direction == Direction.LONG:
                    partial_pnl = (partial_price - position.entry_price) * partial_size
                else:
                    partial_pnl = (position.entry_price - partial_price) * partial_size

                position.partial_exits.append({
                    "level": "2R",
                    "fraction": PARTIAL_2_FRACTION,
                    "price": float(partial_price),
                    "pnl_usd": float(partial_pnl),
                })
                position.remaining_fraction = round(
                    position.remaining_fraction - PARTIAL_2_FRACTION, 6
                )
                logger.debug(
                    "Position %s: partial exit at +2R (%.0f%% → remaining=%.0f%%)",
                    position.position_id,
                    PARTIAL_2_FRACTION * 100,
                    position.remaining_fraction * 100,
                )

    def _apply_breakeven_stop(self, position: Position, features: FeatureVector) -> None:
        """
        Breakeven time stop: if bars_held >= BREAKEVEN_BARS and current pnl_r < BREAKEVEN_MIN_R,
        tighten stop to entry_price.  Does NOT force an exit — just moves the stop.
        Only applies if stop has not already been moved above entry (for LONG) or
        below entry (for SHORT) by the trailing stop logic.
        """
        if position.bars_held < BREAKEVEN_BARS:
            return
        if position.r_amount <= 0 or position.entry_price <= 0:
            return

        # Compute current unrealized R
        if position.direction == Direction.LONG:
            r_dist = position.entry_price - position.stop_price
            current_r = (
                float((features.close - position.entry_price) / r_dist)
                if r_dist > 0 else 0.0
            )
            if current_r < BREAKEVEN_MIN_R:
                if position.stop_price < position.entry_price:
                    position.stop_price = position.entry_price
                    logger.debug(
                        "Position %s: breakeven stop applied at %s (bars=%d, pnl_r=%.2f)",
                        position.position_id, position.entry_price,
                        position.bars_held, current_r,
                    )
        else:  # SHORT
            r_dist = position.stop_price - position.entry_price
            current_r = (
                float((position.entry_price - features.close) / r_dist)
                if r_dist > 0 else 0.0
            )
            if current_r < BREAKEVEN_MIN_R:
                if position.stop_price > position.entry_price:
                    position.stop_price = position.entry_price
                    logger.debug(
                        "Position %s: breakeven stop applied at %s (bars=%d, pnl_r=%.2f)",
                        position.position_id, position.entry_price,
                        position.bars_held, current_r,
                    )

    def _check_stop_loss(self, position: Position, features: FeatureVector) -> bool:
        if position.direction == Direction.LONG:
            return features.low <= position.stop_price
        else:
            return features.high >= position.stop_price

    def _check_target(self, position: Position, features: FeatureVector) -> bool:
        if position.direction == Direction.LONG:
            return features.high >= position.target_price
        else:
            return features.low <= position.target_price

    def _check_trailing_stop(self, position: Position, features: FeatureVector) -> bool:
        if position.trailing_stop_price is None:
            return False
        if position.direction == Direction.LONG:
            return features.low <= position.trailing_stop_price
        else:
            return features.high >= position.trailing_stop_price

    def _update_trailing_stop(self, position: Position, features: FeatureVector) -> Optional[Decimal]:
        """
        Activate trailing stop once position reaches +0.75R.

        Trail distance is tightened as trade progresses:
          - Default:      1.5×ATR14
          - After +1.5R:  1.0×ATR14
          - After +2.5R:  0.6×ATR14

        Never widens trailing stop (ratchet rule).
        """
        if position.r_amount <= 0:
            return None

        if position.direction == Direction.LONG:
            r_dist = position.entry_price - position.stop_price
            if r_dist <= 0:
                return None

            current_r = float((features.close - position.entry_price) / r_dist)
            if current_r < TRAIL_ACTIVATE_R:
                return None

            # Select trail ATR multiplier based on current R level
            if current_r >= TRAIL_TIGHT_2_R:
                atr_mult = TRAIL_ATR_TIGHT_2
            elif current_r >= TRAIL_TIGHT_1_R:
                atr_mult = TRAIL_ATR_TIGHT_1
            else:
                atr_mult = TRAIL_ATR_INITIAL

            candidate = features.close - atr_mult * features.atr14
            # Do NOT floor to breakeven here — _apply_breakeven_stop() handles that
            # independently. Combining both caused double-tightening that cut winners.
            new_trail = candidate

            if position.trailing_stop_price is None or new_trail > position.trailing_stop_price:
                return new_trail

        else:  # SHORT
            r_dist = position.stop_price - position.entry_price
            if r_dist <= 0:
                return None

            current_r = float((position.entry_price - features.close) / r_dist)
            if current_r < TRAIL_ACTIVATE_R:
                return None

            # Select trail ATR multiplier based on current R level
            if current_r >= TRAIL_TIGHT_2_R:
                atr_mult = TRAIL_ATR_TIGHT_2
            elif current_r >= TRAIL_TIGHT_1_R:
                atr_mult = TRAIL_ATR_TIGHT_1
            else:
                atr_mult = TRAIL_ATR_INITIAL

            candidate = features.close + atr_mult * features.atr14
            # Do NOT ceil to breakeven — _apply_breakeven_stop() handles that independently
            new_trail = candidate

            if position.trailing_stop_price is None or new_trail < position.trailing_stop_price:
                return new_trail

        return None

    def _compute_pnl(self, position: Position, exit_price: Decimal) -> tuple[Decimal, float]:
        """
        Compute total PnL including locked profits from partial exits.

        Total PnL = locked_pnl (from partial_exits) + remaining_fraction × open_pnl

        pnl_r = total_pnl_usd / r_amount  (R-multiple of FULL original position)
        """
        if position.entry_price <= 0:
            return Decimal("0"), 0.0

        size_base = position.position_size_usd / position.entry_price

        # Remaining open position PnL
        remaining_size = size_base * Decimal(str(position.remaining_fraction))
        if position.direction == Direction.LONG:
            open_pnl = (exit_price - position.entry_price) * remaining_size
        else:
            open_pnl = (position.entry_price - exit_price) * remaining_size

        # Locked PnL from partial exits
        locked_pnl = sum(
            Decimal(str(pe.get("pnl_usd", 0.0))) for pe in position.partial_exits
        )

        total_pnl = locked_pnl + open_pnl
        pnl_r = float(total_pnl / position.r_amount) if position.r_amount > 0 else 0.0
        return total_pnl, pnl_r

    async def _execute_exit(self, position: Position, exit_signal: ExitSignal) -> None:
        """
        Finalize exit:
        1. Call state.close_position(position_id, pnl_usd).
        2. Compute reward signal via RewardComputer.
        3. Publish PositionCloseEvent(exit_signal, final_position, reward_signal).
        """
        from core.reward import RewardComputer

        await self.state.close_position(position.position_id, exit_signal.pnl_usd)

        # Build account_state for reward computation
        portfolio = self.state.portfolio
        account_state = {
            "drawdown_pct": getattr(portfolio, "drawdown_pct", 0.0),
            "recent_trade_count": getattr(portfolio, "recent_trade_count", 0),
        }
        reward = RewardComputer().compute(position, exit_signal, account_state)

        await self.bus.publish(
            PositionCloseEvent(
                source=self.group_id.value,
                exit_signal=exit_signal,
                final_position=position,
                reward_signal=reward,
                state_snapshot_id=getattr(position, "state_snapshot_id", ""),
            )
        )
        from utils.bar_duration import format_bars
        tf = getattr(position, "timeframe", "1h") or "1h"
        logger.info(
            "Position %s closed: %s at %s after %s. PnL: $%.2f (%.2fR) reward=%.3f",
            position.position_id, exit_signal.exit_reason.value,
            exit_signal.exit_price, format_bars(exit_signal.bars_held, tf),
            exit_signal.pnl_usd, exit_signal.pnl_r, reward,
        )
