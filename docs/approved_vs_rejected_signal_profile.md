# Approved vs Rejected Signal Profile

**Date:** 2026-03-29
**Phase:** 6

---

## Purpose

Compare the signal profile of proposals the panel REJECTS (current Phase 5.75 replay candidates) versus the profile of proposals the panel APPROVES (ideal Phase 3 synthetic), and map the delta to specific upstream fixes.

---

## Profile Comparison

| Dimension | Rejected (Phase 5.75 replay) | Approved (ideal Phase 3) | Delta |
|-----------|------------------------------|--------------------------|-------|
| **EMA alignment** | `"mixed"` — close > EMA200, EMA20 ≈ EMA50 | `"full_bear"` — close < EMA20 < EMA50 < EMA200 | Most impactful |
| **Generation timing** | At exact EMA20/50 crossover bar | During established downtrend pullback | Structural |
| **EMA separation** | ~0% (just crossed) | ≥ 0.2–0.5% (committed trend) | Fixed by H3-005 |
| **Candlestick pattern** | None (0 patterns) | `evening_star` at resistance | Fixed by gate enforcement |
| **candlestick_quality** | 0.0 | 0.70–0.75 | Fixed by bundle wait |
| **indicator_quality** | 0.85 (death_cross) | 0.85–0.90 (H3-005) | Similar |
| **Volume ratio** | 0.92x (below average) | ≥ 1.2x | Fixed by H3-005 requirement |
| **Structure quality** | `"none"` | `"strong"` | Indirect (H3-005 requires pullback to level) |
| **RSI** | 75.14 rising (still overbought) | 72.0 falling or 50 mid-zone | Fixed by H3-005 RSI 35–65 gate |
| **at_resistance** | True | True | Same |
| **R:R** | 2.0 | 3.5 | Not in scope of this phase |
| **Macro** | bear (correct) | bear (correct) | Same |
| **Composite score** | 0.45–0.50 (borderline) | 0.83 (well above) | Fixed |

---

## Panel Score Breakdown Comparison

### Rejected (Phase 5.75 replay best candidate) — After Phase 5.9 repair

| # | Evaluator | Score | Vote | Root cause |
|---|-----------|-------|------|-----------|
| 1 | TrendFollowing | 4.5 | reject | `ema_alignment="mixed"` → -2.0 penalty |
| 2 | Momentum | 5.5 | abstain | RSI 75.14 rising, volume 0.92x |
| 3 | MeanReversion | 6.0 | abstain | Not reversal entry |
| 4 | Breakout | 4.5 | reject | No patterns, vol < 1.0 |
| 5 | Structure | 7.5 | approve | at_resistance=True |
| 6 | Candlestick | 4.0 | abstain | No patterns detected |
| 7 | RiskParity | 7.0 | approve | R:R=2.0 → 7.0 (fixed) |
| 8 | Volatility | 7.0 | approve | Normal regime |
| 9 | VolumeProfile | 5.0 | abstain | volume_ratio=0.92 |
| 10 | MacroRegime | 9.0 | approve | Bear macro + SHORT |
| 11 | Contrary | 4.0 | reject | structure_quality="none" |
| 12 | ProfitTarget | 7.0 | approve | R:R=2.0 |
| 13 | EntryTiming | 8.0 | approve | at_resistance=True |
| 14 | Confluence | 7.5 | approve | 5/7 |
| 15 | DrawdownRisk | 5.5 | abstain | R:R=2.0, +0.5 lift |
| 16 | LeverageSpecialist | 8.0 | approve | |
| 17 | PatternCompletion | 5.0 | abstain | Group excluded (fixed) |
| 18 | WickAnalysis | 5.5 | abstain | No candlestick context |
| 19 | MarketContext | 6.0 | abstain | Limited context |
| 20 | ExecutionQuality | 7.0 | approve | |

**Totals: 9/20 approve, avg=6.05 → HOLD**

---

### Approved (Ideal Phase 3 synthetic) — After Phase 5.9 repair

