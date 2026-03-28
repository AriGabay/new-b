# Phase 5.75 — Entry Policy Viability Audit

**Date:** 2026-03-28
**Phase:** 5.75 — Entry Policy Viability Repair

---

## Audit Questions and Answers

### Q1: Why can no natural entries fire in Phase 3?

**Answer:** The `composite_score` formula in `EntryGroup._compute_composite_score()` uses a fixed denominator of 1.0, which assumes all 5 signal groups are active. In Phase 3, `ChartPatternGroup` (weight 0.35) and `HistorianAgent` (weight 0.10) are excluded — they always contribute 0.0. The maximum achievable raw score is therefore:

```
max_raw = 0.25×0.75 + 0.20×1.0 + 0.10×1.0 = 0.4875
```

`COMPOSITE_SCORE_THRESHOLD = 0.50`. The ceiling (0.4875) is below the threshold (0.50) by 0.0125. This gap cannot be crossed regardless of signal quality.

---

### Q2: Is this a bug or a design choice?

**Answer:** It is a **design gap** — not an intentional constraint. The formula was written for a complete 5-group system, then applied in a phase where only 3 groups exist. The formula was never updated to reflect Phase 3 scope. The threshold of 0.50 was intended to mean "50% of maximum possible quality." Without normalization, it silently means "50% of maximum possible quality *if all groups were active*" — a standard that was impossible to meet.

---

### Q3: What is the correct repair?

**Answer:** Normalize the raw score by the sum of weights for active groups only:

```python
composite_score = raw_score / ACTIVE_COMPOSITE_WEIGHT_SUM
```

Where `ACTIVE_COMPOSITE_WEIGHT_SUM = sum({candlestick: 0.25, indicator: 0.20, structural: 0.10}) = 0.55`.

This preserves the intent of the 0.50 threshold (≥50% of achievable quality) while correctly calibrating "achievable quality" to the groups that exist.

---

### Q4: Does the repair lower the quality bar?

**Answer:** No. The threshold remains at 0.50. A proposal still needs to demonstrate 50% of the maximum achievable quality from active groups. A perfect Phase 3 proposal (all indicators aligned, best pattern, at structural level) now scores 0.8864 — meaning the quality bar is meaningful and non-trivial. Weak proposals (raw score < 0.275) are still blocked.

---

### Q5: Does the repair bypass the panel or risk gates?

**Answer:** No. The normalization change is scoped to `_compute_composite_score()` in EntryGroup. The panel (`TraderEvaluatorPanel`) and risk gates (`RiskLeverageGroup`) are downstream components that receive `BTCSetupProposal` objects. Their constants were not touched:

- `APPROVE_THRESHOLD = 14` (unchanged)
- `MIN_AVG_SCORE = 6.5` (unchanged)
- Risk rule structure (unchanged)

Tests `test_panel_still_evaluates_after_repair` and `test_risk_rule_completeness_gate_unchanged` confirm this.

---

### Q6: Do natural entries fire after the repair?

**Answer (precise):** **CandidateTradeEvents fire.** 8 candidates fired across 900 bars in the post-repair replay. All had `composite_score ≥ 0.50`.

**Positions do NOT open.** The panel (Layer B) rejects all 8 proposals. This is a separate structural barrier.

"Natural entry" in the full sense (position open → risk evaluated → position managed) requires clearing all three layers. Phase 5.75 cleared Layer A. Layer B remains blocked.

---

### Q7: Why does the panel reject Phase 3 proposals?

**Answer:** Phase 3 proposals are `BTCSetupProposal` objects with `critic_report = None` and `historian_analog = None`. Multiple traders in the panel downgrade proposals with missing analyst context. The combined effect:

- `avg_score ≈ 5.9` (threshold: 6.5) — below `MIN_AVG_SCORE`
- `approvals ≈ 9/20` (threshold: 14) — below `APPROVE_THRESHOLD`
- `abstentions ≈ 7/20` — traders in the 4.5–6.5 abstain zone who don't approve without analyst context

Both conditions must be met simultaneously; neither is. This is the second structural barrier.

---

### Q8: Can the panel barrier be fixed in Phase 5.75?

**Answer:** No, and it should not be. The panel barrier requires Phase 4+ components:
- `CriticAgent` → populates `critic_report`
- `HistorianAgent` → populates `historian_analog`

These components provide genuine information that raises proposal quality. Lowering `APPROVE_THRESHOLD` or `MIN_AVG_SCORE` without providing real context would be fabricating approval. The panel barrier is documented as a known limitation, not fixed.

---

### Q9: Is there a cross-bar timing artifact in signal accumulation?

**Answer:** Yes, documented. CandlestickGroup fires `GroupSignalEvent` *after* IndicatorsGroup in the same bar's event processing. When EntryGroup evaluates on the indicators event, the candlestick event from the current bar has not yet been received. The typical accumulation pattern is:

- Bar N: CandlestickGroup signal received (buffered)
- Bar N+1: IndicatorsGroup signal received → confirmation gate ≥2 → score computed

This means a 2-bar confirmation window is effectively in use. The candlestick pattern sets up the precondition; the next bar's indicators confirm it. This is an architectural timing artifact, not a correctness bug. It is more selective than intended (requires two bars rather than one) but does not fabricate signals.

---

### Q10: What changed in production code?

**Answer:** One method in one file:

**`src/groups/entry/group.py`:**
- Added `_ACTIVE_SCORE_COMPONENTS` dict (new constant documenting active groups)
- Added `ACTIVE_COMPOSITE_WEIGHT_SUM` constant (0.55)
- Modified `_compute_composite_score()` to compute `raw_score` separately, then divide by `ACTIVE_COMPOSITE_WEIGHT_SUM`
- Updated docstring to document Phase 3 normalization math and Phase 4+ behavior

No other production files were changed.

---

## Phase 5.75 Audit Summary

| Audit Item | Finding | Status |
|-----------|---------|--------|
| Reason for zero entries (Phase 3) | composite_score ceiling 0.4875 < 0.50 threshold | IDENTIFIED |
| Root cause | Unnormalized denominator + excluded groups = implicit penalty | IDENTIFIED |
| Repair type | Normalization by active weight sum | APPLIED |
| Repair justification | Reflects architecture reality; threshold intent preserved | SOUND |
| Threshold changed | NO — COMPOSITE_SCORE_THRESHOLD remains 0.50 | CONFIRMED |
| Panel bypassed | NO — APPROVE_THRESHOLD and MIN_AVG_SCORE unchanged | CONFIRMED |
| Risk bypassed | NO — RiskLeverageGroup untouched | CONFIRMED |
| Candidates fire after repair | YES — 8 events across 900 bars | CONFIRMED |
| Positions open after repair | NO — panel is second barrier | DOCUMENTED |
| Second barrier identified | YES — panel requires Phase 4+ components | DOCUMENTED |
| Tests passing | 22/22 new + 192/192 total | CONFIRMED |
