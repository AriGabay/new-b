# Panel Threshold Sensitivity Analysis

**Source:** `sensitivity_analysis_only` (non-production analysis — NOT edge evidence)
**Date:** 2026-03-28
**Basis:** 10 panel evaluation records (event_driven_runtime_simulation)
**Method:** Re-evaluating PanelResult approve_count/avg_score against 8 threshold scenarios

---

## ⚠️ Critical Disclaimer

**This analysis does NOT mutate production thresholds.**

`TraderEvaluatorPanel.APPROVE_THRESHOLD` (14) and `TraderEvaluatorPanel.MIN_AVG_SCORE` (6.5)
are read-only constants. This analysis only asks: *"How would enter/hold rates change
if we had chosen different thresholds?"*

Results labeled `sensitivity_analysis_only` must NOT be used as edge evidence.
No threshold changes should be made from this analysis alone.

---

## Results (10 scenarios)

| Label | Threshold | Min Avg | Enter | Hold | Rate | Note |
|-------|-----------|---------|-------|------|------|------|
| Lenient_10/5.0 | 10/20 | 5.0 | 7 | 3 | 70.0% | sensitivity_analysis_only |
| Relaxed_11/5.5 | 11/20 | 5.5 | 7 | 3 | 70.0% | sensitivity_analysis_only |
| Moderate_12/6.0 | 12/20 | 6.0 | 6 | 4 | 60.0% | sensitivity_analysis_only |
| Moderate_13/6.0 | 13/20 | 6.0 | 5 | 5 | 50.0% | sensitivity_analysis_only |
| **PRODUCTION_14/6.5** | **14/20** | **6.5** | **3** | **7** | **30.0%** | **← PRODUCTION THRESHOLD (not mutated)** |
| Strict_15/7.0 | 15/20 | 7.0 | 1 | 9 | 10.0% | sensitivity_analysis_only |
| VeryStrict_16/7.0 | 16/20 | 7.0 | 0 | 10 | 0.0% | sensitivity_analysis_only |
| Extreme_18/7.5 | 18/20 | 7.5 | 0 | 10 | 0.0% | sensitivity_analysis_only |

---

## Interpretation

**Production threshold (14/6.5) produces 3/10 enters (30.0%) on this scenario set.**

Relaxing to 10/20 + avg≥5.0 would add 4 more enters (+40% of batch).

Tightening to 18/20 + avg≥7.5 would remove 3 enters (−30% of batch).

**WARNING:** Production threshold is highly restrictive (<20% enter rate on low-consensus scenarios).
This may be correct risk management, or thresholds may need recalibration
once real trade outcomes are available.

---

## What the Threshold Range Reveals

### 10-11/20 ("Lenient" band) — 70% enter rate
These scenarios would allow:
- s07 (Mean Reversion, 12 approves, avg=6.6): would enter
- s08 (Overbought, 7 approves) and s06 (Ranging, 4 approves): still held by avg_score < 5.0
- Lenient band is not reckless on this scenario set — the avg_score filter still blocks poor quality

### 12-13/20 ("Moderate" band) — 50-60% enter rate
- At 12/20: Mean Reversion (12 approves, avg=6.6) enters
- At 13/20: High Vol scenario (13 approves, avg=7.0) would panel-pass (Rail6 still blocks it in FinalDecision)
- This band is consistent with a moderately selective system

### 14/6.5 (PRODUCTION) — 30% enter rate
- Correctly excludes Mean Reversion (12/20) and High Vol (13/20, blocked anyway by Rail6)
- Admits Ideal Bull, Ideal Bear, Excellent R:R — the highest quality scenarios
- Bear Macro LONG passes panel (14/20) but is blocked by FinalDecisionGroup Rail5

### 15-18/20 ("Strict" and above) — 0-10% enter rate
- 15/20: Only s09 (Excellent R:R, 15 approves) enters
- 16/20 and above: No entries in this scenario set
- These thresholds would be unusably restrictive in practice

---

## Comparison: Panel Threshold vs Safety Rails

This analysis varies **panel consensus thresholds only**.
FinalDecisionGroup safety rails (R1-R6) are applied on top and are **NOT varied**.

Example: Bear Macro LONG (s03) has 14/20 approvals and avg=6.5 — it passes the panel threshold
at every scenario in this analysis. But Rail5 blocks it regardless. The safety rails add
an independent layer of protection that the panel threshold cannot replicate.

---

## Production Threshold Calibration Note

The production threshold (14/20, avg≥6.5) was set conservatively before any real trade data.
Recalibration should only happen after observing:
- Minimum 30 closed trades under `event_driven_runtime_replay`
- Win rates segmented by approve_count band
- Whether high-approve-count trades outperform borderline-approve trades

**Until then: do not change the production threshold.** These sensitivity numbers
reflect filtering rates on 10 constructed scenarios, not real edge evidence.
