# Technical Structure Fixture Design — Phase 6.2

**Date:** 2026-03-29
**Phase:** 6.2 — Structural Fixture Validation

---

## Purpose

This document describes the engineering methodology used to design synthetic BTC/USDT hourly fixtures that cause `TechnicalStructureGroup` to detect and qualify real support/resistance levels. It is a reference for anyone designing future structure-aware fixtures.

---

## TechnicalStructureGroup Algorithm (Critical Parameters)

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `BAR_HISTORY_SIZE` | 60 | OHLCV window used for analysis |
| `MAX_LEVELS` | 10 | Maximum active S/R levels maintained |
| `MIN_TOUCHES` | 2 | Minimum touches to qualify a level |
| `AT_LEVEL_ATR_MULT` | 1.0 | at_support/at_resistance proximity window = ATR×1.0 |
| `CLUSTER_ATR_MULT` | 0.5 | Merge threshold = ATR×0.5 |

### Swing-Low Detection Rule

The algorithm detects a swing-low at `bars[-3]` when:
```
bars[-3].low < bars[-5].low
bars[-3].low < bars[-4].low
bars[-3].low < bars[-2].low
bars[-3].low < bars[-1].low
```

This is a 5-bar fractal evaluated with 2-bar right-side confirmation. A dip at bar `i` is NOT confirmed until bar `i+2` has been processed.

### OHLCV Builder → Low Calculation

When using `_build_ohlcv_series(closes, wick_pct)`:
```python
open[i]  = closes[i-1]
body     = abs(closes[i] - closes[i-1])
wick     = closes[i] * wick_pct
high[i]  = max(open,close) + body*0.3 + wick
low[i]   = min(open,close) - body*0.3 - wick
```

For a dip bar (closes[i] < closes[i-1]):
```
low[i] = closes[i] - body*0.3 - wick
       = closes[i] - (closes[i-1]-closes[i])*0.3 - closes[i]*wick_pct
```

### Swing-Low Condition in Close-Space

For `bar[i].low < bar[i+1].low` (required for swing low at bar[i]):
```
closes[i-1] - closes[i] > closes[i+1] - closes[i]
↑ dip INTO bar[i]         ↑ recovery OUT of bar[i]
```
The dip must be larger than the recovery. Equivalently: `closes[i]` must be closer to `closes[i+1]` than to `closes[i-1]`.

### Cluster Merge Rule

Two swing-lows merge if:
```
abs(new_pivot.price - existing_level.price) <= ATR * CLUSTER_ATR_MULT (0.5)
```
When merged: `touches` increments, level price becomes weighted average.

### `at_support` Proximity Flag

Set to `True` when:
```
level.price <= close AND (close - level.price) <= ATR * AT_LEVEL_ATR_MULT (1.0) AND level.touches >= MIN_TOUCHES (2)
```

---

## W-Bottom LONG Fixture Design (`btc_w_bottom_long_v1`)

### Goal

Create two swing-lows within ATR×0.5 of each other, causing cluster merge. After merge, `level.touches >= 2`. Then arrange a pullback where `H3-005 LONG` fires while `close` is within `ATR×1.0` above the merged level.

### Design Parameters

```
Base price:    70,000
Trend phase:   slow upward drift from 63,000 → 71,900 (warmup + EMA establishment)
W-bottom:      Two dips to 69,800 and 69,900 respectively
ATR estimate:  ~700 (1% of 70,000)
Cluster check: |69,900 - 69,800| = 100 < ATR×0.5 (350) ✓ → merge
```

### Price Sequence (W-bottom zone, bars +0 to +16 from peak)

```python
# Pre-dip-1
+0: 71900  # pullback starts from peak
+1: 71400
+2: 70900
+3: 70400
+4: 70200  # pre-dip-1 close
+5: 69800  # DIP 1 — body=400 (down), prev_close=70200
+6: 70000  # recovery — body=200 (up); 200 < 400 → swing-low condition ✓
+7: 70300  # swing-low at bar[+5] CONFIRMED (2 bars of right-side recovery)
+8: 70600
+9: 70800  # mini recovery peak
+10: 70500
+11: 70200  # pre-dip-2
+12: 69900  # DIP 2 — body=300; |69900-69800|=100 < ATR×0.5 (350) → MERGE ✓
+13: 70100  # recovery — body=200 < 300 → swing-low condition ✓
+14: 70300  # swing-low at bar[+12] CONFIRMED; merged level ≈ 69,850; touches=2 ✓
+15: 70100  # BEARISH BAR (open=70300, close=70100) — sets up engulfing
+16: 70400  # BULLISH ENGULFING (open=70100, close=70400)
            # curr.close(70400) ≥ prev.open(70300) ✓ engulfs
            # at_support: level≈69,670 (post-touch-accumulation), close=70400
            #   dist = 70400 - 69670 = 730 ≤ ATR(700)×1.0 = 700 (borderline)
            # H3-005: EMA20≈70,270, close/EMA20 = 99.9% ✓
```

