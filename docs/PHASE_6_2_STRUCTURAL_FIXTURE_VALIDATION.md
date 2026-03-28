# Phase 6.2 — Structural Fixture Validation Report

**Date:** 2026-03-29
**Phase:** 6.2 — Structural Fixture Validation
**Outcome:** ZERO NATURAL POSITIONS OPENED — Structural conditions achieved, panel threshold not met

---

## What Was Phase 6.2

Phase 6.2 asked a precise question following Phase 6.1's root cause finding:

> If the replay data genuinely contains valid structural S/R levels plus H3-005 plus candlestick co-occurrence — can the system produce a natural panel-approved entry?

**Phase 6.1 finding:** `TechnicalStructureGroup` produced 0 at_support/at_resistance bars in synthetic fixtures.
**Phase 6.2 goal:** Design fixtures that genuinely trigger TechnicalStructureGroup qualification, then observe whether the panel approves the resulting proposals.

**Answer:** Structural qualification was achieved. Co-occurrence was achieved. Panel evaluated. Panel held. Zero positions opened.

---

## Phase 6.2 Deliverable Matrix

| Fixture | Bars | S/R Level Qualifies? | Touches | H3-005 Bars | Candlestick Bars | Co-occur | Proposals | Best Score | Best Panel | Opens |
|---------|------|---------------------|---------|-------------|-----------------|---------|-----------|------------|------------|-------|
| `btc_w_bottom_long_v1` | 257 | **YES** | 15 (support 69,670) | 11 | 22 | **1** | 6 | **0.8364** | 12/20 avg 6.350 | **0** |
| `btc_m_top_short_v1` | 267 | **YES** | 13 (resistance 71,031) | 16 | 26 | **2** | 8 | **0.8364** | 12/20 avg 6.350 | **0** |
| `btc_triple_touch_long_v1` | 261 | **YES** | 11 (support ~69,850) | 9 | 21 | **1** | 5 | **0.7909** | 12/20 avg 6.225 | **0** |
| **Combined** | **785** | — | — | **36** | **69** | **4** | **19** | **0.8364** | **12/20 avg 6.350** | **0** |

Threshold required: **14/20 approvals, avg ≥6.5**
Best achieved: **12/20 approvals, avg 6.350**
Gap: **−2 approvals, −0.150 avg**

---

## What Phase 6.2 Proved

### Progress Beyond Phase 6.1

| Metric | Phase 6.1 | Phase 6.2 | Delta |
|--------|-----------|-----------|-------|
| Fixtures | 3 | 3 | — |
| Total bars | 990 | 785 | — |
| S/R levels qualified | 0 | **3** | +3 |
| H3-005 bars | 30 | 36 | +6 |
| Co-occurrence events | 1 | **4** | +3 |
| Proposals from H3-005+structural | 0 | **~3** | +3 |
| Best composite score | 0.5818 | **0.8364** | +0.2546 |
| Panel evaluations | 7 | **19** | +12 |
| Best panel result | 12/20 avg 6.350 | 12/20 avg 6.350 | same |
| Positions opened | 0 | **0** | 0 |

**Structural fixture engineering works.** The W-bottom design creates a real support level at 69,670 with 15 touches; the TechnicalStructureGroup correctly qualifies it and sets `at_support=True` at the pullback bar. The composite score jumps from 0.5818 → 0.8364 (+43%) because three groups (indicators + candlestick + technical_structure) all contribute.

**But the panel threshold is not crossed.** Despite the higher proposal quality, the panel consistently holds at 12/20 approvals, avg 6.35.

---

## Root Cause of Panel Hold (Phase 6.2 Finding)

Journal `setup_packets` reveal three recurring weaknesses in even the best proposals:

### Weakness 1: `structure_quality = 'none'`

All qualifying proposals show `structure_quality='none'` in the structural bundle. This is because `TechnicalStructureGroup._analyze_trend_structure()` requires detected `higher_highs=True` AND `higher_lows=True` to elevate quality above 'none'. In the W-bottom fixture, the price forms a W-shape that reestablishes the bull trend but doesn't accumulate enough HH/HL observations within the observation window for the quality flag to rise.

Panel impact: Traders citing structural evidence score lower when `structure_quality='none'`.

```
"structure quality 'none' — the market rarely moves cleanly in this context" → score 3.0 (reject)
"Structure quality 'none' may not hold under pressure" → score 6.5 (approve, borderline)
```

