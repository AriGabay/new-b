# Upstream Signal Trigger Audit

**Date:** 2026-03-29
**Phase:** 6

---

## Purpose

Audit every upstream component in the candidate generation path and determine what signal conditions currently trigger CandidateTradeProposals, whether those conditions are compatible with the current panel policy, and what was changed.

---

## Component Map

```
FeatureReadyEvent (bar close)
    ↓
IndicatorsGroup   → GroupSignalEvent(indicators_bundle)
CandlestickGroup  → GroupSignalEvent(candlestick_bundle)  [always published]
TechnicalStructureGroup → GroupSignalEvent(structure_bundle)
    ↓
EntryGroup._collect_bundle() — accumulates bundles
EntryGroup._evaluate_trade_opportunity() — triggers when BOTH indicators + candlestick arrive
    ↓
(confirmation gate → composite score → proposal)
    ↓
PanelDecisionGroup (Layer B)
```

---

## Upstream Component Audit

### IndicatorsGroup — Active Signals

| Signal | Hypothesis | Trigger Condition | Panel Compatibility |
|--------|-----------|------------------|---------------------|
| `death_cross` | H3-002 | `prev_ema20 > prev_ema50` AND `ema20 < ema50`, ADX ≥ 20 | **POOR** — fires at exact transition bar. EMA alignment = "mixed" or "partial_bear". TrendFollowing scores 4.5 (reject). |
| `golden_cross` | H3-002 | `prev_ema20 < prev_ema50` AND `ema20 > ema50`, ADX ≥ 20 | **POOR** — same as above, "mixed" alignment |
| `trend_continuation_short` | **H3-005 (NEW)** | full_bear alignment + EMA sep ≥ 0.2% + price within 3% of EMA20 + ADX ≥ 25 + vol ≥ 1.0 + RSI 35–65 | **GOOD** — fires in established trend. EMA alignment = "full_bear". TrendFollowing scores 8.0+. |
| `trend_continuation_long` | **H3-005 (NEW)** | full_bull alignment + same conditions | **GOOD** |
| `rsi_overbought_fade` | H3-001 | RSI > 70 AND NOT rising, ADX ≥ 20 | Moderate — valid signal but needs candlestick confirmation to pass gate |
| `rsi_oversold_bounce` | H3-001 | RSI < 30 AND rising, ADX ≥ 20 | Moderate — same |
| `rsi_bearish_divergence` | H3-001 | price higher high, RSI lower high, ADX ≥ 25 | Moderate |
| `macd_bearish_cross` | None | MACD line crosses below signal line | Moderate — lagging |
| `bb_squeeze_breakout_short` | H3-004 | After squeeze, close < bb_lower, vol > 1.5x | Good if at structure level |

### CandlestickGroup — Active Signals

| Signal | Hypothesis | Requirement | Notes |
|--------|-----------|-------------|-------|
| `bearish_engulfing` | H2-001 | at_resistance, ADX ≥ 20 | Strong SHORT confirmation |
| `bullish_engulfing` | H2-001 | at_support, ADX ≥ 20 | Strong LONG confirmation |
| `evening_star` | H2-002 | at_resistance, 3-bar | Best SHORT signal; R3.5 reversal |
| `morning_star` | H2-002 | at_support, 3-bar | Best LONG signal |
| `three_black_crows` | H2-003 | No S/R required, 3 consec bearish | S/R independent |
| `inverted_hammer` | H2-004 | at_resistance, SHORT only | Bearish continuation |
| `doji` | H2-005 | After 2+ trend candles | Lower quality (0.55) |

CandlestickGroup **always publishes** a bundle every bar (even with 0 signals). This makes the "wait for candlestick bundle" trigger safe.

### EntryGroup — Trigger and Gate Logic

#### Old behavior:
```
Trigger: fires when indicators bundle arrives (candlestick not required)
Gate: >= 2 signals in same direction (any type — including pure indicator-only)
```

#### New behavior (Phase 6):
```
Trigger: fires when BOTH indicators AND candlestick bundles are present
Gate: >= 2 signals in same direction
      + at least 1 must be candlestick or chart_pattern (enforced)
```

---

## What Changed and Why

