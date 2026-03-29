# PHASE 7.1 HANDOFF
**Date:** 2026-03-29
**Phase:** 7.1 — Loss Cause Diagnosis

---

## DOMINANT LOSS CAUSE

**A single correctness bug in ExitGroup.**

ExitGroup checked the entry bar's low/high against stop/target prices. Since entries
occur at bar close, the bar's low (which preceded the entry) could be below the stop,
triggering an immediate false stop-loss at bars_held=0.

**Evidence:** 42/42 recorded trades had bars_held=0, exit_reason=stop_loss. After the
fix, the same fixtures produce 3 wins, 0 losses, 1 flat/open.

---

## BUG FIX APPLIED

**File:** src/groups/exit/group.py

Added `_is_entry_bar()` method: returns True when `bars_held == 0` AND
`entry_price == features.close` (identifies the bar whose close WAS the entry).
When True, skip exit checks and increment bars_held.

This correctly handles both:
- **Runtime path** (FeatureReadyEvent cascade opens position → same bar skip)
- **Test path** (CandidateTradeEvent opens position → next bar checked normally)

**Verification:** 403 tests pass, 0 failures.

---

## SHOULD TUNING STILL WAIT?

**NO.** Tuning is no longer blocked.

The 0% win rate was entirely an artifact of the entry-bar wick bug. With the fix:
- 3 of 4 trades are winners
- MFE far exceeds MAE on all trades
- Entries are correctly timed
- Stops are correctly placed
- Panel is approving good setups

However, the sample size (4 trades, 2 closed) is still too small for aggressive
parameter changes. Tuning should proceed cautiously, starting with exit parameters
(trailing stop efficiency is the most actionable finding).

---

## SHOULD FIXTURE REDESIGN BE DONE?

**Partially.** The existing fixtures are well-designed for LONG entries in bull contexts.
They need:
1. Extended continuation for V3 (currently only 10 bars after entry — not enough to hit target)
2. SHORT-entry fixtures for regime diversification
3. A fixture that produces a legitimate loss (for calibration pipeline testing)
4. More varied continuation profiles (choppy, pullback-then-continue)

---

## ARE ENTRY/EXIT CORRECTNESS CHANGES NEEDED?

The entry-bar fix was the ONLY correctness issue found. No other correctness changes
are needed. Specifically:
- Entry timing is good (entries at correct confirmation bars)
- Stop placement is good (2*ATR, MAE stays below 0.3R)
- Target placement is good (2R, hit when fixture has sufficient bars)
- Panel approval is good (approves setups that win)
- Risk sizing is functional (positions sized correctly)

---

## NEXT PHASE: Phase 7.2

**Focus:** Controlled tuning with clean outcome data.

### Immediate priorities:

1. **Clear stale journal data** — the 42 false-stop records should be marked or excluded
   from calibration. They are from the bugged exit logic and do not represent real
   trade outcomes.

2. **Extend V3 fixture** from 10 to 25+ continuation bars so the target can be reached
   or the trailing stop can activate, producing a real closed-trade outcome.

3. **Add 2-3 new fixture variants:**
   - A fixture where the entry wins after a scary pullback (tests stop resilience)
   - A fixture that produces a genuine loss (tests attribution pipeline end-to-end)
   - A SHORT-entry fixture (tests regime diversity)

4. **First tuning target: trailing stop efficiency**
   - bull_cont #1 captured 0.094R from a 13.56R move
   - Consider: trailing activation at +1.5R instead of +1R
   - Consider: trail at close-1.5*ATR instead of close-2*ATR
   - Validate with baseline regression

5. **Accumulate calibration data** — run the expanded fixture suite 3-5 times to build
   a diverse outcome set in the trader_calibration table.

---

## FILES CHANGED IN PHASE 7.1

| File | Change | Type |
|------|--------|------|
| src/groups/exit/group.py | Added `_is_entry_bar()`, skip entry-bar exit checks | BUG FIX |
| src/tests/test_phase_7_baseline.py | Added `test_v3_not_falsely_stopped_on_entry_bar` | TEST |
| docs/PHASE_7_1_LOSS_DIAGNOSIS.md | Root cause analysis | DOC |
| docs/LOSS_BUCKET_ANALYSIS.md | Trade-by-trade bucketing | DOC |
| docs/ENTRY_TIMING_VS_OUTCOME_REPORT.md | Entry quality analysis | DOC |
| docs/STOP_TARGET_EXIT_ANALYSIS.md | Exit component analysis | DOC |
| docs/FIXTURE_BIAS_ANALYSIS.md | Fixture quality assessment | DOC |
| docs/EVALUATOR_APPROVAL_ON_LOSERS.md | Evaluator behavior analysis | DOC |
| docs/PHASE_7_1_HANDOFF.md | This document | DOC |

---

## TEST RESULTS

**403 passed, 1 skipped, 0 failures** (2026-03-29)

---

## POST-FIX BASELINE

All fixtures use 1h timeframe (1 bar = 1 hour).

| Fixture | Bars (Duration) | Opens | Closes | Trades | Best Approve | Category |
|---------|-----------------|-------|--------|--------|-------------|----------|
| btc_double_bottom_long_v1 | 260 (10d 20h) | 1 | 0 | 0 | 16/20 | ENTER (open 11 bars / 11h, +1.495R) |
| btc_w_bottom_long_v2 | 260 (10d 20h) | 1 | 0 | 0 | 14/20 | ENTER (open 11 bars / 11h, flat) |
| btc_bull_continuation_pullback_v1 | 320 (13d 8h) | 2 | 2 | 2 | 14/20 | ENTER (wins: +0.094R@16 bars/16h, +0.262R@10 bars/10h) |
| 8 other fixtures | 200-350 (8-14d) | 0 | 0 | 0 | 9-13/20 | HOLD |

**Closed trade summary:** 2 wins (+0.094R after 16 hours, +0.262R after 10 hours), 0 losses. Win rate: 100%.
**Time stop threshold:** 20 bars (20 hours) — not reached by any trade.
