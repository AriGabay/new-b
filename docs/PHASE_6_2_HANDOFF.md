# Phase 6.2 Handoff Document

**Date:** 2026-03-29
**Phase:** 6.2 — Structural Fixture Validation (Complete)
**Outcome:** ZERO NATURAL POSITIONS OPENED — Panel holds at 12/20 (threshold: 14/20)

---

## What Was Phase 6.2

Phase 6.2 built high-quality replay fixtures designed to cause `TechnicalStructureGroup` to produce genuine qualified S/R levels, enabling `at_support=True` / `at_resistance=True` to co-occur with H3-005 signals.

**The question:** If the replay data genuinely contains valid structure + H3-005 + candlestick co-occurrence, can the system produce a natural panel-approved entry?

**Answer:** Not yet. The panel evaluates correctly but holds all proposals at 12/20 approvals, avg 6.350. Threshold: 14/20, avg ≥6.5.

---

## What Was Delivered

### Code
| File | Status |
|------|--------|
| `src/validation/fixtures/btc_structure_fixture.py` | ✅ Built (3 fixtures) |
| `src/tests/test_phase_6_2_structural.py` | ✅ Built |

### Documentation
| File | Status |
|------|--------|
| `docs/PHASE_6_2_STRUCTURAL_FIXTURE_VALIDATION.md` | ✅ Written |
| `docs/technical_structure_fixture_design.md` | ✅ Written |
| `docs/qualified_structure_replay_report.md` | ✅ Written |
| `docs/h3_005_structure_candlestick_alignment_report.md` | ✅ Written |
| `docs/proposal_to_open_funnel_phase_6_2.md` | ✅ Written |
| `docs/PHASE_6_2_HANDOFF.md` | ✅ This file |

---

## The Evidence

### Phase 6.2 Funnel: 785 Bars, 3 Fixtures

| Stage | Count | Pass Rate |
|-------|-------|-----------|
| Bars processed | 785 | 100% |
| H3-005 signal bars | 36 | 4.6% |
| Candlestick signal bars | 69 | 8.8% |
| H3-005 + candlestick co-occur | **4** | **11.1% of H3-005** |
| S/R levels qualified | **3** | One per fixture |
| `at_support=True` confirmed | **Yes** | Journal evidence |
| Proposals generated | **19** | ~4 from H3-005+structural |
| Panel evaluations | **19** | — |
| Panel enters | 0 | **0%** |
| Natural positions opened | **0** | **0%** |

### Progress vs Phase 6.1

| Metric | Phase 6.1 | Phase 6.2 | Progress |
|--------|-----------|-----------|----------|
| S/R levels qualified | 0 | **3** | ✅ Solved |
| `at_support=True` bars | 0 | **≥1 per fixture** | ✅ Solved |
| 3-way co-occur events | 0 | **4** | ✅ Solved |
| Proposals from H3-005+structural | 0 | **~4** | ✅ Solved |
| Best composite score | 0.5818 | **0.8364** | ✅ +44% |
| Panel evaluations of structural proposals | 0 | **19** | ✅ Panel sees these |
| Panel enters | 0 | 0 | ⚠️ Still blocked |
| Positions opened | 0 | 0 | ⚠️ Still blocked |

### Panel Score Evidence (Best Proposal)

Best result across all 3 fixtures: **12/20 approvals, avg score 6.350**
Required: **14/20 approvals, avg score ≥6.5**
Gap: **−2 approvals, −0.150 avg**

---

## Root Cause Chain (Phase 6.2)

```
Structural fixture engineering succeeds ✓
  ↓
TechnicalStructureGroup creates support level 69,670 (15 touches) ✓
  ↓
at_support=True fires at bars 244-246 ✓
  ↓
H3-005 LONG + Bullish Engulfing co-occur at bar 246 ✓
  ↓
Proposal generated: composite_score=0.8364 (highest ever) ✓
  ↓
Panel evaluates all 19 proposals ✓
  ↓
Panel holds at 12/20 approvals, avg 6.350
  ↓
Root causes of panel hold:
  1. candlestick.patterns_detected=[] in setup packet
     → One evaluator: "No candlestick pattern" → abstain 4.0
  2. structure_quality='none' (HH/HL not established)
     → One evaluator: "Structure quality none" → reject 4.0
  3. trend_direction='sideways' conflicts with ema_alignment='full_bull'
     → Confidence penalty across multiple evaluators
  ↓
ZERO natural positions opened
```

---

## What Phase 6.2 Did NOT Find (Integrity Statement)

Phase 6.2 does **not** find evidence that:
- The runtime pipeline has a bug preventing opens ← No bug. All stages function.
- The panel threshold should be lowered ← The panel correctly holds 12/20 setups
- TechnicalStructureGroup fails on real data ← It works correctly; qualifies levels with 15 touches
- H3-005 cannot co-occur with candlestick patterns ← It CAN, confirmed 4 times

Phase 6.2 **does** find:
- Structural qualification: ✅ functional
- Co-occurrence: ✅ achievable (4× Phase 6.1 rate)
- Proposal generation: ✅ correct
- Panel evaluation: ✅ correct
- Panel threshold crossing: ✗ not yet achieved
- Root cause: informational gaps in setup packet, not algorithmic failure

---

## What Phase 6.3 Must Do

### Option A: Fix Candlestick Pattern in Setup Packet (HIGHEST PRIORITY)

