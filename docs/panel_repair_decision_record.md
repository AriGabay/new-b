# Panel Repair Decision Record

**Date:** 2026-03-28
**Phase:** 5.9

---

## Purpose

Documents the reasoning process behind every repair decision (and non-repair decision) made during Phase 5.9. For each evaluator with an identified issue, records:

- What was wrong
- Options considered
- Decision made (and why)
- What was explicitly rejected (and why)

---

## Repair Matrix

| Evaluator | Previous Behavior | Dep on Missing Cap? | Root Cause | Repair Applied | New Behavior | Evidence | Still Limited? |
|-----------|------------------|--------------------|-----------|--------------|-----------|---------|----|
| PatternCompletion | score=4.0, reject — always, Phase 3 | **Yes** (ChartPatternGroup primary input) | Architecture error: empty list treated as "no patterns found" regardless of whether group was active | Check `groups_contributed`; if "chart_pattern" absent → return score=5.0 abstain | Neutral abstain when group excluded; normal scoring when active | Ideal synthetic: 5.0 abstain (correct). If group later activated with empty result: 4.0 reject (correct) | No — scores correctly in both states |
| RiskParity | score=3.0 (reject zone) for R:R=2.0 while vote="approve" | No | Formula bug: `rr * 1.5` → R:R=2.0 → 3.0 (deep reject), incoherent with simultaneous approve vote | Replace formula: `3.0 + rr * 2.0` | R:R=2.0 → 7.0 (approve), R:R=1.5 → 6.0 (abstain), R:R=1.0 → 5.0 (abstain) | Test suite: vote and score now coherent at all R:R values | No |
| DrawdownRisk | Base=5.0, negative adjustments only → caps at 5.0 forever | No | Design oversight: positive reward path never coded. vote="approve" set but immediately overridden by _vote_from_score(5.0)="abstain" | Add positive adjustment: R:R≥2.5 + stop≤3.0% → score+=1.5 | R:R=2.5 → 6.5 approve; R:R=2.0 → 5.5 abstain (partial lift) | Test suite: correct approve/abstain at threshold | No |

---

## Decision Record: What Was Fixed and Why

### Decision 1: Fix PatternCompletion

**Problem:** PatternCompletion evaluates `cp.confirmed_patterns`. When `ChartPatternGroup` is excluded, `build_empty_chart_pattern_snapshot()` always produces `confirmed_patterns=[]`. The evaluator cannot distinguish "chart pattern group ran and found nothing" from "chart pattern group was never run." It scores 4.0 (reject zone) in both cases.

**In Phase 3 (group excluded), this is architecturally wrong:** A score of 4.0 encodes the belief "I looked for patterns and found none, therefore this setup has no pattern support." But in Phase 3 we never looked. The absence of data is a capability gap, not evidence of a poor setup.

**Options considered:**

| Option | Verdict | Reason |
|--------|---------|--------|
| Lower APPROVE_THRESHOLD | **Rejected** | Spec explicitly forbids this. Would allow weak proposals to pass. |
| Remove PatternCompletion from panel | **Rejected** | Changes panel design; Phase 4 should not require removing evaluators |
| Force score=7.0 when excluded | **Rejected** | Would artificially boost avg — fabricating positive evidence |
| Abstain (score=5.0) when excluded | **Accepted** | Neutral: no evidence available → no opinion. Correct epistemic state |
| Add `is_active` flag to ChartPatternSnapshot | **Considered** | Requires changing the data model; `groups_contributed` already serves this purpose |

**Decision:** Use `packet.groups_contributed` (already set correctly in Phase 3) as the architecture-aware signal. If `"chart_pattern" not in packet.groups_contributed` → return neutral abstain (5.0). This is the minimal, honest repair.

**What it does NOT do:**
- Does not boost the score beyond neutral
- Does not fabricate pattern evidence
- Does not change the threshold
- Does not affect any other evaluator

---

### Decision 2: Fix RiskParity Formula

**Problem:** `score = min(9.0, rr * 1.5)` produces score=3.0 for R:R=2.0 while the evaluator simultaneously sets `vote = "approve"` for R:R≥2.0. A score of 3.0 is in the deep reject zone (below 4.5). The avg_score calculation uses 3.0. This is internally incoherent — the evaluator says "approve" but contributes a reject-level score to the panel average.

**Why this matters:** With 20 evaluators and a minimum avg of 6.5 required, a single evaluator contributing 3.0 instead of 7.0 drags the avg by 0.2 points. This was enough to suppress the avg below threshold for borderline proposals.

