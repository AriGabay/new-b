"""
Objective function for walk-forward optimization.

Scores a parameter set's performance on a FeatureVector sequence by running
the full pipeline (RuntimeReplayHarness) and computing a multi-factor score.

Factors:
  1. Expectancy (primary) — average R-multiple per trade
  2. Drawdown penalty — penalize max drawdown > threshold
  3. Trade count — penalize too few or too many trades (overfitting signal)
  4. Win rate — bonus for higher win rate
  5. Profit factor — gross profit / gross loss

The final score is a weighted combination. Higher is better.

Anti-overfitting:
  - Minimum trade count required for score to be valid
  - Drawdown penalty is asymmetric (harsh above threshold)
  - No score inflation from single lucky trades
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# Objective function weights
WEIGHT_EXPECTANCY = 0.40
WEIGHT_PROFIT_FACTOR = 0.20
WEIGHT_WIN_RATE = 0.15
WEIGHT_TRADE_COUNT = 0.10
WEIGHT_DRAWDOWN = 0.15

# Thresholds
MIN_TRADES_FOR_VALID_SCORE = 3
MAX_DRAWDOWN_THRESHOLD = 0.05  # 5% — penalty kicks in above this
IDEAL_TRADE_RATE_PER_1000_BARS = 5  # ~5 trades per 1000 bars is healthy


@dataclass
class TradeResult:
    """Result of a single trade from the replay."""
    entry_price: Decimal
    exit_price: Decimal
    direction: str         # "long" or "short"
    r_multiple: float      # PnL expressed in R-multiples
    bars_held: int
    pnl_usd: float


@dataclass
class RunMetrics:
    """Aggregated metrics from a single parameter trial run."""
    bars_run: int
    trades: list[TradeResult] = field(default_factory=list)
    positions_opened: int = 0
    positions_closed: int = 0
    final_equity: float = 100_000.0
    starting_equity: float = 100_000.0
    max_drawdown_pct: float = 0.0
    peak_equity: float = 100_000.0

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.r_multiple > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.r_multiple <= 0)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return self.wins / len(self.trades)

    @property
    def expectancy(self) -> float:
        """Average R-multiple per trade."""
        if not self.trades:
            return 0.0
        return sum(t.r_multiple for t in self.trades) / len(self.trades)

    @property
    def profit_factor(self) -> float:
        """Gross profit / gross loss. Returns inf if no losses."""
        gross_profit = sum(t.pnl_usd for t in self.trades if t.pnl_usd > 0)
        gross_loss = abs(sum(t.pnl_usd for t in self.trades if t.pnl_usd < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl_usd for t in self.trades)

    @property
    def avg_bars_held(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.bars_held for t in self.trades) / len(self.trades)

    def to_dict(self) -> dict:
        return {
            "bars_run": self.bars_run,
            "trade_count": self.trade_count,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 4),
            "expectancy": round(self.expectancy, 4),
            "profit_factor": round(min(self.profit_factor, 99.0), 4),
            "total_pnl": round(self.total_pnl, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "avg_bars_held": round(self.avg_bars_held, 1),
            "positions_opened": self.positions_opened,
            "positions_closed": self.positions_closed,
        }


@dataclass
class ObjectiveResult:
    """Result of evaluating the objective function."""
    score: float
    is_valid: bool
    reason: str
    metrics: RunMetrics
    component_scores: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 6),
            "is_valid": self.is_valid,
            "reason": self.reason,
            "metrics": self.metrics.to_dict(),
            "component_scores": {
                k: round(v, 6) for k, v in self.component_scores.items()
            },
        }


def compute_objective(metrics: RunMetrics) -> ObjectiveResult:
    """
    Compute the multi-factor objective score from run metrics.

    Returns ObjectiveResult with score (higher is better) and validity flag.
    Invalid results (too few trades) get score = -1.0.
    """
    # Validity gate: minimum trade count
    if metrics.trade_count < MIN_TRADES_FOR_VALID_SCORE:
        return ObjectiveResult(
            score=-1.0,
            is_valid=False,
            reason=f"Only {metrics.trade_count} trades, need >= {MIN_TRADES_FOR_VALID_SCORE}",
            metrics=metrics,
            component_scores={},
        )

    # Component 1: Expectancy score (0 to 1, capped)
    # 0R → 0.0, 1R → 0.5, 2R → 0.75, 3R+ → approaching 1.0
    raw_exp = metrics.expectancy
    exp_score = _sigmoid_score(raw_exp, midpoint=1.0, scale=1.5)

    # Component 2: Profit factor score
    pf = min(metrics.profit_factor, 10.0)
    pf_score = _sigmoid_score(pf, midpoint=1.5, scale=1.0)

    # Component 3: Win rate score
    # 50% → 0.5, 60% → 0.75, 40% → 0.25
    wr_score = metrics.win_rate

    # Component 4: Trade count score
    # Penalize both too few and too many trades
    if metrics.bars_run > 0:
        trades_per_1000 = (metrics.trade_count / metrics.bars_run) * 1000
    else:
        trades_per_1000 = 0
    tc_score = _trade_count_score(trades_per_1000, IDEAL_TRADE_RATE_PER_1000_BARS)

    # Component 5: Drawdown penalty
    # 0% dd → 1.0, 5% dd → 0.7, 10% dd → 0.3, 20% dd → 0.05
    dd_score = _drawdown_score(metrics.max_drawdown_pct)

    components = {
        "expectancy": exp_score,
        "profit_factor": pf_score,
        "win_rate": wr_score,
        "trade_count": tc_score,
        "drawdown": dd_score,
    }

    score = (
        WEIGHT_EXPECTANCY * exp_score
        + WEIGHT_PROFIT_FACTOR * pf_score
        + WEIGHT_WIN_RATE * wr_score
        + WEIGHT_TRADE_COUNT * tc_score
        + WEIGHT_DRAWDOWN * dd_score
    )

    return ObjectiveResult(
        score=score,
        is_valid=True,
        reason=f"Valid: {metrics.trade_count} trades, "
               f"exp={metrics.expectancy:.3f}R, "
               f"wr={metrics.win_rate:.1%}, "
               f"dd={metrics.max_drawdown_pct:.1%}",
        metrics=metrics,
        component_scores=components,
    )


def _sigmoid_score(value: float, midpoint: float, scale: float) -> float:
    """Map a raw value to [0, 1] using a sigmoid centered on midpoint."""
    x = (value - midpoint) * scale
    return 1.0 / (1.0 + math.exp(-x))


def _trade_count_score(trades_per_1000: float, ideal: float) -> float:
    """
    Score trade frequency. Peak at ideal, drops for too few or too many.
    Uses a Gaussian-like shape centered on ideal.
    """
    if trades_per_1000 <= 0:
        return 0.0
    sigma = ideal * 0.8  # width of the bell
    return math.exp(-0.5 * ((trades_per_1000 - ideal) / sigma) ** 2)


def _drawdown_score(max_dd_pct: float) -> float:
    """
    Score drawdown. 0% → 1.0, harsh penalty above threshold.
    Uses exponential decay above MAX_DRAWDOWN_THRESHOLD.
    """
    if max_dd_pct <= 0:
        return 1.0
    if max_dd_pct <= MAX_DRAWDOWN_THRESHOLD:
        # Linear decay: 0% → 1.0, threshold → 0.7
        return 1.0 - 0.3 * (max_dd_pct / MAX_DRAWDOWN_THRESHOLD)
    # Exponential decay above threshold
    excess = max_dd_pct - MAX_DRAWDOWN_THRESHOLD
    return 0.7 * math.exp(-5.0 * excess)
