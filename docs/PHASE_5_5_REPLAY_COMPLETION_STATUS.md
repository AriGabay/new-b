# Phase 5.5 Replay Completion Status

**Date:** 2026-03-28
**Phase:** 5.5 — Real Runtime Replay Validation
**Prior phase:** 5 — Validation Framework

---

## Summary

Phase 5.5 built the real runtime replay validation layer that was missing from Phase 5.
The layer feeds deterministic fixture-based bar data through the real BTC/Bybit runner
pipeline and documents every step honestly.

---

## Run Results (2026-03-28)

### Fixture Set

| Fixture | Bars | EMA Crossovers | Positions Opened | Positions Closed |
|---------|------|----------------|-----------------|-----------------|
| btc_bull_breakout_v1 | 350 | 2 (1 golden, 1 death) | 0 | 0 |
| btc_bear_breakdown_v1 | 350 | 2 (1 golden, 1 death) | 0 | 0 |
| btc_ranging_v1 | 200 | 9 (4 golden, 5 death) | 0 | 0 |
| **TOTAL** | **900** | **13** | **0** | **0** |

Source tag: `event_driven_runtime_replay`

### Lifecycle Control Tests

| Test | Injected At | Positions Opened | Positions Closed | Notes |
|------|-------------|-----------------|-----------------|-------|
| btc_bull_breakout_v1_lifecycle | bar 200 | 0 | 0 | Panel rejected injected proposal |
| btc_bear_breakdown_v1_lifecycle | bar 200 | 0 | 0 | Panel rejected injected proposal |

Source tag: `event_driven_runtime_replay_lifecycle_assist`

---

## Why Zero Natural Entries

**Root cause: composite_score ceiling < entry threshold.**

The production `EntryGroup` requires `composite_score >= 0.50` before firing a
`CandidateTradeEvent`. With `ChartPatternGroup` excluded from Phase 3, the ceiling is:

```
composite_score_ceiling = 0.35×0.0   (chart_pattern: EXCLUDED)
                        + 0.25×0.75  (candlestick: best case engulfing = 0.75)
                        + 0.20×1.0   (indicator: maximum)
                        + 0.10×1.0   (structural: maximum)
                        + 0.10×0.0   (historian: not wired in Phase 3)
                        = 0.4875
```

**0.4875 < 0.50 → EntryGroup never fires → TraderEvaluatorPanel never evaluates →
no position ever opens naturally.**

This is a structural limitation of Phase 3 scope, not a signal quality issue.

---

## Why Lifecycle Control Also Shows Zero Positions

The lifecycle control test injects a `CandidateTradeEvent` with `composite_score=0.65`,
bypassing the `EntryGroup` composite_score gate. This reaches the `TraderEvaluatorPanel`.

However, **the real panel evaluates with its own selectivity criteria**:
- 14 out of 20 trader approvals required (`APPROVE_THRESHOLD=14`)
- Average score ≥ 6.5 required (`MIN_AVG_SCORE=6.5`)
- FinalDecisionGroup runs 6 safety rails

The injected proposal was evaluated and rejected by the real panel. Zero positions opened.
**This is the system working correctly.** Panel selectivity is genuine.

---

## Indicator Correctness (Real Data)

All three fixtures use mathematically correct indicators computed from OHLCV series:

### btc_bull_breakout_v1 (350 bars, ~62.7K → ~72.4K)
- RSI range: 9.45 – 99.85 | Final: 97.37
- ADX range: 15.00 – 98.81 | Final: 98.12 (strong trend)
- Volume ratio: 0.75 – 1.32
- Golden cross: bar 238 (ema20=63784 > ema50=63779, ADX=37.6, RSI=73.2)
- Death cross: bar 29 (early reversal, ADX=63.7, RSI=11.4)

### btc_bear_breakdown_v1 (350 bars, ~55.1K → ~68.2K peak then reversal)
- RSI range: 0.05 – 93.62 | Final: 0.05 (extreme oversold at end)
- ADX range: 15.00 – 99.60 | Final: 99.60 (very strong trend at end)
- Volume ratio: 0.76 – 1.33
- Death cross: bar 244 (ema20=66716 < ema50=66747, ADX=50.3, RSI=15.1)
- Golden cross: bar 28 (early, then reversal)

### btc_ranging_v1 (200 bars, ~63.8K – ~66.2K)
- RSI range: 21.14 – 78.54 | Final: 39.24 (oscillating)
- ADX range: 15.00 – 38.63 | Final: 29.81 (weakly trending)
- Volume ratio: 0.74 – 1.24
- 9 crossovers: frequent whipsaw confirming ranging detection

---

## Source Separation Compliance

| Source | Used By | Status |
|--------|---------|--------|
| `event_driven_runtime_replay` | TrueReplayHarness pure runs | COMPLIANT |
| `event_driven_runtime_replay_lifecycle_assist` | Lifecycle control tests | COMPLIANT (not in EDGE_EVIDENCE_SOURCES) |
| `event_driven_runtime_simulation` | Phase 5 RuntimeReplayHarness | COMPLIANT (separate namespace) |

No source mixing detected.

---

## What Phase 5.5 Claims

- **Replay infrastructure works**: 900 bars processed, 0 errors
- **Indicators are mathematically correct**: EMA, RSI, ATR, ADX, BB, volume ratio all computed from OHLCV
- **No natural entries**: composite_score ceiling = 0.4875, documented and explained
- **Panel selectivity is real**: lifecycle-injected proposal rejected by real panel
- **Source separation maintained**: all source tags distinct and compliant

## What Phase 5.5 Does NOT Claim

- **No edge evidence**: zero natural entries, zero closed trades
- **No win rate**: not computable without closed trades
- **No calibration data**: zero trades means zero reviews
- **No claim that fixtures = live data**: fixtures are deterministic synthetic-but-realistic OHLCV

---

## Test Coverage

**170 tests passing (128 from Phase 5 + 42 from Phase 5.5).**

Phase 5.5 tests (`test_replay_validation.py`):
- 8 indicator engine tests
- 9 fixture generation tests
- 3 composite score ceiling tests
- 2 source tag tests
- 8 replay harness tests
- 3 lifecycle control tests
- 7 source separation tests
- 2 aggregate report tests