### Change 1: Wait for candlestick bundle

**Before**: EntryGroup evaluated as soon as IndicatorsGroup published. CandlestickGroup had not yet published for the same bar. Result: `candlestick_quality = 0.0` in composite score.

**After**: EntryGroup evaluates when both indicators AND candlestick bundles are accumulated. `candlestick_quality > 0` when a pattern fires.

**Effect**: Composite score now reflects real candlestick quality. The panel evaluators (Candlestick, WickAnalysis, MarketContext) receive actual pattern data.

### Change 2: Enforce candlestick/chart_pattern in confirmation gate

**Before**: Two indicator signals (e.g., `death_cross` + `rsi_overbought_fade`) could pass the gate. The docstring said "at least 1 must be candlestick or chart_pattern" but this was not enforced in code.

**After**: Proposals with only indicator signals are suppressed. At least 1 signal must be `signal_type == "candlestick"` or `"chart_pattern"`.

**Why this is correct**: Pure indicator proposals at EMA crossover bars have:
- `ema_alignment = "mixed"` → TrendFollowing 4.5 (reject)
- No candlestick pattern → Candlestick 4.0 (abstain), WickAnalysis low
- Structurally unable to reach avg_score ≥ 6.5

The gate was allowing proposals that the panel was guaranteed to reject. Enforcing it at the gate prevents wasted evaluation cycles and noise.

### Change 3: H3-005 trend continuation signal

**Before**: Only H3-002 (EMA crossover) provided the primary indicator signal. H3-002 fires at transition bars.

**After**: H3-005 fires during **established trend phases** when price pulls back near EMA20. These bars have:
- `ema_alignment = "full_bear"` or `"full_bull"` → TrendFollowing 8.0+
- ADX ≥ 25 (trending confirmed) → multiple evaluators benefit
- Volume ≥ 1.0x (at least average) → VolumeProfile neutral or better
- RSI in 35–65 zone (pulled back, not oversold) → Momentum moderate score

H3-005 fires on bars where the panel CAN approve the proposal. H3-002 fired on bars where the panel was structurally unable to approve.

---

## Signal Timing Comparison

| Scenario | H3-002 (old primary) | H3-005 (new primary) |
|----------|---------------------|---------------------|
| When fires | EMA20 first crosses EMA50 | AFTER trend established, on pullback |
| EMA alignment | "mixed" or "partial_bear" | "full_bear" or "full_bull" |
| EMA separation | ~0% (just crossed) | ≥ 0.2% (committed) |
| Price vs EMA200 | Often still above (not full_bear) | Must be full alignment |
| RSI at fire time | Often overbought (recent momentum) | 35–65 (pulled back) |
| Volume | Any (often declining post-cross) | ≥ 1.0x required |
| Typical TrendFollowing score | 4.5 (reject) | 8.0+ (approve) |
| Panel outcome | HOLD (< 14 approvals) | Potentially ENTER (≥ 14 approvals with candlestick) |

---

## Composite Score Comparison

**Old (H3-002 only, no candlestick):**
```
indicator_quality ≈ 0.85 (death_cross, ADX=37, EMA bears, but volume 0.92x)
candlestick_quality = 0.0 (evaluated before CS bundle arrived)
structural_alignment = 1.0 (at_resistance=True)

raw = 0.20 × 0.85 + 0.25 × 0.0 + 0.10 × 1.0 = 0.17 + 0.00 + 0.10 = 0.27
composite = 0.27 / 0.55 = 0.491 → BELOW 0.50 THRESHOLD (or barely above on best bars)
```

**New (H3-005 + candlestick, at structure):**
```
indicator_quality ≈ 0.90 (H3-005, ADX=28, full_bear, vol=1.2x, RSI=50)
candlestick_quality ≈ 0.70 (bearish_engulfing or evening_star)
structural_alignment = 1.0 (at_resistance required for most CS patterns)

raw = 0.20 × 0.90 + 0.25 × 0.70 + 0.10 × 1.0 = 0.18 + 0.175 + 0.10 = 0.455
composite = 0.455 / 0.55 = 0.827 → WELL ABOVE 0.50 THRESHOLD ✓
```
