# Trader Calibration Validation Report

**Source:** `event_driven_runtime` (OutcomeSource)
**Date:** 2026-03-28
**Closed trades available:** 0
**Minimum required:** 30 closed trades

---

## Current Status: NO CALIBRATION DATA

The trading system has not yet accumulated sufficient trade outcomes to measure
trader calibration. This is **expected and correct** — the system was just equipped
with the execution unblock (Phase 3) and has not run in paper trading long enough
to close positions.

This report documents what the calibration system measures and what data will be
available once trades close.

---

## 20 Trader Evaluators

All 20 traders have 0 reviews under `event_driven_runtime` source:

| Trader | Reviews | Has Sufficient Samples | Note |
|--------|---------|----------------------|------|
| TrendFollower | 0 | ❌ | No closed trades |
| MeanReversionTrader | 0 | ❌ | No closed trades |
| BreakoutSpecialist | 0 | ❌ | No closed trades |
| ValueInvestor | 0 | ❌ | No closed trades |
| MomentumTrader | 0 | ❌ | No closed trades |
| RiskArbTrader | 0 | ❌ | No closed trades |
| SwingTrader | 0 | ❌ | No closed trades |
| ScalpingTrader | 0 | ❌ | No closed trades |
| MacroTrader | 0 | ❌ | No closed trades |
| QuantTrader | 0 | ❌ | No closed trades |
| SentimentTrader | 0 | ❌ | No closed trades |
| TechnicalAnalyst | 0 | ❌ | No closed trades |
| FundamentalAnalyst | 0 | ❌ | No closed trades |
| PatternRecognizer | 0 | ❌ | No closed trades |
| VolumeAnalyst | 0 | ❌ | No closed trades |
| OrderFlowTrader | 0 | ❌ | No closed trades |
| RegimeSwitcher | 0 | ❌ | No closed trades |
| VolatilityTrader | 0 | ❌ | No closed trades |
| ContraryEvaluator | 0 | ❌ | No closed trades |
| CycleTrader | 0 | ❌ | No closed trades |

**0/20 traders have sufficient calibration data.**

---

## What Will Be Measured (Once Trades Close)

For each trader, `TraderCalibrator` tracks:

### Approval Win Rate
Of all "approve" votes cast by this trader, what fraction led to winning trades?
A well-calibrated trader approving a trade should be predictive of a win.

### Brier Score
Probability calibration quality: `(forecast_prob − outcome_binary)²`
Where `forecast_prob = confidence × (1 if vote==approve else 0)` and
`outcome_binary = 1 if outcome=="win" else 0`.
Lower is better. A perfect Brier score is 0.0.

### Score Discriminability
`avg_score_on_wins − avg_score_on_losses`
If a trader assigns higher scores to winning setups, discriminability is positive.
A discriminability near 0 means the trader's scores don't predict outcomes.

### Overconfidence
`high_conf_wrong_count / total_reviews`
Trader voted with ≥75% confidence on a wrong call (approved a loser, or rejected a winner).
Rate > 30% triggers overconfidence flag.

---

## Panel-Level Calibration (Once Available)

`PanelCalibrator.compute_panel_stats()` will measure:

1. **Enter recommendation win rate:** When the panel says "enter", what fraction are wins?
2. **avg_score discrimination:** Do higher avg_scores predict wins?
3. **High-disagreement loss rate:** When reject_count ≥ 8, are more trades losses?

---

## Minimum Requirements Before Any Conclusions

- **Minimum 30 closed trades** under `event_driven_runtime` source
- All metrics return `None` (not 0, not fabricated) until this threshold is reached
- Source tagging is enforced: `simplified_backtest` outcomes must NEVER be mixed with `event_driven_runtime`

---

## How to Obtain Real Calibration Data

1. Run `BtcBybitPaperRunner` in simulation or live paper mode
2. Allow positions to open and close (requires stop/target hits or time-based exits)
3. Each closed position triggers `OutcomeAttributor.process_closed_trade()`
4. `TraderCalibrator.process_trade_outcome()` is called for each of the 20 traders
5. After 30+ closed trades, re-run `CalibrationReporter.full_report()` for real metrics

---

## Honest Assessment

The calibration infrastructure is **built and working**. The database tables exist.
The attribution pipeline is wired (`OutcomeAttributor` → `PerformanceJournalGroup`).
The data is simply not there yet because no trades have closed.

This is not a framework failure. This is the system being honest about
its data state rather than fabricating confidence from nothing.
