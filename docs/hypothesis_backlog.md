# Hypothesis Backlog — Prioritized for Validation
## Date: 2026-03-28
## System: Crypto Quantitative Trading Research Layer

---

## Overview

This is the prioritized backlog of testable hypotheses for Phase 2 validation. All hypotheses are currently UNTESTED. None should be implemented in live logic until validated.

The ordering reflects:
1. Statistical confidence in equity markets (Bulkowski baseline)
2. Conceptual simplicity (easier to implement cleanly)
3. Expected signal frequency (more frequent = more statistically meaningful backtest)
4. Regime independence (works in both bull and bear markets)
5. Risk management relevance (even if edge is marginal, useful as risk tool)

---

## SPRINT 1 — Foundation Validation (Implement First)

These must be tested first because all other strategy decisions depend on them.

### [S1-1] EMA Crossover Baseline Benchmark
**Hypothesis:** H3-002
**Question:** What is the baseline performance of a simple 20/50 EMA crossover on daily BTC data?
**Why First:** Establishes the minimum bar any complex strategy must beat. Without this baseline, we cannot know if our patterns add value.
**Implementation:** Simple: long when 20-EMA > 50-EMA; short/cash when below. Measure: profit factor, max drawdown, Sharpe ratio.
**Data:** BTC/USD daily, 2017-2025

---

### [S1-2] ATR Stop Loss Validation
**Hypothesis:** H3-003
**Question:** Does ATR-scaled stop sizing (2× ATR) improve Sharpe ratio vs. fixed % stops on the EMA crossover system?
**Why Second:** If ATR stops don't materially improve risk metrics on the baseline system, reconsider their role.
**Implementation:** Apply EMA crossover signals with (a) fixed 5% stop and (b) 2× ATR stop. Compare Sharpe ratios.
**Data:** BTC/USD daily, 2017-2025

---

### [S1-3] Volume Filter Effect
**Hypothesis:** H4-001
**Question:** Do signals from assets with >$10M daily volume have lower failure rates than from low-volume assets?
**Why Third:** Determines whether universe filtering is worth the implementation complexity.
**Implementation:** Run any pattern on a high-volume universe vs. low-volume universe; compare failure rates.
**Data:** Multi-asset OHLCV + volume, 2020-2025

---

## SPRINT 2 — Critical Pattern Validation (Highest Priority Patterns)

### [S2-1] Head and Shoulders Top
**Hypothesis:** H1-001
**Equity Baseline:** 93% break downward, ~7% failure rate
**Implementation Complexity:** Medium (need to define left shoulder, head, right shoulder, neckline algorithmically)
**Expected Frequency:** ~5-10 per year on daily BTC chart
**Acceptance Criteria:** Failure rate < 20% in crypto; profit factor > 1.2 after fees

---

### [S2-2] Inverse Head and Shoulders
**Hypothesis:** H1-002
**Equity Baseline:** High reliability, commonly studied
**Acceptance Criteria:** Same as S2-1

---

### [S2-3] Double Bottom with Confirmation Rule
**Hypothesis:** H1-003
**Key Test:** BOTH confirmed and unconfirmed double bottoms must be measured.
**Key Expected Result:** Confirmed: < 15% failure; Unconfirmed: > 40% failure
**Acceptance Criteria:** Confirmation rule shows statistically significant improvement

---

### [S2-4] Descending Triangle Confirmed Breakout Short
**Hypothesis:** H1-004
**Equity Baseline:** 4% failure rate with confirmed breakout
**Acceptance Criteria:** Failure rate < 15% in crypto

---

### [S2-5] Triple Bottom Long Entry
**Hypothesis:** H1-005
**Equity Baseline:** 4% failure rate, 38% average rise
**Acceptance Criteria:** Failure rate < 15%; average gain > 15%

---

## SPRINT 3 — High-Priority Patterns

### [S3-1] Bull Flag / Bear Flag Performance
**Hypothesis:** H1-006
**Key Question:** Do targets need to be discounted even more in crypto vs. equities?
**Expected Result:** Failure rate < 20%; targets must be 50% discounted

