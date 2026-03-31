"""
PerformanceMetrics: compute backtest and live performance statistics.

Used by:
  - BacktestEngine (after replay)
  - PerformanceJournalGroup (ongoing live metrics)
  - HypothesisValidator (gate checks)

All computations are deterministic, stateless, unit-testable.

Statistical testing:
  - Bonferroni correction for 25 hypotheses: p_threshold = 0.05 / 25 = 0.002
  - Bootstrap resampling for confidence intervals (Phase 3).
  - OOS retention: recent_metric >= 0.60 × in_sample_metric.

Source: /docs/learning_system/learning_contract.md
        /docs/adr/ADR-004-validation-gates-before-live-promotion.md
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

# Bonferroni correction: 25 hypotheses, family-wise error rate 0.05
NUM_HYPOTHESES         = 25
ALPHA_FAMILYWISE       = 0.05
BONFERRONI_THRESHOLD   = ALPHA_FAMILYWISE / NUM_HYPOTHESES   # 0.002

# Gate 1 thresholds (in-sample)
GATE1_MIN_PROFIT_FACTOR = 1.2
GATE1_MIN_WIN_RATE      = 0.45
GATE1_MAX_DRAWDOWN      = 0.30
GATE1_MIN_TRADES        = 30

# Gate 2 thresholds (OOS)
GATE2_MIN_PROFIT_FACTOR = 1.15
GATE2_OOS_RETENTION     = 0.60   # OOS metric must be >= 60% of IS metric
GATE2_MIN_TRADES        = 20


@dataclass
class TradeRecord:
    """Minimal trade record for metric computation (from JournalDB query)."""
    trade_id:       str
    hypothesis_id:  str
    pnl_usd:        float
    pnl_r:          float
    outcome:        str   # "win" | "loss" | "breakeven"
    bars_held:      int


@dataclass
class HypothesisMetrics:
    """Full metric set for one hypothesis over a set of trades."""
    hypothesis_id:    str
    total_trades:     int = 0
    winning_trades:   int = 0
    losing_trades:    int = 0
    win_rate:         float = 0.0
    profit_factor:    float = 0.0
    avg_r_multiple:   float = 0.0
    avg_bars_held:    float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio:     float = 0.0
    total_pnl_r:      float = 0.0
    sample_size_ok:   bool = False   # >= GATE1_MIN_TRADES
    gate1_passed:     bool = False
    gate2_passed:     bool = False


class PerformanceMetrics:
    """
    Stateless performance metric calculator.

    Usage:
        metrics = PerformanceMetrics()
        result = metrics.compute(trades, hypothesis_id="H1-001")
    """

    def compute(
        self,
        trades: list[TradeRecord],
        hypothesis_id: str,
        initial_equity: float = 1_000.0,  # Capital: $1,000 with 10x leverage = $10,000 notional
    ) -> HypothesisMetrics:
        """
        Compute full metric set from a list of closed trades.
        Returns HypothesisMetrics with gate flags set.
        """
        raise NotImplementedError("PerformanceMetrics.compute() — Phase 2 implementation pending")

    def compute_profit_factor(self, trades: list[TradeRecord]) -> float:
        """
        Profit factor = gross profit / gross loss.
        Returns float('inf') if no losing trades.
        Returns 0.0 if no trades.
        """
        raise NotImplementedError("Phase 2 pending")

    def compute_win_rate(self, trades: list[TradeRecord]) -> float:
        """Win rate = winning trades / total trades."""
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.outcome == "win")
        return wins / len(trades)

    def compute_max_drawdown(
        self,
        trades: list[TradeRecord],
        initial_equity: float,
    ) -> float:
        """
        Compute max drawdown from equity curve.
        Equity curve built from sequential PnL (assumes trades in order).
        Returns drawdown as a positive fraction (e.g., 0.15 = 15%).
        """
        raise NotImplementedError("Phase 2 pending")

    def compute_sharpe(
        self,
        pnl_series: list[float],
        risk_free_rate: float = 0.04,
        periods_per_year: int = 252,
    ) -> float:
        """
        Annualized Sharpe ratio from daily PnL series.
        Sharpe = (mean_return − risk_free) / std_return × sqrt(periods_per_year)
        Returns 0.0 if std is 0 or fewer than 2 observations.
        """
        raise NotImplementedError("Phase 2 pending")

    def check_gate1(self, metrics: HypothesisMetrics) -> bool:
        """
        Gate 1 (IS backtest → Shadow) criteria:
        - profit_factor > 1.2
        - win_rate > 45%
        - max_drawdown < 30%
        - total_trades >= 30
        """
        return (
            metrics.total_trades >= GATE1_MIN_TRADES
            and metrics.profit_factor > GATE1_MIN_PROFIT_FACTOR
            and metrics.win_rate > GATE1_MIN_WIN_RATE
            and metrics.max_drawdown_pct < GATE1_MAX_DRAWDOWN
        )

    def check_gate2(
        self,
        oos_metrics: HypothesisMetrics,
        is_metrics: HypothesisMetrics,
    ) -> bool:
        """
        Gate 2 (OOS backtest + shadow → Live) criteria:
        - OOS profit_factor > 1.15
        - OOS trades >= 20
        - OOS profit_factor >= 0.60 × IS profit_factor (OOS retention)
        - p-value < 0.002 (Bonferroni) — Phase 3 statistical test
        """
        if oos_metrics.total_trades < GATE2_MIN_TRADES:
            return False
        if oos_metrics.profit_factor < GATE2_MIN_PROFIT_FACTOR:
            return False
        if is_metrics.profit_factor > 0 and (
            oos_metrics.profit_factor < GATE2_OOS_RETENTION * is_metrics.profit_factor
        ):
            return False
        return True

    def check_oos_retention(
        self,
        oos_metric: float,
        is_metric: float,
    ) -> bool:
        """
        OOS retention: oos_metric must be >= 60% of is_metric.
        If is_metric == 0: returns True (no degradation possible from zero).
        """
        if is_metric <= 0:
            return True
        return oos_metric >= GATE2_OOS_RETENTION * is_metric
