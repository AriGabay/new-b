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
    # Rolling window of last 20 closed trade outcomes (True=win, False=loss).
    # Updated by SystemState.close_position(). Used by MDPStateBuilder for R1 win-rate guard.
    recent_outcomes:          list = field(default_factory=list)
    # Close timestamps for last 48 trades (datetime). Used to compute trades_last_24_bars.
    recent_trade_close_times: list = field(default_factory=list)

    @property
    def recent_win_rate(self) -> float:
        """Win rate over last 20 closed trades. Returns 0.5 when no history."""
        if not self.recent_outcomes:
            return 0.5
        return sum(1 for o in self.recent_outcomes if o) / len(self.recent_outcomes)

    @property
    def trades_last_24_bars(self) -> int:
        """Count of trades closed in the last 24 hours (= last 24 1h bars)."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=24)
        return sum(1 for t in self.recent_trade_close_times if t >= cutoff)


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
        # Macro state — updated by NewsMacroGroup on each bar close.
        # macro_position_modifier: 0.0 (block), 0.5 (halved), 1.0 (full)
        self.macro_position_modifier: float = 1.0
        self.fear_greed_index: float = 50.0
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
            # Deduct margin (notional / leverage), not full notional, for leveraged futures.
            margin = position.position_size_usd / Decimal(str(max(position.leverage, 1.0)))
            self.portfolio.available -= margin

    async def close_position(self, position_id: str, pnl_usd: Decimal) -> None:
        async with self._lock:
            pos = self.portfolio.open_positions.pop(position_id, None)
            if pos:
                margin = pos.position_size_usd / Decimal(str(max(pos.leverage, 1.0)))
                self.portfolio.available += margin
            self.portfolio.equity += pnl_usd
            self.portfolio.daily_pnl += pnl_usd
            self.portfolio.daily_pnl_pct = float(
                self.portfolio.daily_pnl / self.portfolio.equity
            )

            # Record outcome in rolling window (keep last 20)
            self.portfolio.recent_outcomes.append(pnl_usd >= 0)
            if len(self.portfolio.recent_outcomes) > 20:
                self.portfolio.recent_outcomes.pop(0)

            # Record close timestamp for trades_last_24_bars window (keep last 48)
            self.portfolio.recent_trade_close_times.append(datetime.utcnow())
            if len(self.portfolio.recent_trade_close_times) > 48:
                self.portfolio.recent_trade_close_times.pop(0)

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

    async def update_macro_state(self, modifier: float, fear_greed: float) -> None:
        """Update macro position modifier and fear/greed index. Called by NewsMacroGroup."""
        async with self._lock:
            self.macro_position_modifier = max(0.0, min(1.0, modifier))
            self.fear_greed_index = fear_greed

    async def reset_daily_pnl(self) -> None:
        async with self._lock:
            self.portfolio.daily_pnl = Decimal("0")
            self.portfolio.daily_pnl_pct = 0.0
            self.portfolio.daily_reset_at = datetime.utcnow()
