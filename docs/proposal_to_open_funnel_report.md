# Proposal-to-Open Funnel Report — Phase 6.1

**Date:** 2026-03-29
**Phase:** 6.1 Observational Replay

---

## Summary

The proposal-to-open funnel measures what happens to a proposal once it is generated. Across 17 proposals generated in Phase 6.1, zero progressed to a position open. The funnel breaks at two stages: (1) no H3-005 proposals due to co-occurrence gap, and (2) panel holds all crossover-bar proposals.

---

## Full Funnel Matrix

| Stage | Count | Pass Rate | Notes | Blocker? |
|-------|-------|-----------|-------|----------|
| Total bars | 990 | 100% | 3 fixtures combined | — |
| Bars with H3-005 signal | 30 | 3.0% | 30/990 bars | — |
| Bars with candlestick signal | 54 | 5.5% | 54/990 bars | — |
| H3-005 + candlestick co-occur | 1 | 3.3% of H3-005 | Only 1 co-occur | ⚠️ Near-zero |
| `CandidateTradeEvent` generated | 17 | — | 0 from H3-005 bars | ⚠️ H3-005 not contributing |
| Panel evaluations (from journal) | 7 | — | Panel holds all (from 7 proposals) | — |
| Panel enters (PanelApprovedProposalEvent) | 0 | 0% | Best: 12/20 approvals, avg 6.35 | 🛑 BLOCKER |
| `FinalDecisionGroup` enters | 0 | 0% | Not reached | — |
| Risk approvals (`RiskDecisionEvent`) | 0 | 0% | Not reached | — |
| Positions opened (`PositionOpenEvent`) | 0 | 0% | Not reached | — |

---

## Proposal Details

### Source of Proposals

All 17 proposals originate from EMA crossover or early-transition bars where `ema_alignment = "mixed"` or `"partial_bull"`. None originate from H3-005 established-trend bars.

Why crossover bars produce proposals:
- At EMA crossover, `ema_alignment = "mixed"` or transitions to `"partial_bull"`
- IndicatorsGroup detects the crossover as signal `H3-002` (EMA crossover hypothesis)
- CandlestickGroup often fires patterns at trend-transition candles (volume surges, momentum candles)
- These two signals co-occur → EntryGroup generates a proposal

Why H3-005 bars don't produce proposals:
- H3-005 bars are in established trend, post-crossover
- CandlestickGroup rarely fires at EMA pullback bars (no S/R context → H2-001/H2-002 blocked)
- Only 1/30 H3-005 bars had a candlestick present

### Proposal Score Distribution

| Fixture | Proposals | Score Min | Score Max | Score Avg | Direction |
|---------|-----------|-----------|-----------|-----------|-----------|
| bull_continuation | 3 | ~0.45 | ~0.54 | ~0.48 | LONG |
| bear_continuation | 7 | ~0.44 | ~0.58 | ~0.50 | LONG/SHORT |
| long_established | 7 | ~0.46 | ~0.56 | ~0.51 | LONG |

Note: Composite score formula = `(0.20 × indicator + 0.25 × candlestick + 0.10 × structural) / 0.55`
- Without structural signals, ceiling is `(0.20 + 0.25) / 0.55 = 0.818`
- Without S/R structural flag, proposals reach ~0.50–0.58 range

---

## Panel Score Breakdown

### Panel Evaluation Evidence (7 evaluations, long_established_trend fixture)

Thresholds: `APPROVE_THRESHOLD = 14`, `MIN_AVG_SCORE = 6.5`

| Packet | Approve | Reject | Abstain | Avg Score | Gap to Threshold |
|--------|---------|--------|---------|-----------|-----------------|
| 7e31bece | 7 | 8 | 5 | 5.675 | -7 approvals, -0.825 avg |
| e2f7776f | 12 | 4 | 4 | 6.225 | -2 approvals, -0.275 avg |
| b5687985 | 12 | 4 | 4 | 6.225 | -2 approvals, -0.275 avg |
| 60a4661c | 12 | 4 | 4 | 6.350 | **-2 approvals, -0.150 avg** |

Best result (60a4661c): 12 approvals, avg 6.35 — within striking distance of threshold but not sufficient.

### Why Panel Holds Crossover Proposals

The panel score is heavily influenced by EMA alignment. The `TrendFollowingEvaluator` — which is one of the 20 traders — scores based on:
- `full_bull` or `full_bear` → score ~8.0–9.0 (approve)
- `partial_bull` or `partial_bear` → score ~6.0–6.5 (abstain)
- `mixed` → score ~4.0–5.0 (abstain or reject)

Crossover proposals have `ema_alignment = "mixed"`. Multiple trend-following evaluators score 4.5 → reject. This pulls approve count and avg score below threshold.

Observed reject pattern (typical crossover proposal):
```
approve: 7.0, 8.0, 7.0, 7.0, 7.0, 7.0, 7.5 (7 traders)
abstain: 6.0, 5.5, 5.0, 5.5, 5.0, 4.0, 6.0, 5.5 (8 traders)
reject:  4.0, 4.0, 4.5, 4.5, 4.5 (5 traders)
```
Result: 7–12 approvals (below 14), avg ~5.7–6.4 (below 6.5).

### What a True H3-005 Proposal Would Score

A genuine H3-005 + Bullish Engulfing at support proposal would have:
- `ema_alignment = "full_bull"` → TrendFollowing scores ~8.5 (approve)
- High composite_score (~0.65–0.72 with structural signal)
- Candlestick confirmation → CandlestickFocused evaluators score high
- Structural proximity → StructuralEvaluators score high

Estimated panel result: 16–18/20 approvals, avg 7.0–7.8 → **WOULD PASS**

But this requires `at_support=True` on the same bar as H3-005, which currently never occurs.

---

## Risk Gate Analysis

Risk gate was never reached (no panel approvals). The 9 deterministic risk rules are assumed functional based on Phase 5.9 verification. No risk-layer defects are implicated in the Phase 6.1 findings.

---

## Conclusion

The proposal funnel has two distinct failure modes in Phase 6.1:

**Failure Mode 1 (primary):** H3-005 proposals never reach the panel because the candlestick gate prevents pure-indicator proposals. The co-occurrence of H3-005 + candlestick is near-zero due to S/R non-detection.

**Failure Mode 2 (secondary):** The proposals that are generated (from crossover bars) score below panel threshold due to mixed EMA alignment, which causes trend-following evaluators to reject.

Both failure modes point to the same root: the system needs `at_support=True` on H3-005 bars to generate high-quality proposals that both satisfy the candlestick gate AND score above panel threshold.
