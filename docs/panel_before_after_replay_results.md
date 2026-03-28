# Panel Before/After Replay Results

**Date:** 2026-03-28
**Phase:** 5.9

---

## Overview

This document records the exact panel scoring results for Phase 3 proposals:
1. Best replay candidate — before repair
2. Best replay candidate — after repair
3. Ideal synthetic Phase 3 proposal — after repair (proof of panel viability)

All replay data is sourced from `btc_bull_breakout_v1` fixture, bar 29 (SHORT proposal at EMA death cross, at_resistance=True, bear macro).

---

## Source Classification

| Dataset | Source Tag | Purpose |
|---------|------------|---------|
| Phase 5.75 replay harness | `REPLAY_SOURCE` | Natural runtime proposals |
| Ideal synthetic packet | `SYNTHETIC_PROOF_SOURCE` | Panel ceiling verification |

These sources are never mixed. The synthetic packet is used only to prove the panel ceiling is above thresholds — it is not a runtime signal.

---

## Before Repair: Best Phase 5.75 Candidate

**Proposal:** SHORT, bar 29 of `btc_bull_breakout_v1`
**Conditions:** `ema_alignment="mixed"`, `volume_ratio=0.92`, no candlestick patterns, `structure_quality="none"`, `at_resistance=True`, R:R=2.0, macro=bear

| # | Evaluator | Score | Vote | Notes |
|---|-----------|-------|------|-------|
| 1 | TrendFollowing | 4.5 | reject | ema_alignment="mixed" → -2.0 penalty |
| 2 | Momentum | 5.5 | abstain | volume_ratio=0.92 penalty |
| 3 | MeanReversion | 6.0 | abstain | Not a reversal entry |
| 4 | Breakout | 4.5 | reject | No confirmed patterns, volume<1.0 |
| 5 | Structure | 7.5 | approve | at_resistance=True |
| 6 | Candlestick | 4.0 | abstain | No patterns detected |
| 7 | RiskParity | **3.0** | approve | **BUG: rr=2.0 → score=3.0 (old formula)** |
| 8 | Volatility | 7.0 | approve | Normal volatility regime |
| 9 | VolumeProfile | 5.0 | abstain | volume_ratio<1.0 |
| 10 | MacroRegime | 9.0 | approve | Bear macro, SHORT direction |
| 11 | Contrary | 4.0 | reject | structure_quality="none" → cannot approve |
| 12 | ProfitTarget | 7.0 | approve | R:R=2.0 sufficient |
| 13 | EntryTiming | 8.0 | approve | at_resistance=True |
| 14 | Confluence | 7.5 | approve | 5/7 agreements (missing pattern, not "strong" structure) |
| 15 | DrawdownRisk | **5.0** | abstain | **BUG: no positive adjustments, caps at 5.0** |
| 16 | LeverageSpecialist | 8.0 | approve | Negative leverage for SHORT → conservative |
| 17 | PatternCompletion | **4.0** | **reject** | **BUG: groups_contributed not checked** |
| 18 | WickAnalysis | 5.5 | abstain | No candle pattern context |
| 19 | MarketContext | 6.0 | abstain | Limited context without chart patterns |
| 20 | ExecutionQuality | 7.0 | approve | Setup quality "B" |

**Before repair totals:**
- Approve count: **9/20**
- Avg score: **5.90**
- Reject count: 4 (TrendFollowing, Breakout, Contrary, PatternCompletion)
- Panel decision: **HOLD** (requires 14/20 and avg ≥ 6.5)

---

## After Repair: Same Replay Candidate (Bar 29, btc_bull_breakout_v1)

**Same proposal, same conditions.** Only 3 evaluators changed behavior:

| # | Evaluator | Score | Vote | Change? |
|---|-----------|-------|------|---------|
| 1 | TrendFollowing | 4.5 | reject | No change |
| 2 | Momentum | 5.5 | abstain | No change |
| 3 | MeanReversion | 6.0 | abstain | No change |
| 4 | Breakout | 4.5 | reject | No change |
| 5 | Structure | 7.5 | approve | No change |
| 6 | Candlestick | 4.0 | abstain | No change |
| 7 | **RiskParity** | **7.0** | **approve** | **Score: 3.0 → 7.0 (formula fix)** |
| 8 | Volatility | 7.0 | approve | No change |
| 9 | VolumeProfile | 5.0 | abstain | No change |
| 10 | MacroRegime | 9.0 | approve | No change |
| 11 | Contrary | 4.0 | reject | No change |
| 12 | ProfitTarget | 7.0 | approve | No change |
| 13 | EntryTiming | 8.0 | approve | No change |
| 14 | Confluence | 7.5 | approve | No change |
| 15 | **DrawdownRisk** | **5.5** | **abstain** | **Score: 5.0 → 5.5 (R:R=2.0 → +0.5 partial lift)** |
| 16 | LeverageSpecialist | 8.0 | approve | No change |
| 17 | **PatternCompletion** | **5.0** | **abstain** | **Score: 4.0 → 5.0 (architecture-aware abstain)** |
| 18 | WickAnalysis | 5.5 | abstain | No change |
| 19 | MarketContext | 6.0 | abstain | No change |
| 20 | ExecutionQuality | 7.0 | approve | No change |

