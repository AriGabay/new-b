"""
SystemState: singleton shared state across all groups.
Thread-safe (uses asyncio.Lock for mutations).

Source: /docs/architecture/runtime_model.md (State Model section)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .schemas import ModeGate, Position, RegimeContext


@dataclass
class PortfolioState:
    equity:              Decimal = Decimal("100000")   # Default: $100k
    available:           Decimal = Decimal("100000")   # Unallocated capital
    open_positions:      dict[str, Position] = field(default_factory=dict)
    daily_pnl:           Decimal = Decimal("0")
    daily_pnl_pct:       float = 0.0
    high_water_mark:     Decimal = Decimal("100000")
    drawdown_pct:        float = 0.0
    consecutive_losses:  int = 0
    total_trades:        int = 0
    daily_reset_at:      Optional[datetime] = None


@dataclass
class RiskState:
    halted:        bool = False
    halt_reason:   Optional[str] = None
    size_reduction: float = 1.0   # 1.0 = normal; 0.5 = half size


class SystemState:
    """
    Singleton shared state. Groups READ state; Risk Engine and Journal WRITE it.
    No other component should write state directly.
    """

    def __init__(
        self,
        mode: ModeGate = ModeGate.RESEARCH,
        initial_equity: Decimal = Decimal("100000"),
    ) -> None:
        self.mode = mode
        self.portfolio = PortfolioState(
            equity=initial_equity,
            available=initial_equity,
            high_water_mark=initial_equity,
        )
        self.regime = RegimeContext(
            btc_macro="unknown",
            trending=False,
            volatility_regime="normal",
            adx14=0.0,
            atr14=Decimal("0"),
            atr14_vs_sma20=1.0,
        )
        self.risk_state = RiskState()
        self.last_close_by_symbol: dict[str, Decimal] = {}
        self.eligible_symbols: set[str] = set()
        self._lock = asyncio.Lock()

    async def update_regime(self, regime: RegimeContext) -> None:
        async with self._lock:
            self.regime = regime

    async def update_universe(self, eligible: set[str]) -> None:
        async with self._lock:
            self.eligible_symbols = eligible

    async def open_position(self, position: Position) -> None:
        async with self._lock:
            self.portfolio.open_positions[position.position_id] = position
            self.portfolio.available -= position.position_size_usd

    async def close_position(self, position_id: str, pnl_usd: Decimal) -> None:
        async with self._lock:
            pos = self.portfolio.open_positions.pop(position_id, None)
            if pos:
                self.portfolio.available += pos.position_size_usd
            self.portfolio.equity += pnl_usd
            self.portfolio.daily_pnl += pnl_usd
            self.portfolio.daily_pnl_pct = float(
                self.portfolio.daily_pnl / self.portfolio.equity
            )

            if pnl_usd < 0:
                self.portfolio.consecutive_losses += 1
            else:
                self.portfolio.consecutive_losses = 0
                # Update HWM
                if self.portfolio.equity > self.portfolio.high_water_mark:
                    self.portfolio.high_water_mark = self.portfolio.equity

            # Update drawdown
            if self.portfolio.high_water_mark > 0:
                self.portfolio.drawdown_pct = float(
                    (self.portfolio.high_water_mark - self.portfolio.equity)
                    / self.portfolio.high_water_mark
                )

            self.portfolio.total_trades += 1

    async def update_risk_state(self, risk_state: RiskState) -> None:
        async with self._lock:
            self.risk_state = risk_state

    async def update_last_close(self, symbol: str, price: Decimal) -> None:
        """Record the latest close price for a symbol. Called by MarketDataGroup."""
        async with self._lock:
            self.last_close_by_symbol[symbol] = price

    async def reset_daily_pnl(self) -> None:
        async with self._lock:
            self.portfolio.daily_pnl = Decimal("0")
            self.portfolio.daily_pnl_pct = 0.0
            self.portfolio.daily_reset_at = datetime.utcnow()
