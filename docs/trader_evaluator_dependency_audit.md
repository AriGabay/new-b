# Trader Evaluator Dependency Audit

**Date:** 2026-03-28
**Phase:** 5.9

---

## Purpose

For each of the 20 trader evaluators, document:
- Which capabilities they depend on
- Whether those capabilities are active in Phase 3
- Whether their behavior is architecture-dependent
- What repair was applied (if any)

---

## Complete Evaluator Matrix

| # | Evaluator | Phase 3 Status | Chart Pattern Dep? | Structural Dep? | Indicator Dep? | R:R/Risk Dep? | Fix Applied |
|---|-----------|---------------|-------------------|-----------------|----------------|---------------|-------------|
| 1 | TrendFollowing | Active — legitimate | No | Yes (trend_direction, hh/hl) | Yes (ema_alignment, adx14) | No | None |
| 2 | Momentum | Active — legitimate | No | No | Yes (rsi14, rsi_direction, volume) | No | None |
| 3 | MeanReversion | Active — design | No | Yes (at_support/resistance) | Yes (rsi14, bb_position) | No | None |
| 4 | Breakout | Partial — no pattern bonus | **Yes** (confirmed_patterns) | No | Yes (volume_ratio, bb_width) | No | None (see note) |
| 5 | Structure | Active — data quality | No | **Yes (at_support/resistance, quality)** | No | No | None |
| 6 | Candlestick | Active — depends on signal | No | No (but pattern_at_structure) | No | No | None |
| 7 | RiskParity | **Formula bug** | No | No | No | Yes (r_r_ratio, stop_pct) | **Yes — formula fix** |
| 8 | Volatility | Active — legitimate | No | No | Yes (volatility_regime, atr_vs_sma) | Yes (stop_pct) | None |
| 9 | VolumeProfile | Active — legitimate | No | No | Yes (volume_ratio, volume_character) | No | None |
| 10 | MacroRegime | Active — legitimate | No | No | No (uses regime) | No | None |
| 11 | Contrary | Active — design | No | Yes (structure_quality) | Yes (volume, adx, volatility) | Yes (r_r_ratio) | None |
| 12 | ProfitTarget | Active — chart pattern bonus | **Yes** (primary_confirmed, target) | No | No | Yes (r_r_ratio) | None |
| 13 | EntryTiming | Active — legitimate | No | Yes (at_support/resistance) | Yes (atr_vs_sma, bb_position) | No | None |
| 14 | Confluence | Active — partial | **Yes** (signal #4 of 7) | Yes (signal #5 of 7) | Yes (ema, rsi, volume) | No | None |
| 15 | DrawdownRisk | **No positive adj** | No | No | Yes (volatility_regime) | Yes (r_r_ratio, stop_pct) | **Yes — positive adjustment** |
| 16 | LeverageSpecialist | Active — leverage bug | No | No | No | Yes (proposed_leverage) | None (see note) |
| 17 | PatternCompletion | **Architecture reject** | **Yes (direct)** | No | No | No | **Yes — architecture-aware** |
| 18 | WickAnalysis | Active — structural | No | Yes (at_support/resistance) | No (uses candlestick patterns) | No | None |
| 19 | MarketContext | Active — composite | **Yes** (pattern_direction) | Yes (at_support/resistance, trend) | Yes (ema_alignment, adx, bb_width) | No | None |
| 20 | ExecutionQuality | Active — legitimate | No | No | No | Yes (r_r_ratio, stop_pct, quality) | None |

---

## Evaluators With Phase 4+ Dependencies

### ChartPatternGroup-dependent evaluators

| Evaluator | Dependency | Phase 3 Impact | Repaired? |
|-----------|-----------|----------------|-----------|
| PatternCompletion | confirmed_patterns, active_patterns | 4.0 (reject) when excluded | **Yes** |
| Breakout | confirmed_patterns, breakout_level | Capped at 5.5 (abstain max), 4.5 (reject) with low volume | **No** — volume legitimately penalized |
| ProfitTarget | primary_confirmed, conservative_target | Misses +2.0 bonus | No — still scores on R:R |
| Confluence | confirmed_patterns (1 of 7 agreements) | Loses 1/7 agreements | No — 6 agreements still possible |
| MarketContext | pattern_direction | Minimal impact | No |

### HistorianAgent-dependent evaluators

None of the 20 evaluators reference `historian_analog`. The `BTCSetupPacket` does not carry historian fields. HistorianAgent is not in the evaluation path. **This was not the root cause of panel rejection** (contrary to the Phase 5.75 assessment which was based on CandidateTradeProposal fields, not BTCSetupPacket fields).

### CriticAgent-dependent evaluators

None of the 20 evaluators reference `critic_report`. Same finding as historian — not in the BTCSetupPacket. **Not the root cause.**

---

## Evaluators With Formula/Design Errors

### RiskParityEvaluator (formula bug)

**Old formula:** `score = min(9.0, rr * 1.5)`
- R:R=1.0 → score=1.5
- R:R=1.5 → score=2.25
- R:R=2.0 → score=3.0 (voted "approve" simultaneously — **incoherent**)
- R:R=6.0 → score=9.0

**New formula:** `score = min(9.0, 3.0 + rr * 2.0)`
- R:R=1.0 → score=5.0 (abstain — correctly uncertain)
- R:R=1.5 → score=6.0 (abstain — just below approve)
- R:R=2.0 → score=7.0 (approve — coherent with vote)
- R:R=3.0 → score=9.0 (approve — excellent R:R)

### DrawdownRiskEvaluator (missing positive adjustment)

**Old behavior:** Base=5.0, only negative adjustments. Maximum score = 5.0 → permanent abstain.

Even with R:R=3.5, stop=2.0%, normal volatility:
- No stop penalty (stop < 3.0%)
- No R:R penalty (rr ≥ 2.0)
- Score stays at 5.0 → `_vote_from_score(5.0)` = "abstain"
- The `vote = "approve"` set by `else` branch is overridden by `_vote_from_score(5.0)`

**New behavior:** Added positive reward:
```python
if rr >= 2.5 and stop_pct <= 3.0:
    score += 1.5   # R:R=2.5 → score=6.5 → approve
elif rr >= 2.0 and stop_pct <= 3.0:
    score += 0.5   # R:R=2.0 → score=5.5 → abstain (better than before)
```

### LeverageSpecialistEvaluator (leverage sign bug — not fixed)

For SHORT proposals, `proposed_leverage = min(entry / (entry - stop), 3.0)`. For SHORT, `entry - stop_price < 0` (stop is above entry), giving negative leverage (e.g., -83.74). Since `-83.74 ≤ 2.0`, LeverageSpecialist gives score=8.0 (conservative leverage) — accidentally correct for Phase 3. **Not fixed in Phase 5.9** because the accidental behavior is conservative (favors not entering on leverage). Documented for Phase 4 cleanup.

---

## Evaluators That Are Intentional Design Choices (Not Architecture Issues)

### ContraryEvaluator

Always defaults to score=4.0 (reject) unless R:R > 3.0 AND structure_quality == "strong". This is intentional — the evaluator is the panel's devil's advocate. It should be hard to satisfy. **Not changed.**

### MeanReversionEvaluator

Gives base 3.0 for trend-following entries (EMA crossover trades are not mean reversion). Only approves when RSI is at an extreme AND price is at S/R AND Bollinger Band extreme. **Not changed.**

Both of these evaluators will reject most Phase 3 EMA crossover proposals. This is by design. To earn their approval requires exceptional setups (e.g., Contrary: R:R > 3.0 + strong structure; MeanReversion: RSI > 70 + at_resistance + bb_above_upper for short).

---

## Structural Data Dependency (TechnicalStructureGroup)

Several evaluators use structural data (at_support, at_resistance, structure_quality). These depend on TechnicalStructureGroup computing and caching a `StructuralLevelBundle`.

**Runner wiring confirmed (runner.py):**
```python
self._panel_decision.set_structural_cache(
    self._technical_structure._structural_cache
)
```

TechnicalStructureGroup IS active in Phase 3 and IS wired to PanelDecisionGroup. The structural cache is populated with real swing pivot levels. When the harness runs replay fixtures, the structural data is genuine.

The Phase 3 candidate at bar 29 (bull fixture death cross) showed:
- `at_resistance=True` (price at swing high level ≈ 64410)
- `at_support=False`
- `structure_quality="none"` (from StructuralLevelBundle — swing levels computed but quality not "strong")

The `structure_quality="none"` penalizes Structure (-1.5), Contrary (can't approve), MeanReversion (no structural reversal bonus). This is real data, not an architecture gap.

---

## Summary: Phase 3 Panel Viability

| Category | Count | Examples |
|----------|-------|---------|
| Fully active, no issues | 12 | TrendFollowing, Momentum, Volatility, MacroRegime, etc. |
| Architecture-dependent (fixed) | 1 | PatternCompletion |
| Formula/design error (fixed) | 2 | RiskParity, DrawdownRisk |
| Architecture-dependent (not fixed, acceptable) | 2 | Breakout, ProfitTarget |
| Intentional skeptics (design) | 2 | Contrary, MeanReversion |
| Known wiring bug (not fixed, conservative) | 1 | LeverageSpecialist leverage sign |

After the 3 fixes, the panel can approve strong Phase 3 proposals (16/20, avg=7.78 demonstrated). Current replay candidates are correctly rejected as weak proposals.
