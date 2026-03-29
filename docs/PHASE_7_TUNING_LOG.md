# PHASE 7 TUNING LOG
**Started:** 2026-03-29

This log records every tuning decision made during Phase 7.
Bug fixes are logged separately from parameter changes.

---

## BUG FIX 1: trader_name="unknown" in trader_reviews

**Date:** 2026-03-29
**Type:** Bug fix (not tuning)
**File:** src/learning/decision_logger.py line 123

**Before:** `trader_name=getattr(verdict, "trader_name", "unknown")`
**After:** `trader_name=getattr(verdict, "trader_id", None) or getattr(verdict, "trader_name", "unknown")`

**Root cause:** TraderVerdict uses `trader_id`, not `trader_name`. All 20 traders were stored
as "unknown" in the trader_reviews table.

**Impact:** trader_reviews now contains correct per-trader names (TrendFollowing, Momentum, etc.)
**Regression check:** 402 tests pass (0 failures)

---

## BUG FIX 2: Empty trader_calibration table

**Date:** 2026-03-29
**Type:** Bug fix (not tuning)
**Files:**
- src/groups/performance_journal/group.py (line ~217)
- src/learning/journal_extension.py (new method: query_trader_reviews_by_packet)

**Before:** `process_closed_trade()` called without `trader_reviews` or `direction` params.
Calibration updates silently skipped because `if trader_reviews:` was always False.

**After:** `_log_position_close()` now fetches trader reviews from DB by packet_id and passes
them to `process_closed_trade()`. Also passes `direction` for ErrorTaxonomy.

**Impact:** trader_calibration table now populated with 20 rows per trade close (one per trader).
**Regression check:** 402 tests pass (0 failures)
**Verified:** V3 fixture close → 20 trader_calibration rows created

---

## BUG FIX 3: runner.py stale docstring

**Date:** 2026-03-29
**Type:** Documentation fix (not tuning)
**File:** src/runtime/runner.py lines 8-22

**Before:** ChartPatternGroup listed as "EXCLUDED: _process_features raises NotImplementedError"
**After:** ChartPatternGroup listed as active (Phase 6.4: DoubleBottomMachine)

---

## BUG FIX 4: Console test_runner.py missing files

**Date:** 2026-03-29
**Type:** Configuration fix (not tuning)
**File:** src/console/test_runner.py TEST_FILES list

**Before:** 8 test files listed (missing Phase 6.x and Phase 7)
**After:** 13 test files listed (added Phase 6.1, 6.2, 6.3, 6.4, and Phase 7 baseline)

---

## TUNING PASS 1: (NOT ATTEMPTED — insufficient data)

**Hypothesis:** N/A
**Reason for deferral:** All 34 existing trade outcomes are losses. No win-rate data exists
to determine whether panel thresholds should be tightened or loosened. Changing thresholds
based on fixture replay alone (without outcome data) is not evidence-based tuning.

---

*Future entries should follow this format:*

```
## TUNING PASS N: [description]

**Date:**
**Hypothesis:**
**Parameter changed:** [param] [before] → [after]
**File:**
**Baseline before:** [relevant fixture results]
**Baseline after:** [relevant fixture results]
**Regression check:** [test results]
**Decision:** ACCEPT / REJECT
**Reason:**
```
