# STOP, TARGET, AND EXIT ANALYSIS
**Date:** 2026-03-29

---

## STOP PLACEMENT

All stops are placed at entry_price - 2*ATR14. This is structurally reasonable:

| Trade | Entry | Stop | Stop Dist | ATR14 | Stop/ATR Ratio | MAE | MAE/Stop |
|-------|-------|------|-----------|-------|---------------|-----|---------|
| V3 double_bottom | 70600 | 69301 | 1299 | 649 | 2.0x | 217 | 0.167 |
| V2 w_bottom | 70500 | 68599 | 1901 | 951 | 2.0x | 1180 | 0.621 |
| bull_cont #1 | 62800 | 61834 | 967 | 387 | 2.5x | 176 | 0.182 |
| bull_cont #2 | 64000 | 63162 | 838 | 419 | 2.0x | 178 | 0.212 |

**Assessment:** Stops are appropriately placed. MAE/Stop ratio stays well below 1.0 for
the winning trades (0.17-0.21), meaning the price never comes close to the stop.
V2 is the exception at 0.62 — the fixture's flat continuation makes this position
vulnerable but it still survives.

**Verdict:** Stop placement is NOT a problem.

---

## TARGET PLACEMENT

All targets are at entry_price + 2*stop_distance (R:R = 2.0):

| Trade | Entry | Target | Target Dist | MFE | MFE > Target? | Target Hit? |
|-------|-------|--------|-------------|-----|--------------|-------------|
| V3 double_bottom | 70600 | 73198 | 2598 | 2149 | NO (1.655R < 2R) | No (fixture too short) |
| V2 w_bottom | 70500 | 74303 | 3803 | 380 | NO | No (fixture too short + flat) |
| bull_cont #1 | 62800 | 64734 | 1933 | 13115 | YES (13.6R >> 2R) | Yes (exited via trailing first) |
| bull_cont #2 | 64000 | 65675 | 1675 | 11905 | YES (14.2R >> 2R) | YES — clean target hit |

**Assessment:**
- Targets are reasonable at 2R.
- Bull_cont fixtures have massive continuation (13-14R MFE), so the 2R target is conservative.
- V3 reaches +1.655R but needs 2R — just 3 more continuation bars would reach target.
- V2 never develops enough momentum to approach target.

**Verdict:** Targets are NOT a problem. The 2R target is hit when the fixture has
sufficient continuation bars.

---

## EXIT LOGIC ANALYSIS

### ExitGroup Bug (NOW FIXED)

- **Bug:** Entry-bar wick check. The bar's low (formed before entry) triggers stop.
- **Impact:** 42/42 historical trades falsely stopped at bars_held=0.
- **Fix:** `_is_entry_bar()` skips the bar whose close matches the entry price.
- **Status:** FIXED. 403 tests pass.

### Trailing Stop Performance

- Bull_cont #1: MFE=13.56R but trailing exit at +0.094R.
  The trailing stop activates at +1R, sets to breakeven, then ratchets at close-2*ATR.
  When the position reaches +1R and the trailing is set to breakeven, a subsequent
  pullback to near breakeven triggers the exit. The 2*ATR trail is reasonable but
  means the first post-activation pullback can trigger an early exit.

  **Secondary issue (not a bug, Phase 7 tuning target):** The trailing stop captures
  only 0.7% of the maximum favorable excursion. This trade's real problem was that it
  reached +1R, activated trailing at breakeven, then pulled back to +0.094R where the
  trail caught it. A tighter ATR multiplier (e.g., 1.5*ATR) or a higher activation
  threshold (e.g., +1.5R) could improve capture. This is a calibration question for
  Phase 7.

### Target Hit

- Bull_cont #2: clean 2R target hit at bar+10. This works exactly as designed.

### Time Stop

- Not triggered in any trade. All exits occur before 20 bars. Time stop is available
  as a safety net but not a factor in current outcomes.

---

## OVERALL VERDICT

| Exit Component | Status | Assessment |
|---------------|--------|-----------|
| Hard stop loss | FIXED (entry-bar bug) | Now works correctly on post-entry bars |
| Target | Working | Clean target hit observed |
| Trailing stop | Working but conservative | Captures small fraction of MFE; tune in Phase 7 |
| Time stop | Working (not triggered) | Available as safety net |
| Signal reversal | Not triggered | Advisory only, not a factor |
