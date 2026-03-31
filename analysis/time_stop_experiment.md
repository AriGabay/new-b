# Time Stop Experiment

Date range : 2023-12-01 → 2024-12-31
Generated  : 2026-03-31 12:04:09
Baseline equity : $1,000

| Metric                  | With Time Stop | No Time Stop | Change |
|-------------------------|----------------|--------------|--------|
| Total trades            |             61 |           58 |     -3 |
| Win rate                |          36.1% |        36.2% | +0.1pp |
| Profit factor           |           0.80 |         0.88 |  +0.08 |
| Net P&L $               |          $-321 |        $-221 |  $+100 |
| Net P&L %               |         -32.1% |       -22.1% | +10.0pp |
| Max drawdown            |          42.9% |        42.9% | +0.0pp |
| Avg bars held           |           16.3 |         19.4 |   +3.0 |
| % closed by time stop   |             0% |           0% |   -0pp |
| % closed by stop loss   |            69% |          66% |   -3pp |
| % closed by trailing SL |            28% |          31% |   +3pp |
| % closed by TP          |             3% |           3% |   +0pp |

> **CONCLUSION: Time stop has minimal impact. Not the main issue.**

---

Files:
- With time stop : `analysis/backtest_trades.csv`
- No time stop   : `analysis/backtest_trades_no_ts.csv`
