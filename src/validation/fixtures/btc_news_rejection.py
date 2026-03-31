"""
BTC News-Rejection Fixture.

80 bars of normal BTC price action followed by a high-impact macro event
represented as a series of extreme impulse candles (body > 2.5 × ATR14),
then 12 bars of volatile aftermath.

Total scenario: 100 bars (within a 320-bar fixture incl. 220-bar warmup).

Background — NewsMacroGroup exclusion:
  NewsMacroGroup raises NotImplementedError in the current runtime and is
  excluded by BtcBybitPaperRunner.  There is therefore NO macro-event gate in
  the live pipeline.  This fixture documents the IMPULSE-CANDLE proxy: when
  bars have impulse_flag=True (body > 2.5 × ATR14), the pipeline DOES fire
  entries if other EMA/RSI conditions happen to align during the spike.

Known pipeline gap documented by this fixture:
  - Extreme impulse candles (news events) CAN trigger entries in the current
    pipeline because NewsMacroGroup is excluded.
  - A production system would suppress these via a macro-event awareness gate.

What this fixture validates:
  1. impulse_flag=True fires correctly on extreme candles (body > 2.5×ATR14).
  2. The pipeline processes all 320 bars without error or crash.
  3. The impulse cluster produces detectable impulse bars via analysis helpers.
  4. The maximum single-bar move exceeds 5% (news-event severity check).

Expected behaviour:
  - Pipeline runs all 320 bars without error.
  - impulse_flag=True on ≥1 news-cluster bar.
  - Entries MAY fire on impulse bars (known gap — no NewsMacroGroup gate).

Price design:
  Warmup  (220 bars): flat oscillation around $45,000 — all EMAs converge.
  Normal  (80 bars):  tight ranging ±400 around $45,000.
  News    (5 bars):   massive alternating impulse moves: ±$3,000–$4,500.
  Aftermath (15 bars): elevated but subsiding volatility, mean-reverting.

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


# ─── Constants ────────────────────────────────────────────────────────────────

# ATR on the warmup bars is approximately $400–$600.
# To guarantee impulse_flag = body > 2.5 × ATR ≈ $1,500, news moves are $3,000+.
_NEWS_BAR_MOVES = [3_200.0, -4_400.0, 3_800.0, -3_000.0, 2_600.0]

_NORMAL_CENTER = 45_000.0
_WARMUP_CENTER = 45_000.0


# ─── Price generation ─────────────────────────────────────────────────────────

def _generate_news_rejection_prices(n_warmup: int = 220) -> list[float]:
    """
    Generate BTC price series with an impulse-cluster news proxy.

    Warmup  (n_warmup bars): FLAT oscillation around 45,000  — no trend,
                             all EMAs converge to ~45,000.
    Normal  (80 bars):       tight ranging ±400 around 45,000, no crossover.
    News    (5 bars):        extreme alternating impulse moves (net-neutral
                             direction: +3,200 -4,400 +3,800 -3,000 +2,600
                             ≈ net +2,200 total, deliberately muted by the
                             aftermath return path so no sustained new trend
                             forms).
    Aftermath (15 bars):     choppy, elevated volatility, mean-reverting to
                             45,000.

    Design goal: no EMA crossover before bar 300 (news cluster start).  The
    impulse moves trigger impulse_flag=True on several bars but do NOT produce
    a clean aligned setup for EntryGroup to score above the threshold.
    """
    prices: list[float] = []

    # ── Warmup: flat oscillation around 45,000 ────────────────────────────────
    # Two low-amplitude sine waves keep EMAs pinned near 45,000.
    # Avoids any sustained slope that would form a death/golden cross.
    for i in range(n_warmup):
        primary   = 300.0 * math.sin(i * 0.11 + 0.5)
        secondary = 150.0 * math.sin(i * 0.37 + 1.3)
        prices.append(_WARMUP_CENTER + primary + secondary)

    # ── Normal pre-news bars (80 bars): tight ranging ─────────────────────────
    # Amplitude deliberately small (±400) so no crossover fires.
    for i in range(80):
        primary   = 400.0 * math.sin(i * 0.14 + 0.9)
        secondary = 180.0 * math.sin(i * 0.39 + 2.1)
        prices.append(_NORMAL_CENTER + primary + secondary)

    # ── News event cluster (5 bars) ───────────────────────────────────────────
    # Each bar applies a large absolute price change from the previous close.
    # These produce body >> 2.5 × ATR14, triggering impulse_flag=True.
    # Moves alternate up/down to prevent a clean directional breakout.
    for move in _NEWS_BAR_MOVES:
        prices.append(prices[-1] + move)

    # ── Volatile aftermath (15 bars) ──────────────────────────────────────────
    # Settles back towards ~45,000 with decreasing amplitude.
    aftermath_start = prices[-1]
    for i in range(15):
        t = i / 15
        trend = aftermath_start + (_NORMAL_CENTER - aftermath_start) * t
        # Amplitude decays as the market processes the news
        amplitude = 900.0 * (1.0 - t * 0.6)
        noise = amplitude * math.sin(i * 0.55 + 2.1)
        prices.append(trend + noise)

    return prices


# ─── Fixture builder ──────────────────────────────────────────────────────────

def get_btc_news_rejection_fixture() -> ReplayFixture:
    """
    320-bar BTC news-rejection fixture.

    80 bars of normal action followed by 5 extreme impulse candles (macro event
    proxy) and 15 bars of volatile aftermath.  The impulse cluster triggers
    impulse_flag=True on multiple consecutive bars.

    Natural entry not expected:
      - No EMA crossover + ADX conditions met simultaneously.
      - composite_score ceiling 0.4875 < 0.50.
      - Impulse bars disrupt indicator alignment.

    NOTE: NewsMacroGroup is EXCLUDED in BtcBybitPaperRunner (raises
    NotImplementedError). Macro-event awareness is therefore not active in the
    pipeline.  This fixture tests the IMPULSE PROXY path — extreme volatility
    preventing entry — rather than a calendar-based news block.
    """
    prices = _generate_news_rejection_prices(n_warmup=220)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(prices, wick_pct=0.002)
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_news_rejection_v1",
        description=(
            "320-bar BTC news-rejection fixture (impulse proxy). "
            "80 stable bars + 5 extreme impulse candles + 15-bar aftermath. "
            "Impulse cluster: ±$3,000–$4,500 moves → impulse_flag=True. "
            "Price range ~$40,000–$50,000. "
            "NewsMacroGroup is EXCLUDED from runner (NotImplementedError). "
            "Known pipeline gap: entries MAY fire on news impulse bars because "
            "no macro-event gate is active. "
            "Fixture documents impulse detection and pipeline robustness, "
            "not entry suppression."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


# ─── Batch accessor ───────────────────────────────────────────────────────────

def get_all_btc_news_rejection_fixtures() -> list[ReplayFixture]:
    """Return all news-rejection fixtures."""
    return [get_btc_news_rejection_fixture()]


# ─── Analysis helpers ─────────────────────────────────────────────────────────

def analyse_fixture_impulse_bars(fixture: ReplayFixture) -> list[dict]:
    """
    Find bars where impulse_flag=True.

    Returns list of {bar_index, price, body, atr14, body_to_atr_ratio}.
    """
    impulse_bars: list[dict] = []
    for i, fv in enumerate(fixture.feature_vectors):
        if fv.impulse_flag:
            atr = float(fv.atr14)
            body = float(fv.candle_body)
            impulse_bars.append(
                {
                    "bar_index": i,
                    "price": float(fv.close),
                    "body": body,
                    "atr14": atr,
                    "body_to_atr_ratio": body / atr if atr > 0 else 0.0,
                }
            )
    return impulse_bars


def analyse_fixture_news_cluster(
    fixture: ReplayFixture,
    n_warmup: int = 220,
    n_normal: int = 80,
) -> dict:
    """
    Return statistics about the news-event cluster.

    The cluster starts at bar  n_warmup + n_normal  and spans 5 bars.

    Returns {cluster_start_bar, cluster_bars, impulse_count_in_cluster,
             max_single_move_pct, pre_news_adx, post_news_adx}.
    """
    fvs = fixture.feature_vectors
    cluster_start = n_warmup + n_normal
    cluster_end = cluster_start + len(_NEWS_BAR_MOVES)

    cluster_bars = fvs[cluster_start:cluster_end]
    pre_bar = fvs[cluster_start - 1] if cluster_start > 0 else None
    post_bar = fvs[cluster_end] if cluster_end < len(fvs) else None

    impulse_count = sum(1 for b in cluster_bars if b.impulse_flag)

    moves_pct: list[float] = []
    for i in range(cluster_start, min(cluster_end, len(fvs))):
        if i > 0:
            prev_close = float(fvs[i - 1].close)
            curr_close = float(fvs[i].close)
            if prev_close > 0:
                moves_pct.append(abs(curr_close - prev_close) / prev_close * 100)

    return {
        "cluster_start_bar": cluster_start,
        "cluster_bars": len(cluster_bars),
        "impulse_count_in_cluster": impulse_count,
        "max_single_move_pct": max(moves_pct) if moves_pct else 0.0,
        "pre_news_adx": pre_bar.adx14 if pre_bar else 0.0,
        "post_news_adx": post_bar.adx14 if post_bar else 0.0,
    }
