# PHASE 5.9 HANDOFF

**Date:** 2026-03-28
**Phase completed:** 5.9 — Panel Viability Repair
**Next phase:** 6.0 — Paper Performance Observation

---

## What Was Wrong (Before Phase 5.9)

All 8 natural trade proposals from the Phase 5.75 runtime were rejected by the TraderEvaluatorPanel. The rejection was uniform (all 8) which suggested a structural barrier rather than genuinely weak proposals.

Investigation identified 3 structural barriers in `src/traders/evaluators.py`:

### 1. PatternCompletion Architecture Error
- **What it did**: Scored 4.0 (reject zone) for every Phase 3 proposal
- **Why**: `confirmed_patterns=[]` because ChartPatternGroup is excluded, but the evaluator treated an empty list from an excluded group identically to "group ran and found nothing" → penalized the absence of a capability as if it were negative evidence
- **Impact**: 1 permanent reject every run, dragged avg score, impossible to remove without architecture data

### 2. RiskParity Formula Incoherence
- **What it did**: Scored 3.0 (deep reject zone) for R:R=2.0 while simultaneously voting "approve"
- **Why**: Formula `rr * 1.5` maps R:R=2.0 → 3.0. Approve vote and reject-level score were incoherent
- **Impact**: Dragged avg score by ~0.2 points every run. For proposals near the avg threshold, this alone was enough to suppress from 6.6 → 6.4

### 3. DrawdownRisk Permanent Abstainer
- **What it did**: Never approved any proposal under any conditions
- **Why**: Base score 5.0, only negative adjustments → caps at 5.0 permanently. Vote="approve" was set in code but immediately overridden by `_vote_from_score(5.0)` = "abstain"
- **Impact**: One permanently missing approve vote; couldn't contribute to reaching 14/20

---

## What Was Repaired

Three targeted fixes in `src/traders/evaluators.py`:

```python
# PatternCompletion — architecture-aware abstain
if "chart_pattern" not in packet.groups_contributed:
    return self._make_verdict(5.0, "abstain", ...)

# RiskParity — coherent formula
score = min(9.0, 3.0 + rr * 2.0)  # was: rr * 1.5

# DrawdownRisk — positive reward path
if rr >= 2.5 and stop_pct <= 3.0:
    score += 1.5
elif rr >= 2.0 and stop_pct <= 3.0:
    score += 0.5
```

**What was NOT changed:**
- `APPROVE_THRESHOLD = 14` (unchanged)
- `MIN_AVG_SCORE = 6.5` (unchanged)
- FinalDecisionGroup safety rails (unchanged)
- Any hardcoded approvals or forced positions (not introduced)
- Contrary, MeanReversion (intentionally strict by design — not changed)

---

## Whether Natural Proposals Now Pass the Panel

**Short answer: Strong proposals do. Weak proposals don't. This is correct.**

### The 8 Phase 5.75 replay candidates: still rejected

These are EMA crossover transition bars with mixed alignment, below-average volume (0.92x), no candlestick patterns, and structure_quality="none." After the repair, they score **9/20 approve, avg=6.05 → HOLD**. This is correct — they are genuinely weak setups.

### Ideal Phase 3 proposals: now correctly approved

A proposal with full EMA alignment, volume conviction, candlestick reversal at structure, excellent R:R, and macro agreement scores **16/20 approve, avg=7.78 → ENTER**. This is the proven panel ceiling for Phase 3 architecture.

**The panel was not broken. It was blocked by 3 structural errors that prevented it from recognizing valid positive evidence. Those are now fixed.**

---

## Whether Positions Can Open Naturally (Without Forcing)

Yes — when the runtime produces proposals that meet the signal quality requirements. Required minimum conditions for natural panel approval:

| Signal | Required Value | Why |
|--------|---------------|-----|
| ema_alignment | "full_bull" or "full_bear" | TrendFollowing scores 8.0+ vs 4.5 for "mixed" |
| volume_ratio | ≥ 1.3x | VolumeProfile and Confluence approve |
| candlestick pattern | Present at entry bar | Candlestick 7.0+, WickAnalysis 6.0+ |
| at_support/resistance | True | Structure, EntryTiming, WickAnalysis benefit |
| structure_quality | "B" or better | Contrary unlock requires "strong"; min for passing is weaker overall |
| R:R | ≥ 2.5 | DrawdownRisk approves; RiskParity scores 8.0 |
| macro direction | Aligned | MacroRegime 9.0 |

**The Phase 5.75 candidate generator fires at EMA crossover bars.** Crossover bars are, by definition, transition moments — the EMA alignment is "mixed" at that point. A proposal generated 3-5 bars after crossover (trend confirmed) would score significantly better.

This is a candidate generation strategy question, not a panel problem. If the runtime is exclusively generating candidates at crossover transition bars, most candidates will be correctly held. The panel is working as intended.

---

## Whether the Repaired Panel Is Viable or Still Limited

**Viable for Phase 3, with known limitations:**

### Viable
- Can reach 16/20 approve, avg=7.78 for strong proposals
- Both primary thresholds achievable without Phase 4+ capabilities
- All 6 FinalDecisionGroup safety rails operate correctly
- Correctly differentiates strong vs weak proposals

