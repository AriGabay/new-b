# Panel Score Ceiling Analysis

**Date:** 2026-03-28
**Phase:** 5.9 — Panel Viability Repair

---

## Problem Statement

Phase 5.75 confirmed that CandidateTradeEvents fire (8 per 900 bars). Phase 5.9 investigated why all 8 proposals were rejected by the panel (Layer B). This document analyzes the panel score ceiling under Phase 3 architecture.

---

## Observed Panel Results (Before Repair)

First candidate traced with real structural data (SHORT, bar 29 of btc_bull_breakout_v1):

| Evaluator | Score | Vote |
|-----------|-------|------|
| TrendFollowing | 4.5 | reject |
| Momentum | 5.5 | abstain |
| MeanReversion | 6.0 | abstain |
| Breakout | 4.5 | reject |
| Structure | 7.5 | approve |
| Candlestick | 4.0 | abstain |
| RiskParity | **3.0** | approve |
| Volatility | 7.0 | approve |
| VolumeProfile | 5.0 | abstain |
| MacroRegime | 9.0 | approve |
| Contrary | 4.0 | reject |
| ProfitTarget | 7.0 | approve |
| EntryTiming | 8.0 | approve |
| Confluence | 7.5 | approve |
| DrawdownRisk | **5.0** | abstain |
| LeverageSpecialist | 8.0 | approve |
| PatternCompletion | **4.0** | **reject** |
| WickAnalysis | 5.5 | abstain |
| MarketContext | 6.0 | abstain |
| ExecutionQuality | 7.0 | approve |

**Result: 9/20 approve, avg=5.90, → hold**

---

## Three Root Causes Identified

### Root Cause 1: PatternCompletion structural reject (architecture-dependent)

`PatternCompletionEvaluator` scores 4.0 (reject zone) when `cp.confirmed_patterns = []`. In Phase 3, `build_empty_chart_pattern_snapshot()` is always called because ChartPatternGroup is excluded. The evaluator cannot distinguish "no patterns found" from "capability not available." It permanently rejects (4.0) every Phase 3 proposal.

**Why this is an architecture problem:** A score of 4.0 for "no patterns" is correct when ChartPatternGroup is active and found nothing. It is incorrect when ChartPatternGroup is excluded — the absence of chart patterns in that case is a capability gap, not evidence of a bad setup.

---

### Root Cause 2: RiskParity formula incoherence

`score = min(9.0, rr * 1.5)` maps R:R = 2.0 → score = 3.0. Simultaneously, the evaluator explicitly sets `vote = "approve"` for R:R ≥ 2.0.

**Why this is a bug:** A score of 3.0 is in the deep reject zone (below 4.5), yet the evaluator votes "approve." The average score calculation uses 3.0 regardless of vote. With a target avg ≥ 6.5, contributing score=3.0 for an approved R:R=2.0 trade dragged the average ~0.2 points below threshold.

Expected behavior: if R:R = 2.0 is worth approving, it should produce a score in the approve range (≥6.5), not score=3.0.

---

### Root Cause 3: DrawdownRisk permanently abstains

`DrawdownRiskEvaluator` starts at 5.0 and applies only negative adjustments. There are no positive adjustments. Even with R:R = 3.5 and perfect stop placement (2%, normal volatility), the score stays at 5.0 (abstain). The evaluator cannot approve any proposal under any Phase 3 condition.

**Why this is a design error:** DrawdownRisk is supposed to evaluate risk management quality. If risk management is excellent (high R:R, controlled stop, normal volatility), the evaluator should approve — but it physically cannot. It's a permanent abstainer.

---

## Panel Ceiling Calculation (Before Repair)

Maximum possible Phase 3 avg score with 3 broken evaluators:

```
PatternCompletion max = 4.0 (always rejects → max 4.0)
RiskParity max (R:R=2.0) = 3.0 (formula cap)
DrawdownRisk max = 5.0 (no positive adjustments)
```

Best-case avg formula:
```
Sum (all other 17 evaluators at max) + 4.0 + 3.0 + 5.0
≈ (17 × 8.5) + 12.0 = 144.5 + 12.0 = 156.5
Max avg = 156.5 / 20 = 7.825
```

But the broken evaluators also constrain which evaluators can approve — with PatternCompletion always rejecting, the maximum approvals from the other 19 is 19. However, the avg impact is more damaging.

---

## Panel Ceiling Calculation (After Repair)

After the 3 repairs:

```
PatternCompletion: 5.0 (neutral abstain when excluded)
RiskParity (R:R=2.0): 7.0 (formula 3.0 + 2.0*2.0 = 7.0)
DrawdownRisk (R:R=2.5, stop=2%): 6.5 (with +1.5 positive adjustment)
```

For an ideal Phase 3 proposal (all signals aligned):
- 16 approvals / 2 abstains (PatternCompletion + Breakout)
- avg_score = 7.78
- Panel recommendation: "enter"
- FinalDecisionGroup: "enter" (all 6 rails clear)

**The ceiling IS above the required thresholds (14/20 and 6.5) for strong Phase 3 proposals.**

---

## Score Distribution After Repair (Ideal Phase 3 SHORT)

| Evaluator | Score | Vote |
|-----------|-------|------|
| TrendFollowing | 10.0 | approve |
| Momentum | 6.5 | approve |
| MeanReversion | 6.0 | abstain |
| Breakout | 5.0 | abstain |
| Structure | 10.0 | approve |
| Candlestick | 10.0 | approve |
| RiskParity | 9.0 | approve |
| Volatility | 7.0 | approve |
| VolumeProfile | 8.0 | approve |
| MacroRegime | 9.0 | approve |
| Contrary | 7.0 | approve |
| ProfitTarget | 8.0 | approve |
| EntryTiming | 7.0 | approve |
| Confluence | 10.0 | approve |
| DrawdownRisk | 6.5 | approve |
| LeverageSpecialist | 8.0 | approve |
| PatternCompletion | 5.0 | abstain |
| WickAnalysis | 5.5 | abstain |
| MarketContext | 9.0 | approve |
| ExecutionQuality | 9.0 | approve |

**Result: 16/20 approve, avg=7.78, → enter**

---

## Why Current Replay Candidates Still Don't Pass

The 8 candidates from Phase 5.75 replay are correctly rejected after the repair. They are weak proposals:

| Signal | Value | Problem |
|--------|-------|---------|
| ema_alignment | "mixed" | TrendFollowing penalizes (-2.0) |
| volume_ratio | 0.92 | VolumeProfile and Breakout at neutral/reject |
| candlestick patterns | none detected | Candlestick abstains (4.0) |
| Structure quality | "none" or weak | Contrary cannot approve |
| RSI at crossover | 75.14 (overbought) | Momentum penalizes (-0.5) |

These are legitimate panel rejections. The panel is not broken — it correctly evaluates weak proposals as insufficient.

---

## Conclusion

The panel ceiling analysis shows:
1. Three evaluators had architecture-dependent or formula errors that depressed avg scores and inflated rejects
2. After repair, the panel ceiling is 16/20 approvals and avg 7.78 for ideal proposals
3. The threshold (14/20, avg≥6.5) IS achievable in Phase 3
4. Current replay candidates correctly fail because they are weak proposals, not because the panel is miscalibrated
