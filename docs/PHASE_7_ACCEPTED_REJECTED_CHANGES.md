# PHASE 7 ACCEPTED / REJECTED CHANGES
**Date:** 2026-03-29

---

## ACCEPTED CHANGES

### A1: Bug Fix — trader_name in trader_reviews (ACCEPTED)
- **Reason:** Correctness bug. trader_id was never read; all traders stored as "unknown".
- **Risk:** None — no parameter change, only data fidelity fix.
- **Regression:** 402/402 tests pass.

### A2: Bug Fix — trader_calibration population (ACCEPTED)
- **Reason:** Correctness bug. Calibration updates silently skipped.
- **Risk:** None — no parameter change, enables future data-driven tuning.
- **Regression:** 402/402 tests pass.

### A3: Docstring Fix — runner.py ChartPatternGroup (ACCEPTED)
- **Reason:** Documentation was materially wrong (said EXCLUDED, code is active).
- **Risk:** None.

### A4: Console test list update (ACCEPTED)
- **Reason:** Console was missing Phase 6.x and Phase 7 test files.
- **Risk:** None.

---

## REJECTED / DEFERRED CHANGES

### R1: Lower APPROVE_THRESHOLD from 14 to 13 (DEFERRED)
- **Hypothesis:** 4 near-miss fixtures at 13/20 would start entering.
- **Reason for deferral:** All 34 existing trades are losses. More entries would mean more
  losses. No evidence that 13/20 setups are better than current 14/20 setups. Will revisit
  after accumulating win/loss data at both approval levels.

### R2: Lower AVG_SCORE_THRESHOLD from 6.5 to 6.0 (DEFERRED)
- **Hypothesis:** Would allow more borderline proposals through.
- **Reason for deferral:** Same as R1. No outcome evidence supports loosening.

### R3: Rebalance EntryGroup composite weights (DEFERRED)
- **Hypothesis:** Current 0.25/0.20/0.10 split may underweight structural alignment.
- **Reason for deferral:** The composite_score formula works correctly (verified by fixture
  tests). Changing weights affects which proposals reach the panel. Without knowing which
  proposals succeed vs fail in practice, rebalancing is premature.

### R4: Modify evaluator scoring logic (DEFERRED)
- **Hypothesis:** Some evaluators may be miscalibrated.
- **Reason for deferral:** trader_calibration was empty until the bug fix. No per-evaluator
  outcome data exists yet. Must accumulate 50+ outcomes first.

### R5: Tighten trailing stop from 2*ATR to 1.5*ATR (DEFERRED)
- **Hypothesis:** Tighter trailing stop might reduce loss magnitude.
- **Reason for deferral:** All 34 trades exit via stop_loss, never reaching +1R (trailing
  activation threshold). Changing the trailing ATR multiplier would have zero effect on
  current outcomes. The issue is that positions never reach +1R, not that trailing is wrong.
  Need to investigate why entries consistently move against the position immediately.
