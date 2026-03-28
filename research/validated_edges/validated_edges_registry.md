# Validated Edges Registry
## Generated: 2026-03-28
## Source: Phase 1 Research Corpus

---

## Status: EMPTY — No Validated Edges at Phase 1

This document will be populated as hypotheses move through the validation pipeline.

---

## What Belongs Here

An "edge" is validated when:
1. The hypothesis has been backtested on out-of-sample cryptocurrency OHLCV data
2. The profit factor > 1.2 OR the Sharpe ratio improvement is statistically significant (p < 0.05)
3. The result is robust to reasonable parameter variation (no single optimal parameter point)
4. The result survives transaction cost assumptions of at least 0.15% per round trip
5. The result has been reviewed for look-ahead bias by an independent check

---

## Process for Validation

### Step 1: Define hypothesis precisely (see /research/hypotheses/hypothesis_registry.md)
### Step 2: Implement pattern detection without lookahead
### Step 3: Run in-sample backtest on training set (e.g., 2019-2022)
### Step 4: Review for parameter overfit (sensitivity analysis)
### Step 5: Run out-of-sample test on holdout set (e.g., 2023-2025)
### Step 6: If OOS results degrade significantly (> 40% performance loss), treat as overfit → do not validate
### Step 7: If OOS results hold, document here with:
  - Pattern definition (exact code/algorithm)
  - Dataset tested (assets, timeframes, date ranges)
  - Performance metrics (win rate, profit factor, max drawdown, Sharpe, Calmar)
  - Regime conditions where it works / breaks
  - Parameter sensitivity analysis
  - Known decay risks (how might this edge get arbitraged away)

---

## What Does NOT Qualify

- Equity market statistics (Bulkowski's) are NOT validated edges for crypto. They are priors.
- Twitter/blog anecdotes are NOT validated edges.
- Patterns that "look good" on a chart are NOT validated edges.
- Backtests on a single period or single asset are NOT validated edges.

---

## Placeholder Fields

When an edge is validated, it will be documented as:

```
EDGE-001:
  Name: [Pattern/Strategy Name]
  Hypothesis: [Corresponding H-ID from hypothesis registry]
  Asset Universe: [e.g., BTC, ETH, Top-10]
  Timeframe: [e.g., Daily, 4h]
  Training Period: [dates]
  OOS Period: [dates]
  Win Rate (OOS): [%]
  Profit Factor (OOS): [value]
  Max Drawdown (OOS): [%]
  Sharpe Ratio (OOS): [value]
  Parameter Sensitivity: [stable / fragile]
  Regime Conditions: [works in X, fails in Y]
  Decay Risk: [assessment]
  Implementation Notes: [key code/logic notes]
  Validated By: [agent/reviewer]
  Validation Date: [date]
```

---

## Current Validated Edge Count: 0

All 25 hypotheses in the registry are awaiting Phase 2 implementation and backtesting.
