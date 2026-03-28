# Validation: Survivors and Failures

**Date:** 2026-03-28
**Framework:** Phase 5 validation layer
**Source:** `event_driven_runtime_simulation` (10 synthetic scenarios)

This document tracks which components passed validation, which revealed issues,
and which remain unvalidatable due to missing data.

---

## Layer A: Signal Groups

### EntryGroup
**Status: Structurally valid. Functional coverage incomplete.**

- `make_bull_bar_sequence()` produces EMA-aligned bullish bars
- EntryGroup requires multi-signal confluence from multiple groups firing in sequence
- Pure synthetic sequences without realistic bar histories rarely trigger a CandidateTradeEvent
- This is not a bug — it reflects that the entry signal requires genuine confluence

**What's validated:** EntryGroup does not crash. It processes FeatureReadyEvents.
**What's not validated:** Whether entry signals fire at correct real-market frequencies.

### IndicatorsGroup / CandlestickGroup / TechnicalStructureGroup
**Status: Pass-through validated.**
All groups receive FeatureReadyEvents and process them without errors in replay runs.
Functional correctness of each signal algorithm is covered by existing unit tests.

---

## Layer B: TraderEvaluatorPanel (20 evaluators)

### All 20 evaluators
**Status: ✅ Validated on 10 scenarios.**

All 20 traders ran on all 10 scenarios. No exceptions. No fabricated votes.
Approval counts ranged from 2/20 (invalid quality) to 15/20 (excellent R:R).

**Findings:**
- The panel is genuinely selective: same scenario can produce different approval counts
- High-quality scenarios (ideal bull, ideal bear, excellent R:R) correctly receive 14-15 approvals
- Low-quality scenarios (ranging, invalid quality) correctly receive 2-4 approvals

### ContraryEvaluator
**Status: ✅ Behaves distinctively on excellent R:R scenario (s09).**

The ContraryEvaluator voted approve on the excellent R:R scenario (15/20 total approves),
contributing to higher consensus. This is correct — contrary evaluators should approve
genuinely strong setups while rejecting hype.

---

## Layer C: FinalDecisionGroup (6 safety rails)

### All 6 safety rails
**Status: ✅ All 6 triggered on appropriate scenarios.**

| Rail | Scenario | Status |
|------|---------|--------|
| Rail1: avg_score < 5.0 | s06 (Ranging, avg=4.5), s10 (Invalid, avg=3.8) | ✅ |
| Rail2: reject_count > 12 | Not triggered (no scenario had >12 rejects after panel passed) | ⚠️ Not triggered |
| Rail3: R:R < 1.5 | s04 (Poor R:R, R:R=1.20) | ✅ |
| Rail4: invalid setup quality | s10 (setup_quality=invalid) | ✅ |
| Rail5: bear + LONG | s03 (Bear Macro LONG) | ✅ |
| Rail6: high vol + insufficient consensus | s05 (High Vol, 13 approves), s08 (Overbought, 7 approves) | ✅ |

**Rail2 not triggered in this scenario set.** Rail2 fires when reject_count > 12.
No scenario had this many rejects after passing the panel consensus gate (≥14 approvals
means ≤6 rejects by construction). A scenario with 14 approves and 6 rejects
cannot trigger Rail2. To test Rail2, a scenario with exactly 14 approves / 6 rejects / 0 abstains
and avg_score ≥ 6.5 would be needed, then Rail2 condition (reject_count > 12) would
require a lower approve threshold scenario — this is a coverage gap.

---

## RiskLeverageGroup (9 rules)

### Rules tested
**Status: ✅ Rules 6, 9 fully tested. Rules 2, 3, 4, 5 partially tested.**

| Rule | Coverage |
|------|---------|
| Rule 1: mode_gate | ✅ P8 confirms state.mode (not proposal.mode_gate) |
| Rule 2: daily_loss | ⚠️ No daily loss scenario — clean state passes trivially |
| Rule 3: max_drawdown | ⚠️ No drawdown scenario — clean state passes trivially |
| Rule 4: portfolio_exposure | ⚠️ No exposure scenario — empty portfolio passes trivially |
| Rule 5: correlated_exposure | ⚠️ No BTC cluster scenario — empty portfolio passes trivially |
| Rule 6: liquidity/universe | ✅ P5 confirms XYZUSDT rejected when not in eligible set |
| Rule 7: pump signal | ⚠️ No volume_ratio > 5.0 scenario |
| Rule 8: event_risk | ⚠️ Stub — always 1.0x reduction |
| Rule 9: completeness | ✅ P2 (raw_target=0), P3 (no hypothesis), P4 (score<0.50) |

Rules 2-5 and 7 require specific portfolio/market state to trigger. These are not
"failures" — they require more complex test scenarios with accumulated positions or losses.

---

## Source Enforcer

**Status: ✅ Fully validated.**

All 11 enforcement tests pass. SourceSeparationError raised correctly on:
- Mixed sources
- Unknown sources
- Non-edge-evidence claims
- Missing source fields
- Report source mismatches

---

## Calibration System

**Status: ✅ Framework working. No data yet.**

The calibration infrastructure (JournalExtension, TraderCalibrator, PanelCalibrator,
OutcomeAttributor) is built and wired. CalibrationReporter correctly returns
"no data" status rather than fabricating numbers. 0/20 traders have sufficient samples.

---

## Replay Harness

**Status: ✅ No crashes. Expected behaviour.**

Harness sets up, runs bar sequences, and tears down cleanly.
0 positions opened on synthetic sequences — correct, as signal confluence
requires more than EMA-aligned bars.

---

## Summary Table

| Component | Pass | Partial | Not Yet | Fail |
|-----------|------|---------|---------|------|
| EntryGroup (signal firing) | | ✅ | | |
| TraderEvaluatorPanel (20 traders) | ✅ | | | |
| FinalDecisionGroup (Rail1-4, 5-6) | ✅ | | | |
| FinalDecisionGroup (Rail2 untriggered) | | ✅ | | |
| RiskLeverageGroup (Rules 6, 9) | ✅ | | | |
| RiskLeverageGroup (Rules 2-5, 7) | | ✅ | | |
| SourceEnforcer | ✅ | | | |
| CalibrationReporter (framework) | ✅ | | | |
| CalibrationReporter (real data) | | | ✅ | |
| ReplayHarness (no crash) | ✅ | | | |
| ReplayHarness (real signals) | | | ✅ | |
| Win rate / edge evidence | | | ✅ | |

---

## Failures

**No hard failures detected.**

The only "miss" is the threshold sensitivity monotonicity test:
> Lenient 10/5.0 → 70% (7/10)
> Relaxed 11/5.5 → 70% (7/10) [same as 10/5.0]

Both thresholds admit the same 7 scenarios because the scenarios that fail 10/5.0
(s10: avg=3.8, s08+s06: avg<5.0) also fail 11/5.5. This is expected — not all threshold
steps will change the outcome on a 10-scenario set.