**After repair totals (replay candidate):**
- Approve count: **9/20** (same — RiskParity was already approving)
- Avg score: **6.05** (was 5.90, delta: +0.15)
- Reject count: **3** (was 4 — PatternCompletion removed from reject column)
- Panel decision: **HOLD** (still below 14/20 threshold)

### Why the replay candidate still doesn't pass:

The score improvement (+0.15 avg) is real but insufficient to reach 14/20. The fundamental issue is **not the 3 repaired evaluators** — it's the signal quality of the proposal itself:

- `ema_alignment="mixed"` → TrendFollowing scores 4.5 (reject). This is a crossover bar — the EMA transition is happening, not established.
- `volume_ratio=0.92` → 3 evaluators penalize below-average volume
- No candlestick patterns → Candlestick, WickAnalysis, MarketContext cannot score well
- `structure_quality="none"` → Contrary cannot approve (requires "strong" structure)
- `at_resistance=True` with poor signal quality → EntryTiming approves but other structure evaluators score weakly

**This is correct behavior.** The panel correctly identifies a noisy, low-confidence entry at an EMA crossover with below-average participation.

---

## After Repair: Ideal Synthetic Phase 3 Proposal (Panel Ceiling Proof)

**Conditions:** `ema_alignment="full_bear"`, `volume_ratio=1.85`, `evening_star` pattern, `at_resistance=True`, `structure_quality="strong"`, R:R=3.5, macro=bear, `stop_pct=2.1%`, normal volatility

This is a synthetic packet constructed to verify the panel ceiling. Not from live replay.

| # | Evaluator | Score | Vote |
|---|-----------|-------|------|
| 1 | TrendFollowing | 10.0 | approve |
| 2 | Momentum | 6.5 | approve |
| 3 | MeanReversion | 6.0 | abstain |
| 4 | Breakout | 5.0 | abstain |
| 5 | Structure | 10.0 | approve |
| 6 | Candlestick | 10.0 | approve |
| 7 | RiskParity | 9.0 | approve |
| 8 | Volatility | 7.0 | approve |
| 9 | VolumeProfile | 8.0 | approve |
| 10 | MacroRegime | 9.0 | approve |
| 11 | Contrary | 7.0 | approve |
| 12 | ProfitTarget | 8.0 | approve |
| 13 | EntryTiming | 7.0 | approve |
| 14 | Confluence | 10.0 | approve |
| 15 | DrawdownRisk | 6.5 | approve |
| 16 | LeverageSpecialist | 8.0 | approve |
| 17 | PatternCompletion | 5.0 | abstain |
| 18 | WickAnalysis | 5.5 | abstain |
| 19 | MarketContext | 9.0 | approve |
| 20 | ExecutionQuality | 9.0 | approve |

**Ideal Phase 3 SHORT totals:**
- Approve count: **16/20** ✅ (threshold: 14)
- Avg score: **7.78** ✅ (threshold: 6.5)
- Reject count: **0**
- Abstain count: **4** (MeanReversion, Breakout, PatternCompletion, WickAnalysis)
- Panel decision: **ENTER** ✅

FinalDecisionGroup rails:
| Rail | Status |
|------|--------|
| avg_score < 5.0 | Not triggered (7.78) |
| reject_count > 12 | Not triggered (0) |
| R:R < 1.5 | Not triggered (R:R=3.5) |
| setup_quality == invalid | Not triggered ("A" quality) |
| bear regime + long | Not triggered (SHORT) |
| high_vol + <16 approvals | Not triggered (normal vol, 16≥16) |

Final output: **"enter"**

---

## Delta Summary

| Metric | Before Repair (replay) | After Repair (replay) | After Repair (ideal) |
|--------|----------------------|----------------------|---------------------|
| PatternCompletion score | 4.0 (reject) | 5.0 (abstain) | 5.0 (abstain) |
| RiskParity score | 3.0 (approve) | 7.0 (approve) | 9.0 (approve) |
| DrawdownRisk score | 5.0 (abstain) | 5.5 (abstain) | 6.5 (approve) |
| Total approve count | 9/20 | 9/20 | 16/20 |
| Avg score | 5.90 | 6.05 | 7.78 |
| Panel decision | hold | hold | **enter** |

---

## Key Finding

The Phase 5.75 replay proposals are **genuinely weak** and correctly held by the panel after the repair. The repair does not convert bad proposals into approvals — it removes structural barriers that would have blocked genuinely good proposals. The ideal synthetic test confirms the panel can and will approve strong Phase 3 proposals.

Natural positions will open when the runtime produces proposals with the signal conditions documented in `panel_threshold_alignment_report.md`.
