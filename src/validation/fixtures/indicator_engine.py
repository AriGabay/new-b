"""
Pure Python indicator computation from OHLCV data.

Used by replay fixtures to compute mathematically correct indicator
values from deterministic price series. No numpy dependency.

All computations match the conventions used by the production groups:
  - EMA: exponential moving average with standard alpha = 2/(period+1)
  - RSI: Wilder's smoothing method
  - ATR: Wilder's smoothed True Range
  - Bollinger Bands: SMA ± 2σ
  - ADX: simplified 14-period directional index
  - Volume ratio: volume / rolling_sma(volume, 20)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional


def compute_ema(prices: list[float], period: int) -> list[float]:
    """
    Compute EMA for all bars. Returns list same length as prices.
    Seeds with SMA of first `period` bars, then applies EMA formula.

    Args:
        prices: Price series (floats)
        period: EMA period (e.g., 20, 50, 200)

    Returns:
        List of EMA values. First (period-1) values are NaN-seeded
        but practically: seed = avg of first `period` prices, then EMA rolls.
    """
    if not prices:
        return []

    k = 2.0 / (period + 1)
    result = []

    # Seed with simple average of first `period` values (or all available)
    seed_n = min(period, len(prices))
    seed = sum(prices[:seed_n]) / seed_n
    result.append(seed)

    for price in prices[1:]:
        result.append(price * k + result[-1] * (1.0 - k))

    return result


def compute_rsi(prices: list[float], period: int = 14) -> list[float]:
    """
    Compute RSI using Wilder's smoothing.
    Returns list same length as prices. First `period` values set to 50.0.
    """
    if len(prices) <= period:
        return [50.0] * len(prices)

    gains = []
    losses = []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # First RSI from simple average over first `period` gains/losses
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi_values = [50.0] * (period + 1)  # pad for alignment with prices

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss < 1e-10:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100.0 - 100.0 / (1.0 + rs))

    return rsi_values


def compute_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """
    Compute ATR(period) using Wilder's smoothing.
    Returns list same length as closes. First value = high - low.
    """
    if not closes:
        return []

    true_ranges = []
    for i in range(len(closes)):
        if i == 0:
            true_ranges.append(highs[0] - lows[0])
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            true_ranges.append(tr)

    # Seed ATR with SMA of first `period` TRs (standard Wilder ATR initialization)
    seed_n = min(period, len(true_ranges))
    seed_atr = sum(true_ranges[:seed_n]) / seed_n
    atr = [seed_atr]
    for i in range(1, len(true_ranges)):
        atr.append((atr[-1] * (period - 1) + true_ranges[i]) / period)

    return atr


def compute_atr_sma20(atr_values: list[float]) -> list[float]:
    """
    Compute 20-period SMA of ATR values.
    First 19 values use partial windows.
    """
    result = []
    for i in range(len(atr_values)):
        window = atr_values[max(0, i - 19): i + 1]
        result.append(sum(window) / len(window))
    return result


def compute_bollinger_bands(
    prices: list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """
    Compute Bollinger Bands.

    Returns (upper, middle, lower, bb_width, bb_width_pct) as lists.
    bb_width = upper - lower
    bb_width_pct = (upper - lower) / middle * 100
    """
    import math

    n = len(prices)
    upper = []
    middle = []
    lower = []
    bb_width = []
    bb_width_pct = []

    for i in range(n):
        window = prices[max(0, i - period + 1): i + 1]
        m = sum(window) / len(window)
        variance = sum((p - m) ** 2 for p in window) / len(window)
        std = math.sqrt(variance)
        u = m + std_dev * std
        l = m - std_dev * std
        w = u - l
        pct = (w / m * 100.0) if m > 0 else 0.0
        upper.append(u)
        middle.append(m)
        lower.append(l)
        bb_width.append(w)
        bb_width_pct.append(pct)

    return upper, middle, lower, bb_width, bb_width_pct


def compute_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """
    Simplified ADX computation.
    Returns list same length as closes.
    """
    if len(closes) < period + 1:
        return [15.0] * len(closes)

    n = len(closes)
    dm_plus = []
    dm_minus = []

    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        dm_plus.append(max(up_move, 0.0) if up_move > down_move else 0.0)
        dm_minus.append(max(down_move, 0.0) if down_move > up_move else 0.0)

    atr_vals = compute_atr(highs, lows, closes, period)

    # Wilder smoothing with SUM seed — standard method for both DM and ATR.
    # Both DM and ATR use identical formula so their ratio (DI) stays in 0-100.
    def smooth_wilder(values: list[float]) -> list[float]:
        seed_n = min(period, len(values))
        result = [sum(values[:seed_n])]  # SUM seed (Wilder convention)
        for v in values[seed_n:]:
            result.append(result[-1] * (period - 1) / period + v)
        return result

    sdm_plus = smooth_wilder(dm_plus)
    sdm_minus = smooth_wilder(dm_minus)

    # Smooth ATR using same Wilder method as DM (SUM seed) for proper DI ratio
    # Compute TR separately here (consistent with dm_plus/dm_minus length)
    true_ranges_for_adx = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges_for_adx.append(tr)
    smoothed_atr = smooth_wilder(true_ranges_for_adx[1:])  # skip first (no prev_close)

    di_plus = []
    di_minus = []
    min_len = min(len(sdm_plus), len(sdm_minus), len(smoothed_atr))
    for i in range(min_len):
        atr_i = smoothed_atr[i]
        dp = 100.0 * sdm_plus[i] / atr_i if atr_i > 0 else 0.0
        dm = 100.0 * sdm_minus[i] / atr_i if atr_i > 0 else 0.0
        # Cap DI values at 100 (edge cases with extreme moves)
        di_plus.append(min(dp, 100.0))
        di_minus.append(min(dm, 100.0))

    dx = []
    for dp, dm in zip(di_plus, di_minus):
        total = dp + dm
        if total < 1e-10:
            dx.append(0.0)
        else:
            dx.append(100.0 * abs(dp - dm) / total)

    # Smooth DX to get ADX using running-average form: ADX = (prev×(N-1) + DX) / N
    # This is different from the SUM-accumulating smooth_wilder used for DM+/DM-.
    # ADX must stay in [0, 100]; accumulating sum would blow up.
    seed_n = min(period, len(dx))
    if seed_n == 0:
        adx_vals: list[float] = []
    else:
        adx_seed = sum(dx[:seed_n]) / seed_n  # avg seed (not sum)
        adx_vals = [adx_seed]
        for d in dx[seed_n:]:
            adx_vals.append((adx_vals[-1] * (period - 1) + d) / period)

    # Align with original length (pad front with 15.0)
    pad = n - len(adx_vals)
    return [15.0] * pad + adx_vals


def compute_volume_ratio(volumes: list[float], period: int = 20) -> list[float]:
    """
    Compute volume ratio = volume / SMA(volume, period).
    """
    result = []
    for i in range(len(volumes)):
        window = volumes[max(0, i - period + 1): i + 1]
        avg = sum(window) / len(window)
        result.append(volumes[i] / avg if avg > 0 else 1.0)
    return result
