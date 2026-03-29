# PHASE 7 PLAN
**Date:** 2026-03-29
**Phase:** 7.0 — Learning, Calibration, and Parameter Optimization

---

## OBJECTIVE

Move the system from "built and validated" into controlled optimization.
Improve decision quality through evidence-based calibration, not intuition.

---

## COMPLETED WORK (This Session)

### Bug Fixes (correctness, not tuning)

1. **trader_reviews stored with trader_name="unknown"** (decision_logger.py)
   - Root cause: `getattr(verdict, "trader_name", "unknown")` but field is `trader_id`
   - Fix: `getattr(verdict, "trader_id", None) or getattr(verdict, "trader_name", "unknown")`
   - Impact: All 20 trader names now correctly stored in trader_reviews table

2. **trader_calibration table always empty** (performance_journal/group.py)
   - Root cause: `_log_position_close()` did not pass `trader_reviews` to `process_closed_trade()`
   - Fix: Added `query_trader_reviews_by_packet()` to JournalExtension, fetch reviews by packet_id
     and pass them to the attribution pipeline
   - Also pass `direction` parameter for ErrorTaxonomy classification
   - Impact: trader_calibration now populated per-trader after each trade close

3. **runner.py docstring stale** (runner.py lines 19-22)
   - Root cause: ChartPatternGroup listed as EXCLUDED, but was activated in Phase 6.4
   - Fix: Updated docstring to reflect ChartPatternGroup as active

4. **Console test_runner.py missing Phase 6.x and Phase 7 test files**
   - Added: test_phase_6_1, test_phase_6_2, test_phase_6_3, test_phase_6_4, test_phase_7_baseline

### Baseline Lock

Created `test_phase_7_baseline.py` — runs all 11 fixtures through real pipeline.
Locked regression contract:

| Fixture | Category | Best Approve | Avg Score | Opens | Closes | Trades |
|---------|----------|-------------|-----------|-------|--------|--------|
| btc_double_bottom_long_v1 | Strong ENTER | 16/20 | 7.325 | 1 | 1 | 1 |
| btc_w_bottom_long_v2 | Threshold ENTER | 14/20 | 6.850 | 1 | 0 | 0 |
| btc_bull_continuation_pullback_v1 | Threshold ENTER | 14/20 | 6.725 | 2 | 2 | 2 |
| btc_long_established_trend_v1 | Near-miss HOLD | 13/20 | 6.700 | 0 | 0 | 0 |
| btc_m_top_short_v1 | Near-miss HOLD | 13/20 | 6.700 | 0 | 0 | 0 |
| btc_w_bottom_long_v1 | Near-miss HOLD | 13/20 | 6.700 | 0 | 0 | 0 |
| btc_triple_touch_long_v1 | Near-miss HOLD | 13/20 | 6.575 | 0 | 0 | 0 |
| btc_bull_breakout_v1 | Clear HOLD | 11/20 | 6.450 | 0 | 0 | 0 |
| btc_bear_continuation_pullback_v1 | Clear HOLD | 10/20 | 6.300 | 0 | 0 | 0 |
| btc_bear_breakdown_v1 | Strong HOLD | 9/20 | 6.200 | 0 | 0 | 0 |
| btc_ranging_v1 | Strong HOLD | 9/20 | 6.250 | 0 | 0 | 0 |

---

## WHY NO PARAMETER TUNING WAS DONE IN THIS SESSION

### Reason 1: Calibration data is insufficient

- 34 existing outcome attributions in journal DB, all losses (0% win rate)
- All exits via stop_loss, avg_pnl_r = -0.184
- This is not enough data for evidence-based parameter adjustment
- The data is also entirely one-sided (no wins), making it unsuitable for
  determining which evaluators are actually predictive

### Reason 2: Bug fixes were higher priority

The two correctness bugs (trader_name="unknown" and empty trader_calibration) meant
the calibration pipeline was broken. Fixing these enables future data-driven tuning
but doesn't itself constitute tuning.

### Reason 3: Lowering thresholds without evidence would be irresponsible

4 fixtures are at 13/20 (gap=1 to threshold). It would be easy to lower
APPROVE_THRESHOLD from 14 to 13 and get more entries. But:
- All 34 existing trade outcomes are losses
- This means the current threshold may already be too permissive
- Lowering it without win-rate evidence would increase losses, not improve quality

---

## NEXT STEPS (Future Sessions)

1. **Accumulate outcome data**: Run --simulate with extended bars to generate 50+ closed
   trades with diverse outcomes (including some wins, if the fixtures support it)

2. **Analyze per-evaluator calibration**: Once trader_calibration has data, identify
   evaluators whose approvals correlate with losses and whose rejections correlate with wins

3. **MeanReversion evaluator review**: MeanReversion always rejects (3.0) on trend
   continuation setups. This is correct behavior (not a bug), but its permanent rejection
   means the approval ceiling is 18/20 at best. Consider whether its scoring should be
   softened for trend contexts.

4. **DrawdownRisk and WickAnalysis review**: Both always abstain (5.5). They contribute
   nothing to the decision. Investigate whether they can be made more informative.

5. **Fixture regime expansion**: Add SHORT and ranging fixtures that SHOULD enter, to
   balance the fixture suite beyond LONG-only bull setups.

---

## TEST RESULTS

All tests pass: **402 passed, 1 skipped, 0 failures** (2026-03-29)
