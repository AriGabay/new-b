# Phase 5.75 Handoff Document

**Date:** 2026-03-28
**Phase:** 5.75 — Entry Policy Viability Repair
**Prior phase:** 5.5 — Real Runtime Replay Validation

---

## What Was Built

Phase 5.75 performed a full viability audit of the entry policy and repaired the structural blocker that prevented any natural entries in Phase 3. No panel constants, risk constants, or downstream components were modified.

### Modified Files

| File | Change |
|------|--------|
| `src/groups/entry/group.py` | Added `_ACTIVE_SCORE_COMPONENTS` dict, `ACTIVE_COMPOSITE_WEIGHT_SUM` constant, normalized `_compute_composite_score()` by active weight sum |

### New Files

| File | Purpose |
|------|---------|
| `src/tests/test_entry_policy_viability.py` | 22 tests covering ceiling math, normalization, replay candidates, panel selectivity, second barrier |

### New Documentation Files

| File | Contents |
|------|---------|
| `docs/PHASE_5_75_ENTRY_POLICY_VIABILITY.md` | Full viability audit — 10 questions, 10 answers |
| `docs/composite_score_ceiling_analysis.md` | Ceiling math, before/after, repair justification |
| `docs/active_group_scoring_contribution_report.md` | Per-group weight, contribution, normalized ceiling |
| `docs/threshold_alignment_report.md` | All thresholds — what changed vs what didn't |
| `docs/post_repair_replay_results.md` | 900-bar replay with 8 candidates, zero positions |
| `docs/entry_policy_before_after_comparison.md` | Component matrix + narrative + code diff |
| `docs/PHASE_5_75_HANDOFF.md` | This document |

---

## Test Status

**192 tests passing** (170 from Phase 5/5.5 + 22 from Phase 5.75).

```
$ cd src && python -m pytest tests/ -q
192 passed in 4.04s
```

22 new tests in `test_entry_policy_viability.py`: **22/22 PASS**

---

## Why Natural Entries Were Impossible Before This Phase

The `composite_score` formula:
```
composite_score = 0.35×chart_pattern + 0.25×candlestick + 0.20×indicator + 0.10×structural + 0.10×historian
```

In Phase 3, `chart_pattern = 0.0` (ChartPatternGroup excluded) and `historian = 0.0` (HistorianAgent excluded). The formula treated these as zero contributions in a denominator-of-1.0 formula. Maximum achievable score:

```
max_raw = 0.25×0.75 + 0.20×1.0 + 0.10×1.0 = 0.4875
```

`COMPOSITE_SCORE_THRESHOLD = 0.50`. Shortfall: 0.0125. This ceiling was structural — no signal quality, no market condition, no bar data could raise the ceiling above 0.4875.

**Result:** Zero `CandidateTradeEvent`s. Zero panel evaluations. Zero positions. This was confirmed across 900 replay bars in Phase 5.5.

---

## What Was Repaired

One change to one method in one file.

### `EntryGroup._compute_composite_score()` — normalization added

**Added constants:**
```python
_ACTIVE_SCORE_COMPONENTS: dict = {
    "indicator":        0.20,   # Phase 3
    "candlestick":      0.25,   # Phase 3
    "structural":       0.10,   # Phase 3
    # "chart_pattern":  0.35,   # Phase 4+
    # "historian":      0.10,   # Phase 4+
}
ACTIVE_COMPOSITE_WEIGHT_SUM: float = sum(_ACTIVE_SCORE_COMPONENTS.values())  # 0.55
```

**Modified formula:**
```python
# Before:
composite_score = raw_score  # implicit / 1.0

# After:
composite_score = raw_score / ACTIVE_COMPOSITE_WEIGHT_SUM if ACTIVE_COMPOSITE_WEIGHT_SUM > 0 else 0.0
```

**Effect on ceiling:**
```
new_ceiling = 0.4875 / 0.55 = 0.8864
```

0.8864 is above 0.50. Entries can now fire on qualifying bars.

**Justification:** The repair reflects architecture reality. A system with 3 active groups should score candidates against those 3 groups, not against a 5-group denominator that includes groups which don't exist yet. The threshold (0.50) remains the same semantic concept: "50% of achievable quality from active groups."

---

## Whether Natural Entries Now Occur

**CandidateTradeEvents: YES — 8 across 900 bars**

After the repair, 8 candidates fired across the 3 BTC replay fixtures:

| Fixture | Bars | Candidates | Score Range |
|---------|------|------------|-------------|
| btc_bull_breakout_v1 | 350 | 2 | 0.7182–0.7227 |
| btc_bear_breakdown_v1 | 350 | 2 | 0.5409–0.7182 |
| btc_ranging_v1 | 200 | 4 | 0.5409–0.7227 |
| **TOTAL** | **900** | **8** | **0.5409–0.7227** |

All 8 candidates had `composite_score ≥ 0.50`.

**Positions opened: NO — 0 positions across all fixtures**

