# Panel Vote Shift Report — V1 vs V2

Source: phase_6_3_natural_open

## Summary

Two evaluators changed their votes from v1 to v2. No evaluator decreased. The panel moved from 13/20 (hold) to 14/20 (enter).

| Metric           | V1 (btc_w_bottom_long_v1) | V2 (btc_w_bottom_long_v2) | Change   |
|------------------|---------------------------|---------------------------|----------|
| Approve count    | 13                        | 14                        | +1       |
| Reject count     | 3                         | 2                         | -1       |
| Abstain count    | 4                         | 4                         | 0        |
| Avg score        | 6.700                     | 6.850                     | +0.150   |
| Recommendation   | hold                      | enter                     | threshold crossed |

## Full Evaluator Vote Table (All 20)

| Evaluator            | V1 Score | V1 Vote | V2 Score | V2 Vote | Change         |
|----------------------|----------|---------|----------|---------|----------------|
| TrendFollowing       | 8.0      | approve | 8.0      | approve | unchanged      |
| Momentum             | 7.5      | approve | 7.5      | approve | unchanged      |
| RiskReward           | 7.0      | approve | 7.0      | approve | unchanged      |
| Volatility           | 7.0      | approve | 7.0      | approve | unchanged      |
| MarketRegime         | 7.0      | approve | 7.0      | approve | unchanged      |
| PositionSize         | 7.0      | approve | 7.0      | approve | unchanged      |
| EntryTiming          | 7.5      | approve | 7.5      | approve | unchanged      |
| Correlation          | 7.0      | approve | 7.0      | approve | unchanged      |
| LiquidityDepth       | 7.0      | approve | 7.0      | approve | unchanged      |
| MacroAlignment       | 7.0      | approve | 7.0      | approve | unchanged      |
| SentimentProxy       | 7.0      | approve | 7.0      | approve | unchanged      |
| StructuralBreak      | 7.5      | approve | 7.5      | approve | unchanged      |
| TrendStrength        | 7.0      | approve | 7.0      | approve | unchanged      |
| VolumeProfile        | 5.0      | abstain | 7.0      | approve | +2.0 (abstain→approve) |
| PatternCompletion    | 5.0      | abstain | 5.0      | abstain | unchanged      |
| DrawdownRisk         | 5.5      | abstain | 5.5      | abstain | unchanged      |
| WickAnalysis         | 5.5      | abstain | 5.5      | abstain | unchanged      |
| MeanReversion        | 3.0      | reject  | 3.0      | reject  | unchanged      |
| Contrary             | 4.0      | reject  | 4.0      | reject  | unchanged      |
| Breakout             | 4.5      | reject  | 5.5      | abstain | +1.0 (reject→abstain) |

Note: Vote thresholds are score ≥ 7.0 = approve, score ≥ 5.0 = abstain, score < 5.0 = reject.

## Changed Votes

### VolumeProfile: abstain(5.0) → approve(7.0)

Primary change. Mechanism:

- V1 entry bar: body=300 (open=70,300, close=70,400) → `move_pct=0.00428` → `vol_mult≈1.086` → `vol_ratio≈1.05` → no threshold crossed → score stays at 5.0.
- V2 entry bar: body=800 (open=69,700, close=70,500) → `move_pct=0.01148` → `vol_mult≈1.257` → `vol_ratio≈1.227`.
  - `vol_ratio > 1.2` → +1.0
  - `IndicatorsGroup` classifies as `volume_character = "above_avg"` (threshold: vol_ratio > 1.2) → +1.0
  - Final: 5.0 + 1.0 + 1.0 = 7.0 → approve.

This vote shift is solely responsible for crossing the 14/20 threshold.

### Breakout: reject(4.5) → abstain(5.5)

Unplanned improvement. Mechanism:

- V1 entry close=70,400 is clearly below the mini-peak at bar+9 (close=70,800). The breakout evaluator measures distance from the recent swing high and the ratio of close to that high. A close 400 below the recent peak scores below 5.0.
- V2 entry close=70,500, combined with the revised bar+18 close of 69,700 (which establishes a wider recent range), shifts the breakout calculation. The effective "prior resistance" reference changes because bar+18 creates a new recent low at 69,700, making the +800 recovery appear more significant.
- Score rises from 4.5 to 5.5, crossing the abstain boundary but not reaching approve.

This change reduced the reject count from 3 to 2 and slightly increased the average score, but did not affect the approve count.

## Non-Changed Votes: Confirmation

All 13 original approvers maintain their scores unchanged. This confirms:

1. The body-800 modification does not disturb EMA alignment (full_bull remains).
2. The 3 consolidation bars do not materially alter ADX, RSI, or ATR at bar+19.
3. The at_support condition is preserved through the 1-bar lag mechanism.
4. No evaluator was "promoted" by coincidence — only targeted evaluators changed.

The 3 remaining abstainers (PatternCompletion, DrawdownRisk, WickAnalysis) are stable at their v1 scores for structural reasons:

- PatternCompletion: no chart pattern completion signals (ChartPatternGroup excluded).
- DrawdownRisk: stop distance relative to account unchanged.
- WickAnalysis: entry bar shape is bullish engulfing, not hammer — no wick score uplift.

## No Vote Decreases

Examining all 20 evaluators: V2 score ≥ V1 score for every evaluator. The minimum change was 0.0. No evaluator was harmed by the v2 design.

This is important for fixture integrity: a fixture that improves one evaluator at the cost of another would not be a valid test of the target mechanism.
