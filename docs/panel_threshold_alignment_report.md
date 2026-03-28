# Panel Threshold Alignment Report

**Date:** 2026-03-28
**Phase:** 5.9

---

## Thresholds Under Review

| Threshold | Value | Unchanged? | Justification |
|-----------|-------|------------|---------------|
| `APPROVE_THRESHOLD` | 14/20 | **YES** | Achievable for strong Phase 3 proposals (proven: 16/20 in ideal case) |
| `MIN_AVG_SCORE` | 6.5 | **YES** | Achievable for strong Phase 3 proposals (proven: 7.78 in ideal case) |
| FinalDecision rail 1: avg_score < 5.0 | 5.0 | **YES** | Very low floor — does not block Phase 3 |
| FinalDecision rail 2: reject_count > 12 | 12 | **YES** | Phase 3 has at most 4-5 rejects for weak proposals |
| FinalDecision rail 3: R:R < 1.5 | 1.5 | **YES** | All Phase 3 proposals have R:R ≥ 2.0 (built by setup_packet_builder) |
| FinalDecision rail 4: setup_quality == invalid | — | **YES** | Phase 3 quality is "B" (composite_score ≥ 0.60) |
| FinalDecision rail 5: bear regime + long | — | **YES** | Current candidates are SHORT in bear macro — rail not triggered |
| FinalDecision rail 6: high vol + <16 approvals | 16 | **YES** | Volatility regime is "normal" — rail not triggered |

---

## Are the Thresholds Calibrated for Phase 3?

### Question: Do the thresholds assume richer upstream information than Phase 3 provides?

**Answer: No — after the 3 evaluator fixes.**

Before the fixes, the effective ceiling was:
- `avg_score` ceiling ≈ 5.9 for our best candidates → below 6.5 threshold
- `approve_count` max ≈ 9/20 for our best candidates → below 14 threshold

This gave the impression the thresholds were too strict. However, the ceiling was artificially depressed by:
1. PatternCompletion always rejecting (4.0) — architecture error
2. RiskParity producing score=3.0 for R:R=2.0 — formula bug
3. DrawdownRisk permanently abstaining — design oversight

After the 3 fixes:
- `avg_score` for ideal Phase 3 = 7.78
- `approve_count` for ideal Phase 3 = 16/20

The thresholds are calibrated correctly for Phase 3. They require good signal quality AND good risk parameters. They do not require Phase 4+ capabilities (chart patterns, historian, critic).

### Question: Was the interpretation correct? (active-architecture vs theoretical completeness)

**Answer: The panel should evaluate active-architecture completeness.**

With 3 active groups (Indicators, Candlestick, Structure), a proposal should be evaluated against what those 3 groups can tell us. The thresholds were designed for a fully-wired system, but they remain appropriate for Phase 3 because:

1. Most evaluators are group-agnostic (they evaluate R:R, leverage, momentum, trend strength)
2. Only PatternCompletion was structurally penalizing excluded capabilities
3. After PatternCompletion is made architecture-aware, the remaining 19 evaluators can collectively reach 14/20 and avg ≥ 6.5 for strong setups

---

## Why 14/20 and 6.5 Are Not Lowered

The repair explicitly avoids lowering thresholds. The spec states:

> "Do NOT simply lower the panel threshold blindly."

The thresholds are correct. The repair fixes broken evaluator logic so that the thresholds are reachable when genuinely good proposals arrive. This is fundamentally different from lowering the quality bar.

**Lower threshold test:** If `APPROVE_THRESHOLD` were lowered to 10 and `MIN_AVG_SCORE` to 5.5, the current weak candidates would pass. But those candidates have:
- Mixed EMA alignment (no trend following conviction)
- Volume ratio 0.92 (below average participation)
- No candlestick patterns (no bar-level confirmation)
- Structure quality "none" (no S/R context)

Approving such entries would be noise trades. The thresholds at 14/20 and 6.5 correctly block them.