---

### [S3-2] High & Tight Flag
**Hypothesis:** H1-007
**Key Question:** Is this rare pattern detectable and does it outperform standard flags?

---

### [S3-3] Falling Wedge Reversal
**Hypothesis:** H1-008
**Expected Result:** Positive expectancy; lower average gain than equity (43% equity → ~20% crypto expected)

---

### [S3-4] Pipe Bottom
**Hypothesis:** H1-009
**Key Challenge:** Algorithmic definition of "two adjacent spike lows" vs. random double wicks

---

### [S3-5] RSI Divergence — Conditional (With Context Filter)
**Hypothesis:** H3-001
**Key Filter:** No impulse candle (< 1.5× ATR); established trend
**Expected Result:** Without filter: near-random. With filter: win rate > 55%.

---

## SPRINT 4 — Candlestick Pattern Validation

### [S4-1] Bearish Engulfing at Resistance
**Hypothesis:** H2-001
**Key Dependency:** Requires structural level detection (OQ-012 must be resolved first)

### [S4-2] Morning Star / Evening Star at Structure
**Hypothesis:** H2-002
**Key Dependency:** Same as S4-1

### [S4-3] Three Black Crows in Uptrend
**Hypothesis:** H2-003

### [S4-4] Inverted Hammer Direction Test
**Hypothesis:** H2-004
**Key Result:** This tests whether Bulkowski's contrary finding (bearish, not bullish) holds in crypto.

### [S4-5] Doji Reversal Conditional
**Hypothesis:** H2-005

---

## SPRINT 5 — Macro / Structural Hypotheses

### [S5-1] Dead-Cat Bounce Short
**Hypothesis:** H4-003
**Application:** Risk management AND short entry

### [S5-2] Inside Bar Directional Bias
**Hypothesis:** H4-004

### [S5-3] BB Squeeze as Breakout Precursor
**Hypothesis:** H3-004

### [S5-4] Round-Number Stop Hunting
**Hypothesis:** H5-001

### [S5-5] Volume Anomaly Pump Filter
**Hypothesis:** H5-002

### [S5-6] MVRV Macro Filter
**Hypothesis:** H4-002
**Note:** Requires on-chain data infrastructure (Glassnode API)

---

## Pre-Conditions Before Any Sprint Begins

These open questions must be resolved before backtesting:

| OQ-ID | Question | Blocking Sprint |
|---|---|---|
| OQ-001 | Bulkowski equity → crypto transfer | S2 onwards |
| OQ-008 | Which data source to use | S1 |
| OQ-009 | Minimum sample size | S2 onwards |
| OQ-016 | Anti-p-hacking methodology | All |
| OQ-012 | S/R level detection method | S4 |
| OQ-013 | Trend definition method | S2, S3, S4 |

---

## Hypothesis Validation Decision Tree

```
For each hypothesis:
  1. Define pattern precisely in code (no ambiguity)
  2. Check: Does definition require any future data? → Fix if yes
  3. Run in-sample backtest (training period)
  4. Run sensitivity analysis (vary parameters ± 20%)
     → If performance collapses: FRAGILE → REJECT
     → If performance is stable: proceed
  5. Run out-of-sample test (holdout period)
     → If OOS degrades > 40%: OVERFIT → REJECT
     → If OOS holds: CANDIDATE EDGE
  6. Apply Bonferroni correction (p < 0.002 for 25 hypotheses)
  7. Document in validated_edges_registry.md
```

---

## Backlog Statistics

| Sprint | Hypotheses | Status |
|---|---|---|
| S1 (Foundation) | 3 | Not started |
| S2 (Critical Patterns) | 5 | Not started |
| S3 (High-Priority) | 5 | Not started |
| S4 (Candlesticks) | 5 | Not started |
| S5 (Macro/Structural) | 6 | Not started |
| **Total** | **24** | **0% complete** |
