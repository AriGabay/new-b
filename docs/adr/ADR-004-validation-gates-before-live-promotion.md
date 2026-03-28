# ADR-004: Validation Must Gate Promotion to Live Logic
## Status: ACCEPTED
## Date: 2026-03-28

---

## Context

Phase 1 produced 25 testable hypotheses with 0 validated edges. The risk of building a full live trading system before validating any of these hypotheses is that we would be live-trading unvalidated ideas. This ADR defines the promotion pipeline that prevents premature live trading.

## Decision

All signals start in RESEARCH mode. Promotion to SHADOW then LIVE requires explicit validation gates. No pattern is allowed to influence live order execution until it passes all gates.

## The Promotion Pipeline

```
RESEARCH MODE (default)
  ↓ Gate 1: In-Sample Backtest
SHADOW MODE (paper trading)
  ↓ Gate 2: OOS Backtest + Statistical Test
LIVE MODE (real orders)
```

### Gate 1: RESEARCH → SHADOW

Requirements:
1. In-sample backtest completed on training period (2017-2022 for BTC/ETH)
2. Profit factor > 1.2 AND win rate > 45% AND max drawdown < 30%
3. Parameter sensitivity analysis: performance must be stable across ±20% variation in all parameters. No single "magic" parameter value.
4. Sample size >= 30 trades in-sample
5. Human sign-off required

Rejection criteria:
- OOS performance < 60% of IS performance (overfit → REJECT, don't promote)
- Any single parameter change by ±20% causes performance to collapse (fragile → REJECT)

### Gate 2: SHADOW → LIVE

Requirements:
1. Out-of-sample backtest on holdout period (2023-2025)
2. OOS profit factor > 1.15 AND statistical significance p < 0.002 (Bonferroni correction for 25 hypotheses)
3. SHADOW paper trading for minimum 90 calendar days with positive P&L
4. Shadow period sample size >= 20 trades
5. Edge decay check: no significant degradation detected in recent window
6. Human sign-off required (senior review)

### The Holdout Principle

The holdout period (2023-2025) is LOCKED. It cannot be used for:
- Parameter optimization
- Pattern refinement
- Exploratory analysis
- Any decision that could influence the pattern design

The holdout is touched ONCE: for the final OOS validation of a pre-committed hypothesis. This is enforced in code (HoldoutManager class raises exception if accessed before Gate 1 is passed).

## Consequences

- Phase 2 system is 100% RESEARCH mode at launch.
- Phase 2 produces backtest results for Sprint 1 patterns only.
- No live trading until Sprint 2 patterns are validated (at earliest).
- LLM usage is minimal in Phase 2 (research mode = no CriticAgent).
- System is safe to run from day 1 because it never fires real orders.

## What This Prevents

- Deploying unvalidated patterns that happened to look good on the chart
- P-hacking: testing 25 patterns and claiming the best one is "validated"
- Overfit patterns: those that work on in-sample data but fail on new data
- Premature live trading based on theoretical equity statistics (Bulkowski) that haven't been validated on crypto

## Alternatives Rejected

- **Immediate live trading with small size:** Rejected. "Testing in production" with real capital is not testing — it's gambling with extra steps.
- **Skip OOS validation, trust IS backtest:** Rejected. IS overfitting is the most common failure mode in systematic trading. IS backtest without OOS is worthless.
- **Skip holdout, use all data for validation:** Rejected. Without a truly untouched holdout, there is no honest OOS test.
