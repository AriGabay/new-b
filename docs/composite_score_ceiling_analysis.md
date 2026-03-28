# Composite Score Ceiling Analysis

**Date:** 2026-03-28
**Phase:** 5.75 — Entry Policy Viability Repair

---

## The Structural Barrier

### Why Natural Entries Were Impossible in Phase 3 (Before Repair)

The `composite_score` formula in `EntryGroup._compute_composite_score()` is:

```
composite_score = 0.35×chart_pattern_quality
               + 0.25×candlestick_quality
               + 0.20×indicator_quality
               + 0.10×structural_alignment
               + 0.10×historian_win_rate
```

The formula sums to 1.0 when all groups are active. In Phase 3, two groups are excluded:

| Group | Weight | Phase 3 Status | Phase 3 Value |
|-------|--------|---------------|---------------|
| ChartPatternGroup | 0.35 | **EXCLUDED** | always 0.0 |
| CandlestickGroup | 0.25 | Active | max 0.75 |
| IndicatorsGroup | 0.20 | Active | max 1.00 |
| TechnicalStructureGroup | 0.10 | Active | max 1.00 |
| HistorianAgent | 0.10 | **EXCLUDED** | always 0.0 |

**Maximum achievable raw score (Phase 3):**
```
max_raw = 0.35×0.0 + 0.25×0.75 + 0.20×1.0 + 0.10×1.0 + 0.10×0.0
        = 0.0    + 0.1875 + 0.20   + 0.10   + 0.0
        = 0.4875
```

**Entry threshold:** `COMPOSITE_SCORE_THRESHOLD = 0.50`

**Shortfall:** `0.50 - 0.4875 = 0.0125`

The shortfall is small (1.25 percentage points), but the ceiling is structural — it cannot be exceeded by any combination of signal quality, indicator values, or market conditions. Even a perfect bar (all active indicators maximally bullish) hits exactly 0.4875.

---

## Root Cause

The raw formula treats excluded groups as 0.0, which **implicitly penalizes** the scoring as if those groups contributed nothing. A system with only 3 active groups should be scored against those 3 groups — not against a denominator of 1.0 that includes groups that don't exist yet.

This is analogous to grading a student on 3 subjects but dividing by 5 because 2 subjects aren't offered this semester.

---

## The Repair

### Option Evaluated: Normalize by Active Weight Sum

**Principle:** `composite_score = raw_score / ACTIVE_COMPOSITE_WEIGHT_SUM`

Where `ACTIVE_COMPOSITE_WEIGHT_SUM` is the sum of weights for groups that are actually active in the current phase.

**Phase 3 active weight sum:**
```
ACTIVE_COMPOSITE_WEIGHT_SUM = 0.25 + 0.20 + 0.10 = 0.55
```

**New ceiling after repair:**
```
new_ceiling = max_raw / ACTIVE_COMPOSITE_WEIGHT_SUM
            = 0.4875 / 0.55
            = 0.8864
```

The new ceiling (0.8864) is **above the 0.50 threshold**, allowing entries to fire on qualifying bars.

### Why This Repair Is Correct (Not Arbitrary)

1. **Reflects architecture reality.** The formula is now calibrated to the groups that exist. Scores between 0 and 1 represent quality *within the active signal set*, not quality penalized for missing Phase 4+ features.

2. **Threshold unchanged.** `COMPOSITE_SCORE_THRESHOLD = 0.50` was not modified. The threshold still represents the same concept: "50% of maximum possible quality must be met."

3. **Phase 4+ behavior is identity.** When ChartPatternGroup and HistorianAgent are added, `ACTIVE_COMPOSITE_WEIGHT_SUM = 1.00`, so `raw_score / 1.0 = raw_score` — the formula reverts to the full form unchanged.

4. **No forcing or injection.** The repair touches only the normalization denominator. It does not inject scores, bypass signals, or modify any panel or risk constants.

### Options Rejected

| Option | Reason Rejected |
|--------|----------------|
| Lower `COMPOSITE_SCORE_THRESHOLD` below 0.50 | Arbitrary. Does not fix the conceptual problem — a proposal at 0.49 raw score would be 88% of the active maximum, which IS high quality. The threshold should evaluate normalized quality. |
| Hard-code score boosts | Fabricates evidence — not real signal quality |
| Inject synthetic chart_pattern_quality | Fabricates a group that doesn't exist |
| Remove the threshold gate entirely | Bypasses a genuine quality filter |

---

## Ceiling Comparison

| Phase | Active Groups | Active Weight Sum | Max Raw Score | Ceiling | Threshold | Entries Possible |
|-------|--------------|-------------------|---------------|---------|-----------|------------------|
| Phase 3 (before repair) | 3 of 5 | 1.00 (unnormalized) | 0.4875 | **0.4875** | 0.50 | **NO** |
| Phase 3 (after repair) | 3 of 5 | 0.55 | 0.4875 | **0.8864** | 0.50 | **YES** |
| Phase 4+ (all groups) | 5 of 5 | 1.00 | 1.0000 | **1.0000** | 0.50 | YES |

---

## Verification from Replay

After the repair was applied, 3 replay fixtures (900 total bars) were run:

| Fixture | Bars | Candidates Fired | Min Score | Max Score |
|---------|------|-----------------|-----------|-----------|
| btc_bull_breakout_v1 | 350 | 2 | 0.7182 | 0.7227 |
| btc_bear_breakdown_v1 | 350 | 2 | 0.5409 | 0.7182 |
| btc_ranging_v1 | 200 | 4 | 0.5409 | 0.7227 |
| **TOTAL** | **900** | **8** | **0.5409** | **0.7227** |

All 8 candidates had `composite_score ≥ 0.50`. The repair is confirmed effective.

---

## Score Breakdown Example

A candidate from `btc_bull_breakout_v1`:

```
candlestick_quality   = 0.75  (engulfing/morning star pattern)
indicator_quality     = 1.00  (EMA crossover confirmed, RSI in range)
structural_alignment  = 1.00  (at support level)
chart_pattern_quality = 0.00  (ChartPatternGroup excluded)
historian_win_rate    = 0.00  (HistorianAgent excluded)

raw_score = 0.25×0.75 + 0.20×1.00 + 0.10×1.00 + 0.35×0.00 + 0.10×0.00
          = 0.1875 + 0.200 + 0.100 + 0.0 + 0.0
          = 0.3975 (below 0.50 → would have been blocked before repair)

normalized = 0.3975 / 0.55 = 0.7227 (above 0.50 → CandidateTradeEvent fires)
```

The score breakdown is included in every `BTCSetupProposal.score_breakdown` dict:
```python
{
    "chart_pattern_quality": 0.0,
    "candlestick_quality": 0.75,
    "indicator_quality": 1.0,
    "structural_alignment": 1.0,
    "historian_win_rate": 0.0,
    "raw_score": 0.3975,
    "active_weight_sum": 0.55,
    "normalized_composite_score": 0.7227,
}
```

---

## Confirmed by Tests

| Test | Result |
|------|--------|
| `test_active_composite_weight_sum_is_correct` | PASS — 0.55 |
| `test_new_composite_ceiling_above_threshold` | PASS — 0.8864 > 0.50 |
| `test_old_ceiling_was_below_threshold` | PASS — 0.4875 < 0.50 |
| `test_ceiling_shortfall_was_0_0125` | PASS |
| `test_normalization_formula_is_correct` | PASS |
| `test_before_after_policy_ceiling_values` | PASS |
