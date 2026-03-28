# Source-of-Outcome Policy

**Phase:** 4 Learning Layer
**Date:** 2026-03-28
**Enforcement:** Mandatory. Violations corrupt learning metrics.

---

## The Four Sources

| Source | Value | Description |
|---|---|---|
| `event_driven_runtime` | live paper/sim execution via full 10-group pipeline | All groups active; real signal evaluation; real position sizing |
| `simplified_backtest` | BacktestEngine EMA-crossover only | NOT the full group pipeline; EMA crossover signal only |
| `synthetic_data` | generated/injected for testing | Not real market data |
| `live_exchange_fed` | live Bybit execution | Phase 5+, not yet enabled |

---

## The Core Rule

**Never aggregate outcomes from different sources.**

Calibration, attribution, and learning conclusions MUST be computed
separately for each outcome source. Mixing sources produces meaningless
metrics.

**Why:**
- `simplified_backtest` uses EMA-crossover signals only. The 20-trader
  panel, specialist groups, and composite scoring are NOT active during
  backtest replay. Outcomes cannot be attributed to trader quality.
- `synthetic_data` is fabricated. Calibration from synthetic outcomes
  has no predictive value.
- `event_driven_runtime` and `live_exchange_fed` are the only sources
  that produce valid calibration data.

---

## Enforcement Points

### 1. OutcomeSource enum (src/learning/outcome_source.py)
Every record written to learning tables carries an `outcome_source` field.
`assert_single_source()` must be called before computing any calibration
metric on a set of records.

### 2. JournalExtension queries
All query methods accept an `outcome_source` parameter and filter on it.
Cross-source queries are not provided.

### 3. Reporting
`LearningReportGenerator` accepts `outcome_source` and generates one
report per source. Cross-source aggregation methods do not exist.

### 4. Recommendations
`RecommendationEngine` generates recommendations per source only.
Recommendations from `simplified_backtest` source are marked advisory
with lower confidence than `event_driven_runtime` recommendations.

---

## Current Status (2026-03-28)

| Source | Status |
|---|---|
| `event_driven_runtime` | Active in paper/sim mode. MarketDataGroup → Bybit connectivity blocked (IP restriction). |
| `simplified_backtest` | Active via BacktestEngine. EMA-crossover only. |
| `synthetic_data` | Used in tests only. |
| `live_exchange_fed` | Not enabled. Phase 5+. |

---

## Minimum Sample Requirements

No calibration conclusions may be drawn with fewer than **30 samples** per
(trader, source) pair or (setup_family, source) pair.

All `TraderCalibrationRecord` and `SetupFamilyRecord` properties return
`None` when `total_reviews < 30`. The `has_sufficient_samples` property
provides the gate check.

This minimum is not adjustable without explicit architectural review.
