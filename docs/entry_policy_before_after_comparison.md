# Entry Policy Before/After Comparison

**Date:** 2026-03-28
**Phase:** 5.75

---

## Component Matrix

| Component / Threshold | Previous Behavior (Phase 5.5) | Root Cause | Repair Applied | New Behavior (Phase 5.75) | Evidence | Still Limited? |
|----------------------|-------------------------------|-----------|----------------|--------------------------|----------|----------------|
| **composite_score formula** | `raw_score / 1.0` — denominator always 1.0 regardless of active groups | Excluded groups (ChartPatternGroup 0.35 + HistorianAgent 0.10) penalized score implicitly | Normalize by `ACTIVE_COMPOSITE_WEIGHT_SUM = 0.55` | `raw_score / 0.55` — scale reflects active groups only | 8 candidates fired (0 before), all ≥ 0.50 | No — correct for Phase 3 |
| **composite_score ceiling** | **0.4875** — structurally below 0.50 threshold | Excluded weights in denominator but not numerator | ACTIVE_COMPOSITE_WEIGHT_SUM = sum of active weights | **0.8864** — 37.8% above threshold | `test_before_after_policy_ceiling_values` PASS | No — entries possible |
| **COMPOSITE_SCORE_THRESHOLD** | 0.50 | Design intent | **NOT CHANGED** | 0.50 | `test_composite_score_threshold_unchanged` PASS | No |
| **CandidateTradeEvent generation** | **0** events across 900 bars | composite_score always < 0.50 (ceiling 0.4875) | Normalization repair | **8** events across 900 bars (2+2+4 per fixture) | replay run results | Depends on signal quality |
| **Confirmation gate** | ≥2 signals same direction required | Design intent | NOT CHANGED | ≥2 signals same direction required | 5 of 13 crossovers filtered out (gate working) | No |
| **Panel evaluation (Layer B)** | Not reached (EntryGroup never fires) | composite_score ceiling blocked Layer A | Repair unblocks Layer A; panel untouched | Panel evaluates all 8 proposals; rejects all | `test_panel_still_evaluates_after_repair` PASS | **YES — second barrier** |
| **Panel APPROVE_THRESHOLD** | 14/20 required | Panel design | NOT CHANGED | 14/20 required | `test_panel_thresholds_unchanged` PASS | YES — Phase 3 gets ~9/20 |
| **Panel MIN_AVG_SCORE** | 6.5 required | Panel design | NOT CHANGED | 6.5 required | `test_panel_thresholds_unchanged` PASS | YES — Phase 3 gets ~5.9 |
| **Positions opened** | 0 | composite_score ceiling (Layer A) | Ceiling raised via normalization | Still 0 (Layer B rejects) | Replay: 0 positions | **YES — Layer B barrier** |
| **Risk gates (Layer C)** | Not reached | No entries | NOT CHANGED | Not reached (no panel approvals) | `test_risk_rule_completeness_gate_unchanged` PASS | YES — never reached yet |

---

## Narrative Summary

### Before Repair (Phase 5.5)

```
[Bar arrives]
  → IndicatorsGroup fires GroupSignalEvent
  → CandlestickGroup fires GroupSignalEvent
  → EntryGroup accumulates signals
  → Confirmation gate: ≥2 signals? YES (for some bars)
  → _compute_composite_score()
      raw_score = 0.25×cand + 0.20×ind + 0.10×struct = max 0.4875
      composite_score = 0.4875 / 1.0 = 0.4875
      threshold = 0.50
      0.4875 < 0.50 → BLOCKED
  → NO CandidateTradeEvent
  → Panel never reached
  → 0 positions, 0 trades
```

### After Repair (Phase 5.75)

```
[Bar arrives]
  → IndicatorsGroup fires GroupSignalEvent
  → CandlestickGroup fires GroupSignalEvent
  → EntryGroup accumulates signals
  → Confirmation gate: ≥2 signals? YES (for qualifying bars)
  → _compute_composite_score()
      raw_score = 0.25×cand + 0.20×ind + 0.10×struct (e.g. 0.3975)
      composite_score = 0.3975 / 0.55 = 0.7227
      threshold = 0.50
      0.7227 ≥ 0.50 → CandidateTradeEvent fires ✓
  → Panel evaluates BTCSetupProposal
      avg_score ≈ 5.9 (needs 6.5) → approvals ≈ 9/20 (needs 14)
      REJECTED → no position opened
  → Panel never reaches risk gates
  → 0 positions, but 8 candidates confirmed
```

---

## Score Formula Change (Code Level)

**Before (Phase 5.5):**
```python
composite_score = (
    0.35 * chart_pattern_quality
    + 0.25 * candlestick_quality
    + 0.20 * indicator_quality
    + 0.10 * structural_alignment
    + 0.10 * historian_win_rate
)
```

**After (Phase 5.75):**
```python
raw_score = (
    0.35 * chart_pattern_quality
    + 0.25 * candlestick_quality
    + 0.20 * indicator_quality
    + 0.10 * structural_alignment
    + 0.10 * historian_win_rate
)
composite_score = (
    raw_score / ACTIVE_COMPOSITE_WEIGHT_SUM
    if ACTIVE_COMPOSITE_WEIGHT_SUM > 0
    else 0.0
)
```

Where:
```python
_ACTIVE_SCORE_COMPONENTS: dict = {
    "indicator":   0.20,  # Phase 3
    "candlestick": 0.25,  # Phase 3
    "structural":  0.10,  # Phase 3
    # "chart_pattern": 0.35,  # Phase 4+
    # "historian":     0.10,  # Phase 4+
}
ACTIVE_COMPOSITE_WEIGHT_SUM: float = sum(_ACTIVE_SCORE_COMPONENTS.values())  # 0.55
```

---

## Barrier Chain: What Blocks Positions

```
Layer A (EntryGroup)     Layer B (Panel)          Layer C (Risk)
─────────────────────    ────────────────────────  ─────────────────────
Phase 5.5: BLOCKED       Not reached               Not reached
           (ceiling)

Phase 5.75: CLEARED      BLOCKED                   Not reached
            (repair)     (avg_score ~5.9 < 6.5,
                          approvals ~9 < 14)

Phase 4+   CLEARED       To be tested              To be tested
(projection) (ceiling    (critic_report +
              ~1.0)       historian_analog
                          should raise scores)
```

---

## What Was NOT Done (Honesty Check)

| Temptation | Action Taken |
|-----------|-------------|
| Lower COMPOSITE_SCORE_THRESHOLD from 0.50 to 0.45 | **Refused.** Threshold is correct; only scale was wrong. |
| Inject synthetic chart_pattern_quality > 0 | **Refused.** ChartPatternGroup is not implemented. |
| Force panel approvals (lower APPROVE_THRESHOLD) | **Refused.** Panel constants not touched. |
| Claim positions opened when none did | **Refused.** Zero positions documented honestly. |
| Remove confirmation gate requirement | **Refused.** Gate is a genuine quality filter. |

---

## Test Coverage (Phase 5.75)

22 new tests in `test_entry_policy_viability.py`, all passing:

| Category | Tests | Status |
|----------|-------|--------|
| Ceiling math | 4 | PASS |
| Normalization formula | 2 | PASS |
| Active components | 2 | PASS |
| Guard clauses | 1 | PASS |
| Replay candidates fire | 3 | PASS |
| Panel not bypassed | 2 | PASS |
| Risk unchanged | 2 | PASS |
| Before/after comparison | 3 | PASS |
| Panel as second barrier | 3 | PASS |
| **Total** | **22** | **22 PASS** |
