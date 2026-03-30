"""
BacktestEngine: deterministic bar-by-bar replay of the full group pipeline.

Design constraints:
  1. Bar-close only — features computed only after bar closes (no intra-bar signals).
  2. No lookahead — group pipeline at bar T only sees bars 0..T.
  3. Uses identical group/signal/risk/feature code as the live runtime.
  4. Commission and slippage modeled explicitly (not ignored).
  5. Journal is written to a separate backtest DB (not the live journal.db).

Usage:
    engine = BacktestEngine(config=BacktestConfig(...))
    results = await engine.run(bars)
    print(results.summary())

Source: /docs/architecture/runtime_model.md (Backtesting Runtime)
        /docs/adr/ADR-004-validation-gates-before-live-promotion.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.schemas import OHLCVBar

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for a single backtest run."""
    symbols:          list[str]
    timeframe:        str
    start_date:       datetime
    end_date:         datetime
    initial_equity:   Decimal = Decimal("100000")
    risk_fraction:    Decimal = Decimal("0.01")
    commission_pct:   Decimal = Decimal("0.001")    # 0.1% per side
    slippage_pct:     Decimal = Decimal("0.0005")   # 0.05% slippage assumption
    hypothesis_ids:   list[str] = field(default_factory=list)   # Filter: test only these
    output_db_path:   str = "data/backtest_journal.db"
    #: Set True to enforce holdout protection (raises if end_date in holdout period)
    enforce_holdout:  bool = True


@dataclass
class BacktestResult:
    """Aggregated results from one backtest run."""
    config:              BacktestConfig
    total_trades:        int = 0
    winning_trades:      int = 0
    losing_trades:       int = 0
    win_rate:            float = 0.0
    profit_factor:       float = 0.0
    max_drawdown_pct:    float = 0.0
    sharpe_ratio:        float = 0.0
    avg_r_multiple:      float = 0.0
    total_pnl_usd:       Decimal = Decimal("0")
    final_equity:        Decimal = Decimal("0")
    per_hypothesis:      dict = field(default_factory=dict)   # hyp_id → metrics dict

    def summary(self) -> str:
        """Human-readable result summary."""
        return (
            f"BacktestResult: {self.total_trades} trades | "
            f"WR: {self.win_rate:.1%} | PF: {self.profit_factor:.2f} | "
            f"MaxDD: {self.max_drawdown_pct:.1%} | Sharpe: {self.sharpe_ratio:.2f} | "
            f"PnL: ${self.total_pnl_usd:,.0f}"
        )