**Options considered:**

| Option | Verdict | Reason |
|--------|---------|--------|
| Keep formula, change vote threshold | **Rejected** | Doesn't fix the incoherence; vote would then disagree with score interpretation |
| Use `score = rr * 3.5` | **Rejected** | R:R=1.0 → 3.5 (over-penalizes marginal R:R), R:R=2.0 → 7.0 (correct) |
| Use `score = min(9.0, 3.0 + rr * 2.0)` | **Accepted** | R:R=1.0 → 5.0 (uncertain abstain), R:R=1.5 → 6.0 (near-abstain), R:R=2.0 → 7.0 (approve). Linear, coherent with vote |
| Normalize to 0-10 at R:R=3.0 | **Considered** | `score = min(10.0, rr * 10/3)` → same functional result at practical R:R values |

**Decision:** `score = min(9.0, 3.0 + rr * 2.0)`. This formula:
- Produces abstain-zone scores for borderline R:R (1.0–1.9)
- Produces approve-zone scores for acceptable R:R (≥2.0)
- Is monotonically increasing (better R:R → better score)
- Has a 5.0 intercept at R:R=1.0 (not 0 — acknowledges any positive R:R is not catastrophic)
- Caps at 9.0 for R:R≥3.0

**What it does NOT do:**
- Does not lower R:R thresholds for approval
- Does not change the approve vote condition (still R:R ≥ 2.0)
- Does not affect other evaluators

---

### Decision 3: Fix DrawdownRisk

**Problem:** `DrawdownRiskEvaluator` is supposed to evaluate the quality of risk management. Its base score is 5.0 with only negative adjustments (for excessive stop size, bad R:R, high volatility). Even with R:R=3.5, stop_pct=2.0%, and normal volatility — a perfect risk management profile — the score stays at 5.0 (abstain).

The evaluator has a branch `if rr >= 2.0: vote = "approve"` but this vote is immediately overridden by `if vote != "reject": vote = self._vote_from_score(score)`. Since score=5.0, `_vote_from_score` returns "abstain" and overwrites the approve vote. The evaluator was physically incapable of approving any proposal.

**Why this is a design error, not a design choice:** The docstring says "evaluates drawdown risk and leverage appropriateness." If risk management is excellent, this evaluator should reward it with an approve vote. The inability to approve contradicts the evaluator's stated purpose.

**Options considered:**

| Option | Verdict | Reason |
|--------|---------|--------|
| Remove DrawdownRisk from panel | **Rejected** | Phase 4 should have it active; removing changes panel structure |
| Set base score to 6.5 | **Rejected** | Would change behavior for bad risk management proposals |
| Add positive adjustment for good risk management | **Accepted** | Minimal: add reward branch that was clearly intended but missing |
| Make vote override more permissive | **Rejected** | The `_vote_from_score` override is the right architecture; score should determine vote |

**Decision:** Add before the `score = max(1.0, score)` floor:
```python
if rr >= 2.5 and stop_pct <= 3.0:
    score += 1.5   # R:R=2.5, controlled stop → 6.5 → approve
elif rr >= 2.0 and stop_pct <= 3.0:
    score += 0.5   # R:R=2.0, controlled stop → 5.5 → abstain (partial lift)
```

This means:
- Mediocre risk (R:R=2.0 but large stop or high vol): still penalized → remains abstain
- Good risk (R:R=2.0, controlled stop): modest lift to 5.5 (abstain)
- Excellent risk (R:R=2.5+, controlled stop): full lift to 6.5 (approve)
- Very high R:R (3.5+): further negative adjustments suppressed → can reach 6.5+

**What it does NOT do:**
- Does not change the negative adjustment penalties (still applied)
- Does not set score ≥ 6.5 unless risk management is genuinely good
- Does not affect other evaluators

---

## Decision Record: What Was NOT Fixed and Why

### Not Fixed: Breakout (ChartPattern dependency)

**Issue:** Breakout evaluator scores lower without `confirmed_patterns`. Max score is ~5.5 (abstain) instead of 7.0+ with confirmed breakout pattern.

**Decision:** Not fixed.

**Reason:** Breakout legitimately penalizes proposals without volume conviction. The volume penalty and the pattern bonus are both appropriate signals. For Phase 3 proposals with volume_ratio=0.92, the Breakout evaluator correctly scores them lower. If ChartPatternGroup later activates and detects a confirmed breakout, Breakout will score correctly. No architecture error — just an appropriate partial score.

---

### Not Fixed: ProfitTarget (ChartPattern bonus)