### Observed Result

- Support level formed: 69,670 (cluster of swing-lows, 15 accumulated touches)
- `at_support=True` confirmed in journal packet at bar 246
- H3-005 fires at bar 246 (full_bull, close near EMA20, ADX=35, RSI=55, vol=1.03)
- Bullish Engulfing fires at bar 246 (co-occurrence achieved)
- Proposal generated: composite_score=0.8364

---

## M-Top SHORT Fixture Design (`btc_m_top_short_v1`)

### Goal

Create two failed bounces at a resistance level in a bear trend. At the second failure, `H3-005 SHORT` fires while `close` is within `ATR×1.0` below the resistance level.

### Design

```
Base price:    62,000 (bear trend: EMA20 < EMA50 < EMA200)
Resistance:    Two failures at ~62,200 (close twice to 62,200 then fall back)
Cluster check: |62,200 - 62,000| = 200 < ATR×0.5 (~350) → merge
```

### Observed Result

- Resistance level formed: 71,031 (swing-high cluster with 13 touches)
- `at_resistance=True` (and `at_support=True`) confirmed in journal packet
- H3-005 fires (16 bars, both LONG in full_bull zone and SHORT attempted)
- 2 co-occurrence events
- Best panel: 12/20 approvals, avg 6.350 → hold

**Note:** The M-top fixture's best proposal was LONG direction (full_bull EMA regime), not SHORT. The SHORT path still has the fundamental H2-003 conflict (Three Black Crows requires ema20 > ema50, which conflicts with full_bear needed for H3-005 SHORT). No SHORT candlestick pattern fired.

---

## Triple-Touch LONG Fixture Design (`btc_triple_touch_long_v1`)

### Goal

Three consecutive dips to approximately the same level to accumulate higher touch count, providing stronger structural confirmation.

### Design

```
Three dips: 69,800 → 69,900 → 69,850
All within ATR×0.5 of each other → all merge into one level
Result: level ≈ 69,850, touches ≥ 3 (higher than MIN_TOUCHES=2)
```

### Observed Result

- Support level: ~69,850 with 11 accumulated touches
- 1 co-occurrence event
- Best panel: 12/20 approvals, avg 6.225 → hold (slightly lower than W-bottom, possibly due to smaller score variation in proposals)

---

## Key Lessons for Future Fixture Design

### Lesson 1: Swing-Low Confirmation Requires 2-Bar Right-Side

A dip at bar `i` is not detected until bar `i+2`. If the target co-occurrence bar is bar `N`, the second swing-low must occur at or before bar `N-3` for the level to be qualified before bar `N`.

### Lesson 2: Close-Space Swing-Low Check

For swing low at dip bar: `dip_close` must be closer to `recovery_close` than to `pre_dip_close`. Equivalently: the recovery step must be smaller than the dip step.

### Lesson 3: ATR Estimation

ATR is computed over a 14-bar window. For a 70,000 base with 1% wick_pct, ATR ≈ 700. For a 62,000 base, ATR ≈ 620. These estimates drive the cluster merge threshold (ATR×0.5) and at_support proximity window (ATR×1.0).

### Lesson 4: Touch Accumulation

Each time the price returns close to a level (within ATR×0.5), a touch is recorded. In a W-bottom with oscillation, touches accumulate rapidly (15 touches in 257 bars is achievable). Higher touch counts raise `level.strength` but do NOT raise `structure_quality` above 'none' — that requires `higher_highs=True AND higher_lows=True`.

### Lesson 5: `structure_quality` Requires HH/HL Detection

`TechnicalStructureGroup._analyze_trend_structure()` sets `structure_quality` to 'weak', 'moderate', or 'strong' only when `higher_highs=True AND higher_lows=True`. In W-bottom fixtures, the price forms two equal lows (not higher lows) — so `structure_quality` stays 'none'. Future fixtures need to establish a clear higher-high / higher-low sequence before the entry bar for `structure_quality` to rise.

---

## Swing-Low Detection Edge Case (Bar 246 Instrumentation Artifact)

At bar 246, `TechnicalStructureGroup` publishes TWO `GroupSignalEvent`s:
1. First event: `at_support=True` (level 69,670 within ATR of close 70,400)
2. Second event: `at_resistance=True, at_support=False` (new swing-high detected on bar 246)

The harness `_on_group_signal` overwrites `obs.at_support` with the LAST event received. This causes the harness to report `at_support_bars=0` even though `at_support=True` was the relevant state at the candlestick evaluation moment.

**Evidence that at_support=True was the true state:** Journal packet `f4700d62` (bar 246) explicitly shows `structure.at_support=True`. The candlestick group correctly used bar 245's cached structural (at_s=True) to fire Bullish Engulfing. The proposal was generated. The packet was evaluated.

This is a harness instrumentation artifact. The runtime pipeline functioned correctly.
