"""
Established-Trend Pullback Fixtures for Phase 6.1 Observational Replay.

These fixtures are specifically designed to contain bars where H3-005 can fire:
  - Full EMA alignment (full_bull or full_bear)
  - EMA separation >= 0.2%
  - Price within 3% of EMA20 (pullback zone)
  - ADX >= 25 (established trend)
  - RSI 35-65 (pulled back from extreme)
  - Volume >= 1.0x

Unlike the original btc_replay_fixture.py (which is pure crossover-transition),
these fixtures extend past the crossover into the established-trend phase
and include deliberate pullback bars.

Critical structural constraints:
  H3-005 SHORT requires full_bear (EMA20 < EMA50).
    Candlestick SHORT patterns that DON'T conflict:
      H2-001 Bearish Engulfing (needs at_resistance=True)
      H2-002 Evening Star     (needs at_resistance=True)
    Patterns that CONFLICT with full_bear:
      H2-003 Three Black Crows (needs ema20 > ema50)
      H2-004 Inverted Hammer   (needs ema20 > ema50)
  => SHORT path requires TechnicalStructureGroup to flag at_resistance.

  H3-005 LONG requires full_bull (EMA20 > EMA50 > EMA200).
    Candlestick LONG patterns:
      H2-001 Bullish Engulfing (needs at_support=True)
      H2-002 Morning Star      (needs at_support=True)
    Minor pullbacks in bull trend create swing-low support levels → at_support more
    reliably achievable than at_resistance in a bear continuation.
  => LONG path is the primary candidate for natural proposal generation.

Source: event_driven_runtime_replay
Phase: 6.1 Observational
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from core.schemas import FeatureVector
from validation.fixtures.btc_replay_fixture import (
    ReplayFixture,
    _build_ohlcv_series,
    _series_to_feature_vectors,
    SYMBOL,
    TIMEFRAME,
    REPLAY_SOURCE,
    FIXTURE_START,
)


# ─── Fixture 1: Bull Continuation Pullback ────────────────────────────────────

def _generate_bull_continuation_pullback_prices(n_warmup: int = 220) -> list[float]:
    """
    Generate a BTC price series designed to produce H3-005 LONG signals.

    Architecture:
      Phase 0 (0 → n_warmup):       Ranging/mild-uptrend 58,000 → 64,000.
                                     EMA200 builds. EMA20/EMA50 near each other.
      Phase 1 (n_warmup → +60):     Strong bull run 64,000 → 72,000.
                                     EMA20 > EMA50 > EMA200 (full_bull).
                                     ADX rises above 30. Minor dips create swing lows.
      Phase 2 (+60 → +75):          Pullback 72,000 → 67,500.
                                     Price approaches EMA20 (~67,000) from above.
                                     2 bearish pullback bars → 1 bullish engulfing bar.
                                     RSI drops from ~72 to ~48 (enters 35-65 window).
      Phase 3 (+75 → +100):         Continuation up to 76,000.

    H3-005 LONG expected at bars n_warmup + 67 through n_warmup + 72 (pullback zone).
    Bullish engulfing expected at bar n_warmup + 72 (reversal bar).

    Target combo at pullback bottom:
      - EMA20 ≈ 67,000 | EMA50 ≈ 65,500 | EMA200 ≈ 63,000 (full_bull ✓)
      - EMA sep: (67,000 - 65,500) / 65,500 = 2.3% >> 0.2% ✓
      - price ≈ 67,200 → within 3% of EMA20: [65,090, 67,670] ✓
      - ADX ≈ 28-35 (strong bull trend) ✓
      - RSI ≈ 45-52 (pulled back from 72) ✓
    """
    prices = []

    # Phase 0: mild uptrend / ranging (warmup)
    for i in range(n_warmup):
        t = i / n_warmup
        base = 58000.0 + (64000.0 - 58000.0) * t
        noise = 400.0 * math.sin(i * 0.28 + 0.7) + 200.0 * math.sin(i * 0.73 + 1.4)
        prices.append(base + noise)

    # Phase 1: strong bull run with minor pullbacks (60 bars, 64,000 → 72,000)
    # Three sub-waves with shallow pullbacks to create swing-low support levels
    for i in range(20):
        t = i / 20
        base = 64000.0 + (67000.0 - 64000.0) * t
        # Small dip at bar 8 (creates first support level ~65,200)
        dip = -600.0 if 6 <= i <= 9 else 0.0
        noise = 120.0 * math.sin(i * 0.5)
        prices.append(base + noise + dip)

    for i in range(20):
        t = i / 20
        base = 67000.0 + (69500.0 - 67000.0) * t
        # Small dip at bar 9 (creates second support level ~67,500)
        dip = -500.0 if 7 <= i <= 10 else 0.0
        noise = 100.0 * math.sin(i * 0.55 + 1.0)
        prices.append(base + noise + dip)

    for i in range(20):
        t = i / 20
        base = 69500.0 + (72000.0 - 69500.0) * t
        # Small dip at bar 10 (creates third support level ~70,200)
        dip = -400.0 if 8 <= i <= 11 else 0.0
        noise = 80.0 * math.sin(i * 0.6 + 0.5)
        prices.append(base + noise + dip)

    # Phase 2: pullback to EMA20 (15 bars, 72,000 → 67,200)
    # Designed to bring price into H3-005 zone and produce candlestick pattern
    pullback_prices = [
        71800.0,  # bar +60: slight peak
        71200.0,  # bar +61: starts declining
        70500.0,  # bar +62: continues
        69800.0,  # bar +63
        69200.0,  # bar +64
        68500.0,  # bar +65
        68000.0,  # bar +66: approaching EMA20
        67600.0,  # bar +67: near EMA20 zone → H3-005 range starts
        67400.0,  # bar +68: fully in zone [EMA20×0.99, EMA20×1.03] (bearish bar 1)
        67250.0,  # bar +69: still in zone (bearish bar 2, RSI ~47)
        67800.0,  # bar +70: BULLISH ENGULFING — open at 67,250, close 67,800 (above prev open 67,400)
        68400.0,  # bar +71: continuation up
        69200.0,  # bar +72
        70100.0,  # bar +73
        71000.0,  # bar +74
    ]
    prices.extend(pullback_prices)

    # Phase 3: continuation up (25 bars, ~71,000 → 76,000)
    for i in range(25):
        t = i / 25
        base = 71000.0 + (76000.0 - 71000.0) * t
        noise = 150.0 * math.sin(i * 0.4 + 0.3)
        prices.append(base + noise)

    return prices


def get_bull_continuation_pullback_fixture() -> ReplayFixture:
    """
    Bull continuation pullback fixture for Phase 6.1 observational replay.

    Total bars: ~320 (220 warmup + 100 active observation)
    Expected H3-005 LONG bars: ~5-8 bars in the pullback zone (bars 285-292)
    Expected candlestick (bullish engulfing) at: bar ~290
    Expected proposal if co-occurrence confirmed: 0-1 natural proposals
    Expected panel result: unknown (depends on panel evaluation)

    Source: event_driven_runtime_replay (real pipeline, no forcing)
    """
    prices = _generate_bull_continuation_pullback_prices(n_warmup=220)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(
        prices, wick_pct=0.0018, volume_base=1200.0, volume_noise_seed=101
    )
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_bull_continuation_pullback_v1",
        description=(
            f"{len(fvs)}-bar BTC bull continuation with deliberate pullback to EMA20. "
            "Phase 6.1 observational fixture. "
            "Designed for H3-005 LONG signal occurrence in pullback zone (~bar 285-295). "
            "Bullish engulfing pattern at pullback bottom. "
            "TechnicalStructureGroup should detect support levels from 3 swing lows in bull phase. "
            "Natural entry possible IF at_support=True + H3-005 co-occur on same bar."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,  # unknown — observational only
        exit_expected_at_bar=None,
    )


# ─── Fixture 2: Bear Continuation Pullback ────────────────────────────────────

def _generate_bear_continuation_pullback_prices(n_warmup: int = 220) -> list[float]:
    """
    Generate a BTC price series designed to probe H3-005 SHORT signals.

    Architecture:
      Phase 0 (0 → n_warmup):       Uptrend 55,000 → 67,000 (build EMA history).
      Phase 1 (n_warmup → +50):     Sharp decline 67,000 → 58,000. Death cross forms.
                                     Three failed bounces create resistance levels.
      Phase 2 (+50 → +30):          Continued decline 58,000 → 53,500.
                                     EMA20 < EMA50 < EMA200 firmly established.
                                     ADX > 30.
      Phase 3 (+30 → +20):          Pullback bounce 53,500 → 56,500.
                                     Price approaches EMA20 (~56,000) from below.
                                     RSI rebounds from ~25 toward ~50.
                                     Failed bounces from Phase 1 = resistance above.
      Phase 4 (+20 → +30):          Continuation decline to 50,000.

    H3-005 SHORT expected in pullback zone where price ≈ EMA20 range.
    Bearish engulfing expected at pullback peak IF at_resistance=True.

    Note: at_resistance depends on swing highs detected by TechnicalStructureGroup
    from the failed bounces in Phase 1. These are ~3-5% above the pullback price.
    Actual firing depends on ATR proximity band.
    """
    prices = []

    # Phase 0: uptrend (warmup)
    for i in range(n_warmup):
        t = i / n_warmup
        base = 55000.0 + (67000.0 - 55000.0) * t
        noise = 350.0 * math.sin(i * 0.3 + 0.8) + 150.0 * math.sin(i * 0.72 + 0.3)
        prices.append(base + noise)

    # Phase 1: sharp decline with 3 failed bounces (50 bars, 67,000 → 58,000)
    # Bounces create resistance levels at known prices
    for i in range(18):
        t = i / 18
        base = 67000.0 - (67000.0 - 62500.0) * t
        noise = 200.0 * math.sin(i * 0.5)
        prices.append(base + noise)

    # First failed bounce: rises to 63,800 (resistance level 1)
    for i in range(6):
        t = i / 6
        base = 62500.0 + (63800.0 - 62500.0) * t
        prices.append(base)

    for i in range(10):
        t = i / 10
        base = 63800.0 - (63800.0 - 60500.0) * t
        noise = 150.0 * math.sin(i * 0.6)
        prices.append(base + noise)

    # Second failed bounce: rises to 61,500 (resistance level 2)
    for i in range(5):
        t = i / 5
        base = 60500.0 + (61500.0 - 60500.0) * t
        prices.append(base)

    for i in range(11):
        t = i / 11
        base = 61500.0 - (61500.0 - 58000.0) * t
        noise = 100.0 * math.sin(i * 0.5)
        prices.append(base + noise)

    # Phase 2: continued decline (30 bars, 58,000 → 53,500)
    for i in range(30):
        t = i / 30
        base = 58000.0 - (58000.0 - 53500.0) * t
        noise = 150.0 * math.sin(i * 0.45 + 1.2)
        prices.append(base + noise)

    # Phase 3: pullback bounce (20 bars, 53,500 → 56,500)
    # EMA20 should be ~55,500-56,500 at this point
    pullback_bounce = [
        53800.0,  # reversal start
        54300.0,
        54900.0,
        55400.0,  # entering H3-005 range if EMA20 ≈ 55,800
        55800.0,  # peak area — in H3-005 zone
        56200.0,  # still near EMA20 (bearish bar 1 — from 56,500 down)
        56500.0,  # might touch previous resistance zone
        56300.0,  # bearish bar 2 (pullback continuing)
        55900.0,  # BEARISH ENGULFING bar if at_resistance=True
        55500.0,
        55000.0,
        54500.0,
        54000.0,
        53600.0,
        53200.0,
        52800.0,
        52400.0,
        52000.0,
        51500.0,
        51000.0,
    ]
    prices.extend(pullback_bounce)

    # Phase 4: continuation decline (10 more bars to 50,000)
    for i in range(10):
        t = i / 10
        base = 51000.0 - (51000.0 - 50000.0) * t
        noise = 80.0 * math.sin(i * 0.4)
        prices.append(base + noise)

    return prices


def get_bear_continuation_pullback_fixture() -> ReplayFixture:
    """
    Bear continuation pullback fixture for Phase 6.1 observational replay.

    Total bars: ~370 (220 warmup + 150 active)
    H3-005 SHORT expected at: pullback bars where price ≈ EMA20 (~55,500-57,000)
    Bearish candlestick expected at pullback peak IF at_resistance=True
    at_resistance depends on: failed-bounce swing highs from Phase 1 vs ATR proximity

    Source: event_driven_runtime_replay (real pipeline, no forcing)
    """
    prices = _generate_bear_continuation_pullback_prices(n_warmup=220)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(
        prices, wick_pct=0.0020, volume_base=1300.0, volume_noise_seed=202
    )
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_bear_continuation_pullback_v1",
        description=(
            f"{len(fvs)}-bar BTC bear continuation with pullback to EMA20 zone. "
            "Phase 6.1 observational fixture. "
            "H3-005 SHORT probed in pullback zone. "
            "at_resistance depends on ATR proximity to swing-high resistance from failed bounces. "
            "Natural SHORT entry possible only if at_resistance=True coincides with H3-005."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


# ─── Fixture 3: Long Established Trend (no specific pullback) ─────────────────

def _generate_long_established_trend_prices(n_warmup: int = 220) -> list[float]:
    """
    300-bar established bull trend — no specific pullback engineering.
    Used to observe how many natural H3-005 bars occur in a genuine trend.

    Price: 60,000 → 78,000 over the post-warmup phase.
    Several natural oscillations that may or may not produce pullbacks.
    This is the 'honest observation' fixture — no price engineering for signals.
    """
    prices = []

    # Phase 0: build EMA history
    for i in range(n_warmup):
        t = i / n_warmup
        base = 60000.0 + (66000.0 - 60000.0) * t
        noise = 500.0 * math.sin(i * 0.25 + 0.6) + 250.0 * math.sin(i * 0.68 + 1.1)
        prices.append(base + noise)

    # Phase 1: steady bull (80 bars, 66,000 → 78,000)
    for i in range(80):
        t = i / 80
        base = 66000.0 + (78000.0 - 66000.0) * t
        # Natural oscillation — several pullbacks of varying depth
        cycle1 = 600.0 * math.sin(i * 0.18 + 0.0)   # ~35-bar wave
        cycle2 = 300.0 * math.sin(i * 0.47 + 0.8)   # ~13-bar wave
        cycle3 = 150.0 * math.sin(i * 1.2 + 0.3)    # ~5-bar wave
        prices.append(base + cycle1 + cycle2 + cycle3)

    return prices


def get_long_established_trend_fixture() -> ReplayFixture:
    """
    300-bar established bull trend — honest observation fixture.
    No deliberate price engineering for pullbacks.
    Used to measure how frequently natural H3-005 conditions arise.

    Source: event_driven_runtime_replay
    """
    prices = _generate_long_established_trend_prices(n_warmup=220)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(
        prices, wick_pct=0.0015, volume_base=1100.0, volume_noise_seed=303
    )
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_long_established_trend_v1",
        description=(
            f"{len(fvs)}-bar BTC established bull trend, honest oscillation. "
            "Phase 6.1 baseline: measures natural H3-005 occurrence rate "
            "without deliberate pullback engineering."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


# ─── Fixture analysis helpers ──────────────────────────────────────────────────

def analyse_h3005_conditions(fixture: ReplayFixture) -> list[dict]:
    """
    Analyse each bar for H3-005 trigger conditions.
    Returns list of bars that satisfy ALL H3-005 requirements.
    """
    results = []
    for i, fv in enumerate(fixture.feature_vectors):
        ema20 = float(fv.ema20)
        ema50 = float(fv.ema50)
        ema200 = float(fv.ema200)
        close = float(fv.close)

        full_bull = ema20 > ema50 > ema200
        full_bear = ema20 < ema50 < ema200

        if not (full_bull or full_bear):
            continue

        ema_sep = abs(ema50 - ema20) / ema50 if ema50 > 0 else 0.0
        if ema_sep < 0.002:
            continue
        if fv.adx14 < 25.0:
            continue
        if fv.volume_ratio < 1.0:
            continue

        rsi = fv.rsi14
        if not (35.0 < rsi < 65.0):
            continue

        if full_bull:
            price_near = (close < ema20 * 1.03) and (close >= ema20 * 0.99)
            alignment = "full_bull"
            direction = "LONG"
        else:
            price_near = (close > ema20 * 0.97) and (close <= ema20 * 1.01)
            alignment = "full_bear"
            direction = "SHORT"

        if not price_near:
            continue

        results.append({
            "bar_index": i,
            "direction": direction,
            "alignment": alignment,
            "close": close,
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
            "ema_sep_pct": round(ema_sep * 100, 2),
            "adx14": round(fv.adx14, 1),
            "rsi14": round(rsi, 1),
            "volume_ratio": round(fv.volume_ratio, 2),
            "price_near_pct": round((close / ema20 - 1) * 100, 2),
        })
    return results


def get_all_phase61_fixtures() -> list[ReplayFixture]:
    return [
        get_bull_continuation_pullback_fixture(),
        get_bear_continuation_pullback_fixture(),
        get_long_established_trend_fixture(),
    ]