---

## Panel Sensitivity: What Signal Conditions Are Needed to Pass?

Based on tracing 20 evaluators, the minimum conditions for 14/20 approvals in Phase 3:

### Required (non-negotiable):
1. **Macro alignment** — regime matches direction (MacroRegime: +3.0 → 9.0 → approve, 1 vote)
2. **R:R ≥ 2.0** — minimum acceptable (RiskParity: 7.0 → approve, DrawdownRisk: 5.5 → abstain. At R:R=2.5: DrawdownRisk approves)
3. **EMA alignment** — full_bull or full_bear for direction (TrendFollowing: +2.0 → possible approve)
4. **Structure** — at_support/resistance matters (Structure: +3.0, EntryTiming: +2.0)

### Recommended (for 14+ approvals):
5. **Volume** ≥ 1.3x (VolumeProfile, Confluence: +1 agreement)
6. **Candlestick pattern** at structure (Candlestick: 7.0-10.0 → approve; WickAnalysis: +2.0)
7. **ADX** ≥ 25 (TrendFollowing: +1.5, Confluence: regime.trending=True)
8. **Structure quality** "strong" (Structure: +2.0, Contrary: +1 unlock, MeanReversion: better score)
9. **R:R ≥ 2.5** (DrawdownRisk: 6.5 → approve, 1 more vote)

### Counter-productive signals:
- `ema_alignment = "mixed"` → TrendFollowing penalizes -2.0 (reject zone)
- `volume_ratio < 1.0` → VolumeProfile and Momentum penalized
- `structure_quality = "none"` → Structure penalized, Contrary cannot approve
- `candlestick.patterns_detected = []` → Candlestick abstains at 4.0

---

## Why Current Candidates Fail the Threshold

The 8 Phase 5.75 candidates are generated at EMA crossover transition bars. These bars have:
- `ema_alignment = "mixed"` (crossover is happening, not established)
- `volume_ratio = 0.92` (below-average volume at crossover)
- No candlestick patterns detected on the crossover bar
- `structure_quality = "none"` at some bars

These are genuinely weak setups. The composite_score normalization fix (Phase 5.75) correctly identifies them as above the 0.50 entry threshold (they have signal confirmation), but the panel's quality requirements are higher and correctly filter them out.

**This is correct behavior.** An EMA crossover with below-average volume and no candlestick confirmation at an unstructured price level is a noisy, unreliable trade. The panel correctly refuses it.

---

## FinalDecisionGroup Threshold Analysis

The 6 safety rails were each verified for Phase 3 candidates:

| Rail | Threshold | Phase 3 Status |
|------|-----------|---------------|
| avg_score < 5.0 | 5.0 | Never triggered — Phase 3 avg ≈ 5.9-6.1 |
| reject_count > 12 | 12 | Never triggered — Phase 3 max rejects ≈ 4-5 |
| R:R < 1.5 | 1.5 | Never triggered — builder ensures R:R ≥ 2.0 |
| setup_quality == invalid | invalid | Never triggered — Phase 3 quality is "B" (composite ≥ 0.60) |
| bear + long | — | Not triggered for our SHORT candidates |
| high_vol + <16 approvals | 16 | Not triggered (volatility = "normal" for replay fixtures) |

No safety rails were triggered for Phase 3 candidates. The FinalDecisionGroup correctly defers to the panel recommendation ("hold" because approve < 14).

---

## Conclusion

The panel thresholds (14/20, avg ≥ 6.5) are correctly aligned for Phase 3 architecture. They are:
- Achievable for strong Phase 3 proposals (proven: 16/20, avg=7.78)
- Not achievable for weak Phase 3 proposals (proven: 9/20, avg=6.05 for best replay candidate after repairs)
- Not reduced by the Phase 5.9 repair
- Independent of Phase 4+ capabilities (chart patterns, historian, critic)
