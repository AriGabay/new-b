# Trader Calibration Framework

**Phase:** 4 Learning Layer
**Date:** 2026-03-28

---

## Purpose

Track whether each of the 20 trader evaluators is actually predicting
winning trades. A trader that consistently approves losing setups should
be flagged; a trader that correctly identifies winners should be recognized.

---

## Metrics

### Approval Win Rate
Of all trades this trader voted "approve" on, what fraction were wins?

```
approval_win_rate = approvals_that_won / approvals_given
```

Requires: `approvals_given >= 30`
Gate: `TraderCalibrationRecord.has_sufficient_samples` must be True

Interpretation:
- < 30%: Quarantine flag (very poor)
- 30–40%: Caution flag
- 40–60%: Normal range
- > 60%: Strong signal; consider increasing weight

### Brier Score
Probability calibration quality. Lower is better. Random = 0.25.

```
brier_component = (forecast_prob - outcome_binary)^2
forecast_prob = confidence * (1 if vote=="approve" else 0)
outcome_binary = 1 if outcome=="win" else 0
brier_score = mean(brier_component) over all reviews
```

Interpretation:
- < 0.20: Well-calibrated
- 0.20–0.25: Acceptable
- > 0.25: Poorly calibrated (no better than random)
- > 0.30: Flag for review

### Score Discriminability
Do higher scores predict wins?

```
discriminability = avg_score_on_wins - avg_score_on_losses
```

Positive value = trader scores winners higher than losers (good).
Negative value = trader gives high scores to losers (bad).

### Overconfidence Detection
High confidence + wrong outcome rate.

```
overconfidence = high_conf_wrong_count / total_reviews
```
where "high confidence" = confidence >= 0.75 AND vote was wrong.

Flagged when overconfidence > 30% (with >= 30 samples).

---

## Minimum Sample Requirements

ALL calibration metrics require `total_reviews >= 30` before any
conclusions are drawn. The `has_sufficient_samples` property on
`TraderCalibrationRecord` enforces this gate.

Phase 4 (paper trading / simulation) will accumulate samples over time.
Do not draw conclusions before the sample minimum is reached.

---

## 20 Trader Evaluators

| # | Evaluator | Evaluation Focus |
|---|---|---|
| 1 | TrendFollowingEvaluator | EMA alignment, ADX trend strength |
| 2 | MomentumEvaluator | RSI, price momentum |
| 3 | MeanReversionEvaluator | BB bands, RSI extremes |
| 4 | BreakoutEvaluator | Breakout above/below structure |
| 5 | StructureEvaluator | S/R level alignment |
| 6 | CandlestickEvaluator | Candlestick pattern quality |
| 7 | RiskParityEvaluator | Stop distance, R:R ratio |
| 8 | VolatilityEvaluator | ATR regime, volatility environment |
| 9 | VolumeProfileEvaluator | Volume confirmation |
| 10 | MacroRegimeEvaluator | BTC macro regime assessment |
| 11 | ContraryEvaluator | Devil's advocate anti-thesis |
| 12 | ProfitTargetEvaluator | Target realism vs. resistance |
| 13 | EntryTimingEvaluator | Bar-level entry quality |
| 14 | ConfluenceEvaluator | Multi-factor confluence |
| 15 | DrawdownRiskEvaluator | Drawdown state risk |
| 16 | LeverageSpecialistEvaluator | Leverage appropriateness |
| 17 | PatternCompletionEvaluator | Setup completeness |
| 18 | WickAnalysisEvaluator | Wick/rejection signals |
| 19 | MarketContextEvaluator | Broader market context |
| 20 | ExecutionQualityEvaluator | Order execution feasibility |
