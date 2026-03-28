"""
BTC Replay Fixtures — deterministic recorded bar sequences for replay validation.

These fixtures represent fixed, reproducible BTC/USDT price scenarios
with mathematically correct indicator values computed from actual OHLCV data.

Unlike scenario_loader.py (which uses constant offsets for EMAs), these fixtures:
  - Compute EMA, RSI, ATR, BB, ADX from actual price series
  - Produce realistic indicator dynamics (crossovers, divergences, etc.)
  - Include enough historical depth for EMA200 to stabilize (200+ warmup bars)
  - Preserve realistic candlestick bodies and wicks

Source tag: event_driven_runtime_replay
Data origin: Deterministic synthetic-but-realistic BTC price scenarios.
             NOT live data. NOT random. Fully reproducible.

IMPORTANT: These fixtures are NOT equivalent to live market replay.
They demonstrate the replay infrastructure with mathematically correct
indicators, but they do NOT represent actual historical BTC prices.
The source tag 'event_driven_runtime_replay' reflects that they use
the same real runner pipeline as live replay would.

Known limitation: With ChartPatternGroup excluded, the maximum achievable
composite_score in EntryGroup is 0.4875 (below the 0.50 threshold).
Natural trade entries CANNOT fire through the unmodified Phase 3 pipeline.
See docs/replay_closed_trade_validation_report.md for analysis.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from core.schemas import FeatureVector
from validation.fixtures.indicator_engine import (
    compute_ema,
    compute_rsi,
    compute_atr,
    compute_atr_sma20,
    compute_bollinger_bands,
    compute_adx,
    compute_volume_ratio,
)

SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"
REPLAY_SOURCE = "event_driven_runtime_replay"

# Start timestamp for fixtures (deterministic, fixed)
FIXTURE_START = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@dataclass
class ReplayFixture:
    """A complete replay fixture: sequence of FeatureVectors + metadata."""
    name: str
    description: str
    feature_vectors: list[FeatureVector]
    validation_source: str = REPLAY_SOURCE
    entry_expected_at_bar: Optional[int] = None  # None = no natural entry expected
    exit_expected_at_bar: Optional[int] = None


def _build_ohlcv_series(
    prices: list[float],
    wick_pct: float = 0.003,
    volume_base: float = 1500.0,
    volume_noise_seed: int = 42,
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """
    Build OHLCV arrays from a close price series.

    Creates realistic OHLC from close prices:
    - open = previous close (simulate overnight continuity)
    - high = close + |close - open| * 0.5 + wick
    - low = close - |close - open| * 0.5 - wick
    - volume: slightly randomised around base, with impulse on large moves

    Returns (opens, highs, lows, closes, volumes).
    """
    import random
    rng = random.Random(volume_noise_seed)

    closes = prices
    n = len(closes)

    opens = []
    highs = []
    lows = []
    volumes = []

    for i in range(n):
        o = closes[i - 1] if i > 0 else closes[0]
        c = closes[i]
        body = abs(c - o)
        wick = closes[i] * wick_pct

        h = max(o, c) + body * 0.3 + wick
        l = min(o, c) - body * 0.3 - wick

        # Volume: surge on large candles
        move_pct = body / o if o > 0 else 0
        vol_mult = 1.0 + move_pct * 20 + rng.gauss(0, 0.1)
        vol = max(volume_base * vol_mult, volume_base * 0.5)

        opens.append(o)
        highs.append(h)
        lows.append(l)
        volumes.append(vol)

    return opens, highs, lows, closes, volumes


def _series_to_feature_vectors(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    start_time: datetime = FIXTURE_START,
) -> list[FeatureVector]:
    """
    Convert OHLCV series to FeatureVector list with all indicators computed.

    Returns list of FeatureVector objects, ready to feed into simulate_bar().
    """
    n = len(closes)

    # Compute all indicators
    ema20 = compute_ema(closes, 20)
    ema50 = compute_ema(closes, 50)
    ema200 = compute_ema(closes, 200)
    rsi14 = compute_rsi(closes, 14)
    atr14 = compute_atr(highs, lows, closes, 14)
    atr14_sma20 = compute_atr_sma20(atr14)
    bb_upper, bb_middle, bb_lower, bb_width, bb_width_pct = compute_bollinger_bands(closes, 20, 2)
    adx14 = compute_adx(highs, lows, closes, 14)
    vol_ratio = compute_volume_ratio(volumes, 20)

    fvs = []
    for i in range(n):
        ts = start_time + timedelta(hours=i)

        prev_ema20 = ema20[i - 1] if i > 0 else ema20[0]
        prev_ema50 = ema50[i - 1] if i > 0 else ema50[0]
        prev_rsi = rsi14[i - 1] if i > 0 else 50.0

        close_d = Decimal(str(round(closes[i], 2)))
        open_d = Decimal(str(round(opens[i], 2)))
        high_d = Decimal(str(round(highs[i], 2)))
        low_d = Decimal(str(round(lows[i], 2)))
        volume_d = Decimal(str(round(volumes[i], 2)))

        atr_d = Decimal(str(round(atr14[i], 2)))
        atr_sma_d = Decimal(str(round(atr14_sma20[i], 2)))

        body = abs(closes[i] - opens[i])
        candle_range = highs[i] - lows[i]
        body_ratio = body / candle_range if candle_range > 0 else 0.5
        upper_shadow = highs[i] - max(opens[i], closes[i])
        lower_shadow = min(opens[i], closes[i]) - lows[i]

        # Detect impulse candle: body > 2.5 × ATR is unusual
        impulse_flag = body > atr14[i] * 2.5
        # Doji: body < 5% of range
        doji_flag = body < candle_range * 0.05 if candle_range > 0 else False

        fv = FeatureVector(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            timestamp=ts,
            open=open_d,
            high=high_d,
            low=low_d,
            close=close_d,
            volume=volume_d,
            true_range=Decimal(str(round(candle_range, 2))),
            atr14=atr_d,
            atr14_sma20=atr_sma_d,
            ema20=Decimal(str(round(ema20[i], 2))),
            ema50=Decimal(str(round(ema50[i], 2))),
            ema200=Decimal(str(round(ema200[i], 2))),
            prev_ema20=Decimal(str(round(prev_ema20, 2))),
            prev_ema50=Decimal(str(round(prev_ema50, 2))),
            rsi14=float(round(rsi14[i], 2)),
            prev_rsi14=float(round(prev_rsi, 2)),
            bb_upper=Decimal(str(round(bb_upper[i], 2))),
            bb_middle=Decimal(str(round(bb_middle[i], 2))),
            bb_lower=Decimal(str(round(bb_lower[i], 2))),
            bb_width=Decimal(str(round(bb_width[i], 2))),
            bb_width_pct=float(round(bb_width_pct[i], 2)),
            adx14=float(round(adx14[i], 2)),
            volume_sma20=Decimal(str(round(volumes[i] / max(vol_ratio[i], 0.01), 2))),
            volume_ratio=float(round(vol_ratio[i], 3)),
            candle_body=Decimal(str(round(body, 2))),
            candle_range=Decimal(str(round(candle_range, 2))),
            body_ratio=float(round(body_ratio, 3)),
            upper_shadow=Decimal(str(round(upper_shadow, 2))),
            lower_shadow=Decimal(str(round(lower_shadow, 2))),
            impulse_flag=impulse_flag,
            doji_flag=doji_flag,
        )
        fvs.append(fv)

    return fvs


def _generate_bull_breakout_prices(n_warmup: int = 220) -> list[float]:
    """
    Generate a deterministic BTC price series with a bull breakout scenario.

    Phases:
      0 – n_warmup:   Ranging/slight-downtrend from 70,000 → 63,000
                      (EMA200 builds, EMA20 dips below EMA50)
      n_warmup – +50: Bounce from support, EMA20 crosses back above EMA50
      +50 – +100:     Bull trend, price rises to ~70,000
      +100 – +130:    Consolidation then target hit

    The golden cross (EMA20 crossing EMA50) occurs around bar n_warmup + 30.
    """
    prices = []

    # Phase 1: Downtrend / ranging (n_warmup bars)
    start = 70000.0
    end = 63000.0
    for i in range(n_warmup):
        t = i / n_warmup
        # Sinusoidal noise on a downward trend
        trend = start + (end - start) * t
        noise = 300.0 * math.sin(i * 0.3 + 1.5)
        prices.append(trend + noise)

    # Phase 2: Recovery from support (50 bars, from 63,000 → 66,500)
    for i in range(50):
        t = i / 50
        base = 63000.0 + (66500.0 - 63000.0) * t
        noise = 200.0 * math.sin(i * 0.5 + 0.8)
        prices.append(base + noise)

    # Phase 3: Bull run (50 bars, from 66,500 → 71,000)
    for i in range(50):
        t = i / 50
        base = 66500.0 + (71000.0 - 66500.0) * t
        noise = 150.0 * math.sin(i * 0.4)
        prices.append(base + noise)

    # Phase 4: Target overshoot + consolidation (30 bars, 71,000 → 72,500)
    for i in range(30):
        t = i / 30
        base = 71000.0 + (72500.0 - 71000.0) * t
        noise = 100.0 * math.sin(i * 0.6)
        prices.append(base + noise)

    return prices


def _generate_bear_breakdown_prices(n_warmup: int = 220) -> list[float]:
    """
    Generate a deterministic BTC price series with a bear breakdown scenario.

    Phases:
      0 – n_warmup:   Uptrend 55,000 → 68,000 (EMA builds history)
      n_warmup – +50: Distribution near 68,000, EMA20 starts dropping
      +50 – +100:     Death cross, price falls to 62,000
      +100 – +130:    Extended bear, price to 60,000
    """
    prices = []

    start = 55000.0
    end = 68000.0
    for i in range(n_warmup):
        t = i / n_warmup
        trend = start + (end - start) * t
        noise = 300.0 * math.sin(i * 0.35 + 0.5)
        prices.append(trend + noise)

    # Distribution
    for i in range(50):
        t = i / 50
        base = 68000.0 - (68000.0 - 64000.0) * t
        noise = 250.0 * math.sin(i * 0.45)
        prices.append(base + noise)

    # Bear run
    for i in range(50):
        t = i / 50
        base = 64000.0 - (64000.0 - 61000.0) * t
        noise = 150.0 * math.sin(i * 0.4)
        prices.append(base + noise)

    # Extended decline
    for i in range(30):
        t = i / 30
        base = 61000.0 - (61000.0 - 60000.0) * t
        noise = 100.0 * math.sin(i * 0.3)
        prices.append(base + noise)

    return prices


def _generate_ranging_prices(n_bars: int = 200) -> list[float]:
    """
    Generate a deterministic BTC price series with ranging/choppy market.
    No clear trend. ADX stays low. No crossovers expected.
    """
    prices = []
    center = 65000.0
    for i in range(n_bars):
        # Oscillating around 65,000 with small amplitude
        noise = 800.0 * math.sin(i * 0.15) + 400.0 * math.sin(i * 0.47 + 1.2)
        prices.append(center + noise)
    return prices


def get_bull_breakout_fixture() -> ReplayFixture:
    """
    Bull breakout fixture: 350 bars with EMA golden cross.

    EMA20 crosses EMA50 around bar 250 after a downtrend and recovery.
    Price rises from ~63,000 to ~72,000.

    Natural entry status: NONE EXPECTED
    Reason: composite_score ceiling is 0.4875 < 0.50 (ChartPatternGroup excluded).
    See docs/replay_closed_trade_validation_report.md.

    What this fixture demonstrates:
    - Bar processing through full pipeline
    - EMA golden cross conditions (bars where prev_ema20 < prev_ema50, ema20 > ema50)
    - Correct indicator computation from price history
    - IndicatorsGroup fires GroupSignalEvent with LONG signals on the cross bar
    - EntryGroup collects signals but fails composite_score threshold (0.4875 vs 0.50)
    """
    prices = _generate_bull_breakout_prices(n_warmup=220)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(prices, wick_pct=0.002)
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_bull_breakout_v1",
        description=(
            "350-bar BTC bull breakout scenario. EMA golden cross around bar 250. "
            "Demonstrates correct indicator dynamics. "
            "Natural entry not expected (composite_score ceiling 0.4875 < 0.50 threshold)."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


def get_bear_breakdown_fixture() -> ReplayFixture:
    """
    Bear breakdown fixture: 350 bars with EMA death cross.

    EMA20 crosses below EMA50 around bar 270 after an uptrend and distribution.
    Price falls from ~68,000 to ~60,000.

    Natural entry status: NONE EXPECTED (same composite_score limitation).
    """
    prices = _generate_bear_breakdown_prices(n_warmup=220)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(prices, wick_pct=0.002)
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_bear_breakdown_v1",
        description=(
            "350-bar BTC bear breakdown scenario. EMA death cross around bar 270. "
            "Demonstrates correct indicator dynamics on SHORT side. "
            "Natural entry not expected (composite_score ceiling 0.4875 < 0.50 threshold)."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


def get_ranging_fixture() -> ReplayFixture:
    """
    Ranging/choppy market: 200 bars with no clear trend.

    ADX stays low (<20). No EMA crossovers. RSI oscillates around 50.
    Validates that no false entries fire in non-trending conditions.
    """
    prices = _generate_ranging_prices(200)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(prices, wick_pct=0.0015)
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_ranging_v1",
        description=(
            "200-bar BTC ranging market. Low ADX. No EMA crossovers. "
            "Validates no false entries in choppy conditions."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


def get_all_replay_fixtures() -> list[ReplayFixture]:
    """Return all standard replay fixtures."""
    return [
        get_bull_breakout_fixture(),
        get_bear_breakdown_fixture(),
        get_ranging_fixture(),
    ]


def analyse_fixture_for_ema_crossovers(fixture: ReplayFixture) -> list[dict]:
    """
    Find bars in the fixture where EMA crossover conditions are met.
    Returns list of {bar_index, price, ema20, ema50, direction, adx}.

    Used to verify the fixture generates the expected signal conditions.
    """
    crossovers = []
    fvs = fixture.feature_vectors
    for i, fv in enumerate(fvs):
        golden = (float(fv.prev_ema20) < float(fv.prev_ema50)) and (float(fv.ema20) > float(fv.ema50))
        death = (float(fv.prev_ema20) > float(fv.prev_ema50)) and (float(fv.ema20) < float(fv.ema50))
        if golden:
            crossovers.append({
                "bar_index": i,
                "price": float(fv.close),
                "ema20": float(fv.ema20),
                "ema50": float(fv.ema50),
                "direction": "LONG (golden cross)",
                "adx": fv.adx14,
                "rsi": fv.rsi14,
            })
        elif death:
            crossovers.append({
                "bar_index": i,
                "price": float(fv.close),
                "ema20": float(fv.ema20),
                "ema50": float(fv.ema50),
                "direction": "SHORT (death cross)",
                "adx": fv.adx14,
                "rsi": fv.rsi14,
            })
    return crossovers


def analyse_fixture_composite_score_ceiling(
    fixture: ReplayFixture,
    max_candlestick_quality: float = 0.75,
) -> dict:
    """
    Compute the theoretical composite_score ceiling for each bar in the fixture.

    This documents the mathematical barrier to natural entries:
    - chart_pattern_quality = 0.0 (excluded)
    - candlestick_quality = max_candlestick_quality (best case morning star = 0.75)
    - indicator_quality = 1.0 (best case)
    - structural_alignment = 1.0 (at S/R level)
    - historian_win_rate = 0.0 (not wired in Phase 3)

    Ceiling = 0.35*0 + 0.25*max_candlestick + 0.20*1.0 + 0.10*1.0 + 0.10*0.0
    """
    ceiling = 0.25 * max_candlestick_quality + 0.20 * 1.0 + 0.10 * 1.0 + 0.10 * 0.0
    entry_threshold = 0.50
    shortfall = entry_threshold - ceiling
    return {
        "fixture_name": fixture.name,
        "total_bars": len(fixture.feature_vectors),
        "chart_pattern_quality": 0.0,
        "chart_pattern_excluded": True,
        "max_candlestick_quality": max_candlestick_quality,
        "max_indicator_quality": 1.0,
        "structural_alignment": 1.0,
        "historian_win_rate": 0.0,
        "theoretical_composite_ceiling": round(ceiling, 4),
        "entry_threshold": entry_threshold,
        "shortfall": round(shortfall, 4),
        "natural_entry_possible": ceiling >= entry_threshold,
        "reason": (
            "ChartPatternGroup EXCLUDED. Max composite_score = "
            f"0.25×{max_candlestick_quality} + 0.20×1.0 + 0.10×1.0 = {ceiling:.4f}. "
            f"Entry threshold = {entry_threshold}. "
            f"Shortfall = {shortfall:.4f}. "
            "Natural entries cannot fire in Phase 3."
        ),
    }
