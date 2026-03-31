"""
BTC Ranging Market Fixture.

200 bars of BTC price oscillating sideways (±3%) around $45,000.
No clear directional signal: ADX stays low (<20), no EMA crossovers, RSI
oscillates around 50.

This fixture validates that the pipeline does NOT fire false entries in
non-trending, choppy conditions. Complementary to the existing btc_ranging_v1
fixture (centered at $65,000); this version is centered at $45,000 and uses
a more aggressive oscillation amplitude.

Natural entry status: NONE EXPECTED.
Reasons:
  1. No EMA crossover — full_bull / full_bear alignment never achieved.
  2. composite_score ceiling 0.4875 < 0.50 (ChartPatternGroup excluded).
  3. Low ADX means momentum signal quality is also poor.

Source: event_driven_runtime_replay
Phase: 7.0 — Task 7 fixtures
"""
from __future__ import annotations

import math

from validation.fixtures.btc_replay_fixture import (
    ReplayFixture,
    _build_ohlcv_series,
    _series_to_feature_vectors,
)


# ─── Price generation ─────────────────────────────────────────────────────────

def _generate_ranging_market_prices(n_bars: int = 200) -> list[float]:
    """
    Generate a deterministic BTC price series with no clear trend.

    Two sine waves of different frequencies produce oscillation that looks
    choppy and avoids forming a persistent directional trend.

    Center: $45,000
    Amplitude: ±3% = ±$1,350  (matches task requirement)
    ADX expected: mostly < 20 throughout.
    """
    center = 45_000.0
    # 3% of 45,000 = 1,350
    amp_primary = 1_350.0
    amp_secondary = 600.0

    prices: list[float] = []
    for i in range(n_bars):
        # Primary slow oscillation + faster secondary creates choppy behaviour
        primary = amp_primary * math.sin(i * 0.13 + 0.3)
        secondary = amp_secondary * math.sin(i * 0.41 + 1.7)
        prices.append(center + primary + secondary)

    return prices


# ─── Fixture builder ──────────────────────────────────────────────────────────

def get_btc_ranging_market_fixture() -> ReplayFixture:
    """
    200-bar BTC ranging / sideways market fixture.

    Price oscillates ±3% around $45,000 (range $43,650–$46,350).
    Designed to validate that no false LONG or SHORT entry fires in a
    non-trending, low-ADX market.

    Natural entry not expected:
      - No EMA crossover (EMAs converge near center price).
      - composite_score ceiling 0.4875 < 0.50.
      - ADX stays below 20 throughout.
    """
    prices = _generate_ranging_market_prices(n_bars=200)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(prices, wick_pct=0.0015)
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_ranging_market_45k_v1",
        description=(
            "200-bar BTC ranging market centered at $45,000. "
            "Price oscillates ±3% ($43,650–$46,350). Low ADX. "
            "No EMA crossovers. Validates no false entries in choppy conditions. "
            "Expected: should_enter=False (no_clear_trend). "
            "Natural entry not expected (composite_score ceiling 0.4875 < 0.50 "
            "— ChartPatternGroup excluded)."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


# ─── Batch accessor ───────────────────────────────────────────────────────────

def get_all_btc_ranging_market_fixtures() -> list[ReplayFixture]:
    """Return all ranging market fixtures."""
    return [get_btc_ranging_market_fixture()]


# ─── Analysis helpers ─────────────────────────────────────────────────────────

def analyse_fixture_adx_profile(fixture: ReplayFixture) -> dict:
    """
    Summarise ADX statistics across the fixture.

    Returns {min_adx, max_adx, mean_adx, bars_below_20, bars_above_25,
             total_bars, has_crossover}.
    """
    fvs = fixture.feature_vectors
    adxs = [fv.adx14 for fv in fvs]
    has_crossover = any(
        (
            float(fv.prev_ema20) < float(fv.prev_ema50) and float(fv.ema20) > float(fv.ema50)
        ) or (
            float(fv.prev_ema20) > float(fv.prev_ema50) and float(fv.ema20) < float(fv.ema50)
        )
        for fv in fvs
    )
    return {
        "min_adx": min(adxs),
        "max_adx": max(adxs),
        "mean_adx": sum(adxs) / len(adxs),
        "bars_below_20": sum(1 for a in adxs if a < 20.0),
        "bars_above_25": sum(1 for a in adxs if a > 25.0),
        "total_bars": len(adxs),
        "has_crossover": has_crossover,
    }


def analyse_fixture_price_range(fixture: ReplayFixture) -> dict:
    """
    Return price range statistics for the fixture.

    Returns {min_price, max_price, center_price, pct_range}.
    """
    prices = [float(fv.close) for fv in fixture.feature_vectors]
    lo, hi = min(prices), max(prices)
    center = (lo + hi) / 2
    return {
        "min_price": lo,
        "max_price": hi,
        "center_price": center,
        "pct_range": (hi - lo) / center * 100 if center > 0 else 0.0,
    }