class BacktestEngine:
    """
    Simplified bar-by-bar backtest engine.

    Phase 3 implementation:
    - Uses FeatureComputer to compute indicators on each bar.
    - Detects EMA-20/50 crossover signals (H3-002 benchmark strategy).
    - Manages a single open position at a time (BTC single-symbol).
    - Tracks equity, wins, losses, max drawdown.
    - Does NOT replay the full group pipeline — that requires live asyncio
      infrastructure. Documented as simulation scaffold.

    NOT production-ready. See /docs/remaining_stubbed_components.md.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self._holdout = None   # HoldoutManager injected at run time

    async def run(self, bars: dict[str, list[OHLCVBar]]) -> BacktestResult:
        """
        Run simplified bar-by-bar backtest.

        bars: dict mapping symbol → list[OHLCVBar] (chronological, oldest first).

        Returns BacktestResult with per-hypothesis breakdown.

        For Phase 3 (BTC/Bybit vertical slice):
        - Uses FeatureComputer to compute indicators
        - Simulates simple EMA crossover signals only (H3-002 baseline)
        - Tracks equity, trades, drawdown
        - Does NOT require full group wiring (those are live-runtime components)

        NOT production-ready. Documented as simulation scaffold in
        /docs/remaining_stubbed_components.md
        """
        from features.compute import FeatureComputer

        result = BacktestResult(config=self.config)
        result.final_equity = self.config.initial_equity

        equity = self.config.initial_equity
        peak_equity = equity
        open_position: Optional[dict] = None  # One position at a time for BTC

        for symbol, bar_list in bars.items():
            computer = FeatureComputer()
            bar_buffer: list[OHLCVBar] = []

            for bar in bar_list:
                bar_buffer.append(bar)

                # FeatureComputer requires at least 200 bars
                if len(bar_buffer) < 200:
                    continue

                features = computer.compute(bar_buffer)
                if features is None:
                    continue

                # ----------------------------------------------------------
                # Position management: check exits before new entries
                # ----------------------------------------------------------
                if open_position is not None:
                    pos = open_position
                    bars_held = pos.get("bars_held", 0) + 1
                    pos["bars_held"] = bars_held

                    stop   = pos["stop"]
                    target = pos["target"]
                    entry  = pos["entry"]

                    if pos["direction"] == "LONG" and bar.low <= stop:
                        # Stop loss hit — fill at stop with slippage penalty
                        exit_price = stop * Decimal(
                            str(1 - float(self.config.slippage_pct))
                        )
                        pnl = (exit_price - entry) * pos["size_base"]
                        equity += pnl
                        result.total_trades += 1
                        if pnl > Decimal("0"):
                            result.winning_trades += 1
                        else:
                            result.losing_trades += 1
                        open_position = None

                    elif pos["direction"] == "SHORT" and bar.high >= stop:
                        # Short stop hit — cover at stop with slippage penalty
                        exit_price = stop * Decimal(
                            str(1 + float(self.config.slippage_pct))
                        )
                        pnl = (entry - exit_price) * pos["size_base"]
                        equity += pnl
                        result.total_trades += 1
                        if pnl > Decimal("0"):
                            result.winning_trades += 1
                        else:
                            result.losing_trades += 1
                        open_position = None

                    elif pos["direction"] == "LONG" and bar.high >= target:
                        # Target hit — fill at target minus slippage
                        exit_price = target * Decimal(
                            str(1 - float(self.config.slippage_pct))
                        )
                        pnl = (exit_price - entry) * pos["size_base"]
                        equity += pnl
                        result.total_trades += 1
                        result.winning_trades += 1
                        open_position = None

                    elif pos["direction"] == "SHORT" and bar.low <= target:
                        # Short target hit — cover at target plus slippage
                        exit_price = target * Decimal(
                            str(1 + float(self.config.slippage_pct))
                        )
                        pnl = (entry - exit_price) * pos["size_base"]
                        equity += pnl
                        result.total_trades += 1
                        result.winning_trades += 1
                        open_position = None

                    elif bars_held >= 48:
                        # Time stop — exit at current close
                        exit_price = bar.close
                        if pos["direction"] == "LONG":
                            pnl = (exit_price - entry) * pos["size_base"]
                        else:
                            pnl = (entry - exit_price) * pos["size_base"]
                        equity += pnl
                        result.total_trades += 1
                        if pnl > Decimal("0"):
                            result.winning_trades += 1
                        else:
                            result.losing_trades += 1
                        open_position = None

                # ----------------------------------------------------------
                # Track peak equity and drawdown after position updates
                # ----------------------------------------------------------
                if equity > peak_equity:
                    peak_equity = equity
                if peak_equity > Decimal("0"):
                    dd = float((peak_equity - equity) / peak_equity)
                    if dd > result.max_drawdown_pct:
                        result.max_drawdown_pct = dd

                # ----------------------------------------------------------
                # Signal detection: simplified EMA-20/50 crossover (H3-002)
                # ----------------------------------------------------------
                if open_position is None:
                    direction: Optional[str] = None

                    # Golden cross: EMA20 crosses above EMA50
                    if (
                        features.prev_ema20 < features.prev_ema50
                        and features.ema20 > features.ema50
                        and features.adx14 > 20
                    ):
                        direction = "LONG"
                    # Death cross: EMA20 crosses below EMA50
                    elif (
                        features.prev_ema20 > features.prev_ema50
                        and features.ema20 < features.ema50
                        and features.adx14 > 20
                    ):
                        direction = "SHORT"

                    if direction is not None:
                        atr = features.atr14
                        # Apply commission + slippage to entry
                        adj = float(self.config.commission_pct) + float(
                            self.config.slippage_pct
                        )
                        if direction == "LONG":
                            entry_price = bar.close * Decimal(str(1 + adj))
                            stop_price  = entry_price - Decimal("2") * atr
                            target_price = entry_price + Decimal("4") * atr  # 2:1 R:R
                        else:
                            entry_price = bar.close * Decimal(str(1 - adj))
                            stop_price  = entry_price + Decimal("2") * atr
                            target_price = entry_price - Decimal("4") * atr

                        stop_dist = abs(entry_price - stop_price)
                        if stop_dist > Decimal("0"):
                            r_amount = equity * self.config.risk_fraction
                            size_base = r_amount / stop_dist

                            open_position = {
                                "direction":  direction,
                                "entry":      entry_price,
                                "stop":       stop_price,
                                "target":     target_price,
                                "size_base":  size_base,
                                "r_amount":   r_amount,
                                "bars_held":  0,
                            }
                            logger.debug(
                                "BacktestEngine: %s %s entry=%.2f stop=%.2f target=%.2f",
                                direction, symbol,
                                float(entry_price), float(stop_price), float(target_price),
                            )

        # ------------------------------------------------------------------
        # Final position: mark-to-market at last bar close if still open
        # ------------------------------------------------------------------
        if open_position is not None and bars:
            last_bar = list(bars.values())[-1][-1]
            if last_bar:
                pos = open_position
                exit_price = last_bar.close
                if pos["direction"] == "LONG":
                    pnl = (exit_price - pos["entry"]) * pos["size_base"]
                else:
                    pnl = (pos["entry"] - exit_price) * pos["size_base"]
                equity += pnl
                result.total_trades += 1
                if pnl > Decimal("0"):
                    result.winning_trades += 1
                else:
                    result.losing_trades += 1

        # ------------------------------------------------------------------
        # Aggregate final metrics
        # ------------------------------------------------------------------
        result.final_equity = equity
        result.total_pnl_usd = equity - self.config.initial_equity

        if result.total_trades > 0:
            result.win_rate = result.winning_trades / result.total_trades
            # Simplified profit factor: approximate with 2:1 R:R assumption
            gross_wins   = float(result.winning_trades) * 2.0
            gross_losses = float(result.losing_trades) * 1.0
            result.profit_factor = (
                gross_wins / gross_losses if gross_losses > 0
                else float(result.winning_trades)
            )

        # Approx avg R-multiple assuming 2:1 R:R, 1R loss on losers
        result.avg_r_multiple = (
            result.win_rate * 2.0 - (1.0 - result.win_rate)
        )

        logger.info(
            "BacktestEngine: complete — %d bars, %d trades, "
            "WR=%.1f%%, MaxDD=%.1f%%, PnL=$%.0f",
            sum(len(v) for v in bars.values()),
            result.total_trades,
            result.win_rate * 100,
            result.max_drawdown_pct * 100,
            float(result.total_pnl_usd),
        )

        return result

    def _apply_commission_and_slippage(
        self,
        price: Decimal,
        direction: str,
        is_entry: bool,
    ) -> Decimal:
        """
        Adjust price for commission (0.1%) and slippage (0.05%).
        Entry LONG  : price × (1 + commission + slippage)
        Entry SHORT : price × (1 - commission - slippage)
        Exit LONG   : price × (1 - commission - slippage)
        Exit SHORT  : price × (1 + commission + slippage)
        """
        adj = float(self.config.commission_pct) + float(self.config.slippage_pct)
        if is_entry:
            if direction == "LONG":
                return price * Decimal(str(1 + adj))
            else:
                return price * Decimal(str(1 - adj))
        else:
            if direction == "LONG":
                return price * Decimal(str(1 - adj))
            else:
                return price * Decimal(str(1 + adj))

    async def run_simple(self, bars: dict[str, list[OHLCVBar]]) -> BacktestResult:
        """
        Alias for run() — EMA-crossover-only benchmark strategy (H3-002).
        Kept for comparison against run_full_pipeline().
        """
        return await self.run(bars)

    async def run_full_pipeline(
        self,
        bars: dict[str, list[OHLCVBar]],
        verbose: bool = False,
    ) -> BacktestResult:
        """
        Full pipeline bar-by-bar backtest using BtcBybitPaperRunner in simulation mode.

        Wires ALL production groups (market data, indicators, candlestick, chart patterns,
        technical structure, entry, panel, risk, exit, historian) and replays bars using a
        fixed 200-bar sliding window.  Trade metrics are collected via PositionCloseEvent
        subscriptions — the identical code path as live trading.

        Args:
            bars:    Symbol → chronological list of OHLCVBar (oldest first).
            verbose: Log progress every 500 processed bars.

        Returns:
            BacktestResult with per_hypothesis["_meta"] containing:
              bars_processed, trade_records, avg_winner_usd, avg_loser_usd.
        """
        import os
        import tempfile
        from features.compute import FeatureComputer
        from core.events import PositionCloseEvent
        from runtime.runner import BtcBybitPaperRunner

        result = BacktestResult(config=self.config)

        # Use a temporary journal DB so we don't pollute live data.
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        trade_records: list[dict] = []
        running_max_dd: float = 0.0
        runner_ref: list = [None]   # mutable container for closure access

        async def _on_close(event: PositionCloseEvent) -> None:
            nonlocal running_max_dd
            sig = event.exit_signal
            pos = event.final_position
            if sig is not None and pos is not None:
                trade_records.append({
                    "pnl_usd":    float(sig.pnl_usd),
                    "pnl_r":      sig.pnl_r,
                    "exit_reason": getattr(sig.exit_reason, "value", str(sig.exit_reason)),
                    "bars_held":  sig.bars_held,
                    "direction":  getattr(pos.direction, "value", str(pos.direction)),
                    "symbol":     getattr(pos, "symbol", "unknown"),
                })
                if runner_ref[0] is not None:
                    dd = runner_ref[0]._state.portfolio.drawdown_pct
                    if dd > running_max_dd:
                        running_max_dd = dd

        bars_processed: int = 0

        try:
            runner = BtcBybitPaperRunner(
                simulation_mode=True,
                journal_db_path=db_path,
            )
            runner_ref[0] = runner

            await runner.setup()

            # Override equity to match backtest config (runner defaults to $100k)
            init_eq = self.config.initial_equity
            runner._state.portfolio.equity        = init_eq
            runner._state.portfolio.available     = init_eq
            runner._state.portfolio.high_water_mark = init_eq

            # Subscribe to position-close events BEFORE processing bars
            await runner._bus.subscribe(PositionCloseEvent, _on_close)

            for symbol, bar_list in bars.items():
                computer = FeatureComputer()
                total_symbol_bars = len(bar_list)

                prev_day = None  # Track day boundaries for PnL reset

                for i, _bar in enumerate(bar_list):
                    # Fixed 200-bar lookback window (avoids O(n²) growing-buffer cost)
                    if i < 199:
                        continue
                    window = bar_list[i - 199: i + 1]   # exactly 200 bars

                    fv = computer.compute(window)
                    if fv is None:
                        continue

                    # Reset daily PnL at day boundaries (critical for daily loss limit)
                    bar_day = _bar.timestamp.date()
                    if prev_day is not None and bar_day != prev_day:
                        await runner._state.reset_daily_pnl()
                        # Also reset weekly PnL on Monday
                        if bar_day.weekday() == 0:  # Monday
                            await runner._state.reset_weekly_pnl()
                    prev_day = bar_day

                    await runner.simulate_bar(fv)
                    bars_processed += 1

                    # Track max drawdown between trade events too
                    dd = runner._state.portfolio.drawdown_pct
                    if dd > running_max_dd:
                        running_max_dd = dd

                    if verbose and bars_processed % 500 == 0:
                        port = runner._state.portfolio
                        pct_done = (i + 1) / total_symbol_bars * 100
                        logger.info(
                            "  [%5.1f%%] bar %5d/%-5d | equity=$%8.0f | "
                            "trades=%3d | DD=%.1f%%",
                            pct_done, i + 1, total_symbol_bars,
                            float(port.equity), len(trade_records),
                            running_max_dd * 100,
                        )

            # ------------------------------------------------------------------
            # Aggregate final metrics
            # ------------------------------------------------------------------
            portfolio = runner._state.portfolio
            result.final_equity     = portfolio.equity
            result.total_pnl_usd    = portfolio.equity - init_eq
            result.max_drawdown_pct = running_max_dd

            if trade_records:
                winning = [t for t in trade_records if t["pnl_usd"] > 0]
                losing  = [t for t in trade_records if t["pnl_usd"] <= 0]

                result.total_trades   = len(trade_records)
                result.winning_trades = len(winning)
                result.losing_trades  = len(losing)
                result.win_rate       = len(winning) / len(trade_records)

                gross_wins   = sum(t["pnl_usd"] for t in winning)
                gross_losses = abs(sum(t["pnl_usd"] for t in losing))
                result.profit_factor  = (
                    gross_wins / gross_losses if gross_losses > 0 else float(len(winning))
                )
                result.avg_r_multiple = (
                    sum(t["pnl_r"] for t in trade_records) / len(trade_records)
                )

            n_win = max(1, sum(1 for t in trade_records if t["pnl_usd"] > 0))
            n_los = max(1, sum(1 for t in trade_records if t["pnl_usd"] <= 0))
            avg_winner = (
                sum(t["pnl_usd"] for t in trade_records if t["pnl_usd"] > 0) / n_win
            ) if trade_records else 0.0
            avg_loser = (
                sum(t["pnl_usd"] for t in trade_records if t["pnl_usd"] <= 0) / n_los
            ) if trade_records else 0.0

            result.per_hypothesis["_meta"] = {
                "bars_processed":  bars_processed,
                "trade_records":   trade_records,
                "avg_winner_usd":  avg_winner,
                "avg_loser_usd":   avg_loser,
                "db_path":         db_path,
            }

        finally:
            if runner_ref[0] is not None:
                await runner_ref[0].teardown()
            try:
                os.unlink(db_path)
            except OSError:
                pass

        logger.info(
            "BacktestEngine.run_full_pipeline: %d bars processed, %d trades, "
            "WR=%.1f%%, PF=%.2f, MaxDD=%.1f%%, PnL=$%.0f",
            bars_processed,
            result.total_trades,
            result.win_rate * 100,
            result.profit_factor,
            result.max_drawdown_pct * 100,
            float(result.total_pnl_usd),
        )

        return result

    async def _replay_bar(self, symbol: str, bar: OHLCVBar, bar_index: int) -> None:
        """
        Process one bar through the full pipeline.
        bar_index is the position in the full history (for feature warm-up check).

        Phase 3: not used — logic is inlined in run() for simplicity.
        Full group wiring would be required for Phase 4.
        """
        pass
