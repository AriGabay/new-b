"""
Phase 6.2 — Structurally Qualified Replay Fixtures.

These fixtures are SPECIFICALLY ENGINEERED to create legitimate TechnicalStructureGroup
support/resistance qualification by including the exact price patterns the algorithm
requires:

  1. Swing-low / swing-high detection (5-bar fractal: bars[-3] is the pivot)
  2. Cluster merge: two pivots within ATR×0.5 → merge into one level
  3. touch count ≥ MIN_TOUCHES=2 → level qualifies
  4. Level survives _prune_broken_levels until the H3-005 bar
  5. Proximity check: current_close within AT_LEVEL_ATR_MULT×ATR14 of the level

Key formula from _build_ohlcv_series (from btc_replay_fixture.py):
  open[i]  = closes[i-1]
  body     = |closes[i] - closes[i-1]|
  wick     = closes[i] × wick_pct
  high[i]  = max(open,close) + body×0.3 + wick
  low[i]   = min(open,close) − body×0.3 − wick

Swing-low design rule:
  For bar[i].low < bar[i+1].low:
      (closes[i-1] - closes[i]) > (closes[i+1] - closes[i])
  i.e., the DIP INTO bar[i] must be LARGER than the RECOVERY OUT of bar[i].

Swing-high design rule (symmetric):
  For bar[i].high > bar[i+1].high:
      (closes[i] - closes[i-1]) > (closes[i] - closes[i+1])
  i.e., the APPROACH to bar[i] must be LARGER than the DEPARTURE from bar[i].

At-support design rule:
  Level price must be in [close - ATR, close] (within 1 ATR below close).
  Level must have touches ≥ 2.

Source: event_driven_runtime_replay
Phase: 6.2 Structural Fixture Validation
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


# ─── Fixture 1: W-Bottom Long (Primary) ───────────────────────────────────────

def _generate_w_bottom_long_prices(n_warmup: int = 200) -> list[float]:
    """
    Generate BTC price series designed to achieve:

      (A) TechnicalStructureGroup detects TWO swing lows near 69,800–69,900
          → they cluster merge (|69900−69800|=100 < cluster_tol≈350)
          → level.touches ≥ 2 (qualifies)

      (B) H3-005 LONG fires on the recovery bar after the W-bottom
          (EMA20≈70,500, close=70,400, full_bull alignment, ADX≥25, RSI 35–65)

      (C) Bullish Engulfing fires on the SAME recovery bar
          (prev bar bearish body=200, curr bar bullish close=70,400 ≥ prev open=70,300)

      (D) at_support=True on that bar
          (level 69,850, close 70,400, distance 550 < ATR≈662)

    Price series engineering:
    Phase 0 (0 → n_warmup):          Mild uptrend 55,000 → 65,500. Builds EMA200.
    Phase 1 (n_warmup → +30):        Strong bull run 65,500 → 72,000. full_bull forms.
    Phase 2 (+30 → +47):             W-bottom pullback. Two swing lows at 69,800/69,900.

    W-bottom bar chart (bar offsets from n_warmup+30):
      +0  71,900  ← peak decline starts
      +1  71,400
      +2  70,900
      +3  70,400
      +4  70,200  ← pre-dip
      +5  69,800  ← DIP 1 (body=400, recovery body=200→swing low confirmed at +7)
      +6  70,000  ← recovery (body=200 < 400 ✓)
      +7  70,300  ← DIP 1 confirmed as swing low; level=69,800, touches≈5
      +8  70,600
      +9  70,800  ← mini-peak
      +10 70,500
      +11 70,200  ← pre-dip 2
      +12 69,900  ← DIP 2 (body=300, cluster |69900−69800|=100<tol ✓ MERGE)
      +13 70,100  ← recovery (body=200 < 300 ✓)
      +14 70,300  ← DIP 2 confirmed; merged level=69,850, touches≥2 ✓
      +15 70,100  ← BEARISH SETUP (body=200)
      +16 70,400  ← BULLISH ENGULFING + H3-005 + at_support=True
    """
    prices: list[float] = []

    # Phase 0: mild uptrend (warmup) — builds EMA history
    for i in range(n_warmup):
        t = i / n_warmup
        base = 55000.0 + 10500.0 * t          # 55,000 → 65,500
        noise = 300.0 * math.sin(i * 0.27 + 0.5) + 150.0 * math.sin(i * 0.71 + 1.2)
        prices.append(base + noise)

    # Phase 1: strong bull run — establishes full_bull (EMA20>EMA50>EMA200)
    for i in range(30):
        t = i / 29
        base = 65500.0 + 6500.0 * t           # 65,500 → 72,000
        noise = 80.0 * math.sin(i * 0.45 + 0.3)
        prices.append(base + noise)

    # Phase 2: W-bottom pullback — precisely engineered
    # DESIGN INVARIANTS (verified analytically):
    #   DIP 1 (bar+5):   body=400, recovery(bar+6)=200 → body>recovery → swing_low ✓
    #   DIP 2 (bar+12):  body=300, recovery(bar+13)=200 → body>recovery → swing_low ✓
    #   Cluster distance: |69900-69800|=100 < cluster_tol(ATR≈700×0.5=350) → MERGE ✓
    #   Merged level: 69,850; distance to bar+16 close: 70,400−69,850=550 < ATR(≈662) ✓
    #   Bearish Engulfing at bar+16:
    #     prev(bar+15): open=70,300, close=70,100 (bearish ✓)
    #     curr(bar+16): open=70,100, close=70,400
    #       open(70,100) ≤ prev.close(70,100) ✓
    #       close(70,400) ≥ prev.open(70,300) ✓  → ENGULFS ✓
    w_bottom: list[float] = [
        71900.0,  # bar +0: pullback starts
        71400.0,  # bar +1
        70900.0,  # bar +2
        70400.0,  # bar +3
        70200.0,  # bar +4: pre-dip-1 (close; next bar opens here)
        69800.0,  # bar +5: *** DIP 1 *** open=70200, close=69800, body=400
        70000.0,  # bar +6: recovery  open=69800, close=70000, body=200 (<400 ✓)
        70300.0,  # bar +7: DIP-1 swing low CONFIRMED (bars[-3]=bar+5 when bar+7 arrives)
        70600.0,  # bar +8
        70800.0,  # bar +9: mini recovery peak
        70500.0,  # bar +10
        70200.0,  # bar +11: pre-dip-2
        69900.0,  # bar +12: *** DIP 2 *** open=70200, close=69900, body=300
        70100.0,  # bar +13: recovery  open=69900, close=70100, body=200 (<300 ✓)
        70300.0,  # bar +14: DIP-2 swing low CONFIRMED; MERGE with DIP-1 level
                  #          merged level≈69,850; count_touches≥5; qualifies ✓
        70100.0,  # bar +15: *** BEARISH SETUP *** open=70300, close=70100, body=200
        70400.0,  # bar +16: *** BULLISH ENGULFING + H3-005 + at_support ***
                  #          open=70100, close=70400 → bullish ✓
                  #          close(70400) ≥ prev.open(70300) ✓ engulfs ✓
                  #          at_support: 70400−69850=550 < ATR(≈662) ✓
                  #          H3-005: EMA20≈70500, close/EMA20≈99.86% ✓
    ]
    prices.extend(w_bottom)

    # Phase 3: brief continuation (to close out the fixture cleanly)
    for i in range(10):
        t = i / 9
        base = 70400.0 + 2000.0 * t           # 70,400 → 72,400
        prices.append(base + 60.0 * math.sin(i * 0.5))

    return prices


def get_w_bottom_long_fixture() -> ReplayFixture:
    """
    W-bottom LONG fixture for Phase 6.2 structural validation.

    Purpose: verify that TechnicalStructureGroup qualifies the double-bottom
    support level, enabling H3-005 + Bullish Engulfing co-occurrence.

    Expected bar count: ~257 (200 warmup + 30 bull + 17 W-bottom + 10 continuation)
    Expected at_support=True: bar ~246 (the engulfing bar)
    Expected co-occurrence: bar ~246 (H3-005 LONG + Bullish Engulfing)
    Expected proposal: 0–1 naturally generated
    Expected panel result: unknown (first observation)

    Source: event_driven_runtime_replay (real pipeline, no forcing)
    Phase: 6.2
    """
    prices = _generate_w_bottom_long_prices(n_warmup=200)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(
        prices, wick_pct=0.002, volume_base=1200.0, volume_noise_seed=621,
    )
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_w_bottom_long_v1",
        description=(
            f"{len(fvs)}-bar BTC W-bottom LONG structural fixture. "
            "Phase 6.2: engineered to produce TechnicalStructureGroup-qualified "
            "support level via two fractal swing lows at 69,800/69,900 (cluster merge). "
            "H3-005 LONG + Bullish Engulfing target co-occurrence at bar ~246. "
            "at_support=True engineered: level 69,850 within 550 of close 70,400 "
            "(< ATR≈662). Real pipeline, no forced approvals."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,   # observational only
        exit_expected_at_bar=None,
    )


# ─── Fixture 2: M-Top Short (Structural Probe) ────────────────────────────────

def _generate_m_top_short_prices(n_warmup: int = 200) -> list[float]:
    """
    Generate BTC price series that probes TechnicalStructureGroup resistance detection
    for H3-005 SHORT + Bearish Engulfing co-occurrence.

    Known structural constraint documented in Phase 6.1:
      - H3-005 SHORT requires full_bear (EMA20 < EMA50 < EMA200)
      - Bearish Engulfing requires at_resistance=True
      - at_resistance: resistance.price >= close AND (resistance-close) ≤ ATR

    The challenge: the Bearish Engulfing bar closes BELOW the resistance peak by
    approximately one candle body, which is ~1 ATR. This makes at_resistance
    borderline. This fixture probes whether the real system achieves co-occurrence
    under the most favourable engineered conditions.

    Architecture:
    Phase 0 (0 → n_warmup):         Uptrend 60,000 → 67,500 (builds EMA history)
    Phase 1 (n_warmup → +35):       Sharp bear decline 67,500 → 59,000
                                     Two failed bounces at 62,200 + 62,000
                                     → swing highs merge → resistance ≈ 62,100
    Phase 2 (+35 → +55):            Continued decline 59,000 → 56,000
                                     full_bear firmly established (EMA20<EMA50<EMA200)
    Phase 3 (+55 → +70):            Pullback toward EMA20 (~60,500)
                                     At peak: H3-005 SHORT probe zone
                                     Bearish Engulfing probe at resistance

    Note: At_resistance may still fail if ATR < distance at the signal bar.
    This fixture is an honest structural probe. Results are reported as evidence.
    """
    prices: list[float] = []

    # Phase 0: uptrend warmup
    for i in range(n_warmup):
        t = i / n_warmup
        base = 60000.0 + 7500.0 * t           # 60,000 → 67,500
        noise = 280.0 * math.sin(i * 0.28 + 0.6) + 130.0 * math.sin(i * 0.74 + 1.0)
        prices.append(base + noise)

    # Phase 1: sharp bear decline with two failed bounces creating resistance
    # SWING HIGH design rule: approach > departure
    #
    # Decline leg 1: 67,500 → 61,000 (12 bars, ~542/bar)
    for i in range(12):
        t = i / 12
        base = 67500.0 - 6500.0 * t
        noise = 80.0 * math.sin(i * 0.4)
        prices.append(base + noise)

    # Bounce 1: 61,000 → 62,200 (3 bars) then back
    # Approach to peak: bar +12→+14: rises 1200 total
    # Swing high at bar +14 (close=62,200), confirmed at bar +16
    # Approach: 62,200-61,000=1200 > departure (62,200-61,500=700) ✓
    bounce1: list[float] = [
        61500.0,   # bar +12: rise
        62200.0,   # bar +13: *** PEAK 1 *** (approach=1200 from 61000)
        61500.0,   # bar +14: departure=700 < approach ✓ → swing high confirmed at bar+15
        61000.0,   # bar +15: confirmation bar (bars[-3]=bar+13 confirmed as swing high)
    ]
    prices.extend(bounce1)

    # Decline leg 2: 61,000 → 60,000 (5 bars)
    for i in range(5):
        t = i / 5
        base = 61000.0 - 1000.0 * t
        noise = 50.0 * math.sin(i * 0.5)
        prices.append(base + noise)

    # Bounce 2: ~60,000 → 62,000 (3 bars) then back
    # Approach: 62,000-60,000=2000, departure: 62,000-61,200=800 < 2000 ✓
    # Swing high at bar ~+23 (close=62,000): |62000-62200|=200 < cluster_tol ✓ MERGE
    bounce2: list[float] = [
        61000.0,   # rise
        62000.0,   # bar +23ish: *** PEAK 2 *** (approach=2000 from 60000)
        61200.0,   # departure=800 < 2000 ✓
        60500.0,   # confirmation bar → swing high merged → resistance ≈ 62,100, touches≥2 ✓
    ]
    prices.extend(bounce2)

    # Continued decline: 60,500 → 56,000 (15 bars)
    for i in range(15):
        t = i / 15
        base = 60500.0 - 4500.0 * t
        noise = 60.0 * math.sin(i * 0.35 + 0.8)
        prices.append(base + noise)

    # Phase 2: deep bear, firm full_bear alignment
    for i in range(10):
        t = i / 10
        base = 56000.0 - 1000.0 * t           # 56,000 → 55,000
        noise = 40.0 * math.sin(i * 0.5)
        prices.append(base + noise)

    # Phase 3: pullback toward EMA20 (~60,000-61,000 estimated)
    # Then H3-005 SHORT probe + Bearish Engulfing at resistance probe
    for i in range(12):
        t = i / 12
        base = 55000.0 + 6500.0 * t           # 55,000 → 61,500
        noise = 50.0 * math.sin(i * 0.6 + 0.2)
        prices.append(base + noise)

    # Setup bars for Bearish Engulfing probe near EMA20 / resistance
    # Bar -1: bullish approach toward resistance
    # Bar 0: bearish engulfing — probes at_resistance
    engulf_probe: list[float] = [
        61500.0,   # pullback continues rising
        61800.0,   # approaches resistance (62,100)
        61500.0,   # *** BEARISH ENGULFING probe ***
                   # open=61800, close=61500; prev open=61500, curr.close≤prev.open ✓
                   # H3-005 SHORT: EMA20≈61,000-62,000 (est); close/EMA20≈99-100% ✓
                   # at_resistance: level≈62,100, distance=600; ATR≈900 → may be TRUE ✓
        61200.0,   # continuation
        60800.0,
    ]
    prices.extend(engulf_probe)

    return prices


def get_m_top_short_fixture() -> ReplayFixture:
    """
    M-top SHORT structural probe for Phase 6.2.

    PURPOSE: Probe whether at_resistance=True can be achieved for H3-005 SHORT.

    KNOWN LIMITATION (documented in Phase 6.1):
    The Bearish Engulfing fires when price closes BELOW the resistance, creating
    a distance of approximately 1 candle body between close and resistance.
    Whether this distance is < ATR×1.0 depends on recent volatility.

    Expected at_resistance: borderline (distance≈600-900, ATR≈700-1000)
    Expected H3-005 SHORT: likely fires if full_bear is established
    Expected co-occurrence: possible but uncertain

    Source: event_driven_runtime_replay
    Phase: 6.2 (structural probe)
    """
    prices = _generate_m_top_short_prices(n_warmup=200)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(
        prices, wick_pct=0.002, volume_base=1300.0, volume_noise_seed=622,
    )
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_m_top_short_v1",
        description=(
            f"{len(fvs)}-bar BTC M-top SHORT structural probe. "
            "Phase 6.2: two failed bounces at 62,200/62,000 create resistance "
            "via swing-high cluster merge (≈62,100). "
            "H3-005 SHORT + Bearish Engulfing probed near EMA20/resistance. "
            "at_resistance borderline: distance≈600-900 vs ATR≈700-1000. "
            "Honest structural probe — result is evidence, not assertion."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


# ─── Fixture 3: Triple-Touch Long (Qualification Verifier) ────────────────────

def _generate_triple_touch_long_prices(n_warmup: int = 200) -> list[float]:
    """
    Three-touch bull fixture — conservative structural qualification.

    Adds a THIRD dip to the W-bottom design, giving the support level 3 touches
    and greatly increasing touch count before the H3-005 window. Used as a
    high-confidence alternative when the double-bottom result is ambiguous.

    Same overall architecture as W-bottom, but with an extra dip cycle:
      DIP 1 at 69,800 (touch 1)
      DIP 2 at 69,900 (touch 2 — merges via cluster)
      DIP 3 at 69,850 (touch 3 — re-merges, strengthens level)
      Signal bar: same Bullish Engulfing + H3-005 pattern
    """
    prices: list[float] = []

    # Phase 0: warmup
    for i in range(n_warmup):
        t = i / n_warmup
        base = 55000.0 + 10500.0 * t
        noise = 280.0 * math.sin(i * 0.27 + 0.5) + 140.0 * math.sin(i * 0.71 + 1.2)
        prices.append(base + noise)

    # Phase 1: bull run
    for i in range(30):
        t = i / 29
        base = 65500.0 + 6500.0 * t
        noise = 70.0 * math.sin(i * 0.45 + 0.3)
        prices.append(base + noise)

    # Phase 2: triple-dip pullback
    triple_dip: list[float] = [
        71900.0,  # +0: pullback
        71400.0,  # +1
        70900.0,  # +2
        70400.0,  # +3
        70200.0,  # +4
        69800.0,  # +5: DIP 1 (body=400 from 70200)
        70000.0,  # +6: recovery (body=200 < 400 ✓)
        70300.0,  # +7: DIP 1 confirmed → level=69800, touches≈5
        70600.0,  # +8
        70800.0,  # +9
        70500.0,  # +10
        70200.0,  # +11
        69900.0,  # +12: DIP 2 (body=300; |69900-69800|=100 < tol ✓ MERGE)
        70100.0,  # +13: recovery (body=200 ✓)
        70300.0,  # +14: DIP 2 confirmed → merged level=69850, touches≥2 ✓
        70600.0,  # +15
        70400.0,  # +16
        70100.0,  # +17
        69850.0,  # +18: DIP 3 (body=250; |69850-69850|=0 < tol ✓ RE-MERGE)
        70050.0,  # +19: recovery (body=200 < 250 ✓)
        70250.0,  # +20: DIP 3 confirmed → touches≥3, strength↑
        70000.0,  # +21: BEARISH SETUP (body=250, open=70250, close=70000)
        70350.0,  # +22: BULLISH ENGULFING
                  #  open=70000, close=70350
                  #  prev.open=70250 → close(70350) ≥ prev.open(70250) ✓
                  #  at_support: level=69850, dist=500 < ATR ✓
                  #  H3-005: EMA20≈70400, close=70350, 99.86% ✓
    ]
    prices.extend(triple_dip)

    # Phase 3: continuation
    for i in range(8):
        t = i / 7
        base = 70350.0 + 2000.0 * t
        prices.append(base + 50.0 * math.sin(i * 0.5))

    return prices


def get_triple_touch_long_fixture() -> ReplayFixture:
    """
    Triple-touch LONG fixture — Phase 6.2 high-confidence qualifier.

    Three dips at 69,800 / 69,900 / 69,850 give the support level 3+ touches.
    Stronger qualification than double-bottom. Used to distinguish between
    'barely qualifies' and 'clearly qualifies' structural scenarios.

    Source: event_driven_runtime_replay
    Phase: 6.2
    """
    prices = _generate_triple_touch_long_prices(n_warmup=200)
    opens, highs, lows, closes, volumes = _build_ohlcv_series(
        prices, wick_pct=0.002, volume_base=1200.0, volume_noise_seed=623,
    )
    fvs = _series_to_feature_vectors(opens, highs, lows, closes, volumes)
    return ReplayFixture(
        name="btc_triple_touch_long_v1",
        description=(
            f"{len(fvs)}-bar BTC triple-touch LONG fixture. "
            "Phase 6.2: three swing-low cluster touches at 69,800/69,900/69,850. "
            "Highest structural confidence. H3-005 + Bullish Engulfing target at bar ~252. "
            "Source: event_driven_runtime_replay. Phase: 6.2."
        ),
        feature_vectors=fvs,
        entry_expected_at_bar=None,
        exit_expected_at_bar=None,
    )


# ─── Pre-analysis helpers ─────────────────────────────────────────────────────

def analyse_structure_formation(fixture: ReplayFixture) -> dict:
    """
    Pre-analysis: simulate TechnicalStructureGroup swing detection logic
    on the fixture's price series WITHOUT running the full runtime.

    Returns a dict with:
      swing_lows: list of (bar_index, price)
      swing_highs: list of (bar_index, price)
      expected_support_levels: list of (price, touches, first_bar, last_bar)
      expected_resistance_levels: list of (price, touches, first_bar, last_bar)
      at_support_estimate_bars: list of bar_indices where at_support might be True
      at_resistance_estimate_bars: list of bar_indices where at_resistance might be True
    """
    fvs = fixture.feature_vectors
    n = len(fvs)

    # Simulate OHLCV-based low/high calculation
    closes_f = [float(fv.close) for fv in fvs]
    opens_f  = [closes_f[i-1] if i > 0 else closes_f[0] for i in range(n)]

    def bar_high(i):
        o, c = opens_f[i], closes_f[i]
        body = abs(c - o)
        wick = c * 0.002
        return max(o, c) + body * 0.3 + wick

    def bar_low(i):
        o, c = opens_f[i], closes_f[i]
        body = abs(c - o)
        wick = c * 0.002
        return min(o, c) - body * 0.3 - wick

    # Detect swing lows (fractal: low[i] < low[i-2], low[i-1], low[i+1], low[i+2])
    swing_lows: list[tuple[int, float]] = []
    for i in range(2, n - 2):
        lo = bar_low(i)
        neighbors = [bar_low(i-2), bar_low(i-1), bar_low(i+1), bar_low(i+2)]
        if all(lo < nl for nl in neighbors):
            swing_lows.append((i, closes_f[i]))

    # Detect swing highs
    swing_highs: list[tuple[int, float]] = []
    for i in range(2, n - 2):
        hi = bar_high(i)
        neighbors = [bar_high(i-2), bar_high(i-1), bar_high(i+1), bar_high(i+2)]
        if all(hi > nh for nh in neighbors):
            swing_highs.append((i, closes_f[i]))

    # Estimate ATR at each bar (simplified: average of last 14 bar ranges)
    def atr_at(i):
        ranges = []
        for j in range(max(0, i-13), i+1):
            ranges.append(bar_high(j) - bar_low(j))
        return sum(ranges) / len(ranges) if ranges else 500.0

    # Cluster swing lows into support levels
    support_levels: list[dict] = []
    for bar_idx, price in swing_lows:
        tol = atr_at(bar_idx) * 0.5
        merged = False
        for lvl in support_levels:
            if abs(lvl['price'] - price) <= tol:
                lvl['price'] = (lvl['price'] + price) / 2
                lvl['touches'] += 1
                lvl['last_bar'] = bar_idx
                merged = True
                break
        if not merged:
            # Count initial touches
            tol2 = tol
            touches = sum(
                1 for j in range(max(0, bar_idx-59), bar_idx+1)
                if bar_high(j) >= price - tol2 and bar_low(j) <= price + tol2
            )
            support_levels.append({
                'price': price,
                'touches': max(touches, 1),
                'first_bar': bar_idx,
                'last_bar': bar_idx,
            })

    # Cluster swing highs into resistance levels
    resistance_levels: list[dict] = []
    for bar_idx, price in swing_highs:
        tol = atr_at(bar_idx) * 0.5
        merged = False
        for lvl in resistance_levels:
            if abs(lvl['price'] - price) <= tol:
                lvl['price'] = (lvl['price'] + price) / 2
                lvl['touches'] += 1
                lvl['last_bar'] = bar_idx
                merged = True
                break
        if not merged:
            resistance_levels.append({
                'price': price,
                'touches': 1,
                'first_bar': bar_idx,
                'last_bar': bar_idx,
            })

    # Find bars where at_support / at_resistance might be True
    at_support_bars: list[int] = []
    at_resistance_bars: list[int] = []
    for i in range(n):
        close = closes_f[i]
        atr = atr_at(i)
        prox = atr * 1.0

        qualified_supports = [lvl for lvl in support_levels
                               if lvl['price'] <= close
                               and lvl['touches'] >= 2
                               and lvl['last_bar'] < i]
        if qualified_supports:
            nearest = max(qualified_supports, key=lambda l: l['price'])
            if (close - nearest['price']) <= prox:
                at_support_bars.append(i)

        qualified_resists = [lvl for lvl in resistance_levels
                              if lvl['price'] >= close
                              and lvl['touches'] >= 2
                              and lvl['last_bar'] < i]
        if qualified_resists:
            nearest = min(qualified_resists, key=lambda l: l['price'])
            if (nearest['price'] - close) <= prox:
                at_resistance_bars.append(i)

    return {
        'fixture_name': fixture.name,
        'total_bars': n,
        'swing_lows': swing_lows,
        'swing_highs': swing_highs,
        'support_levels': support_levels,
        'resistance_levels': resistance_levels,
        'at_support_estimate_bars': at_support_bars,
        'at_resistance_estimate_bars': at_resistance_bars,
    }


def get_all_phase62_fixtures() -> list[ReplayFixture]:
    """Return all Phase 6.2 structural fixtures."""
    return [
        get_w_bottom_long_fixture(),
        get_m_top_short_fixture(),
        get_triple_touch_long_fixture(),
    ]
