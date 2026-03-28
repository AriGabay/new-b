# Panel Compatibility of Upstream Proposals

**Date:** 2026-03-29
**Phase:** 6

---

## Purpose

Assess whether the upstream candidate generator now produces proposals that are compatible with the current panel policy, and what residual limitations remain.

---

## Compatibility Matrix: Old vs New Proposal Type

### Old: EMA Crossover (H3-002 only, indicator-only)

| Panel Evaluator | Score (old) | Reason |
|----------------|-------------|--------|
| TrendFollowing | 4.5 (reject) | ema_alignment="mixed" — -2.0 penalty |
| Momentum | 5.5 (abstain) | Volume 0.92x, RSI rising |
| MeanReversion | 6.0 (abstain) | Not reversal entry |
| Breakout | 4.5 (reject) | No patterns, low volume |
| Structure | 7.5 (approve) | at_resistance=True |
| Candlestick | 4.0 (abstain) | No pattern |
| RiskParity | 7.0 (approve) | R:R=2.0 → 7.0 (fixed) |
| Volatility | 7.0 (approve) | Normal |
| VolumeProfile | 5.0 (abstain) | vol=0.92x |
| MacroRegime | 9.0 (approve) | Bear + SHORT |
| Contrary | 4.0 (reject) | structure_quality="none" |
| ProfitTarget | 7.0 (approve) | R:R=2.0 |
| EntryTiming | 8.0 (approve) | at_resistance |
| Confluence | 7.5 (approve) | 5/7 |
| DrawdownRisk | 5.5 (abstain) | R:R=2.0 → 5.5 |
| LeverageSpecialist | 8.0 (approve) | |
| PatternCompletion | 5.0 (abstain) | Group excluded |
| WickAnalysis | 5.5 (abstain) | No CS context |
| MarketContext | 6.0 (abstain) | Limited |
| ExecutionQuality | 7.0 (approve) | |

**Result: 9/20 approve, avg=6.05 → HOLD**
**Compatible with panel policy: NO**

---

### New: H3-005 Continuation + Candlestick (projected for ideal conditions)

| Panel Evaluator | Score (projected) | Reason |
|----------------|------------------|--------|
| TrendFollowing | 8.0–10.0 (approve) | ema_alignment="full_bear" (key change) |
| Momentum | 6.5 (approve) | RSI 35–65, volume ≥ 1.0x |
| MeanReversion | 6.0 (abstain) | Not reversal entry (design) |
| Breakout | 5.0 (abstain) | No chart patterns (expected) |
| Structure | 7.5–10.0 (approve) | at_resistance + candlestick requires structure |
| Candlestick | 7.0–10.0 (approve) | CS pattern detected (key change) |
| RiskParity | 7.0–9.0 (approve) | R:R ≥ 2.0 |
| Volatility | 7.0 (approve) | Normal regime |
| VolumeProfile | 6.5–8.0 (approve) | volume ≥ 1.0x required |
| MacroRegime | 9.0 (approve) | Bear + SHORT |
| Contrary | 4.0–7.0 (varies) | Needs structure_quality="strong" + R:R>3.0 |
| ProfitTarget | 7.0–8.0 (approve) | R:R ≥ 2.0 |
| EntryTiming | 7.0–8.0 (approve) | at_resistance + normal ATR |
| Confluence | 8.0–10.0 (approve) | More signal agreements (CS+indicator) |
| DrawdownRisk | 5.5–6.5 (abstain/approve) | R:R=2.0 → 5.5, R:R=2.5 → 6.5 |
| LeverageSpecialist | 8.0 (approve) | Conservative (SHORT sign) |
| PatternCompletion | 5.0 (abstain) | Group excluded |
| WickAnalysis | 6.0–7.0 (abstain/approve) | CS pattern context available |
| MarketContext | 7.0–9.0 (approve) | CS + EMA context available |
| ExecutionQuality | 7.0–9.0 (approve) | Better setup quality with confirmation |

**Projected result (minimum viable)**: 12–14/20 approve, avg=6.5–7.0
**Projected result (ideal conditions)**: 16/20 approve, avg=7.5+

**Compatible with panel policy: CONDITIONALLY YES**
- Strong conditions (R:R ≥ 2.5, evening_star, structure_quality="strong"): ENTER
- Moderate conditions (R:R=2.0, bearish_engulfing, structure_quality="B"): borderline

---

## Key Panel Compatibility Requirements for H3-005 Proposals

For a H3-005 + candlestick proposal to pass the panel (14/20, avg ≥ 6.5):

### Non-negotiable (evaluators will reject without these):
1. `ema_alignment = "full_bear"` — TrendFollowing approve (✓ required by H3-005)
2. Candlestick pattern present — Candlestick approve (✓ required by gate)
3. MacroRegime aligned (bear for SHORT) — MacroRegime approve (✓ regime filter)
4. `at_resistance=True` — Structure, EntryTiming approve (✓ required for most CS patterns)

### Important (approve count closer to 14+):
5. R:R ≥ 2.0 — RiskParity, ProfitTarget, DrawdownRisk approvals
6. `volume_ratio ≥ 1.2x` — VolumeProfile approve (H3-005 requires only ≥ 1.0x, but 1.2x+ gives better score)
7. Normal volatility — Volatility approve
8. ADX ≥ 25 — Trending flag for Confluence, EntryTiming (✓ required by H3-005)

### Boosts approval count significantly:
9. R:R ≥ 2.5 — DrawdownRisk approve (+1 vote)
10. `structure_quality = "strong"` — Contrary approve (requires R:R>3.0 AND strong) (+2 net votes)
11. Evening Star or Engulfing pattern (vs Doji) — Candlestick 10.0 vs 5.5 (+0.25 avg)

---

## What the Panel CANNOT Evaluate in Phase 3 (Residual Limitations)

Even with Phase 6 improvements, 5 evaluators remain partially limited by excluded capabilities:

| Evaluator | Limitation | Impact |
|-----------|-----------|--------|
| PatternCompletion | Abstains (5.0) — chart_pattern group excluded | Neutral (not a blocker) |
| Breakout | Capped at 5.0–5.5 without confirmed breakout | 1 evaluator contributes abstain |
| ProfitTarget | No +2.0 bonus without primary_confirmed | Scores on R:R alone |
| Confluence | Loses 1/7 agreements (pattern signal absent) | Still 6/7 achievable |
| LeverageSpecialist | Sign bug for SHORT (accidentally conservative) | Conservative, not harmful |

These 5 evaluators are not improved by Phase 6. They will contribute abstains or partial scores. The 15 unaffected evaluators must carry the panel to 14/20.

With Phase 6 proposals (full_bear + candlestick), the 15 architecture-independent evaluators can achieve 14–16 approve votes, sufficient for the panel to pass.

---

## Conclusion

The upstream candidate generator, after Phase 6 repair, produces proposals that are **conditionally compatible** with the current panel policy.

- Proposals with full EMA alignment + strong candlestick + adequate R:R + at structure → Panel approves (14+/20)
- Proposals with full EMA alignment + weak candlestick or marginal R:R → Panel may hold (10-13/20)
- Proposals with mixed EMA alignment → Blocked at confirmation gate (never reach panel)

The panel policy is not the bottleneck. The candidate generator now produces the right type of proposals. Whether those proposals pass also depends on the specific market conditions captured in replay fixtures and live data.