### Remaining limitations

| Limitation | Impact | Resolution |
|-----------|--------|-----------|
| ChartPatternGroup excluded | 5 evaluators partially limited; PatternCompletion abstains neutrally | Activate ChartPatternGroup in future phase |
| EMA crossover candidates are transition signals | Most natural candidates weak by design | Consider post-confirmation candidate generation |
| Contrary requires "strong" structure | One evaluator always rejects unless structure_quality="strong" | Higher structural data quality from replay fixtures |
| LeverageSpecialist sign bug (SHORT) | Accidentally conservative; not corrected | Fix in Phase 4 with proper SHORT leverage formula review |

---

## What Remains Before Serious Paper Performance Observation

### Immediate prerequisites (for Phase 6.0)
1. **Candidate generation quality**: The runtime needs to generate candidates in established trend conditions, not just at EMA crossover transition bars. If candidates are always generated at "mixed" EMA alignment moments, the panel will always hold them. This is a feature gap in candidate generation strategy.

2. **Replay fixture diversity**: The Phase 5.75 replay fixtures (`btc_bull_breakout_v1`, `btc_bear_drop_v1`) represent specific market conditions. Paper observation requires fixtures or live data with:
   - Established trend bars (EMA alignment = "full_bull"/"full_bear")
   - Volume spikes at structural levels
   - Candlestick pattern days
   - Multiple R:R scenarios

3. **Execution layer verification**: Phase 5.9 confirmed the panel can approve strong proposals. The execution path from panel decision → position open → position management has not been end-to-end validated with a position that actually opens.

### Deferred items (not blockers for Phase 6.0)
- ChartPatternGroup activation (Phase 4+ scope)
- LeverageSpecialist SHORT leverage formula fix (Phase 4)
- Historian/Critic wiring (Phase 4+)
- HistorianGroup analog evaluation (Phase 5+)

---

## What Must Not Be Misrepresented

1. **The 8 Phase 5.75 candidates are not passing after this repair.** They are still correctly held. The repair enables good proposals to pass; it does not rescue bad proposals.

2. **The ideal synthetic packet is not a live signal.** It demonstrates the panel ceiling is above the threshold. It is not evidence that the runtime will produce such proposals with current candidate generation logic.

3. **No positions have opened naturally yet.** Phase 5.9 proves the panel CAN approve strong proposals. It does not claim positions are now opening. Phase 6.0 paper observation will establish whether and how often strong-enough proposals occur in practice.

4. **LeverageSpecialist is still producing negative leverage values for SHORT proposals.** The behavior is accidentally conservative. The formula is wrong. This is documented but not fixed.

5. **The panel is making real decisions.** It is not a filter that can be tuned — its thresholds reflect genuine signal quality requirements. If the system produces many held proposals, that is correct behavior for weak market conditions. Do not interpret held proposals as system failure.

---

## Test Suite State

**224 tests total, all passing.**

| Test File | Tests | Phase |
|-----------|-------|-------|
| test_entry_policy_viability.py | 22 | 5.75 |
| test_panel_viability.py | 32 | 5.9 |
| (prior phases) | 170 | 1–5.5 |

Phase 5.9 test file: `src/tests/test_panel_viability.py`
- PatternCompletion architecture-awareness: 4 tests
- RiskParity formula coherence: 4 tests
- DrawdownRisk positive adjustment: 4 tests
- Panel passes ideal Phase 3: 4 tests
- Weak proposals still rejected: 2 tests
- Panel not bypassed / no forced positions: 2 tests
- Risk gates unchanged: 3 tests
- Before/after reproducibility: 3 tests
- Phase 3 viability proof: 3 tests
- Source separation: 2 tests

---

## Documentation Index

| Document | Location | Contents |
|----------|----------|---------|
| Phase summary | `docs/PHASE_5_9_PANEL_VIABILITY.md` | Full phase documentation |
| Score ceiling analysis | `docs/panel_score_ceiling_analysis.md` | Before/after ceiling calculation |
| Evaluator dependency audit | `docs/trader_evaluator_dependency_audit.md` | 20-evaluator matrix |
| Threshold alignment | `docs/panel_threshold_alignment_report.md` | Threshold calibration proof |
| Before/after results | `docs/panel_before_after_replay_results.md` | Exact scores for all scenarios |
| Architecture gap analysis | `docs/active_architecture_vs_panel_expectation.md` | What panel can/cannot assess |
| Repair decision record | `docs/panel_repair_decision_record.md` | Why each repair was/wasn't made |
| **This handoff** | `docs/PHASE_5_9_HANDOFF.md` | — |

---

## Passing to Phase 6.0

Phase 6.0 (Paper Performance Observation) begins from a stable baseline:

- Layer A (candidate generation): confirmed active, 8 events/900 bars
- Layer B (panel evaluation): confirmed viable for strong proposals after 3 repairs
- Layer C (execution): wired but not yet validated with a naturally-opened position
- Risk management: all safety rails active and unmodified

The primary open question for Phase 6.0: **does the runtime produce proposals with sufficient signal quality to earn panel approval under live or richer replay conditions?**
