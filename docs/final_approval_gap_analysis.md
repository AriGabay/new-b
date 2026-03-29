# Final Approval Gap Analysis — V1 Fixture at 13/20

Source: phase_6_3_natural_open

## Context

The `btc_w_bottom_long_v1` fixture produced the best panel result of Phase 6.2: 13/20 approvals, avg=6.700, rec=hold. The panel threshold is 14/20 with avg ≥ 6.5. The gap was exactly one approval vote.

This document explains why each of the 7 non-approving evaluators scored below 7.0 in v1, which are addressable through fixture design, and why VolumeProfile was the most actionable target.

## V1 Panel Summary

| Result  | Count | Evaluators                                                                      |
|---------|-------|---------------------------------------------------------------------------------|
| Approve | 13    | TrendFollowing, Momentum, RiskReward, Volatility, MarketRegime, PositionSize,   |
|         |       | EntryTiming, Correlation, LiquidityDepth, MacroAlignment, SentimentProxy,       |
|         |       | StructuralBreak, TrendStrength                                                  |
| Abstain | 4     | VolumeProfile(5.0), PatternCompletion(5.0), DrawdownRisk(5.5), WickAnalysis(5.5)|
| Reject  | 3     | MeanReversion(3.0), Contrary(4.0), Breakout(4.5)                               |

## Rejecters

### MeanReversion — score 3.0

`MeanReversionEvaluator` detects that price at bar+16 (close=70,400) is recovering sharply from a double-bottom. Its mandate is to fade extended moves; a bullish engulfing at support reads as "entering after a multi-bar decline has reversed" — the classic mean-reversion sell signal from the evaluator's perspective. This evaluator will always reject recovery-at-support entries; it is architecturally opposed to the W-bottom pattern. Score of 3.0 is consistent with strong counter-signal. No fixture change can address this without contradicting the trade setup itself.

### Contrary — score 4.0

`ContraryEvaluator` assigns low scores when most other panel members are approving. Its purpose is to introduce dissent when consensus is high. With 13/20 approving in v1, Contrary reads strong consensus and reduces its score accordingly. This evaluator cannot be satisfied by improving fundamentals — doing so would strengthen consensus further and depress Contrary's score. This is architectural.

### Breakout — score 4.5 (v1) → 5.5 (v2, bonus)

`BreakoutEvaluator` looks for price clearing above a prior resistance level. The v1 entry bar (close=70,400) closed below the last mini-peak (70,800 at bar+9). In v1 this was a reject. In v2, the entry close of 70,500 and the revised preceding structure slightly improve the breakout assessment from 4.5 to 5.5 (abstain). This was an unplanned improvement that emerged from the body-800 design. It did not contribute to the vote count change, as 5.5 still abstains.

## Abstainers

### VolumeProfile — score 5.0 (v1) → 7.0 (v2)

`VolumeProfileEvaluator` started at 5.0 (neutral). In v1, the entry bar body of 300 produced `vol_ratio ≈ 1.05`, which fell between the `> 0.8` and `> 1.2` thresholds — no adjustment applied. Volume character was `normal` (vol_ratio < 1.2). Score stayed at 5.0.

This was the most actionable target: `vol_ratio` is directly controlled by entry bar body size, which is a fixture design parameter with no architectural constraint. Raising body to 800 pushes `vol_ratio` to 1.227, crossing both `> 1.2` thresholds:

- `vol_ratio > 1.2` → +1.0
- `volume_character = "above_avg"` → +1.0
- Result: 5.0 + 2.0 = 7.0 → approve

### PatternCompletion — score 5.0

`PatternCompletionEvaluator` requires `ChartPatternGroup` to supply completed chart pattern signals (head-and-shoulders completion, cup-and-handle, etc.). `ChartPatternGroup` is excluded from the active runtime — it raises `NotImplementedError` if triggered. Without chart pattern completions, this evaluator sees no pattern signals and returns the default neutral score of 5.0. Addressing this requires re-enabling `ChartPatternGroup`, which is out of scope for fixture-only changes. This is an architectural limitation.

### DrawdownRisk — score 5.5

`DrawdownRiskEvaluator` assesses the risk of the proposed entry in terms of potential drawdown relative to the account. At a 70,500 entry with a stop below 69,670 (support level), the risk distance is approximately 830 points. The evaluator's calculation of risk relative to position size and account balance produces a score that sits in abstain territory (5.5). To move this evaluator to approve (≥ 7.0) would require either a tighter stop (which conflicts with the structural level) or a larger account buffer (which is a runtime configuration parameter, not a fixture parameter). Feasible in principle but outside the Phase 6.3 scope of fixture-only changes.

### WickAnalysis — score 5.5

`WickAnalysisEvaluator` rewards entries accompanied by hammer or pin-bar candlestick patterns at support — specifically long lower wicks indicating rejection of the lower price area. The v1 entry bar (bullish engulfing, body=200, open=70,100, close=70,400) has moderate wicks but not the prominent lower wick of a hammer. The score of 5.5 reflects partial credit: the bar is bullish and at support, but lacks the hammer-specific wick signature. Achieving a hammer pattern would require close > open (bullish), and lower_shadow / candle_range > 0.6. Engineering a hammer at this exact price level is feasible but was not needed given the VolumeProfile path.

## Why VolumeProfile Was Chosen

| Evaluator      | Addressable by fixture? | Mechanism                       | Risk of breaking other evaluators |
|----------------|-------------------------|---------------------------------|-----------------------------------|
| VolumeProfile  | Yes                     | Increase entry bar body         | None — volume is locally computed |
| PatternCompletion | No                   | Requires excluded ChartPatternGroup | N/A                           |
| DrawdownRisk   | Partially               | Requires runtime config change  | Would affect other tests          |
| WickAnalysis   | Feasible                | Requires hammer pattern design  | Would change entry bar shape      |
| MeanReversion  | No                      | Architecturally opposed to setup | N/A                             |
| Contrary       | No                      | Rises with consensus            | Higher consensus = lower Contrary |
| Breakout       | Partially               | Needs higher entry close        | Would conflict with at_support    |

VolumeProfile was selected because:

1. The scoring rule is a simple threshold comparison (`vol_ratio > 1.2`).
2. `vol_ratio` is entirely determined by the entry bar's body size and the preceding volume baseline.
3. No other evaluator's score decreases when volume increases — there is no trade-off.
4. The mechanism is documented, testable, and reproducible.

## Conclusion

The v1 fixture was stuck at 13/20 because it generated an entry bar with insufficient volume uplift. The 4 abstaining evaluators all have different root causes, but only VolumeProfile offered a clean, side-effect-free path to approval through fixture design alone.
