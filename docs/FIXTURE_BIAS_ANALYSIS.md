# FIXTURE BIAS ANALYSIS
**Date:** 2026-03-29

---

## QUESTION: Are the fixtures biased toward losses?

**ANSWER: NO.** The fixtures are biased toward FAVORABLE continuation. The losses were
entirely caused by the entry-bar wick bug, not fixture design.

---

## FIXTURE CONTINUATION QUALITY

| Fixture | Enters? | Continuation Bars After Entry | Price Direction After Entry | MFE (R) | Favorable? |
|---------|---------|------------------------------|---------------------------|---------|-----------|
| btc_double_bottom_long_v1 | YES | 10 | Unbroken upward | 1.655R | YES |
| btc_w_bottom_long_v2 | YES | 19 | Choppy/flat | 0.200R | MARGINAL |
| btc_bull_continuation_pullback_v1 | YES (2x) | 124 / 99 | Strong uptrend | 13.56R / 14.22R | YES |
| btc_w_bottom_long_v1 | NO | — | — | — | — |
| btc_m_top_short_v1 | NO | — | — | — | — |
| btc_triple_touch_long_v1 | NO | — | — | — | — |
| btc_long_established_trend_v1 | NO | — | — | — | — |
| btc_bear_continuation_pullback_v1 | NO | — | — | — | — |
| btc_bull_breakout_v1 | NO | — | — | — | — |
| btc_bear_breakdown_v1 | NO | — | — | — | — |
| btc_ranging_v1 | NO | — | — | — | — |

---

## ACTUAL BIASES IDENTIFIED

### Bias 1: LONG-only entries

All 3 entering fixtures produce LONG entries in bullish contexts. No SHORT entry has
ever been approved. This means the system's behavior in bearish regimes is untested
through the fixture suite.

**Impact on calibration:** All outcome data will be from LONG/bull setups. Evaluator
calibration will be biased toward bull contexts.

**Fix:** Create SHORT-entry fixtures (bearish engulfing at resistance, head & shoulders
confirmation, etc.) for Phase 7.

### Bias 2: V2 continuation is flat

btc_w_bottom_long_v2 has 19 bars of continuation but the price chops around the entry
price (MFE only 0.200R, MAE 0.621R). This makes the V2 fixture a "coin-flip" trade
rather than a clearly favorable setup.

**Impact:** V2 is not a strong test of entry quality. It demonstrates that the panel
CAN approve at threshold-edge (14/20), but the subsequent price action doesn't
validate the entry's quality.

### Bias 3: bull_continuation fixtures have extreme MFE

The bull_continuation_pullback_v1 fixture has 120+ bars of strong uptrend after entry,
producing 13-14R MFE. This is unrealistically favorable for calibration purposes —
real BTC 1h bars rarely produce unbroken 120-bar trends.

**Impact:** The trailing stop and target analyses from this fixture overstate the system's
real-world profit potential.

### Bias 4: Insufficient fixture count for entering fixtures

Only 3/11 fixtures enter (27% entry rate). With 4 total trades (2 from one fixture),
the sample size is too small for meaningful win-rate statistics.

---

## RECOMMENDATIONS

1. **Add 3-5 more entering fixtures** with diverse continuation profiles:
   - A fixture where the entry is correct but price pulls back to near-stop before recovering
   - A fixture where the target is barely reached
   - A fixture that produces a genuine loss (to test the exit and attribution pipeline)
   - A SHORT-entry fixture

2. **Extend V3 continuation** from 10 bars to 20+ bars so the target can be hit or missed
   naturally, producing a real closed-trade outcome instead of an open position at fixture end.

3. **Add a fixture with flat/choppy continuation** that should produce a time-stop exit,
   testing the 20-bar time stop path.

---

## VERDICT

The fixtures are NOT biased toward losses. They are biased toward favorable continuations.
The sole cause of the observed losses was the entry-bar wick bug.

The fixtures DO have limitations (LONG-only, small sample, some unrealistically long
continuations), but these are quality-of-calibration concerns, not loss-cause factors.