| # | Evaluator | Score | Vote | Reason |
|---|-----------|-------|------|--------|
| 1 | TrendFollowing | 10.0 | approve | `ema_alignment="full_bear"` |
| 2 | Momentum | 6.5 | approve | RSI=72.0 falling, volume=1.8x |
| 3 | MeanReversion | 6.0 | abstain | Not reversal entry (expected) |
| 4 | Breakout | 5.0 | abstain | No chart pattern (expected) |
| 5 | Structure | 10.0 | approve | at_resistance=True, quality="strong" |
| 6 | Candlestick | 10.0 | approve | `evening_star` detected |
| 7 | RiskParity | 9.0 | approve | R:R=3.5 |
| 8 | Volatility | 7.0 | approve | Normal regime |
| 9 | VolumeProfile | 8.0 | approve | volume=1.8x |
| 10 | MacroRegime | 9.0 | approve | Bear macro + SHORT |
| 11 | Contrary | 7.0 | approve | R:R=3.5 > 3.0, quality="strong" |
| 12 | ProfitTarget | 8.0 | approve | R:R=3.5, target confirmed |
| 13 | EntryTiming | 7.0 | approve | at_resistance, atr normal |
| 14 | Confluence | 10.0 | approve | 6/7 agreements |
| 15 | DrawdownRisk | 6.5 | approve | R:R=3.5, stop=2.0% |
| 16 | LeverageSpecialist | 8.0 | approve | |
| 17 | PatternCompletion | 5.0 | abstain | Group excluded (neutral) |
| 18 | WickAnalysis | 5.5 | abstain | No wick analysis context |
| 19 | MarketContext | 9.0 | approve | Full context available |
| 20 | ExecutionQuality | 9.0 | approve | Setup quality "A" |

**Totals: 16/20 approve, avg=7.78 → ENTER**

---

## What Separates Reject from Approve

The critical differences (ranked by impact):

### 1. EMA alignment (highest impact)

- **Reject**: `"mixed"` → TrendFollowing **rejects** (4.5)
- **Approve**: `"full_bear"` → TrendFollowing **approves** (10.0)
- **Delta**: +5.5 score, flip from reject to approve = +2 votes net

TrendFollowing is the highest-weight evaluator in the panel (it covers the most fundamental question: "is the trade in the right direction?"). A reject from TrendFollowing costs ~1 approval vote AND drags avg score down by 5.5/20 = 0.275 points.

### 2. Candlestick pattern presence

- **Reject**: `patterns_detected=[]` → Candlestick **abstains** (4.0)
- **Approve**: `patterns_detected=["evening_star"]` → Candlestick **approves** (10.0)
- **Delta**: +6.0 score, abstain → approve = +1 vote

A detected pattern also unlocks:
- WickAnalysis: improves from 5.5 to higher
- MarketContext: from 6.0 to 9.0 (pattern context available)
- Confluence: 1 more agreement

### 3. Volume above average

- **Reject**: 0.92x → VolumeProfile abstains (5.0)
- **Approve**: 1.8x → VolumeProfile approves (8.0)
- **Delta**: +3.0 score, abstain → approve = +1 vote

### 4. Structure quality

- **Reject**: `structure_quality="none"` → Contrary rejects (4.0), Structure moderate
- **Approve**: `structure_quality="strong"` → Contrary approves (7.0), Structure 10.0
- **Delta**: Contrary flip from reject → approve = +2 net votes, avg +3/20 = +0.15

### 5. RSI position

- **Reject**: RSI=75.14 rising → momentum still bullish (bad for SHORT)
- **Approve**: RSI=72.0 falling → momentum turning bearish (good for SHORT)
- **Delta**: Momentum 5.5 → 6.5, abstain → approve = +1 vote

---

## How Phase 6 Repairs Address Each Gap

| Signal gap | Phase 6 fix | Mechanism |
|-----------|------------|----------|
| EMA alignment "mixed" | H3-005 requires full alignment | H3-005 only fires when EMA20 < EMA50 < EMA200 (full_bear) with meaningful separation |
| No candlestick pattern | Candlestick bundle required + gate enforced | EntryGroup waits for CS bundle; gate blocks proposals without CS signal |
| Volume below average | H3-005 requires volume ≥ 1.0x | Built into H3-005 conditions |
| RSI still overbought | H3-005 requires RSI 35–65 | Built into H3-005 conditions |
| Structure quality weak | Candlestick gate (CS patterns require at S/R) | Most CS patterns require structural context; H3-005 fires near EMA20 (often near structural levels) |

---

## Conclusion

The 8 Phase 5.75 proposals were uniformly rejected because they were generated at EMA crossover transition bars. Every critical signal dimension (EMA alignment, candlestick, volume, RSI) was in the wrong state at those bars.

The Phase 6 repair doesn't lower the panel bar — it generates proposals at bars where the signal quality is fundamentally different. H3-005 fires during the established trend phase; the candlestick gate ensures bar-level confirmation exists. Together, these changes produce proposals that are structurally compatible with the panel's requirements.
