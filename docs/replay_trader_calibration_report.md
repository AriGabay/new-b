# Replay Trader Calibration Report

**Date:** 2026-03-28
**Source:** event_driven_runtime_replay
**Phase:** 5.5

---

## Status: NO CALIBRATION DATA AVAILABLE

No trades were closed during replay validation. Calibration requires a minimum of
30 closed trades per trader (`MIN_SAMPLES = 30`). Current closed trades: **0**.

---

## Why No Calibration Data Exists

### Root Cause (same as closed-trade report)

Replay fixtures produce 0 natural entries due to the composite_score ceiling (0.4875 < 0.50).
Without entries, there are no positions. Without positions, there are no closures.
Without closures, there is no calibration data.

The lifecycle control tests also produced 0 positions (panel rejected injected proposal).

### Calibration Architecture

The `CalibrationReporter` wraps:
- `TraderCalibrator` — per-trader accuracy and discrimination metrics
- `PanelCalibrator` — consensus quality metrics across 20 traders

Both require `MIN_SAMPLES = 30` closed trades before any percentage is computed.
Below this threshold, all methods return `None` or `"insufficient"` status.

---

## Per-Trader Status

| Trader | Replay Closed Trades | Min Required | Status |
|--------|---------------------|--------------|--------|
| technical_analyst | 0 | 30 | INSUFFICIENT |
| risk_manager | 0 | 30 | INSUFFICIENT |
| momentum_trader | 0 | 30 | INSUFFICIENT |
| mean_reversion | 0 | 30 | INSUFFICIENT |
| trend_follower | 0 | 30 | INSUFFICIENT |
| contrarian | 0 | 30 | INSUFFICIENT |
| volume_analyst | 0 | 30 | INSUFFICIENT |
| sentiment_analyst | 0 | 30 | INSUFFICIENT |
| macro_analyst | 0 | 30 | INSUFFICIENT |
| execution_specialist | 0 | 30 | INSUFFICIENT |
| volatility_analyst | 0 | 30 | INSUFFICIENT |
| pattern_reader | 0 | 30 | INSUFFICIENT |
| position_sizer | 0 | 30 | INSUFFICIENT |
| drawdown_guardian | 0 | 30 | INSUFFICIENT |
| correlation_analyst | 0 | 30 | INSUFFICIENT |
| liquidity_specialist | 0 | 30 | INSUFFICIENT |
| event_trader | 0 | 30 | INSUFFICIENT |
| hypothesis_validator | 0 | 30 | INSUFFICIENT |
| regime_detector | 0 | 30 | INSUFFICIENT |
| final_arbiter | 0 | 30 | INSUFFICIENT |

**All 20 traders: 0 reviews from replay source.**

---

## Panel-Level Calibration

| Metric | Value | Minimum Required | Status |
|--------|-------|-----------------|--------|
| consensus_accuracy | N/A | 30 trades | INSUFFICIENT |
| overconfidence_rate | N/A | 30 trades | INSUFFICIENT |
| avg_panel_score | N/A | 30 trades | INSUFFICIENT |
| discriminability | N/A | 30 trades | INSUFFICIENT |

---

## What Calibration Would Show (When Available)

Once 30+ closed trades are available from replay or paper trading:

### Per-trader metrics (from TraderCalibrator)
- `hit_rate`: fraction of approved trades that were winning
- `false_positive_rate`: fraction of approvals on losing trades
- `overconfidence_score`: how often a trader approves when panel rejects
- `discrimination_score`: ability to differentiate winning from losing proposals

### Panel metrics (from PanelCalibrator)
- `consensus_accuracy`: does panel approval predict wins?
- `avg_approve_threshold_quality`: do approved trades outperform rejected ones?
- `rail_trigger_rate`: how often each safety rail fires

### Calibration Actions
- Traders with high `false_positive_rate` flagged for recalibration
- Traders with `overconfidence_score > 0.7` reviewed for threshold adjustment
- Panel thresholds (APPROVE_THRESHOLD, MIN_AVG_SCORE) evaluated for sensitivity

---

## Source Separation Note

Replay calibration data (from `event_driven_runtime_replay`) must NOT be mixed with:
- Simulation data (`event_driven_runtime_simulation`)
- Backtest data (`simplified_backtest`)
- Lifecycle control data (`event_driven_runtime_replay_lifecycle_assist`)

The `SourceEnforcer` enforces this. CalibrationReporter only accepts
`event_driven_runtime_replay` or `live_exchange_fed_paper` as valid calibration sources.

---

## Conclusion

Replay calibration is not available. The framework is architecturally ready.
Data becomes available when the composite_score ceiling is resolved (Phase 4+)
or when live paper trading begins and produces ≥ 30 closed positions.
