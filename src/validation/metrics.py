"""
Validation metrics — win rate, expectancy, profit factor, drawdown, Sharpe.

All functions accept lists of raw values and return None if insufficient data.
Minimum sample gates are enforced at the caller level (calibration_reporter.py).
"""
from __future__ import annotations

import math
from typing import Optional


def win_rate(outcomes: list[str]) -> Optional[float]:
    """
    Fraction of closed trades that are 'win'.
    Returns None if outcomes is empty.
    outcomes must be strings: "win" / "loss" / "breakeven"
    """
    closed = [o for o in outcomes if o in ("win", "loss", "breakeven")]
    if not closed:
        return None
    return sum(1 for o in closed if o == "win") / len(closed)


def expectancy(pnl_r_values: list[float]) -> Optional[float]:
    """
    Average R-multiple across all closed trades.
    Positive expectancy = edge exists (at this sample size).
    Returns None if empty.
    """
    if not pnl_r_values:
        return None
    return sum(pnl_r_values) / len(pnl_r_values)


def profit_factor(pnl_r_values: list[float]) -> Optional[float]:
    """
    Sum of wins / abs(sum of losses).
    Returns None if no losses or empty.
    Returns inf if wins exist but no losses.
    """
    if not pnl_r_values:
        return None
    gross_wins = sum(r for r in pnl_r_values if r > 0)
    gross_losses = abs(sum(r for r in pnl_r_values if r < 0))
    if gross_losses == 0:
        return float("inf") if gross_wins > 0 else None
    return round(gross_wins / gross_losses, 3)


def max_drawdown(equity_curve: list[float]) -> Optional[float]:
    """
    Maximum peak-to-trough drawdown as a fraction (0.0–1.0).
    Returns None if fewer than 2 data points.
    """
    if len(equity_curve) < 2:
        return None
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 4)


def sharpe_ratio(
    returns: list[float],
    risk_free: float = 0.0,
    annualize: bool = False,
    periods_per_year: int = 8760,  # hourly bars in a year
) -> Optional[float]:
    """
    Sharpe ratio of per-trade R-multiple returns.
    Returns None if fewer than 2 trades.
    annualize: if True, multiplies by sqrt(periods_per_year / n).
    """
    if len(returns) < 2:
        return None
    n = len(returns)
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    if variance <= 0:
        return None
    std = math.sqrt(variance)
    sr = (mean - risk_free) / std
    if annualize and n > 0:
        sr *= math.sqrt(periods_per_year / n)
    return round(sr, 3)


def sample_size_warning(n: int, minimum: int = 30) -> Optional[str]:
    """
    Returns a warning string if sample size is below minimum, else None.
    Used to gate calibration conclusions.
    """
    if n < minimum:
        return (
            f"INSUFFICIENT SAMPLES: {n}/{minimum} minimum. "
            "No conclusions should be drawn from these metrics."
        )
    return None


def describe(values: list[float]) -> dict:
    """
    Basic descriptive stats: count, mean, min, max, median, std.
    Returns empty dict if values is empty.
    """
    if not values:
        return {"count": 0}
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
    std = math.sqrt(variance)
    sorted_v = sorted(values)
    median = sorted_v[n // 2] if n % 2 == 1 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    return {
        "count": n,
        "mean": round(mean, 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "median": round(median, 3),
        "std": round(std, 3),
        "p25": round(sorted_v[n // 4], 3),
        "p75": round(sorted_v[3 * n // 4], 3),
    }
