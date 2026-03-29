# EVALUATOR APPROVAL ON LOSERS
**Date:** 2026-03-29

---

## KEY FINDING: There are no real losers to analyze

The 42 historical "losses" were all caused by the entry-bar wick bug (bars_held=0 false
stops). After fixing the bug, the system produces 3 wins, 0 losses, and 1 flat/open from
the entering fixtures.

Therefore, evaluator-approval-on-losers analysis is NOT APPLICABLE for the current data.

---

## EVALUATOR BEHAVIOR ON THE 4 TRADES (POST-FIX)

### Consistent Approvers (approve on all entering fixtures)

| Evaluator | V3 Score | V2 Score | BullCont Score | Role |
|-----------|----------|----------|---------------|------|
| TrendFollowing | 8.0 | 8.0 | 6.5 | EMA alignment detection |
| Momentum | 8.0 | 8.0 | 8.0 | RSI + volume confirmation |
| Structure | 6.5 | 6.5 | 6.5 | S/R alignment |
| Candlestick | 10.0 | 10.0 | 10.0 | Pattern strength |
| RiskParity | 7.0 | 7.0 | 7.0 | R:R assessment |
| Volatility | 7.0 | 7.0 | 7.0 | ATR regime |
| VolumeProfile | 7.0 | 7.0 | 7.0 | Volume confirmation |
| MacroRegime | 9.0 | 9.0 | 8.0 | Bull macro context |
| ProfitTarget | 9.0/7.0 | 7.0 | 7.0 | Target realism |
| EntryTiming | 7.0 | 7.0 | 7.0 | Confirmation bar |
| Confluence | 10.0 | 10.0 | 10.0 | Multi-signal alignment |
| LeverageSpecialist | 7.0 | 7.0 | 7.0 | Position sizing |
| MarketContext | 7.0 | 7.0 | 7.0 | Regime context |
| ExecutionQuality | 8.0 | 8.0 | 8.0 | Entry quality |

### Consistent Rejecters

| Evaluator | Score | Vote | Reason | Correct? |
|-----------|-------|------|--------|----------|
| MeanReversion | 3.0 | reject | These are trend-continuation setups | YES — correct rejection |
| Contrary | 4.0 | reject | These are with-trend, not contrarian | YES — correct rejection |

### Consistent Abstainers

| Evaluator | Score | Vote | Reason | Concerning? |
|-----------|-------|------|--------|-------------|
| DrawdownRisk | 5.5 | abstain | No drawdown context in paper mode | NO — expected |
| WickAnalysis | 5.5 | abstain | Weak wick scoring model | MINOR — low information |

### Variable Voters (swing evaluators)

| Evaluator | V3 Score | V2 Score | BullCont Score | Behavior |
|-----------|----------|----------|---------------|----------|
| Breakout | 8.0 (approve) | 5.5 (abstain) | 5.5 (abstain) | Approves only with confirmed chart pattern |
| PatternCompletion | 10.0 (approve) | 5.0 (abstain) | 5.0 (abstain) | Approves only with confirmed chart pattern |

These two evaluators are the swing voters that push V3 from 14/20 to 16/20 when a
double bottom chart pattern is confirmed. This is correct and well-designed behavior.

---

## EVALUATOR ACCURACY ASSESSMENT

Since all 4 trades are winners (post-fix), every approving evaluator was correct.
The rejecting evaluators (MeanReversion, Contrary) were incorrect in the literal sense
(the trades won), but their rejection logic is semantically correct — they are designed
to identify mean-reversion and contrarian setups, not trend-continuation setups.

**Per-evaluator accuracy requires more diverse data:** We need fixtures where some entries
lose to determine which evaluators correctly predict failures. With 100% win rate,
all approvers look equally good and all rejecters look equally bad.

---

## RECOMMENDATION

1. **Do not change evaluator weights yet.** The 100% win rate (post-fix) means we cannot
   distinguish predictive from non-predictive evaluators.

2. **Create fixtures that produce legitimate losses** (e.g., entries in choppy regimes
   where stops are hit) to test which evaluators correctly predict failures.

3. **Monitor trader_calibration data** as it accumulates from future replay runs.
   The calibration pipeline is now fixed and will record per-evaluator accuracy.
