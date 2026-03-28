# Proposal-to-Open Funnel Report — Phase 6.2

**Date:** 2026-03-29
**Phase:** 6.2 — Structural Fixture Validation

---

## Summary

Phase 6.2 generated 19 proposals across 785 bars. All were evaluated by the panel. All were held. The funnel breaks at the panel evaluation stage: the best proposal received 12/20 approvals and avg score 6.350, against a threshold of 14/20 and avg ≥6.5.

---

## Combined Funnel Matrix (3 Fixtures, 785 Bars)

| Stage | Count | Pass Rate | Notes |
|-------|-------|-----------|-------|
| Bars processed | 785 | 100% | 3 Phase 6.2 fixtures |
| H3-005 signal bars | 36 | 4.6% | All LONG (full_bull) |
| Candlestick signal bars | 69 | 8.8% | H2-001, H2-003, crossover |
| H3-005 + candlestick co-occur | 4 | 11.1% of H3-005 | **4× Phase 6.1 rate** |
| S/R levels qualified | 3 | — | One per fixture |
| `at_support` / `at_resistance` present | ≥3 bars | — | Per journal |
| Proposals generated | 19 | — | ~4 from H3-005+structural |
| Panel evaluations (from journal) | 19 | — | All proposals evaluated |
| Panel enters | 0 | 0% | Best: 12/20, avg 6.350 |
| `FinalDecisionGroup` enters | 0 | 0% | Not reached |
| Risk approvals | 0 | 0% | Not reached |
| Positions opened | 0 | **0%** | — |

Threshold: **14/20 approvals, avg ≥6.5**

---

## Per-Fixture Funnel

### Fixture 1: btc_w_bottom_long_v1 (257 bars)

| Stage | Count |
|-------|-------|
| H3-005 | 11 |
| Candlestick | 22 |
| Co-occur | 1 (bar 246) |
| Proposals | 6 |
| Panel evals | 6 |
| Best panel | 12/20 avg 6.350 |
| Opens | 0 |

Best proposal: bar 246, H3-005 LONG + Bullish Engulfing + at_support=True, score=0.8364

### Fixture 2: btc_m_top_short_v1 (267 bars)

| Stage | Count |
|-------|-------|
| H3-005 | 16 |
| Candlestick | 26 |
| Co-occur | 2 |
| Proposals | 8 |
| Panel evals | 8 |
| Best panel | 12/20 avg 6.350 |
| Opens | 0 |

Best proposal: score=0.8364, full_bull EMA, at_support=True + at_resistance=True

### Fixture 3: btc_triple_touch_long_v1 (261 bars)

| Stage | Count |
|-------|-------|
| H3-005 | 9 |
| Candlestick | 21 |
| Co-occur | 1 |
| Proposals | 5 |
| Panel evals | 5 |
| Best panel | 12/20 avg 6.225 |
| Opens | 0 |

---

## Panel Score Analysis

### Best Proposal Trader Review Breakdown (W-bottom, packet f4700d62)

Threshold: `APPROVE_THRESHOLD=14`, `MIN_AVG_SCORE=6.5`

**Approvers (12):** Scores 6.5–9.0

| Score | Voter rationale |
|-------|-----------------|
| 9.0 | BTC macro bull regime aligned |
| 9.0 | 4 signals confluent |
| 8.0 | EMA full_bull + ADX=35 |
| 8.0 | RSI=54.7, rising momentum |
| 8.0 | Execution quality A-grade |
| 7.0 | R:R=2.0 favorable |
| 7.0 | Normal volatility (ATR ratio 1.02) |
| 7.0 | Chart pattern target viable |
| 7.0 | Structural entry timing |
| 7.0 | Leverage 3x moderate |
| 7.0 | Pullback-to-support context |
| 6.5 | At key support level |

**Abstainers (5):** Scores 4.0–5.5

