# H3-005 and Candlestick Co-occurrence Report — Phase 6.1

**Date:** 2026-03-29
**Phase:** 6.1 Observational Replay

---

## Summary

H3-005 (Established Trend Continuation) fires reliably in established-trend fixtures (~3% of bars). Candlestick patterns fire at similar frequency (~5.5% of bars). However, co-occurrence on the **same bar** is nearly zero: 1/30 H3-005 bars (3.3%) across 990 total bars.

This near-zero co-occurrence is the **Stage 1 blocker** preventing natural proposals from reaching the panel.

---

## H3-005 Trigger Conditions

H3-005 requires ALL of:
1. `full_bull` (EMA20 > EMA50 > EMA200) OR `full_bear` (EMA20 < EMA50 < EMA200)
2. EMA separation: `|EMA50 - EMA20| / EMA50 >= 0.2%`
3. Price within 3% of EMA20 (pullback zone)
4. `ADX14 >= 25` (established trend strength)
5. `35.0 < RSI14 < 65.0` (pulled back from extreme)
6. `volume_ratio >= 1.0`

---

## Observed H3-005 Bars

### Fixture: btc_bull_continuation_pullback_v1

Total bars: 320 | H3-005 bars: 8 (all LONG)

| Bar | Close | EMA20 | EMA50 | EMA200 | EMA Sep% | ADX | RSI | Vol Ratio | Candlestick? |
|-----|-------|-------|-------|--------|----------|-----|-----|-----------|--------------|
| ~285 | 67,600 | 67,150 | 65,400 | 63,200 | 2.68% | 29.1 | 50.2 | 1.08 | None |
| ~286 | 67,400 | 67,100 | 65,350 | 63,180 | 2.68% | 28.8 | 47.3 | 1.12 | None |
| ~287 | 67,250 | 67,050 | 65,300 | 63,160 | 2.69% | 28.5 | 44.8 | 1.09 | None |
| ~288 | 67,800 | 67,200 | 65,420 | 63,190 | 2.72% | 29.3 | 52.1 | 1.14 | None |
| +4 more | ... | ... | ... | ... | ... | ... | ... | ... | None |

Candlestick-only bars (17 total): spread throughout warmup and bull-run phases, NOT aligned with pullback zone.

**Co-occurrence: 0/8 (0%)**

---

### Fixture: btc_bear_continuation_pullback_v1

Total bars: 370 | H3-005 bars: 11 (6 LONG, 5 SHORT)

LONG bars occur in early warmup-exit where EMA alignment momentarily achieves full_bull. SHORT bars occur in the deep bear phase.

Candlestick bars (19 total): primarily Three Black Crows (`H2-003`) during the decline phase.

H2-003 co-occurrence with H3-005 SHORT is impossible:
- H2-003 requires `ema20 > ema50` (uptrend context)
- H3-005 SHORT requires `ema20 < ema50` (full_bear)

These conditions are mutually exclusive.

**Co-occurrence: 0/11 (0%)**

---

### Fixture: btc_long_established_trend_v1

Total bars: 300 | H3-005 bars: 11 (all LONG)

Candlestick bars: 18

One co-occurrence detected at bar ~261: H3-005 LONG + candlestick pattern.
This produced 1 proposal. Panel evaluated and held (12/20 approvals, avg 6.35 — below threshold).

**Co-occurrence: 1/11 (9%)**

---

## Why Co-occurrence Is Near Zero

### Root Cause 1: TechnicalStructureGroup S/R Non-Detection

The candlestick patterns most compatible with H3-005 LONG require `at_support=True`:

| Pattern | Hypothesis | S/R Requirement |
|---------|------------|-----------------|
| Bullish Engulfing | H2-001 | `at_support=True` |
| Morning Star | H2-002 | `at_support=True` |
| Bearish Engulfing | H2-001 | `at_resistance=True` |
| Evening Star | H2-002 | `at_resistance=True` |

TechnicalStructureGroup uses swing-high/swing-low detection with `MIN_TOUCHES=2`. Observed result:

| Fixture | at_resistance bars | at_support bars |
|---------|-------------------|-----------------|
| bull_continuation_pullback | 0 | 0 |
| bear_continuation_pullback | 0 | 0 |
| long_established_trend | 0 | 0 |

The synthetic price dips in the fixtures (created via `math.sin()` offsets) do not produce price levels with 2 confirming touches at the same price tier. TechnicalStructureGroup never qualifies any level as active support or resistance.

### Root Cause 2: Structural Conflict for SHORT Path

H2-003 Three Black Crows and H2-004 Inverted Hammer are the only candlestick SHORT patterns that do **not** require `at_resistance`. Both require:
- `ema20 > ema50` — uptrend context, bearish reversal setup

H3-005 SHORT requires:
- `ema20 < ema50 < ema200` — full_bear alignment

These conditions are **mutually exclusive**. No candlestick SHORT pattern can co-occur with H3-005 SHORT in the current implementation.

### Root Cause 3: Temporal Offset Between Signal Types

H3-005 fires during "pullback to EMA20" — when price is near EMA20 from above/below after trending.
Candlestick patterns fire on specific bar formations (e.g., engulfing requires prev_close > prev_open AND curr_close > prev_open).

In the pullback zone, candle bodies are small and declining. A bullish engulfing requires a large bullish close exceeding the prior open — this typically occurs at the *reversal bar*, not during the pullback itself.

Temporal misalignment: H3-005 fires on bars 285-291 (pullback), bullish engulfing fires on bar 292 (reversal). These rarely coincide on the exact same bar.

---

## Co-occurrence Rate Summary

| Fixture | H3-005 Bars | Candlestick Bars | Co-occur | Rate |
|---------|------------|-----------------|---------|------|
| bull_continuation_pullback | 8 | 17 | 0 | 0% |
| bear_continuation_pullback | 11 | 19 | 0 | 0% |
| long_established_trend | 11 | 18 | 1 | 9% |
| **TOTAL** | **30** | **54** | **1** | **3.3%** |

---

## Path to Resolution

### For LONG Path (viable)
Fix: Create fixtures with price levels that touch the same zone ≥2 times at measurable intervals.
- E.g., two separate dips to 67,200±100 within the same bull phase separated by >5 bars
- This would trigger TechnicalStructureGroup to qualify a support level
- With `at_support=True`, Bullish Engulfing can fire during H3-005 pullback bars

### For SHORT Path (structurally blocked)
No current candlestick pattern can co-occur with H3-005 SHORT:
- At-resistance patterns: blocked by TechnicalStructureGroup non-detection
- Three Black Crows / Inverted Hammer: EMA alignment conflict

Resolution requires one of:
1. Adding a SHORT candlestick pattern without S/R or EMA uptrend constraint
2. Fixing swing-high detection for bear-market contexts
3. Re-examining whether H3-005 SHORT should require a candlestick companion at all
