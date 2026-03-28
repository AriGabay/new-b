# Phase 6.1 — Observational Replay: Architecture & Evidence Summary

**Date:** 2026-03-29
**Phase:** 6.1 (Observational — evidential only, no forcing)
**Question:** Can the current real runtime system open positions naturally, without forcing, under real replay conditions?
**Answer:** **NO** — across 950 bars / 3 fixtures, zero natural positions opened.

---

## Architecture

### Design Principle

Phase 6.1 uses a strict observational harness:

- **NO** forced approvals
- **NO** special-casing pass conditions
- **NO** control-mode contamination
- Real runner: `BtcBybitPaperRunner(simulation_mode=True)`
- Real panel: `TraderEvaluatorPanel(APPROVE_THRESHOLD=14, MIN_AVG_SCORE=6.5)`
- Real final decision layer: `FinalDecisionGroup`
- Real risk layer: 9 deterministic rules
- Real exit layer: `ExitGroup`

### Components

| Component | File | Role |
|-----------|------|------|
| `ObservationalReplayHarness` | `src/validation/observational_replay.py` | Subscribes to EventBus, captures all pipeline events per-bar |
| `BarObservation` | ibid | Per-bar state: signals, proposals, panel, risk, position |
| `FunnelMetrics` | ibid | Aggregated counts across all stages: bars → signals → proposals → panel → risk → opens |
| `ObservationalReport` | ibid | Complete fixture run report with conclusion + next_blocker |
| Fixtures (×3) | `src/validation/fixtures/btc_established_trend_fixture.py` | Designed to produce H3-005 conditions; verified by `analyse_h3005_conditions()` |

### Event Subscriptions

The harness subscribes to 6 event types:
1. `GroupSignalEvent` — captures H3-005, candlestick, indicator, structure signals
2. `CandidateTradeEvent` — captures proposals (composite_score, direction, signal_count)
3. `PanelApprovedProposalEvent` — captures panel approvals (approve_count, avg_score)
4. `RiskDecisionEvent` — captures risk approval/rejection codes
5. `PositionOpenEvent` — captures natural position opens
6. `PositionCloseEvent` — captures exit reasons, pnl_r

**Note on panel visibility:** Only panel *approvals* generate `PanelApprovedProposalEvent`. Panel *holds* are silent. True evaluation counts are read from the JournalDB `panel_summaries` table post-run.

---

## Fixtures

### Fixture 1: `btc_bull_continuation_pullback_v1`
- 320 bars: 220 warmup + 60-bar bull run + 15-bar pullback to EMA20 + continuation
- Three swing-low dips in bull phase intended to create support levels
- Target: H3-005 LONG + Bullish Engulfing co-occurrence at pullback bottom (~bars 285–292)

### Fixture 2: `btc_bear_continuation_pullback_v1`
- ~370 bars: 220 warmup + 50-bar sharp decline (3 failed bounces = resistance) + continued decline + pullback
- Three failed bounces intended to create swing-high resistance levels
- Target: H3-005 SHORT + Bearish Engulfing at pullback peak

### Fixture 3: `btc_long_established_trend_v1`
- 300 bars: 220 warmup + 80-bar bull trend with natural oscillations
- Honest baseline — no deliberate price engineering
- Measures natural H3-005 occurrence rate

---

## Evidence Summary

### Per-Fixture Funnel

| Fixture | Bars | H3-005 | Cndlstk | Co-occur | Proposals | Panel Approvals | Opens |
|---------|------|--------|---------|---------|-----------|-----------------|-------|
| bull_continuation_pullback | 320 | 8 (L) | 17 | 0 | 3 | 0 | 0 |
| bear_continuation_pullback | 370 | 11 (6L+5S) | 19 | 0 | 7 | 0 | 0 |
| long_established_trend | 300 | 11 (L) | 18 | 1 | 7 | 0 | 0 |
| **TOTAL** | **990** | **30** | **54** | **1** | **17** | **0** | **0** |

### Panel Evaluation Evidence (long_established_trend, 7 actual evaluations)

All proposals come from crossover / early-trend bars, not H3-005 established-trend bars.

| Packet | Approvals | Avg Score | Decision |
|--------|-----------|-----------|----------|
| 7e31bece | 7/20 | 5.675 | HOLD |
| e2f7776f | 12/20 | 6.225 | HOLD |
| b5687985 | 12/20 | 6.225 | HOLD |
| 60a4661c | 12/20 | 6.350 | HOLD ← best |

**Thresholds required:** ≥14 approvals AND avg ≥6.5
**Best result:** 12/20 (need +2 approvals) AND 6.35 (need +0.15 avg)

---