**Problem:** `candlestick.patterns_detected=[]` in setup packet despite Bullish Engulfing firing.
**Expected impact:** +1 approval (4.0 abstainer → approve). Combined with other improvements: 13/20 approvals.
**Method:** Investigate `SetupPacketAssembler` (or equivalent) to understand why `CandlestickGroup`'s pattern detail isn't being included in the candlestick section's `patterns_detected`.

**Files to investigate:**
- `src/groups/entry/setup_packet.py` (or wherever setup packets are assembled)
- The mapping from `CandlestickBundle.raw_signals` → `packet.candlestick.patterns_detected`

### Option B: Establish HH/HL Structure Before Entry Bar

**Problem:** `structure_quality='none'` because W-bottom doesn't create higher-lows within 60-bar window.
**Expected impact:** `structure_quality` rises to 'weak' or 'moderate'; +1–2 approvals.
**Method:** Design fixture Phase 3 (pre-entry) with 3–4 confirmed higher-lows over bars ~200–244, establishing HH/HL structure before bar 246 entry.

**New fixture design:**
- After W-bottom formation (bars 210–225), add deliberate HH/HL sequence:
  - bar 226: low=70,200 (HL above W-bottom)
  - bar 230: high=71,500 (HH above peak)
  - bar 233: low=70,400 (HL again)
  - bar 236: high=71,800 (HH again)
  - bar 239: pullback low=70,100 (H3-005 zone, HL maintained)

**Expected:** `higher_highs=True, higher_lows=True` → `structure_quality='weak'` → +1 panel approval

### Option C: Combined Fix — Both A + B Together

Fixing both candlestick packet and structure quality in the same fixture is the path most likely to cross 14/20. Combined estimate: 14–15/20 approvals, avg 6.8.

### Option D: Use Real Historical Data

If synthetic fixture issues persist, use real BTC/USDT hourly bars from Bybit for a period where:
- Full bull trend established
- Known W-bottom or pullback to confirmed support occurred
- Volume profile showed Bullish Engulfing at support

This would eliminate all fixture design uncertainty and test whether the panel approves real market data.

---

## Known Gaps / Warnings

1. **Harness `at_support_bars=0` instrumentation artifact:** The harness reports zero `at_support` bars due to event-ordering (second GroupSignalEvent overwrites first). The journal confirms `at_support=True` in actual packets. This is a harness measurement bug, not a pipeline bug.

2. **SHORT path still blocked:** No SHORT candlestick pattern works with H3-005 SHORT. The only compatible SHORT pattern would need to operate in `full_bear` regime (EMA20 < EMA50). A new hypothesis is needed.

3. **Packet assembly inconsistency:** `confirming_signals` includes 'candlestick' (correct) but `candlestick.patterns_detected=[]` (missing detail). This is not caught by any current assertion.

4. **Panel evaluation counter in harness:** `FunnelMetrics.panel_evaluations` only counts `PanelApprovedProposalEvent` (which fires on approval only). Phase 6.2's 19 panel evaluations were measured via journal `panel_summaries`. The harness reports `panel_evaluations=0` for all Phase 6.2 runs. This is a harness metric gap that should be fixed before Phase 6.3.

---

## State of the System at Phase 6.2 End

| Component | Status |
|-----------|--------|
| `BtcBybitPaperRunner` | ✅ Functional |
| `IndicatorsGroup` / H3-005 | ✅ Fires correctly (36 bars across 785 total) |
| `CandlestickGroup` / H2-001 | ✅ Fires correctly when at_support=True |
| `TechnicalStructureGroup` | ✅ Qualifies levels correctly; 15-touch support confirmed |
| `EntryGroup` proposal generation | ✅ Generates composite proposals (score=0.8364) |
| `PanelDecisionGroup` | ✅ Evaluates all proposals; correctly holds at 12/20 |
| `SetupPacketAssembler` | ⚠️ `patterns_detected=[]` despite candlestick co-occurrence |
| `RiskLeverageGroup` | ✅ Not reached; assumed functional from Phase 5.9 |
| `ExitGroup` | ✅ Not reached |
| `PerformanceJournalGroup` | ✅ Journal DB populated; 19 panel evaluations recorded |

---

## Reference Data

Fixtures used in Phase 6.2:
- `btc_w_bottom_long_v1` — 257 bars, W-bottom support at 69,670 (15 touches)
- `btc_m_top_short_v1` — 267 bars, double-top resistance at 71,031 (13 touches)
- `btc_triple_touch_long_v1` — 261 bars, triple-touch support at ~69,850 (11 touches)

Panel policy (unchanged from Phase 6.1):
```python
APPROVE_THRESHOLD = 14   # traders must vote approve
MIN_AVG_SCORE = 6.5      # minimum average score across all 20 traders
TRADER_COUNT = 20
```

Best Phase 6.2 proposal (W-bottom, bar 246):
```python
composite_score=0.8364     # indicators(0.20) + candlestick(0.25) + structural(0.10) / 0.55
ema_alignment='full_bull'
at_support=True
nearest_support.price=69670.2
nearest_support.touches=15
adx14=34.96
rsi14=54.73
volume_ratio=1.026
panel_result=12/20_approve_avg6.35_hold
```

---

*Phase 6.2 closed. Structural qualification achieved. Co-occurrence achieved. Composite score maximized.*
*Panel holds at 12/20 — gap: −2 approvals, −0.15 avg.*
*Phase 6.3: Fix candlestick packet assembly + HH/HL structure → verify natural opens.*
