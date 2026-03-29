# PHASE 7 BASELINE — Locked Regression Contract
**Date:** 2026-03-29
**Source:** test_phase_7_baseline.py (all 11 fixtures through real BtcBybitPaperRunner)
**Test result:** 19/19 pass

This is the regression baseline for Phase 7 tuning. Every parameter change must be
validated against this baseline. If any fixture regresses without documented justification,
the change is rejected.

---

## FULL BASELINE TABLE

| Fixture | Bars | Candidates | Approvals | Best Approve | Avg Score | Opens | Closes | Trades | Category |
|---------|------|-----------|-----------|-------------|-----------|-------|--------|--------|----------|
| btc_double_bottom_long_v1 | 260 | 6 | 1 | 16/20 | 7.325 | 1 | 1 | 1 | Strong ENTER |
| btc_w_bottom_long_v2 | 260 | 6 | 1 | 14/20 | 6.850 | 1 | 0 | 0 | Threshold ENTER |
| btc_bull_continuation_pullback_v1 | 320 | 3 | 2 | 14/20 | 6.725 | 2 | 2 | 2 | Threshold ENTER |
| btc_long_established_trend_v1 | 300 | 7 | 0 | 13/20 | 6.700 | 0 | 0 | 0 | Near-miss HOLD |
| btc_m_top_short_v1 | 267 | 8 | 0 | 13/20 | 6.700 | 0 | 0 | 0 | Near-miss HOLD |
| btc_w_bottom_long_v1 | 257 | 6 | 0 | 13/20 | 6.700 | 0 | 0 | 0 | Near-miss HOLD |
| btc_triple_touch_long_v1 | 261 | 5 | 0 | 13/20 | 6.575 | 0 | 0 | 0 | Near-miss HOLD |
| btc_bull_breakout_v1 | 350 | 6 | 0 | 11/20 | 6.450 | 0 | 0 | 0 | Clear HOLD |
| btc_bear_continuation_pullback_v1 | 330 | 7 | 0 | 10/20 | 6.300 | 0 | 0 | 0 | Clear HOLD |
| btc_bear_breakdown_v1 | 350 | 2 | 0 | 9/20 | 6.200 | 0 | 0 | 0 | Strong HOLD |
| btc_ranging_v1 | 200 | 2 | 0 | 9/20 | 6.250 | 0 | 0 | 0 | Strong HOLD |

**Summary:** 3 entering, 8 holding. Entry rate = 27%.

---

## EVALUATOR BREAKDOWN FOR ENTERING FIXTURES

### btc_double_bottom_long_v1 (16/20, avg=7.325)

| Evaluator | Score | Vote | Key |
|-----------|-------|------|-----|
| TrendFollowing | 8.0 | approve | EMA alignment |
| Momentum | 8.0 | approve | RSI + volume |
| MeanReversion | 3.0 | **reject** | Always rejects trend setups |
| Breakout | 8.0 | approve | Chart pattern confirmed |
| Structure | 6.5 | approve | S/R alignment |
| Candlestick | 10.0 | approve | Strong engulfing |
| RiskParity | 7.0 | approve | R:R acceptable |
| Volatility | 7.0 | approve | ATR normal |
| VolumeProfile | 7.0 | approve | vol_ratio > 1.2 |
| MacroRegime | 9.0 | approve | Bull macro |
| Contrary | 4.0 | **reject** | Not contrarian setup |
| ProfitTarget | 9.0 | approve | Target realistic |
| EntryTiming | 7.0 | approve | Confirmation bar |
| Confluence | 10.0 | approve | Multi-signal |
| DrawdownRisk | 5.5 | abstain | Neutral |
| LeverageSpecialist | 7.0 | approve | Sizing OK |
| PatternCompletion | 10.0 | approve | Double bottom confirmed |
| WickAnalysis | 5.5 | abstain | Neutral |
| MarketContext | 7.0 | approve | Trend context |
| ExecutionQuality | 8.0 | approve | Entry quality |

### btc_w_bottom_long_v2 (14/20, avg=6.850)

Same as above except:
- Breakout: 5.5 (abstain) — no confirmed chart pattern
- PatternCompletion: 5.0 (abstain) — no chart pattern
- ProfitTarget: 7.0 (approve) — target less clear without pattern

### btc_bull_continuation_pullback_v1 (14/20, avg=6.725)

Same pattern as V2: no chart pattern assistance, so PatternCompletion and Breakout abstain.
TrendFollowing slightly weaker (6.5 vs 8.0 for V3).

---

## PERMANENT REJECTERS AND ABSTAINERS

These evaluators never approve on the current fixture suite:

| Evaluator | Typical Score | Vote | Reason |
|-----------|-------------|------|--------|
| MeanReversion | 3.0 | reject | All fixtures are trend continuation — correct behavior |
| Contrary | 4.0 | reject | All fixtures are with-trend — correct behavior |
| DrawdownRisk | 5.5 | abstain | No drawdown context in paper mode — always neutral |
| WickAnalysis | 5.5 | abstain | Weak wick scoring — may be undertrained |

This creates a floor of 2 rejects + 2 abstains = 4 non-approves minimum.
Maximum possible approvals = 16/20 (only achievable with chart pattern boost).
Without chart patterns, maximum = 14/20 (exactly at threshold).

---

## NEAR-MISS DISTRIBUTION

4 fixtures at 13/20 (gap=1). The swing voter between 13 and 14 is typically
one of: TrendFollowing, Structure, or VolumeProfile dropping from approve to abstain
when the setup quality is marginally weaker.

---

## EXISTING OUTCOME DATA

| Metric | Value |
|--------|-------|
| Closed trades in DB | 34 |
| Win rate | 0% (all losses) |
| Avg pnl_r | -0.184 |
| All exit reasons | stop_loss |
| Outcome source | event_driven_runtime |
| trader_calibration rows | 0 (was broken, now fixed) |