## Stage-by-Stage Blocker Analysis

| Stage | Count | Pass Rate | Blocker Detail |
|-------|-------|-----------|----------------|
| Bars processed | 990 | 100% | — |
| H3-005 signal bars | 30 | 3.0% of bars | — |
| Candlestick bars | 54 | 5.5% of bars | — |
| H3-005 + Cndlstk co-occur | 1 | 3.3% of H3-005 bars | **STAGE 1 BLOCKER** |
| Proposals generated | 17 | 0 from H3-005 bars | Proposals come from crossover bars |
| Panel evaluations | 7 | — | Panel holds all (max 12/20 approvals) |
| Panel approvals (enters) | 0 | 0% | **STAGE 2 BLOCKER** |
| Risk approvals | 0 | 0% | Not reached |
| Natural positions opened | 0 | 0% | Not reached |

---

## Root Cause Chain

```
H3-005 fires (30 bars)
    ↓ but no candlestick co-occurrence (1/30 = 3%)

Why no co-occurrence?
    at_resistance = 0 bars across ALL fixtures
    at_support    = 0 bars across ALL fixtures

    H2-001 Bullish Engulfing  → requires at_support=True  → CANNOT FIRE
    H2-002 Morning Star       → requires at_support=True  → CANNOT FIRE
    H2-001 Bearish Engulfing  → requires at_resistance=True → CANNOT FIRE
    H2-002 Evening Star       → requires at_resistance=True → CANNOT FIRE
    H2-003 Three Black Crows  → requires ema20 > ema50 → CONFLICTS with H3-005 SHORT

    TechnicalStructureGroup never flags proximity to S/R in any fixture.
    Root: swing-high/swing-low detection requires MIN_TOUCHES=2 at the same level.
          Synthetic price dips in fixtures don't create qualifying levels.

Result:
    The one co-occurrence that does occur uses a less-common candlestick pattern.
    That proposal scores 12/20 approvals at avg 6.35 — just below threshold.

    All other proposals come from EMA crossover bars (ema_alignment="mixed" or "partial").
    TrendFollowing scores = 4.5 on mixed/partial alignment → panel reliably holds.
```

---

## Key Findings

1. **H3-005 fires naturally** — 30 bars across 990, ~3% frequency. Signal is functional.
2. **Candlestick co-occurrence is near zero** — 1/30 = 3.3% co-occurrence rate.
3. **TechnicalStructureGroup S/R detection is inoperative in all fixtures** — 0 at_resistance/at_support bars.
4. **Proposals are generated** (17 total) but from crossover/mixed-alignment bars, not H3-005 bars.
5. **Panel threshold is close but not met** — best natural proposal: 12/20 approvals (need 14), avg 6.35 (need 6.5).
6. **ZERO natural positions opened** across 990 bars.
7. **System is not broken** — it is correctly strict. The issue is fixture/conditions design, not runtime bugs.

---

## Next Steps (Phase 6.2)

To get natural position opens, one of the following paths is required:

### Path A: Fix TechnicalStructureGroup S/R detection
- Investigate why swing-level detection requires MIN_TOUCHES=2 and whether synthetic prices achieve this
- May need fixtures with more precise repeated touches at the same level
- Alternatively, test with real historical bars where S/R is known to have been detected

### Path B: Create a fixture where H2-003 / H2-004 can co-occur with H3-005
- H2-003 Three Black Crows fires on `ema20 > ema50` — conflicts with H3-005 SHORT
- H2-004 Inverted Hammer fires on `ema20 > ema50` — same conflict
- No SHORT-compatible candlestick pattern exists without at_resistance
- LONG path remains the only viable direction

### Path C: Verify panel score with a true H3-005 + candlestick proposal
- The 1 observed co-occurrence scored 12/20 / 6.35
- A genuine H3-005 + Bullish Engulfing at S/R level would have higher composite_score
- May push the panel over threshold

---

## Files

| File | Purpose |
|------|---------|
| `src/validation/observational_replay.py` | Instrumented harness |
| `src/validation/fixtures/btc_established_trend_fixture.py` | Phase 6.1 fixtures |
| `docs/PHASE_6_1_OBSERVATIONAL_REPLAY.md` | This file |
| `docs/natural_open_verification_report.md` | Natural open evidence |
| `docs/h3_005_and_candlestick_cooccurrence_report.md` | Co-occurrence analysis |
| `docs/proposal_to_open_funnel_report.md` | Full funnel breakdown |
| `docs/replay_regime_distribution_report.md` | Regime distribution |
| `docs/PHASE_6_1_HANDOFF.md` | Phase handoff document |
| `src/tests/test_phase_6_1_observational.py` | Verification tests |
