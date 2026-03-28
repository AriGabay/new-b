# Specialist Group Reliability Framework

**Phase:** 4 Learning Layer
**Date:** 2026-03-28

---

## Purpose

Track how reliably each specialist group's signals contribute to
profitable trades. Groups that consistently emit signals before wins
are high-reliability; groups whose signals precede losses are suspect.

---

## The 10 Specialist Groups

| # | Group | Layer A Role |
|---|---|---|
| 1 | MarketDataGroup | OHLCV + FeatureVector computation |
| 2 | IndicatorsGroup | EMA, RSI, BB, ATR, ADX signals |
| 3 | CandlestickGroup | Candlestick pattern signals |
| 4 | ChartPatternGroup | Chart pattern signals (STUBBED — Phase 4+) |
| 5 | TechnicalStructureGroup | S/R levels, structural signals |
| 6 | NewsMarcoGroup | Macro regime classification |
| 7 | EntryGroup | Signal aggregation → CandidateTradeProposal |
| 8 | RiskLeverageGroup | Risk gates → RiskApprovedOrder |
| 9 | ExitGroup | Position exit logic |
| 10 | PerformanceJournalGroup | Journaling + learning hooks |

**ChartPatternGroup is stubbed.** It emits no signals. Do not attribute
outcomes to it until it is implemented.

---

## Reliability Metrics

### Win Contribution Rate
Of signals from this group that contributed to trades, what fraction
were on winning trades?

```
win_contribution_rate = signals_on_winning_trades /
                        (signals_on_winning_trades + signals_on_losing_trades)
```

Requires: 30+ signal-trade pairs.

### Quality Score Discrimination
Average quality score on winning trades vs losing trades.

If `avg_quality_score_wins > avg_quality_score_losses`, the group's
quality scoring is discriminative (good signal).

---

## Current Reliability Status (2026-03-28)

| Group | Status | Reliability Data |
|---|---|---|
| IndicatorsGroup | Active | Accumulating |
| CandlestickGroup | Active | Accumulating |
| ChartPatternGroup | STUBBED | No data — do not analyze |
| TechnicalStructureGroup | Active | Accumulating |
| NewsMarcoGroup | Partial | Macro regime only |

All groups have zero samples — data accumulates in paper trading.

---

## Sample Minimum

30 signal-trade pairs per group before reliability conclusions.
`SpecialistGroupRecord.has_sufficient_samples` enforces this gate.
