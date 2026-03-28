# Validation Methodology

## Status: ACCEPTED
## Date: 2026-03-28

---

## Overview

This document defines the full statistical validation methodology for all 25 hypotheses in the system. It specifies what "validated" means, how to avoid p-hacking, and what tests are required at each gate.

**No hypothesis is live-traded until it passes both gates.**

---

## The Core Problem: 25 Hypotheses × 1 Dataset

With 25 hypotheses tested on the same crypto dataset, the probability of finding at least one false positive at α=0.05 is:

```
P(at least 1 false positive) = 1 - (1 - 0.05)^25 ≈ 72%
```

This means that without correction, roughly **3 of the 25 hypotheses will appear validated by chance alone**.

### Solution: Bonferroni Correction

Divide the family-wise error rate by the number of hypotheses:

```
α_corrected = 0.05 / 25 = 0.002
```

Every statistical test requires **p < 0.002** to claim significance. This is a hard requirement, not a recommendation.

---

## Training / Holdout Split

| Period             | Dates                        | Use                                                         |
|--------------------|------------------------------|-------------------------------------------------------------|
| **Training set**   | 2017-01-01 → 2022-12-31      | In-sample backtest, parameter optimization, EDA             |
| **Holdout set**    | 2023-01-01 → 2025-12-31      | Final OOS validation only — touch ONCE per hypothesis       |

**The holdout set is locked.** Any query against holdout data without Gate 1 clearance raises `HoldoutViolationError` in the `HoldoutManager` class.

---

## Gate 1: In-Sample Backtest → Shadow Promotion

### Required Tests

**1. Performance Metrics (all must pass)**
- Profit factor > 1.2
- Win rate > 45%
- Maximum drawdown < 30%
- Sample size ≥ 30 trades

**2. Parameter Sensitivity Analysis**
- Vary each parameter by ±20% independently.
- Performance must not collapse (profit factor must remain > 1.0).
- A single "magic" parameter value that explains all the edge → REJECT.

**3. Statistical Test on In-Sample Trades**
- Bootstrap resampling (10,000 draws with replacement).
- Compute 95% CI on profit factor.
- CI lower bound must be > 1.0.
- Note: full Bonferroni p < 0.002 test is reserved for Gate 2 (holdout).

**4. Human Sign-Off**
- A human reviews the backtest report before promotion to shadow.
- Automated gate check is necessary but not sufficient.

### Rejection Criteria
- OOS performance < 60% of IS performance → REJECT immediately (don't wait for Gate 2).
  - This is a "pre-flight" check run on a 20% subsample of training data held back during IS optimization.
- Any single ±20% parameter change causes profit factor to drop below 1.0 → REJECT (fragile).

---

## Gate 2: OOS Backtest + Shadow → Live Promotion

### Required Tests

**1. Out-of-Sample Backtest (holdout: 2023-2025)**
- Profit factor > 1.15
- Sample size ≥ 20 trades
- OOS retention: `oos_profit_factor ≥ 0.60 × is_profit_factor`

**2. Statistical Significance Test**
- One-sample t-test on R-multiples (H₀: mean R-multiple ≤ 0).
- **p < 0.002** (Bonferroni threshold).
- Or equivalent bootstrap test at same threshold.

**3. Shadow Period**
- Paper trading for minimum 90 calendar days.
- Shadow period positive P&L (not just technically passing).
- Shadow sample size ≥ 20 trades.

**4. Edge Decay Check**
- Last 20 shadow trades must not show significant decay vs first 20.
- Win rate in recent half vs first half: no significant degradation.

**5. Human Sign-Off (Senior Review)**
- A second human reviewer signs off.
- Documents approval rationale in the hypothesis registry.

---

## What "Validated" Means

A hypothesis is `VALIDATED` only when:
- Gate 1 passed (IS backtest metrics + parameter sensitivity + human sign-off)
- Gate 2 passed (OOS backtest p < 0.002 + OOS retention + shadow period + senior sign-off)
- HYPOTHESIS_REGISTRY status updated to `validated`
- Date and approver name recorded in registry entry

**Current status: 0 hypotheses validated.** All 25 are `UNTESTED`.

---

## What "Validated" Does NOT Mean

- "Validated" does not mean the edge will last forever. Edge decay monitoring continues after live promotion.
- "Validated" does not mean the hypothesis is correct in theory — only that it has measurable positive expectancy in tested data.
- "Validated" does not override risk rules. A validated hypothesis that exceeds daily loss limits is still blocked.

---

## Parameter Sensitivity Protocol

For each numeric parameter in a hypothesis detector, define the ±20% variation grid:

```
base_value × {0.80, 0.90, 1.00, 1.10, 1.20}
```

Run full IS backtest for each combination. Required: at least 4 of 5 combinations achieve profit_factor > 1.0. If only 1 combination works: fragile edge → REJECT.

### Tested Parameters by Pattern Type

**Chart Patterns (H1 series):**
- Neckline tolerance (±X% from exact price)
- Shoulder symmetry tolerance (left vs right height ratio)
- Minimum bars in formation
- Volume at breakout threshold

**Candlestick Patterns (H2 series):**
- Body ratio threshold (e.g., 0.6 minimum for engulfing)
- Structural level proximity (ATR multiplier for "at level")
- Trend definition (ADX threshold)

**Indicator Signals (H3 series):**
- EMA periods (if applicable)
- RSI divergence lookback
- ADX threshold for trend filter

---

## Reporting Requirements

Every IS backtest must produce:
1. **Full equity curve** (bar-by-bar cumulative PnL)
2. **Per-trade table** (trade_id, hypothesis, entry/exit, PnL, R-multiple, bars_held)
3. **Parameter sensitivity grid** (profit factor across all ±20% combinations)
4. **Max drawdown analysis** (drawdown curve, time underwater)
5. **Monthly breakdown** (win rate and PnL by month — reveal seasonality)
6. **Comparison to benchmark** (H3-002 EMA crossover baseline)

Every OOS backtest must additionally produce:
7. **IS vs OOS comparison table** (all metrics side by side)
8. **OOS retention score** per metric
9. **Statistical test results** (t-statistic, p-value, bootstrap CI)

---

## Edge Decay Monitoring (Post-Live)

After a hypothesis goes live, the PerformanceJournalGroup monitors for edge decay using a rolling window comparison:

- **Recent window:** last 50 live trades
- **Full window:** all 200+ live trades
- **Decay threshold:** recent_metric < 0.60 × full_window_metric

If decay detected:
1. SystemAlertEvent emitted (severity=warning)
2. Hypothesis status reviewed by human
3. If confirmed: status downgraded, system moves hypothesis back to shadow

---

## Anti-P-Hacking Commitments

These commitments are made before any hypothesis is tested:

1. **Pre-registration:** Hypothesis acceptance criteria written before IS backtest runs (see HYPOTHESIS_REGISTRY).
2. **Single OOS touch:** Holdout data accessed at most once per hypothesis. No re-running after seeing results.
3. **No cherry-picking:** All 25 hypotheses are reported, including rejections. No hypothesis is silently dropped.
4. **No parameter re-tuning after OOS:** If OOS results are poor, hypothesis is REJECTED (not optimized and retested).
5. **Bonferroni correction applied systemically:** Not as a post-hoc adjustment.