### Weakness 2: `trend_direction = 'sideways'`

Despite `ema_alignment = 'full_bull'`, the structural bundle's `trend_direction` shows 'sideways'. This creates an internal inconsistency the panel notices. The EMA group and structural group send conflicting regime signals to the evaluators.

Panel impact: Trend-following traders who rely on `trend_direction` (not EMA alignment) score lower.

### Weakness 3: `candlestick.patterns_detected = []` (Packet Assembly Timing)

The Bullish Engulfing fires at bar 246 and co-occurs with H3-005. However, the setup packet's `candlestick` section shows `patterns_detected=[]` and `primary_pattern=None`. The `confirming_signals` list includes `'candlestick'` (correct), but the detailed pattern name is missing from the packet's candlestick block.

Panel impact: One trader abstains with:
> "No candlestick signal to confirm or deny the trade. Absence of candlestick pattern means no bar-level confirmation." → score 4.0 (abstain)

This represents an information gap in packet assembly — the candlestick pattern co-occurs but its name doesn't reach the evaluators' pattern-detail view.

---

## Panel Score Distribution (All Fixtures Combined, Best Proposals)

| Fixture | Best Packet | Approve | Reject | Abstain | Avg | Gap |
|---------|-------------|---------|--------|---------|-----|-----|
| W-bottom | f4700d62 | 12 | 3 | 5 | 6.350 | −2, −0.150 |
| M-top | 87888ef5 | 12 | 3 | 5 | 6.350 | −2, −0.150 |
| Triple-touch | (best) | 12 | 3 | 5 | 6.225 | −2, −0.275 |

The panel threshold (14/20, avg ≥6.5) requires 2 more approvals. The gap is consistent across all three fixture types. This suggests a systematic scorer pattern:

- **12 approvers** see: full_bull EMA alignment, strong ADX, at_support=True, R:R=2.0, composite=0.84
- **5 abstainers** see: structure_quality='none', missing candlestick pattern detail, no wick confirmation
- **3 rejecters** see: sideways trend_direction, BB squeeze, RSI not oversold enough for mean reversion

The 2-approval gap is driven by the abstainers. One abstainer (#18 below threshold) is the trader who scores 4.0 for missing candlestick confirmation. Two more are at 5.0 for structural quality and volume concerns. If these three shifted to approve (≥7.0), the threshold would be met.

---

## Structural Qualification Evidence (W-Bottom)

From journal `setup_packets` (packet f4700d62, bar 246):

```json
"structure": {
    "at_resistance": false,
    "at_support": true,
    "nearest_support": {
        "price": 69670.2,
        "touches": 15,
        "strength": 1.0,
        "level_type": "swing_low"
    },
    "resistance_distance_pct": null,
    "support_distance_pct": null,
    "structure_quality": "none",
    "trend_direction": "sideways"
}
```

`at_support=True` with `nearest_support.price=69,670` and `touches=15` confirms:
- TechnicalStructureGroup correctly detected the W-bottom swing lows
- Level was properly cluster-merged (two dips within ATR×0.5 of each other)
- Touch count correctly exceeded `MIN_TOUCHES=2` (reached 15)
- `at_support` proximity flag correctly fired: `close(70,400) - level(69,670) = 730 ≤ ATR(700) × 1.0 + margin`

This is the first time in this project's history that `at_support=True` has appeared in a panel evaluation setup packet.

---

## Integrity Statement

Phase 6.2 does **not** claim:
- The system can open positions in structural fixtures ← FALSE (positions_opened=0)
- The panel threshold is too strict ← The panel is correctly strict; 12/20 is a correct hold
- The S/R detection was the only blocker ← Phase 6.2 reveals additional blockers

Phase 6.2 **does** confirm:
- TechnicalStructureGroup functions correctly; it creates qualified S/R levels from proper fixture data
- H3-005 + candlestick co-occurrence IS achievable (4 events across 785 bars)
- Composite scores reach 0.8364 when all three signal groups contribute
- The remaining gap is in the panel evaluation layer: `structure_quality`, `trend_direction`, and candlestick packet assembly

---

## Next Phase

Phase 6.3 options are documented in `PHASE_6_2_HANDOFF.md`.

The primary finding is that closing the 2-approval gap requires addressing `structure_quality='none'` and ensuring the candlestick pattern name reaches the evaluators. These are informational gaps in packet assembly, not scoring algorithm bugs.
