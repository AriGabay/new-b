# Trend Maturity and Pullback Logic

**Date:** 2026-03-29
**Phase:** 6

---

## Overview

This document explains the conceptual foundation for H3-005 (EMA trend continuation signal) and the pullback-to-EMA entry approach, and contrasts it with H3-002 (EMA crossover) which was the previous primary signal.

---

## The Problem with Crossover Entries (H3-002)

EMA crossover signals (H3-002) detect the **moment of trend transition** — the single bar where EMA20 crosses EMA50. This bar has specific properties:

1. **EMA separation is near zero**: EMA20 just crossed EMA50, so they're nearly equal. The "trend signal" is just beginning.
2. **Price position is ambiguous**: Price may still be above EMA200 (the long-term average), making EMA alignment "mixed" or "partial_bear" rather than "full_bear."
3. **Volume is unreliable**: The price momentum that drove the crossover may have already peaked. Volume at the crossover bar may be declining.
4. **No candlestick confirmation**: The crossover bar is an indicator artifact — there's no requirement for the price action at that bar to show reversal or continuation patterns.

From the panel's perspective, a crossover entry says: "The 20-period and 50-period moving averages have just swapped positions, so let's trade." This is a trend-following entry at its weakest point — when the trend is beginning to form.

---

## What "Trend Maturity" Means

A mature trend has these properties:

| Property | Immature (crossover bar) | Mature (continuation bar) |
|----------|-------------------------|--------------------------|
| EMA alignment | "partial_bear" or "mixed" | "full_bear" (EMA20 < EMA50 < EMA200) |
| EMA separation | ~0% | ≥ 0.2–1.0% (EMAs have diverged) |
| Price position | Often above EMA200 | Below all three EMAs |
| RSI state | Often recently overbought | Pulled back to 35–65 mid-zone |
| Volume | Declining from momentum peak | Returning to average after pullback |
| ADX | Just breaking above 20 | ≥ 25 (sustained momentum) |

An established trend (H3-005 zone) occurs typically 3–15 bars after the initial crossover, during the "continuation" phase of the trend.

---

## What "Pullback-to-EMA" Means

Within an established downtrend (full_bear alignment), price doesn't fall in a straight line. It makes lower lows interspersed with pullbacks (counter-trend bounces). The most reliable SHORT continuation entry is at the **pullback retest of EMA20**:

```
Established downtrend:
  Price                    EMA20 (declining)
  ···················
          ↓ impulse (short leg)
  ····················     <- EMA20 here
       ↗ pullback (price rises back toward EMA20)
  → SHORT entry at this zone (H3-005 trigger)
       ↘ continuation of downtrend
```

This entry timing is superior to the crossover entry because:
1. The trend is confirmed (all EMAs aligned, ADX ≥ 25)
2. Price has pulled back (RSI retreated from overbought)
3. The entry is near EMA20 (which acts as resistance in a downtrend)
4. Candlestick reversal patterns (evening star, bearish engulfing) are more likely to form at these pullback-to-resistance levels

---

## H3-005 Implementation Logic

H3-005 fires when ALL of these conditions are true simultaneously:

### Full EMA alignment (trend confirmed)

```
SHORT: EMA20 < EMA50 < EMA200
LONG:  EMA20 > EMA50 > EMA200
```

This requires the full three-EMA stacking to be in place. At an EMA20/50 crossover bar, EMA200 has not yet had time to respond — so this condition typically isn't met at the crossover bar itself.

### EMA separation ≥ 0.2%

```
|EMA50 - EMA20| / EMA50 >= 0.002
```

Prevents firing immediately after a bare crossover where EMA20 and EMA50 are essentially equal. Requires that the EMAs have actually diverged, confirming the trend is committed.

### Price within 3% of EMA20 (pullback zone)

```
SHORT: close is between EMA20 × 0.97 and EMA20 × 1.01
LONG:  close is between EMA20 × 0.99 and EMA20 × 1.03
```

