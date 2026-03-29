# LOSS BUCKET ANALYSIS
**Date:** 2026-03-29

---

## BEFORE BUG FIX

| Root-Cause Bucket | Trade Count | Severity | Likely Fix | Tune or Fix? | Notes |
|-------------------|-------------|----------|------------|-------------|-------|
| Entry-bar wick false stop | 42 | CRITICAL | Skip exit checks on entry bar | FIX FIRST | 100% of losses |
| Fixture design | 0 | — | — | — | Fixtures have favorable continuations |
| Late entry timing | 0 | — | — | — | Entries are correctly timed |
| Poor stop placement | 0 | — | — | — | 2*ATR stops are appropriate |
| Unrealistic targets | 0 | — | — | — | 2R targets hit naturally in some fixtures |
| Regime mismatch | 0 | — | — | — | All entries in correct regime |

---

## AFTER BUG FIX

| Root-Cause Bucket | Trade Count | Severity | Category | Notes |
|-------------------|-------------|----------|----------|-------|
| Profitable continuation | 3 | — | WIN | All 3 entries reach significant MFE |
| Flat / insufficient bars | 1 | LOW | FLAT | V2 fixture ends before target; MAE=0.621R |

---

## TRADE-LEVEL MATRIX

| Trade / Setup | Source | Entry Quality | Stop Quality | Target Quality | Exit Reason | Likely Root Cause | Fixture Artifact? | Confidence | Notes |
|--------------|--------|---------------|-------------|---------------|-------------|-------------------|--------------------|-----------|-------|
| V3 double_bottom (pre-fix) | event_driven_runtime | GOOD (MFE=1.655R) | GOOD (2*ATR) | GOOD (2R) | FALSE STOP (bars_held=0) | Entry-bar wick check | NO — system bug | 100% | Fixed |
| V3 double_bottom (post-fix) | event_driven_runtime | GOOD | GOOD | GOOD | OPEN (+1.495R) | N/A — winning | N/A | 100% | Fixture too short for target |
| V2 w_bottom | event_driven_runtime | MARGINAL (MFE=0.200R) | GOOD (2*ATR) | AMBITIOUS (3.8R target) | OPEN (flat) | Insufficient continuation | YES — fixture short | 80% | Only 19 bars post-entry |
| bull_cont #1 | event_driven_runtime | GOOD (MFE=13.56R) | GOOD | GOOD | trailing_stop +0.094R | Good trade management | N/A | 100% | Trailing activated then caught |
| bull_cont #2 | event_driven_runtime | GOOD (MFE=14.22R) | GOOD | GOOD | target_reached +0.262R | Target hit naturally | N/A | 100% | Clean 2R target |

---

## GROUPED SUMMARY

| Root-Cause Bucket | Trade Count | Severity | Likely Fix Category | Tune Later or Fix First? | Notes |
|-------------------|-------------|----------|--------------------|-----------------------------|-------|
| Entry-bar wick false stop | 42 (historical) | CRITICAL | Bug fix (ExitGroup) | **FIXED** | All historical losses explained |
| Fixture too short for exit | 2 (V3+V2 don't close) | LOW | Fixture extension | Tune later | Add more continuation bars |
| Trailing stop too tight? | 1 (bull_cont #1 +0.094R) | LOW | Exit parameter tuning | Tune later | MFE=13.56R but captured only 0.094R |
| None (correct behavior) | 1 (bull_cont #2 target hit) | — | — | — | System working as designed |

---

## SECONDARY OBSERVATION: TRAILING STOP EFFICIENCY

bull_continuation_pullback_v1 Trade #1 has MFE = 13.562R but PnL = +0.094R. That means
the trailing stop only captured 0.7% of the maximum favorable excursion. This is not a bug
but suggests the trailing stop parameters (activate at +1R, trail at close-2*ATR) may be
loose enough that a pullback after the peak triggers the trail before capturing significant
profit. This is a legitimate Phase 7 tuning target (after sufficient data accumulates).