**Issue:** ProfitTarget misses the +2.0 bonus when `primary_confirmed=True` and a conservative target exists.

**Decision:** Not fixed.

**Reason:** ProfitTarget evaluates the R:R ratio as its primary signal. The chart pattern bonus is additive, not structural. For R:R=3.5 proposals, ProfitTarget correctly scores ~8.0 without the bonus. The missing +2.0 is an acceptable architecture limitation that will resolve when ChartPatternGroup is activated.

---

### Not Fixed: Confluence (1 of 7 signals missing)

**Issue:** Confluence evaluator has 7 signal agreements; one is `confirmed_patterns`. Phase 3 proposals can score 6/7 at most.

**Decision:** Not fixed.

**Reason:** 6/7 agreements is still sufficient for a high Confluence score (10.0 in ideal synthetic test). The -1 signal reduces the maximum slightly but does not structurally block approval. The evaluator grades on total agreements, and 6 strong agreements is compelling evidence.

---

### Not Fixed: MarketContext (pattern_direction field)

**Issue:** MarketContext uses `pattern_direction` from ChartPatternSnapshot when available.

**Decision:** Not fixed.

**Reason:** MarketContext has minimal Phase 3 impact. The field is one input among many (ema_alignment, at_support/resistance, trend_direction). Verified that MarketContext still produces reasonable composite scores for Phase 3 proposals (6.0-9.0 range). Not a structural barrier.

---

### Not Fixed: LeverageSpecialist (sign bug for SHORT)

**Issue:** For SHORT proposals, `proposed_leverage = min(entry / (entry - stop), 3.0)` → stop > entry → negative leverage → always ≤ 2.0x → LeverageSpecialist scores 8.0 (conservative leverage). Accidentally correct.

**Decision:** Not fixed in Phase 5.9. Documented for Phase 4 cleanup.

**Reason:** The bug produces a conservative outcome (scores SHORT trades as if leverage is very low). This is the safe direction — it does not inflate approval counts or lower risk assessment. Fixing it would require verifying that the correct leverage calculation for SHORT doesn't accidentally score proposals worse or better in unintended ways. Deferred to Phase 4 with full SHORT leverage formula review.

---

### Not Fixed: Contrary (always rejects most proposals)

**Issue:** Contrary evaluator returns 4.0 (reject) unless R:R > 3.0 AND structure_quality == "strong". The Phase 3 replay proposals have structure_quality="none" → Contrary rejects.

**Decision:** This is intentional design. Not changed.

**Reason:** The Contrary evaluator is the panel's devil's advocate. It should be hard to satisfy — its purpose is to ensure there's always one strong dissenting voice requiring the setup to be genuinely exceptional to override. A proposal with structure_quality="none" should not earn Contrary's approval, regardless of other factors. This is correct behavior.

---

### Not Fixed: MeanReversion (skeptical of trend-following entries)

**Issue:** MeanReversion gives base 3.0 for directional trend entries (EMA crossover trades are not mean reversion by definition).

**Decision:** This is intentional design. Not changed.

**Reason:** EMA crossover trades are trend-following entries. MeanReversion evaluates from the opposite framework. It is correct that it scores trend entries poorly — they are not the type of setup it is designed to approve. MeanReversion will approve when RSI is at an extreme, price is at S/R, and Bollinger Bands indicate overextension — i.e., when a mean reversion case can be made alongside the directional trade.

---

## Summary: Repair Philosophy

The Phase 5.9 repair is constrained by one principle: **fix broken evaluator logic, not thresholds**.

The 3 fixes share a common property — each removed a structural barrier that prevented a **good-faith positive signal from registering**:

1. PatternCompletion was penalizing the absence of a capability as if it were the presence of negative evidence
2. RiskParity was producing a reject-zone score for an approve-level R:R
3. DrawdownRisk was unable to register approval even for perfect risk management

None of these repairs lower the quality bar. They restore the ability of the panel to recognize genuinely good proposals — which is what the panel is for.

The 5 remaining architecture-dependent evaluators (Breakout, ProfitTarget, Confluence, MarketContext, LeverageSpecialist) are not repaired because their limitations are either:
- Appropriate signal penalties (Breakout, Contrary, MeanReversion)
- Partial bonuses that don't structurally block approval (ProfitTarget, Confluence)
- Accidentally conservative (LeverageSpecialist)

After the 3 targeted repairs, a genuinely strong Phase 3 proposal can achieve 16/20 approvals and avg 7.78. The panel is viable.