The panel (Layer B, `TraderEvaluatorPanel`) rejected all 8 proposals. This is the second structural barrier.

---

## Whether the Repaired Policy Is Viable or Still Limited

**Layer A (EntryGroup): VIABLE** — ceiling raised from 0.4875 to 0.8864. Candidates fire on real signal setups. The confirmation gate (≥2 signals) still filters out noise — 5 of 13 crossovers did not generate candidates.

**Layer B (Panel): STILL LIMITED** — Phase 3 proposals are rejected because:
1. `critic_report = None` → traders downgrade proposals without analyst context → `avg_score ≈ 5.9` (needs ≥ 6.5)
2. `historian_analog = None` → traders abstain without historical analog → `approvals ≈ 9/20` (needs ≥ 14)

This is not a bug. The panel is supposed to be selective. It requires real analyst context that Phase 4+ components provide.

**Layer C (Risk): UNTESTED** — never reached. No panel approvals → no risk evaluation.

**Conclusion:** The repaired entry policy is architecturally viable. The pipeline now reaches the panel on qualifying bars. Full position lifecycle requires Phase 4+ components to satisfy the panel.

---

## What Remains Before Serious Paper-Performance Observation

1. **Phase 4: Implement ChartPatternGroup**
   - Adds 0.35 weight to the active components
   - `ACTIVE_COMPOSITE_WEIGHT_SUM` updates to 0.90
   - Proposals become richer; more candidates may fire
   - More importantly: Phase 4 activates CriticAgent which populates `critic_report`

2. **Phase 4: Implement CriticAgent**
   - Populates `critic_report` in BTCSetupProposal
   - Raises panel trader scores from ~5.9 toward ≥6.5
   - First real chance at panel approval

3. **Phase 4: Implement HistorianAgent**
   - Populates `historian_analog` in BTCSetupProposal
   - Further raises trader approval count from ~9 toward ≥14
   - Adds 0.10 weight to active components (ACTIVE_COMPOSITE_WEIGHT_SUM → 1.0)

4. **First natural position open**
   - After CriticAgent + HistorianAgent active, panel should approve qualified setups
   - First real layer A → B → C → position lifecycle

5. **Collect ≥30 closed trades**
   - Enables CalibrationReporter with real win rate / expectancy
   - First valid edge evidence from `event_driven_runtime_replay` source

6. **Verify ExitGroup closes positions**
   - After first open, confirm stop/target logic closes positions as expected

---

## What Must Not Be Misrepresented

- **8 candidates ≠ 8 positions.** All were rejected by the panel.
- **Normalization ≠ lowering the bar.** The threshold (0.50) is unchanged. The scale was corrected.
- **"Entries viability repaired" ≠ "trades are working."** The entry pipeline unblocked. Trade lifecycle requires Phase 4+.
- **Phase 5.75 does not provide edge evidence.** No closed trades → no win rate → no calibration data.
- **Panel rejection in Phase 3 is expected.** It is not a regression; it is the designed behavior for incomplete proposals.

---

## Known Limitations

### L1: Panel Rejects All Phase 3 Proposals

The panel requires `critic_report` and `historian_analog` to score proposals at `avg_score ≥ 6.5`. Phase 3 provides neither. This is a Phase 4+ dependency, not a Phase 5.75 scope.

### L2: Zero Closed Trades (Unchanged from Phase 5.5)

No trades opened → no trades closed → no calibration possible. CalibrationReporter remains unavailable.

### L3: Fixtures Are Synthetic

The replay fixtures produce realistic but deterministic price series. They are not historical BTC data. Candidate scores reflect signal quality on synthetic bars; real historical bars may produce different candidate rates.

### L4: Cross-Bar Confirmation Timing

The 2-bar confirmation window (CandlestickGroup bar N + IndicatorsGroup bar N+1) is an architectural timing artifact. It reduces candidate rate compared to single-bar confirmation. The artifact is documented but not fixed in Phase 5.75 — it is not a critical blocker.

---

## Phase Summary

| Objective | Result |
|-----------|--------|
| Audit entry policy viability | COMPLETE ✅ |
| Identify root cause of zero entries | IDENTIFIED ✅ (ceiling 0.4875, excluded groups) |
| Apply correct repair (not threshold lowering) | APPLIED ✅ (normalization, ACTIVE_COMPOSITE_WEIGHT_SUM = 0.55) |
| Confirm candidates fire after repair | CONFIRMED ✅ (8 candidates across 900 bars) |
| Confirm scores ≥ 0.50 | CONFIRMED ✅ (range: 0.5409–0.7227) |
| Confirm panel not bypassed | CONFIRMED ✅ (panel evaluates and rejects) |
| Confirm risk not modified | CONFIRMED ✅ (Layer C unchanged) |
| Document second barrier (panel) | DOCUMENTED ✅ |
| Tests | 22/22 new, 192/192 total ✅ |
| Positions opened | 0 (documented, not hidden) ✅ |

The entry pipeline is repaired and viable. Natural entries now reach the panel. Positions require Phase 4+ components.
