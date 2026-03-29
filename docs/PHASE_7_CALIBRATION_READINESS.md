# PHASE 7 CALIBRATION READINESS
**Date:** 2026-03-29

---

## CURRENT STATE: INSUFFICIENT FOR DATA-DRIVEN TUNING

### Outcome Data

| Metric | Value | Assessment |
|--------|-------|-----------|
| Total closed trades in journal DB | 34 | Below 50 minimum |
| Win rate | 0% (0 wins, 34 losses) | Cannot distinguish good from bad evaluators |
| Average pnl_r | -0.184 | All trades are losing but not catastrophic |
| Exit reasons | 100% stop_loss | No target/trailing/time exits observed |
| Outcome source | event_driven_runtime | Correct — no source mixing |

### Calibration Pipeline

| Component | Status | Notes |
|-----------|--------|-------|
| outcome_attributions table | 34 rows | Working |
| trader_calibration table | **0 rows (WAS BROKEN, NOW FIXED)** | Bug: trader_name="unknown" + missing trader_reviews pass |
| setup_family_records | Present | Not verified |
| specialist_group_records | Present | Not verified |
| ErrorTaxonomy | Active | All 34 classified as stop_placement (B) or unknown (G) |

### Bugs Fixed in This Session

1. **DecisionTraceLogger** used `trader_name` attr instead of `trader_id` on TraderVerdict.
   All 20 traders were stored as "unknown". Fixed: now uses `trader_id` correctly.

2. **PerformanceJournalGroup._log_position_close()** did not pass `trader_reviews` to
   `OutcomeAttributor.process_closed_trade()`. Calibration updates were silently skipped.
   Fixed: now queries reviews by packet_id and passes them through.

---

## WHAT CAN BE DONE NOW

Even with insufficient data, the following is possible:

1. **Verify calibration pipeline works end-to-end**: Run a fixture, confirm trader_calibration
   populates with 20 rows of per-trader data. DONE — verified working.

2. **Analyze the 34 loss pattern**: All trades are stop_loss exits with avg_pnl_r=-0.184.
   This suggests stops are placed approximately correctly (not hitting -1.0R full stops
   on average), but the entries are consistently on the wrong side. The setups that pass
   the panel at 14/20 are not winning.

3. **Exit parameter exploration**: Since all exits are stop_loss, investigate whether:
   - Stop placement is too tight (hit by noise)
   - Trailing stop never activates (needs +1R move that never happens)
   - Time stop at 20 bars is never reached (stopped out earlier)

---

## WHAT REQUIRES MORE DATA

1. **Evaluator reweighting**: Requires knowing which evaluators' approvals correlate with
   wins vs losses. With 0 wins, all evaluators look equally bad.

2. **Panel threshold adjustment**: Requires a distribution of outcomes at different approval
   levels. Currently everything that enters loses, so the information value is near zero.

3. **Setup family analysis**: Requires multiple outcomes per setup family. Currently all
   setups are "indicator" or "candlestick" families.

---

## RECOMMENDATION

Phase 7 tuning should focus on:

1. **Exit parameters** (tunable now, low regression risk)
2. **Fixture expansion** (provides more regime diversity)
3. **Running extended simulations** (accumulate 50+ outcomes for calibration)

And defer until more data exists:
4. Panel threshold changes
5. Evaluator scoring changes
6. Entry weight rebalancing
