# Natural Open Verification Report — Phase 6.1

**Date:** 2026-03-29
**Phase:** 6.1 Observational Replay
**Verdict: ZERO NATURAL POSITIONS OPENED**

This report documents the direct evidence that the BTC/Bybit runtime pipeline does not open positions naturally across any of the three Phase 6.1 observational fixtures.

---

## Question Being Answered

> Can the current real runtime system (BtcBybitPaperRunner, simulation_mode=True) open positions naturally — without any forced approvals, without any special-casing, using real panel thresholds and real risk rules — when run against realistic BTC price fixtures?

---

## Evidence

### Run Configuration

| Parameter | Value |
|-----------|-------|
| Runner | `BtcBybitPaperRunner(simulation_mode=True)` |
| Mode gate | `ModeGate.SHADOW` (paper trade mode) |
| Forced approvals | NONE |
| Panel APPROVE_THRESHOLD | 14 |
| Panel MIN_AVG_SCORE | 6.5 |
| Risk rules | 9 deterministic rules (unmodified) |
| Harness | `ObservationalReplayHarness` (event bus subscriber only) |

### Position Open Count by Fixture

| Fixture | Total Bars | Proposals | Panel Enters | Risk Approvals | **Positions Opened** |
|---------|-----------|-----------|-------------|----------------|----------------------|
| `btc_bull_continuation_pullback_v1` | 320 | 3 | 0 | 0 | **0** |
| `btc_bear_continuation_pullback_v1` | 370 | 7 | 0 | 0 | **0** |
| `btc_long_established_trend_v1` | 300 | 7 | 0 | 0 | **0** |
| **TOTAL** | **990** | **17** | **0** | **0** | **0** |

### Position Close Count by Fixture

| Fixture | Positions Closed | Exit Reasons |
|---------|-----------------|--------------|
| All | 0 | — |

---

## Why No Positions Opened

The pipeline has two primary blockers operating in sequence:

### Blocker 1: H3-005 and Candlestick Co-occurrence (Stage 1)

The `EntryGroup` requires at least one candlestick or chart-pattern signal to accompany an indicator signal before issuing a `CandidateTradeEvent`. This "candlestick gate" means pure H3-005 indicator signals cannot produce proposals alone.

Observed co-occurrence rates:
- `btc_bull_continuation_pullback_v1`: H3-005 fired 8 bars, candlestick fired 17 bars, co-occurrence = **0**
- `btc_bear_continuation_pullback_v1`: H3-005 fired 11 bars, candlestick fired 19 bars, co-occurrence = **0**
- `btc_long_established_trend_v1`: H3-005 fired 11 bars, candlestick fired 18 bars, co-occurrence = **1**

Total: 1 co-occurrence out of 30 H3-005 bars (3.3%).

The co-occurrence gap is caused by TechnicalStructureGroup never flagging `at_resistance=True` or `at_support=True`:
- All candlestick LONG patterns (H2-001 Bullish Engulfing, H2-002 Morning Star) require `at_support=True`
- All candlestick SHORT patterns (H2-001 Bearish Engulfing, H2-002 Evening Star) require `at_resistance=True`
- H2-003 Three Black Crows requires `ema20 > ema50` — conflicts with H3-005 SHORT (needs `ema20 < ema50`)
- Zero at_resistance bars detected; zero at_support bars detected

### Blocker 2: Panel Score Insufficient (Stage 2)

The 17 proposals that were generated come from EMA crossover / mixed-alignment bars (not H3-005 established-trend bars). These proposals score poorly because:
- `ema_alignment = "mixed"` → TrendFollowing evaluator scores 4.5/10
- Best observed proposal: 12/20 trader approvals, avg score 6.35
- Threshold requires: ≥14/20 approvals AND avg ≥6.5
- Gap: missing 2 approvals and 0.15 avg score points

The single H3-005 + candlestick co-occurrence (in long_established_trend fixture) produced a proposal that was evaluated and held by the panel. The co-occurrence composite score was higher than crossover-bar proposals but still below panel threshold.

---

## Integrity Verification

This report explicitly documents failure to open positions. The following claims are false and are not made here:
- ~~"The system successfully opened positions"~~
- ~~"Phase 6.1 validation passed"~~
- ~~"The pipeline is viable"~~

The system is **correctly strict**. The panel threshold (14/20, avg 6.5) represents a genuine quality bar that synthetic price fixtures — with their smooth price paths and absent structural levels — do not currently satisfy.

---

## Next Action

Phase 6.2 must either:
1. Establish a fixture where TechnicalStructureGroup detects valid S/R levels (requires repeated price touches)
2. Use real historical BTC bars where S/R structure has been empirically verified
3. Examine whether panel threshold can be justified for reduction (out of scope for observational phase)