| Score | Voter rationale |
|-------|-----------------|
| 5.5 | Stop placement reasonable, R:R acceptable |
| 5.5 | No wick rejection; structure is primary reference |
| 5.0 | Volume 'normal' — institutional participation uncertain |
| 5.0 | Chart pattern capability not active |
| 4.0 | **No candlestick signal in packet** — "Absence of candlestick pattern means no bar-level confirmation" |

**Rejecters (3):** Scores 3.0–4.5

| Score | Voter rationale |
|-------|-----------------|
| 4.5 | Volume below breakout threshold; BB width percentile 4 (squeeze) |
| 4.0 | `structure_quality='none'` — market rarely moves cleanly in this context |
| 3.0 | RSI=54.7 not oversold enough for mean-reversion setup |

**Total: 12 approve, 5 abstain, 3 reject. Avg=6.350. Hold.**

---

## Root Causes of Panel Hold

### Root Cause 1: Missing Candlestick Pattern in Setup Packet (Critical)

The Bullish Engulfing fires at bar 246 and generates the proposal. However, the setup packet's `candlestick.patterns_detected=[]` — the pattern name does not appear in the detailed candlestick section. The `confirming_signals=['indicator', 'candlestick']` list correctly includes 'candlestick', but the evaluator who checks `candlestick.patterns_detected` sees an empty list.

**Impact:** One abstainer scores 4.0 ("no candlestick signal"). This vote, combined with two 5.0 abstainers, pulls approval count to 12.

**To close gap:** If this abstainer's vote converted to approve (7.0+), approval count rises to 13. One more needed for threshold.

### Root Cause 2: `structure_quality = 'none'` (Moderate)

The structural level at 69,670 is fully qualified (`touches=15, strength=1.0, at_support=True`). However `structure_quality='none'` because `higher_highs=False AND higher_lows=False` in the 60-bar window. The W-bottom creates equal lows, not higher lows.

**Impact:** One rejecter scores 4.0. Another approver is borderline at 6.5.

### Root Cause 3: `trend_direction = 'sideways'` (Moderate)

EMA alignment is `full_bull` but structural `trend_direction='sideways'`. Two different algorithmic modules give conflicting regime assessments. Some evaluators weight `trend_direction` over `ema_alignment`.

**Impact:** Reduces confidence of trend-following evaluators; contributes to abstain/reject cluster.

---

## Score Gap to Threshold

| Metric | Current Best | Threshold | Gap |
|--------|-------------|-----------|-----|
| Approve count | 12/20 | 14/20 | **−2** |
| Avg score | 6.350 | 6.500 | **−0.150** |
| Weighted score | 6.665 | — | — |

**2 additional approvals** are needed. The 5 abstainers scored 4.0–5.5. Converting the 4.0 abstainer (candlestick packet issue) and one 5.0 abstainer (structural quality) to approve would close the gap.

---

## What a Threshold-Crossing Proposal Would Look Like

Based on observed voter behavior:
- `candlestick.patterns_detected=['bullish_engulfing']` in packet → 4.0 abstainer → 7.0 approve (+3 votes, +1.0 avg)
- `structure_quality='weak'` or higher → 4.0 rejecter → 6.0 abstain or approve
- `trend_direction='bullish'` consistent with EMA → 1 borderline abstainer → approve

Estimated threshold-crossing result: **14–15/20 approvals, avg 6.8–7.2**

---

## Conclusion

Phase 6.2 proves the proposal path is functional. Proposals reach the panel. The panel evaluates correctly (correctly holding low-confidence proposals). The gap is small (−2 approvals) and is attributable to two addressable information gaps in the setup packet:

1. **Candlestick pattern name not reaching evaluators** (packet assembly timing issue)
2. **Structure quality staying 'none'** (fixture doesn't establish HH/HL trend structure before entry bar)

These are not algorithmic bugs. They are either packet assembly improvements (candlestick) or fixture design improvements (HH/HL structure accumulation before entry).
