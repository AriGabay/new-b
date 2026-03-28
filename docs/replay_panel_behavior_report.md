# Replay Panel Behavior Report

**Date:** 2026-03-28
**Source:** event_driven_runtime_replay + event_driven_runtime_replay_lifecycle_assist
**Phase:** 5.5

---

## Overview

This report documents TraderEvaluatorPanel behavior during replay validation.

**Key finding:** The panel was evaluated once via lifecycle control injection.
The injected proposal (`composite_score=0.65`, LONG direction) was **rejected**.
Zero natural entries reached the panel across all three replay fixtures.

---

## Natural Entry Path

Across 900 replay bars (3 fixtures), the panel was never reached via natural entry.
`EntryGroup` never fired a `CandidateTradeEvent` because `composite_score` could not
exceed the 0.4875 ceiling (< 0.50 threshold).

**Panel evaluations from natural signals: 0**

This is not a panel finding. It is an upstream architectural barrier.

---

## Lifecycle Control Panel Evaluation

The lifecycle control test injected a `CandidateTradeEvent` directly into the bus
at bar 200 of the bull breakout fixture, with:

```
direction: LONG
composite_score: 0.65  (above EntryGroup threshold of 0.50)
entry_price: ~64,200 USDT
stop_price: ~63,500 USDT (approximate ATR-based)
target_price: ~65,600 USDT (R:R ≈ 2.0)
hypothesis_refs: ["H3-002"]
setup_refs: ["replay_lifecycle_control"]
```

**Panel outcome: REJECTED (0 positions opened)**

The real TraderEvaluatorPanel evaluated this proposal and rejected it.
Details of the evaluation are not logged per-trader in this harness,
but the outcome (zero position opens) is definitive.

---

## Panel Architecture (Documented for Reference)

The `TraderEvaluatorPanel` in Phase 3 consists of 20 independent trader evaluators.
Each emits a `TraderVerdictEvent` with APPROVE or REJECT and a numeric score.

### Approval Requirements (read-only constants)
```python
APPROVE_THRESHOLD = 14   # minimum approvals out of 20
MIN_AVG_SCORE = 6.5      # minimum average score from all 20 traders
```

### FinalDecisionGroup Safety Rails
Rail 1: avg_score < 5.0 → REJECT
Rail 2: reject_count > 12 → REJECT
Rail 3: R:R ratio < 1.5 → REJECT
Rail 4: invalid setup → REJECT
Rail 5: bear market + LONG proposal → REJECT
Rail 6: high volatility + fewer than 16 approvals → REJECT

### What Can Cause Lifecycle Rejection

The injected proposal may have triggered one or more of:
- Fewer than 14 approvals (traders applied own selectivity criteria)
- R:R ratio check — the injected parameters used `raw_target = entry + atr × 2.0`,
  which should be R:R ≥ 2.0 unless ATR was very small
- Any trader applying "lifecycle_control" setup references with high skepticism

The lifecycle test is designed to show the pipeline mechanics, not to guarantee
an open position. Panel rejection is valid and expected behavior.

---

## Comparison with Phase 5 Panel Results

In Phase 5, the panel was evaluated using `synthetic_control_scenarios` —
hand-crafted BTCSetupPackets. Results: 30% enter rate (3/10 scenarios).

| Mode | Proposals Evaluated | Enter Rate | Source |
|------|---------------------|------------|--------|
| Phase 5 (synthetic control) | 10 | 30% (3/10) | synthetic_control_scenarios |
| Phase 5.5 (replay natural) | 0 | N/A | event_driven_runtime_replay |
| Phase 5.5 (lifecycle inject) | 1 | 0% (0/1) | event_driven_runtime_replay_lifecycle_assist |

**These sources must NOT be mixed.** The panel's 30% enter rate on synthetic control
says nothing about how it would perform on replay or natural entries.

---

## Panel Behavior on Replay Bars (Structural Analysis)

While the panel was not reached via natural entries, we can analyse what would happen
if the composite_score ceiling were resolved:

### Bull Breakout Scenario (bar 238 — golden cross)
- ema20 > ema50: YES (63,784 > 63,779)
- ADX: 37.6 (> 20 threshold for IndicatorsGroup)
- RSI: 73.2 (bullish, not overbought at 80)
- Volume ratio: normal (< 1.5, no pump signal)

If this bar reached the panel with a well-formed BTCSetupPacket:
- IndicatorsGroup: likely high quality score (ADX > 25, RSI aligned)
- CandlestickGroup: depends on candlestick pattern at bar 238 (not assessed here)
- Outcome would depend on 20 trader evaluations — not predictable from bar data alone

### Bear Breakdown Scenario (bar 244 — death cross)
- ema20 < ema50: YES (66,716 < 66,747)
- ADX: 50.3 (very strong trend)
- RSI: 15.1 (very oversold — strong SHORT signal)
- Rail 5 (bear + LONG) would not apply if proposal is SHORT

If this bar reached the panel as a SHORT proposal:
- IndicatorsGroup: likely high quality score
- Rail 5 would not block (direction matches regime)
- Panel evaluation outcome is still uncertain without actual evaluator scoring

---

## Conclusion

Phase 5.5 replay validation produced no panel evaluation data from natural entries.
The one lifecycle control evaluation resulted in rejection. No panel calibration data
is available from the replay source. This is documented honestly.
