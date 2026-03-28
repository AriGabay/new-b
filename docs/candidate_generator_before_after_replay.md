# Candidate Generator Before/After Replay Results

**Date:** 2026-03-29
**Phase:** 6

---

## Overview

This document records what is known about replay proposal generation before and after the Phase 6 candidate generator repair, and explains what "replay" evidence is and is not available.

---

## Source Classification

| Source | Tag | Validity |
|--------|-----|---------|
| Phase 5.75 natural replay | `REPLAY_SOURCE` | Real runtime path, 900 bars, btc_bull_breakout_v1 + btc_bear_drop_v1 |
| Phase 5.9 panel synthetic | `SYNTHETIC_PROOF_SOURCE` | Panel ceiling proof only — not runtime signals |
| Phase 6 analysis | Projected from signal conditions | Signal condition analysis, not forced scenarios |

---

## Before Phase 6 Repair (Phase 5.75 Replay)

**Runtime**: Phase 5.75 replay harness, 2 fixtures × ~450 bars each ≈ 900 bars

**Proposals generated**: 8 natural CandidateTradeEvents

**Panel outcomes**: 0 panel approvals, 0 positions opened

**Proposal profile** (all 8 were similar):
- Triggered at: EMA20/50 crossover bars (H3-002 death cross or golden cross)
- EMA alignment: `"mixed"` (close above EMA200, EMA20 just crossed EMA50)
- Volume: 0.92x average
- Candlestick: No patterns detected
- Structure quality: `"none"` at most bars
- Panel score: 9/20 approve, avg=6.05 → HOLD

**Root causes of panel rejection** (pre-Phase 5.9):
1. PatternCompletion architecture error: 4.0 reject (fixed in Phase 5.9)
2. RiskParity formula bug: 3.0 score (fixed in Phase 5.9)
3. DrawdownRisk permanent abstain (fixed in Phase 5.9)

**Root causes of panel rejection** (post-Phase 5.9, pre-Phase 6):
4. EMA alignment "mixed": TrendFollowing 4.5 (reject) — structural, not a bug
5. No candlestick: Candlestick 4.0, WickAnalysis low — correct, not a bug

The Phase 5.9 repair fixed (1–3), but (4–5) persist because they reflect genuinely weak signal conditions at crossover bars.

---

## After Phase 6 Repair — Expected Behavior

The Phase 6 repair changes the TRIGGER CONDITION for proposals, not the panel thresholds. Therefore:

### Old proposals (EMA crossover bars): No longer generated

The candlestick gate now requires at least 1 candlestick signal in the primary direction. At EMA crossover bars:
- CandlestickGroup typically detects no patterns (the crossover bar is an indicator artifact, not a price action event)
- The gate blocks these proposals before they reach the panel

**Before repair**: 8 proposals (all rejected)
**After repair**: ~0 proposals at crossover bars (blocked at gate)

### New proposals (established trend pullback bars): Expected to generate

H3-005 fires when:
- EMA alignment = "full_bear" or "full_bull" (established trend)
- Price is near EMA20 (within 3%) — the pullback zone
- ADX ≥ 25, volume ≥ 1.0x, RSI 35–65

These bars coincide with periods where CandlestickGroup can detect patterns (Three Black Crows when pullback collapses; Bearish Engulfing when pullback reverses at resistance; Evening Star 3-bar reversal at EMA20 if structural level present).

**Fixture analysis** (btc_bull_breakout_v1 Phase 1: bars 0–220, downtrend 70000→63000):
- During this phase, EMA20 < EMA50 < EMA200 established (after initial crossover)
- Price makes pullbacks in the declining trend
- TechnicalStructureGroup computes swing resistance levels above price
- If pullback reaches EMA20 near a swing resistance: H3-005 fires + CS pattern likely

**Number of proposals**: Cannot be precisely estimated without running the full replay. Key dependencies:
- How many bars have H3-005 + candlestick pattern coinciding
- How many meet the structural context requirements for candlestick patterns
- Whether the macro regime is "bear" for relevant SHORT proposals

---

## Why Exact Post-Repair Replay Numbers Are Not Available

The Phase 6 repair involves CandlestickGroup's pattern detection and TechnicalStructureGroup's structural cache working together across multiple bars. Running a full 900-bar replay to collect exact proposal counts would require:

1. The replay harness (Phase 5.75 infrastructure) to be re-run
2. Logging of each H3-005 signal, each candlestick bundle, and each gate outcome
3. Full panel evaluation for any proposals that fire

This analysis is deferred to Phase 6.1 (live observation). The honest assessment is:

**We do not have exact post-repair replay proposal counts.** What we have:

- **Confirmed**: H3-005 fires correctly in unit tests (20/20 tests pass)
- **Confirmed**: The candlestick gate correctly blocks indicator-only proposals
- **Confirmed**: Composite score with H3-005 + candlestick + structure ≈ 0.83 (above 0.50)
- **Confirmed**: Panel passes ideal Phase 3 proposal (16/20, avg=7.78) — unchanged from Phase 5.9
- **Estimated**: Some proposals will fire in the downtrend phase of replay fixtures where H3-005 and CS patterns coincide
- **Uncertain**: Exact count of new proposals and how many pass the panel

---

## Before/After Summary Matrix

| Metric | Phase 5.75 (pre-repair) | Phase 6 (post-repair) | Notes |
|--------|------------------------|----------------------|-------|
| Proposals at crossover bars | 8 | ~0 | Blocked by candlestick gate |
| Proposals at pullback-to-EMA bars | 0 | TBD (estimated > 0) | H3-005 + CS required |
| Panel approvals | 0 | TBD | Depends on proposal quality |
| Positions opened | 0 | TBD | Depends on panel + risk layer |
| Panel threshold | 14/20, avg≥6.5 | 14/20, avg≥6.5 | UNCHANGED |
| Forced approvals | 0 | 0 | No forced approvals in repair |
| Composite score at gate | 0.45–0.50 | 0.79–0.83 (expected) | Signal profile change |
| EMA alignment of proposals | "mixed" | "full_bear" / "full_bull" | Structural improvement |

---

## Selectivity Preservation

The repair does not sacrifice selectivity:

1. **Gate tightened** (not loosened): Adding the candlestick requirement REDUCES the number of proposals that can pass the gate (previously indicator-only could pass; now they can't).

2. **Signal quality improved**: H3-005 + candlestick proposals have objectively better signal profiles (full alignment, volume ≥ 1.0x, RSI 35–65, candlestick at structure).

3. **Panel unchanged**: 14/20, avg ≥ 6.5 thresholds are intact. A strong H3-005 + CS proposal needs to earn those votes just like any other proposal.

4. **Test verification**: The weak proposal (mixed EMA, no candlestick) still produces HOLD in panel regression tests, confirming selectivity is preserved.

The Phase 6 repair produces **fewer proposals** (crossover transitions are now blocked) but **higher-quality proposals** (each proposal has full trend alignment + candlestick confirmation). This is the correct direction.
