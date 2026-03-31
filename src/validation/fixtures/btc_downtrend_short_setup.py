"""
BTC Downtrend / Short-Setup Fixture.

120 bars of clear BTC downtrend with EMA death cross and bearish engulfing
conditions. Price moves from ~$52,000 down to ~$41,000 (scenario bars in the
$40,000–$50,000 range requested by task 7).

Phases:
  Warmup  (220 bars): Uptrend $45,000 → $52,000 — builds EMA200, aligns EMAs bullish.
  Phase 1  (20 bars): Distribution / topping, $52,000 → $50,500.
  Phase 2  (40 bars): EMA death cross, $50,500 → $46,000.
  Phase 3  (60 bars): Extended bear, $46,000 → $41,000.

Total: 340 bars.  Scenario price range: $41,000–$52,000.

Natural entry status: NONE EXPECTED.
Reason: composite_score ceiling is 0.4875 < 0.50 (ChartPatternGroup excluded).
The death cross and bearish engulfing conditions are detectable via the analysis
helpers below, but the pipeline will not fire a CandidateTradeEvent without
ChartPatternGroup's contribution.

Bearish engulfing definition used here (adapted to open = prev_close convention):
  - Previous bar bullish:  closes[i-1] > closes[i-2]
  - Current bar bearish:   closes[i] < closes[i-1]
  - Current close below prev open:  closes[i] < closes[i-2]
  - Current body > previous body

Source: event_driven_runtime_replay
Phase: 7.0 — Task 7 fixtures
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from validation.fixtures.btc_replay_fixture import (
    ReplayFixture,
    _build_ohlcv_series,
    _series_to_feature_vectors,
    SYMBOL,
    TIMEFRAME,
    REPLAY_SOURCE,
    FIXTURE_START,
)


# ─── Price generation ─────────────────────────────────────────────────────────

def _generate_downtrend_short_prices(n_warmup: int = 220) -> list[float]:
    """
    Generate a BTC price series designed to produce a clear SHORT scenario.

    Warmup: uptrend $45,000 → $52,000  (EMA200 stabilises, full-bull alignment)
    Phase 1: distribution at top, starts the decline.
    Phase 2: EMA death cross — EMA20 crosses below EMA50.
    Phase 3: extended bear leg $46,000 → $41,000.
    """
    prices: list[float] = []

    # ── Warmup: mild uptrend, 220 bars ───────────────────────────────────────
    # EMA20 > EMA50 > EMA200 at the end of this phase.
    warmup_start, warmup_end = 45_000.0, 52_000.0
    for i in range(n_warmup):
        t = i / n_warmup
        trend = warmup_start + (warmup_end - warmup_start) * t
        noise = 200.0 * math.sin(i * 0.30 + 0.5)
        prices.append(trend + noise)

    # ── Phase 1: topping / early distribution (20 bars) ──────────────────────
    # Small decline from 52,000 → 50,500; EMAs still bullish.
    for i in range(20):
        t = i / 20
        base = 52_000.0 - (52_000.0 - 50_500.0) * t
        noise = 200.0 * math.sin(i * 0.40 + 1.5)
        prices.append(base + noise)

    # ── Phase 2: death cross (40 bars, 50,500 → 46,000) ──────────────────────
    # Sustained drop causes EMA20 to cross below EMA50 ~20 bars in.
    # Bearish engulfing opportunity engineered at bar 8 of this phase:
    #   bar[7]: small uptick (prices[N+7])
    #   bar[8]: large bearish reversal (prices[N+8] < prices[N+6])
    phase2_prices: list[float] = []
    for i in range(40):
        t = i / 40
        base = 50_500.0 - (50_500.0 - 46_000.0) * t
        noise = 250.0 * math.sin(i * 0.45 + 0.8)
        phase2_prices.append(base + noise)

    # Inject a clear bearish engulfing at index 8 of phase 2
    # index 7: force small uptick (bullish bar)
    # index 8: force large bearish bar whose close < index-7 price
    if len(phase2_prices) > 9:
        p6 = phase2_prices[6]
        phase2_prices[7] = p6 + 280.0          # small uptick → bullish bar
        phase2_prices[8] = p6 - 450.0          # close below bar[6] open → engulfing

    prices.extend(phase2_prices)

    # ── Phase 3: extended downtrend (60 bars, 46,000 → 41,000) ──────────────
    for i in range(60):
        t = i / 60
        base = 46_000.0 - (46_000.0 - 41_000.0) * t
        noise = 200.0 * math.sin(i * 0.35 + 0.3)
        prices.append(base + noise)

    return prices


# ─── Fixture builder ──────────────────────────────────────────────────────────

def get_btc_downtrend_short_fixture() -> ReplayFixture:
    """
    340-bar BTC downtrend / short-setup fixture.

    Warmup builds full-bull EMA alignment. Scenario introduces death cross and
    sustained bear trend from $52,000 to $41,000. Contains an engineered bearish
    engulfing at bar ~228 (Phase 2, bar 8).

    Natural entry not expected: composite_score ceiling 0.4875 < 0.50 threshold.
    """
    prices = _generate_downtrend_short_prices(n_warmup=220)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(prices, wick_pct=0.002)
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_downtrend_short_setup_v1",
        description=(
            "340-bar BTC downtrend scenario. Warmup builds bullish EMA alignment "
            "(45k→52k). Scenario: death cross, sustained bear leg to $41,000. "
            "Bearish engulfing engineered at ~bar 228. "
            "Price range $40,000–$52,000. "
            "Natural SHORT entry not expected (composite_score ceiling 0.4875 < 0.50 "
            "— ChartPatternGroup excluded)."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


# ─── Batch accessor ───────────────────────────────────────────────────────────

def get_all_btc_downtrend_fixtures() -> list[ReplayFixture]:
    """Return all downtrend / short-setup fixtures."""
    return [get_btc_downtrend_short_fixture()]


# ─── Analysis helpers ─────────────────────────────────────────────────────────

def analyse_fixture_for_death_cross(fixture: ReplayFixture) -> list[dict]:
    """
    Find bars where EMA20 crosses below EMA50 (death cross).

    Returns list of {bar_index, price, ema20, ema50, adx, rsi}.
    """
    crosses: list[dict] = []
    fvs = fixture.feature_vectors
    for i, fv in enumerate(fvs):
        prev_ema20 = float(fv.prev_ema20)
        prev_ema50 = float(fv.prev_ema50)
        ema20 = float(fv.ema20)
        ema50 = float(fv.ema50)
        if prev_ema20 > prev_ema50 and ema20 < ema50:
            crosses.append(
                {
                    "bar_index": i,
                    "price": float(fv.close),
                    "ema20": ema20,
                    "ema50": ema50,
                    "adx": fv.adx14,
                    "rsi": fv.rsi14,
                }
            )
    return crosses


def analyse_fixture_for_bearish_engulfing(fixture: ReplayFixture) -> list[dict]:
    """
    Find bars where a bearish engulfing pattern is present.

    Adapted definition (open = prev_close convention in synthetic fixtures):
      - Previous bar bullish: close[i-1] > open[i-1]
      - Current bar bearish:  close[i] < open[i]
      - Current body > previous body
      - Current close < previous open (engulfing)

    Returns list of {bar_index, price, prev_body, curr_body}.
    """
    patterns: list[dict] = []
    fvs = fixture.feature_vectors
    for i in range(1, len(fvs)):
        prev = fvs[i - 1]
        curr = fvs[i]
        prev_bullish = float(prev.close) > float(prev.open)
        curr_bearish = float(curr.close) < float(curr.open)
        curr_body = float(curr.candle_body)
        prev_body = float(prev.candle_body)
        engulfs = float(curr.close) < float(prev.open)
        if prev_bullish and curr_bearish and curr_body > prev_body and engulfs:
            patterns.append(
                {
                    "bar_index": i,
                    "price": float(curr.close),
                    "prev_body": prev_body,
                    "curr_body": curr_body,
                }
            )
    return patterns
