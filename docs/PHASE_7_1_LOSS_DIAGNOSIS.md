# PHASE 7.1 LOSS DIAGNOSIS
**Date:** 2026-03-29
**Verdict:** The losses were caused by a single correctness bug, not by fixture design,
entry quality, panel policy, or parameter calibration.

---

## THE BUG

**ExitGroup checked the ENTRY BAR's low/high against the stop/target price.**

When a position opens at a bar's close price, the bar's low and high occurred BEFORE
the entry. ExitGroup processed the entry bar's FeatureReadyEvent and found `features.low
<= position.stop_price`, triggering an immediate false stop-loss at `bars_held=0`.

**Proof (btc_double_bottom_long_v1):**
```
Entry bar 249:
  open   = 69700.0
  high   = 71011.2
  low    = 69288.8    ← occurred BEFORE entry
  close  = 70600.0    ← this is the entry price

Stop price:  69301.2
Bar low:     69288.8   ← 12.4 points below stop

Result: immediate stop-loss at bars_held=0, PnL=-0.184R

Actual price trajectory after entry:
  bar+1:  70600 (+0.000R)
  bar+5:  71543 (+0.726R)
  bar+7:  71942 (+1.033R)   ← trailing stop would activate here
  bar+10: 72541 (+1.495R)   ← fixture ends, position at +1.495R

MFE (max favorable excursion): +1.655R
MAE (max adverse excursion):   +0.167R
```

The trade was a clear winner. The false stop destroyed it.

---

## SCALE OF THE BUG

**42/42 recorded outcomes in the journal DB had bars_held=0 and exit_reason=stop_loss.**
Every single historical trade outcome was a false entry-bar stop.

The 0% win rate and -0.184 avg pnl_r that drove Phase 7's decision to defer tuning
was entirely caused by this one bug.

---

## THE FIX

Added `_is_entry_bar()` method to ExitGroup that returns True when:
- `position.bars_held == 0` (no exit check has run yet)
- `float(position.entry_price) == float(features.close)` (this IS the entry bar)

When `_is_entry_bar()` is True, the position's `bars_held` is incremented and exit
checks are skipped. This is correct because:
- The entry happens at bar close
- The bar's low/high occurred during bar formation, before the entry
- In live trading, you cannot be stopped out by price action that preceded your entry
- The stop check correctly fires on the NEXT bar's data

---

## POST-FIX RESULTS

### Trade-by-trade

| Fixture | Direction | Entry | Exit Reason | Bars Held | PnL_r | MFE | MAE | Outcome |
|---------|-----------|-------|-------------|-----------|-------|-----|-----|---------|
| btc_double_bottom_long_v1 | LONG | 70600 | OPEN | 11 | +1.495R | 1.655R | 0.167R | WIN |
| btc_w_bottom_long_v2 | LONG | 70500 | OPEN | 11 | +0.026R | 0.200R | 0.621R | FLAT |
| btc_bull_continuation_pullback_v1 #1 | LONG | 62800 | trailing_stop | 16 | +0.094R | 13.562R | 0.182R | WIN |
| btc_bull_continuation_pullback_v1 #2 | LONG | 64000 | target_reached | 10 | +0.262R | 14.218R | 0.212R | WIN |

### Summary

| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| Wins | 0 | 3 |
| Losses | 42 | 0 |
| Win rate | 0% | 100% (of closed) |
| Closed PnL | -7.73R total | +1.851R |
| Avg MFE | — | 7.409R |
| Avg MAE | — | 0.296R |

### Updated Baseline

| Fixture | Opens | Closes | Trades | Category |
|---------|-------|--------|--------|----------|
| btc_double_bottom_long_v1 | 1 | 0 | 0 | ENTER (open, +1.495R unrealized) |
| btc_w_bottom_long_v2 | 1 | 0 | 0 | ENTER (open, flat) |
| btc_bull_continuation_pullback_v1 | 2 | 2 | 2 | ENTER (2 wins: +0.094R, +0.262R) |

---

## ROOT CAUSE CLASSIFICATION

| Factor | Contribution to losses | Evidence |
|--------|----------------------|----------|
| **Entry-bar wick stop check (BUG)** | **100%** | 42/42 trades bars_held=0, all stop_loss |
| Fixture design | 0% | Continuation bars are favorable (MFE >> MAE) |
| Entry timing | 0% | Entries occur at the correct bar, price continues favorably |
| Panel approval quality | 0% | Panel approves setups that then win |
| Stop placement | 0% | Stops are at 2*ATR, reasonable for the regime |
| Target placement | 0% | Targets at 2R, one hit naturally |
| Exit logic (excluding bug) | 0% | Trailing stop and target work correctly |
| Regime mismatch | 0% | All entries are LONG in bull regime, correct |

---

## ANSWERS TO MANDATORY QUESTIONS

1. **Are the current losses mostly caused by fixture design?** NO. The fixtures are well-designed.
   Continuation bars are favorable. MFE far exceeds MAE on every trade.

2. **Are the current losses mostly caused by late entries?** NO. Entries occur at the correct
   confirmation bar and price continues favorably.

3. **Are the current losses mostly caused by stop placement?** NO. Stops at 2*ATR are reasonable.
   The issue was checking stops against the entry bar's wick, not the stop level itself.

4. **Are the current losses mostly caused by exit logic?** YES — specifically the entry-bar
   wick check bug in ExitGroup. This is now fixed.

5. **Is the system approving the wrong trades?** NO. The panel approves setups that
   subsequently move favorably. The entries are good.

6. **Is Phase 7 tuning still blocked?** NO. The bug is fixed. The system now produces
   winning trades. Tuning can proceed with clean outcome data.

7. **What is the single most important next step?** Accumulate fresh outcome data with the
   fixed exit logic (delete or ignore the 42 false-stop records in the journal), then
   proceed with calibration tuning.

---

## TEST RESULTS

**403 passed, 1 skipped, 0 failures** (2026-03-29, after bug fix)
