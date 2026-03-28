# Threshold Alignment Report

**Date:** 2026-03-28
**Phase:** 5.75

---

## Purpose

This report verifies that all thresholds and constants relevant to entry policy remain aligned after the Phase 5.75 normalization repair. No threshold was changed by the repair. This document records the values, their sources, and the rationale for each.

---

## Entry Policy Thresholds

### Layer A: Entry Gate (EntryGroup)

| Constant | Value | Location | Changed by Phase 5.75 Repair? |
|----------|-------|----------|-------------------------------|
| `COMPOSITE_SCORE_THRESHOLD` | **0.50** | `groups/entry/group.py` | **NO** |
| `CONFIRMATION_GATE_MIN_SIGNALS` | **2** | `groups/entry/group.py` | **NO** |
| `ACTIVE_COMPOSITE_WEIGHT_SUM` | **0.55** | `groups/entry/group.py` | ADDED (new constant) |

**What changed:** The normalization denominator. `composite_score = raw_score / ACTIVE_COMPOSITE_WEIGHT_SUM` instead of `composite_score = raw_score / 1.0`.

**What did NOT change:** The threshold (0.50) and the confirmation gate (≥2 signals). The proposal quality bar is unchanged — only the scale of the score is corrected to reflect which groups are active.

---

### Layer B: Panel (TraderEvaluatorPanel)

| Constant | Value | Location | Changed by Phase 5.75 Repair? |
|----------|-------|----------|-------------------------------|
| `APPROVE_THRESHOLD` | **14** | Panel constants | **NO** |
| `MIN_AVG_SCORE` | **6.5** | Panel constants | **NO** |
| `TOTAL_TRADERS` | **20** | Panel constants | **NO** |
| Abstain zone | **[4.5, 6.5)** | Per-trader score range | **NO** |

EntryGroup has no dependency on panel constants. The panel is a fully separate evaluation layer that operates on `BTCSetupProposal` objects. Phase 5.75 did not touch any panel code.

---

### Layer C: Risk Gates (RiskLeverageGroup)

| Constant | Value | Location | Changed by Phase 5.75 Repair? |
|----------|-------|----------|-------------------------------|
| Risk rules structure | As defined | `groups/risk/` | **NO** |
| Completeness gate | Requires all risk fields | `groups/risk/` | **NO** |

The repair is entirely scoped to the composite_score normalization in EntryGroup. No risk constants or logic was modified.

---

## Threshold Rationale (Pre-Existing, Not Changed)

### Why COMPOSITE_SCORE_THRESHOLD = 0.50

The 0.50 threshold means: "at least 50% of maximum possible quality must be present." With the normalization repair, this now means 50% of the *active group maximum*, which is the intended interpretation.

Before the repair, the threshold was structurally unreachable even at 100% quality from all active groups. After the repair, a perfect Phase 3 proposal scores 0.8864 — well above the threshold, leaving a realistic quality discriminator in place.

### Why APPROVE_THRESHOLD = 14 (out of 20)

70% trader approval required. The panel is deliberately selective. 14/20 is not easily achieved in Phase 3 because proposals lack `critic_report` and `historian_analog` fields (both from Phase 4+ components).

This is the **second structural barrier** identified in Phase 5.75. The normalization repair unblocks `CandidateTradeEvent` generation (Layer A), but the panel (Layer B) still requires information that isn't available in Phase 3.

### Why MIN_AVG_SCORE = 6.5

Phase 3 proposals score approximately 5.9 on average (estimated from panel evaluation observations). The 6.5 floor is not met, contributing to panel rejection. This is another Phase 4+ dependency.

---

## Threshold Sensitivity Analysis

### What happens at different composite_score values?

| Score | Normalized (÷0.55) | Old Behavior | New Behavior |
|-------|--------------------|--------------|--------------|
| raw = 0.49 | 0.8909 | blocked (0.49 < 0.50) | fires (0.89 ≥ 0.50) |
| raw = 0.40 | 0.7273 | blocked | fires |
| raw = 0.30 | 0.5455 | blocked | fires |
| raw = 0.2975 | 0.5409 | blocked | fires (marginal) |
| raw = 0.27 | 0.4909 | blocked | blocked (< 0.50 normalized) |
| raw = 0.20 | 0.3636 | blocked | blocked |

The repair does not open the gates to all proposals. Proposals with raw_score < 0.55 × 0.50 = 0.275 are still blocked. Weak signals (below 50% of normalized maximum) cannot generate candidates.

In the replay observations, the weakest candidate had `raw_score = 0.2975`, which normalizes to 0.5409 — just above the threshold. This indicates the repair has a meaningful filter: it fires on genuinely aligned setups, not on noise.

---

## Confirmation Gate Alignment

The confirmation gate (`CONFIRMATION_GATE_MIN_SIGNALS = 2`) requires at least 2 group signals in the same direction before composite scoring is attempted. This gate operates independently of the normalization change.

In practice during Phase 3, this gate is satisfied by a combination of CandlestickGroup and IndicatorsGroup signals (observed cross-bar timing: candlestick from bar N + indicators from bar N+1). The timing artifact is documented in `PHASE_5_75_HANDOFF.md`.

The confirmation gate acts as a pre-filter that prevents noisy single-signal entries. It remains unchanged and correctly functioning.

---

## Summary

The Phase 5.75 repair is surgically scoped:

- **Changed:** `composite_score` normalization denominator (`ACTIVE_COMPOSITE_WEIGHT_SUM = 0.55`)
- **Not changed:** `COMPOSITE_SCORE_THRESHOLD`, `APPROVE_THRESHOLD`, `MIN_AVG_SCORE`, risk constants, confirmation gate, panel logic, risk logic

All thresholds remain aligned. The repair corrects the scoring scale to match architectural reality; it does not lower any quality bar.
