"""
Exit Group (Group 8 — always_on=False, implementation_priority=3).

Responsibilities:
  - Monitor all open positions against each new bar.
  - Check stop loss (fixed and trailing), target, time stop.
  - Emit ExitSignal when any exit condition is triggered.
  - Update trailing stop on favorable price movement.
  - Publish PositionCloseEvent via EventBus.

LLM: NOT permitted.
Trigger: FeatureReadyEvent (checks open positions on each bar close).
Depends on: MARKET_DATA, INDICATORS, CHART_PATTERN.
Always-on: NO (active only when there are open positions).

Phase 2 deliverable: Stop loss exit, target exit, time stop exit.

Exit priority (first condition triggered wins):
  1. Hard stop loss   — price crosses stop_price (LONG: low ≤ stop; SHORT: high ≥ stop)
  2. Target reached   — price crosses target_price (LONG: high ≥ target; SHORT: low ≤ target)
  3. Trailing stop    — trailing_stop_price set after 1R favorable move
  4. Time stop        — bars_held ≥ max_bars_to_hold
  5. Signal reversal  — opposing ChartPattern/Indicator signal (advisory, not forced)

Trailing stop rules:
  - Activate when position reaches +1R (favorable).
  - Set trailing stop at entry_price (breakeven) initially.
  - Move to highest/lowest close − 2×ATR14 as position moves favorably.
  - Never widen trailing stop.

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
            exit_signal = self._evaluate_position(position, features)
            if exit_signal:
                await self._execute_exit(position, exit_signal)

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
        4. Time stop (bars_held >= 20)

        Before checking, update trailing stop if position is favorable.
        """
        # Update trailing stop (ratchet only — never widens)
        new_trail = self._update_trailing_stop(position, features)
        if new_trail is not None:
            position.trailing_stop_price = new_trail
            logger.debug(
                "Position %s: trailing stop updated to %s",
                position.position_id, new_trail,
            )

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
        if position.bars_held >= 20:
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
        Activate trailing stop once position reaches +1R.
        LONG:  trail = max(existing_trail, close - 2*ATR14). Never lower than entry (breakeven).
        SHORT: trail = min(existing_trail, close + 2*ATR14). Never higher than entry.
        """
        if position.r_amount <= 0:
            return None

        if position.direction == Direction.LONG:
            one_r_distance = position.entry_price - position.stop_price
            at_favorable = features.close >= position.entry_price + one_r_distance

            if not at_favorable:
                return None

            breakeven = position.entry_price
            candidate = features.close - 2 * features.atr14
            new_trail = max(breakeven, candidate)

            if position.trailing_stop_price is None or new_trail > position.trailing_stop_price:
                return new_trail

        else:  # SHORT
            one_r_distance = position.stop_price - position.entry_price
            at_favorable = features.close <= position.entry_price - one_r_distance

            if not at_favorable:
                return None

            breakeven = position.entry_price
            candidate = features.close + 2 * features.atr14
            new_trail = min(breakeven, candidate)

            if position.trailing_stop_price is None or new_trail < position.trailing_stop_price:
                return new_trail

        return None

    def _compute_pnl(self, position: Position, exit_price: Decimal) -> tuple[Decimal, float]:
        """
        pnl_usd = price_diff * size_base_units
        size_base_units = position_size_usd / entry_price
        pnl_r = pnl_usd / r_amount
        """
        if position.entry_price <= 0:
            return Decimal("0"), 0.0

        size_base = position.position_size_usd / position.entry_price

        if position.direction == Direction.LONG:
            pnl_usd = (exit_price - position.entry_price) * size_base
        else:
            pnl_usd = (position.entry_price - exit_price) * size_base

        pnl_r = float(pnl_usd / position.r_amount) if position.r_amount > 0 else 0.0
        return pnl_usd, pnl_r

    async def _execute_exit(self, position: Position, exit_signal: ExitSignal) -> None:
        """
        Finalize exit:
        1. Call state.close_position(position_id, pnl_usd).
        2. Publish PositionCloseEvent(exit_signal, final_position).
        """
        await self.state.close_position(position.position_id, exit_signal.pnl_usd)
        await self.bus.publish(
            PositionCloseEvent(
                source=self.group_id.value,
                exit_signal=exit_signal,
                final_position=position,
            )
        )
        logger.info(
            "Position %s closed: %s at %s. PnL: $%.2f (%.2fR)",
            position.position_id, exit_signal.exit_reason.value,
            exit_signal.exit_price, exit_signal.pnl_usd, exit_signal.pnl_r,
        )