The 3% window captures:
- Price touching EMA20 from below (the ideal pullback retest)
- Price slightly below EMA20 (already at resistance level)
- Price briefly above EMA20 (during the pullback itself)

It excludes:
- Price deep in the trend (far below EMA20) — different setup type
- Price far above EMA20 (trending against the larger direction)

### ADX ≥ 25

Ensures the trend has sufficient momentum strength. ADX = 25 is the conventional threshold for "trending vs ranging." A pullback in a ranging market is meaningless.

### Volume ≥ 1.0x

At least average participation. Volume below average at a pullback to EMA suggests weak conviction — the market isn't actively retesting the level. H3-002 had no volume requirement and could fire with volume_ratio=0.92.

### RSI between 35 and 65

The pullback mid-zone. After an impulse move down (overbought RSI in the 70s), the pullback brings RSI back toward 50. At RSI 35–65, the trade has:
- Not yet re-entered overbought territory (not too late for the pullback entry)
- Not yet become oversold (not capitulating, which would be a different setup)

---

## Why Candlestick Confirmation is Required at These Bars

H3-005 alone is not sufficient for a proposal to fire — the confirmation gate requires at least 1 candlestick or chart_pattern signal.

At pullback-to-EMA bars in a downtrend, CandlestickGroup will detect patterns like:

| Pattern | Why it fires at these bars |
|---------|--------------------------|
| Bearish Engulfing (H2-001) | Pullback ends with a large bearish bar that engulfs the prior bullish (pullback) bar. Requires at_resistance (EMA20 often near a swing level). |
| Evening Star (H2-002) | 3-bar reversal at pullback top: bullish → small body → large bearish. Most powerful reversal pattern. Requires at_resistance. |
| Inverted Hammer (H2-004) | Short-term bearish continuation after pullback. Requires at_resistance. |
| Three Black Crows (H2-003) | 3 consecutive bearish bars during or after the pullback. No S/R required — fires when the pullback collapses. |

The combination of H3-005 (established trend, pullback zone) + H2-001/H2-002/H2-003 (bearish reversal at the retest) produces proposals that reflect genuine price action confirmation, not just indicator arithmetic.

---

## Transition Setup vs Continuation Setup

The spec explicitly asks to distinguish these:

| Setup type | Trigger bar type | EMA alignment | Candlestick likely? | Panel outcome |
|------------|-----------------|---------------|--------------------|-----------|
| Transition (H3-002) | EMA crossover bar | mixed/partial | No (crossover bar) | HOLD |
| Continuation (H3-005 + CS) | Pullback-to-EMA in established trend | full_bear/full_bull | Yes (at S/R levels) | Potentially ENTER |
| Pullback (future) | Deep retracement to EMA50/200 | full_bear but below H3-005 zone | Yes if at support | To be implemented |

Phase 6 implements the **continuation** setup type. Transition setups are now suppressed by the candlestick gate. Pullback setups (deep retracement to EMA50 or EMA200) remain a future enhancement.

---

## What Still Limits Proposal Quality

Even with H3-005 and the candlestick gate:

1. **R:R depends on structural levels**: The distance from the pullback entry to the stop (above EMA20) and target (next structural support) determines R:R. Not all pullback bars will produce R:R ≥ 2.5.

2. **Structure quality may still be weak**: H3-005 fires near EMA20 but doesn't require "strong" structure quality. Contrary evaluator requires R:R > 3.0 AND structure_quality = "strong" — a high bar.

3. **H3-005 fires every bar in the pullback zone**: During a sustained pullback, H3-005 may fire on multiple consecutive bars. Only the bars where CandlestickGroup also fires will produce proposals (natural filtering), but the system could generate a few proposals in quick succession.

4. **ChartPatternGroup still excluded**: Pattern-aware evaluators (PatternCompletion abstains, Breakout capped, ProfitTarget no bonus) remain limited. This is a Phase 4+ enhancement.
