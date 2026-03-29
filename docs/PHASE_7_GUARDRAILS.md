# PHASE 7 GUARDRAILS
**Date:** 2026-03-29

These rules are non-negotiable during Phase 7 tuning work.

---

## RULE 1: One Category at a Time

Never change parameters from two different categories in the same pass.
Categories: entry weights, panel thresholds, safety rails, risk sizing, exit params, evaluator logic.

## RULE 2: Re-run Baseline After Every Change

Run `pytest tests/test_phase_7_baseline.py -v` after every parameter change.
If any test fails, the change is rejected or the test must be deliberately updated
with documented justification.

## RULE 3: ACTIVE_COMPOSITE_WEIGHT_SUM Must Match

If you change entry weight values in `_ACTIVE_SCORE_COMPONENTS`, you MUST update
`ACTIVE_COMPOSITE_WEIGHT_SUM` to equal the sum of active weights. Failure causes
composite_score normalization errors.

## RULE 4: V1 Must Continue to Hold

btc_w_bottom_long_v1 must NOT approve. It is the regression anchor.
If a tuning change causes V1 to enter, the change is wrong — it has weakened
the discrimination ability of the panel.

## RULE 5: No Threshold Changes Without Outcome Evidence

APPROVE_THRESHOLD (14) and AVG_SCORE_THRESHOLD (6.5) must not be changed
until at least 50 closed trades exist with a non-zero win rate. Currently
all 34 existing trades are losses. Loosening thresholds would make this worse.

## RULE 6: Source Separation Must Hold

Run `pytest tests/test_validation.py::test_source_separation_no_backtest_mixed_with_runtime`
after every change. backtest and runtime outcomes must never be mixed.

## RULE 7: Safety Rails Cannot Be Removed

FinalDecisionGroup's 6 safety rails can be adjusted but never removed entirely.
Minimum R:R must stay >= 1.0. min_avg_score must stay >= 4.0.

## RULE 8: No Evaluator Changes Without Calibration Data

The trader_calibration table was empty until the bugs were fixed in this session.
Do not change evaluator scoring logic until the calibration pipeline has accumulated
meaningful per-trader outcome data (>= 50 trades).

## RULE 9: Document Every Change

Every tuning change must be recorded in PHASE_7_TUNING_LOG.md with:
- Hypothesis
- Parameter changed (before → after)
- Baseline results before
- Baseline results after
- Accept / Reject decision
- Reason

## RULE 10: Do Not Claim Edge from Small Samples

Do not declare a parameter change "improves performance" based on fewer than 30
independent trade outcomes. Fixture replay results show whether the pipeline behaves
correctly, not whether it is profitable.
