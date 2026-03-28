# Real Runtime Replay Framework

**Phase:** 5.5
**Source tag:** `event_driven_runtime_replay`

---

## Purpose

The real runtime replay framework provides a way to validate the full BTC/Bybit runner
pipeline against deterministic, historically-structured bar data — without connecting to
a live exchange. It is distinct from:

- **Simulation mode** (`event_driven_runtime_simulation`): fully synthetic bars with
  constant-offset indicators, no price dynamics
- **Backtest mode** (`simplified_backtest`): backtesting engine with different execution
  semantics
- **Synthetic control** (`synthetic_control_scenarios`): hand-crafted BTCSetupPacket
  objects, no bar-by-bar feeding

---

## Architecture

```
btc_replay_fixture.py
  ├── _generate_bull_breakout_prices()   → deterministic OHLCV price series
  ├── _generate_bear_breakdown_prices()  → deterministic OHLCV price series
  ├── _generate_ranging_prices()         → deterministic OHLCV price series
  ├── _build_ohlcv_series()              → (opens, highs, lows, closes, volumes)
  ├── _series_to_feature_vectors()       → list[FeatureVector] with real indicators
  └── get_{bull,bear,ranging}_fixture()  → ReplayFixture

indicator_engine.py
  ├── compute_ema(prices, period)
  ├── compute_rsi(prices, period=14)
  ├── compute_atr(highs, lows, closes, period=14)
  ├── compute_atr_sma20(atr_values)
  ├── compute_bollinger_bands(prices, period=20, std_dev=2.0)
  ├── compute_adx(highs, lows, closes, period=14)
  └── compute_volume_ratio(volumes, period=20)

true_replay_harness.py
  ├── TrueReplayHarness
  │   ├── setup()                         → creates BtcBybitPaperRunner(simulation_mode=True)
  │   ├── run_fixture(fixture)            → ReplayFixtureReport (pure replay)
  │   ├── run_lifecycle_control_test()    → ReplayFixtureReport (injected entry)
  │   └── teardown()
  └── make_replay_aggregate_report()     → aggregate dict
```

---

## Indicator Computation

All indicators in the replay fixtures are computed from real OHLCV data using pure-Python
implementations in `indicator_engine.py`. No constant offsets. No numpy.

### EMA
- Alpha: `k = 2.0 / (period + 1)`
- Seed: simple average of first `period` bars
- Formula: `ema[i] = price[i] * k + ema[i-1] * (1 - k)`

### RSI (Wilder)
- Seed: simple average of first 14 gains/losses
- Formula: `avg_gain = (prev_avg_gain * 13 + gain) / 14`
- Output: `100 - 100 / (1 + avg_gain / avg_loss)`

### ATR (Wilder)
- True Range: `max(H-L, |H-prevC|, |L-prevC|)`
- Seed: SMA of first 14 TRs
- Wilder smoothing: `atr[i] = (atr[i-1] * 13 + TR[i]) / 14`

### ADX
- DM+ / DM- smoothed with Wilder SUM-accumulating form (industry standard)
- DI+ = 100 × smoothed_DM+ / smoothed_TR, capped at 100
- DX = 100 × |DI+ - DI-| / (DI+ + DI-)
- ADX uses running-average form: `adx = (prev_adx * 13 + dx) / 14`
  (NOT the SUM-accumulating form — ADX must stay in [0, 100])

### Bollinger Bands
- Period: 20, StdDev: 2.0
- Middle = SMA(20), Upper = SMA + 2σ, Lower = SMA - 2σ
- bb_width = upper - lower
- bb_width_pct = (upper - lower) / middle × 100

### Volume Ratio
- `volume_ratio = volume / SMA(volume, 20)`

---

## Data Flow

```
ReplayFixture
  └── feature_vectors: list[FeatureVector]   (with real indicators)
        ↓
TrueReplayHarness.run_fixture()
  └── for each fv:
        └── runner.simulate_bar(fv)
              ↓ EventBus
          IndicatorsGroup   → GroupSignalBundle
          CandlestickGroup  → GroupSignalBundle
          TechnicalStructureGroup → GroupSignalBundle
          ChartPatternGroup → (not implemented, skipped)
          EntryGroup        → CandidateTradeEvent IF composite_score >= 0.50
                              (currently NEVER fires — ceiling 0.4875)
          TraderEvaluatorPanel → TraderVerdictEvent × 20
          FinalDecisionGroup   → ApproveTradeEvent OR RejectTradeEvent
          RiskLeverageGroup    → TradeSizedEvent
          ExecutionGroup       → PositionOpenEvent
          ExitGroup            → PositionCloseEvent (on subsequent bars)
```

---

## Known Structural Limitation

**Natural entries cannot fire in Phase 3 runner.**

`ChartPatternGroup` raises `NotImplementedError` in the current codebase. Without chart
pattern scores, the maximum `composite_score` is:

```
0.35 × 0.0 (chart: excluded)
+ 0.25 × 0.75 (candlestick: max quality)
+ 0.20 × 1.0 (indicator: max)
+ 0.10 × 1.0 (structural: max)
+ 0.10 × 0.0 (historian: not wired)
= 0.4875
```

Entry threshold = 0.50. Shortfall = 0.0125. All three fixtures confirmed 0 natural entries.

To enable natural entries:
1. Implement ChartPatternGroup (Phase 4+), OR
2. Lower `COMPOSITE_SCORE_THRESHOLD` to ≤ 0.4875 (only if deliberate threshold change)

---

## Lifecycle Control Mode

When natural entries cannot fire, the harness provides a lifecycle control mode
(`run_lifecycle_control_test()`) that:

1. Injects one `CandidateTradeEvent` at a specified bar
2. The **real panel evaluates it** — no forcing, no approvals bypassed
3. Records whether the panel approved and a position opened

This is tagged separately as `event_driven_runtime_replay_lifecycle_assist` so it
cannot be used as edge evidence.

In Phase 5.5 runs, the lifecycle control test showed 0 positions opened. The real panel's
selectivity requirements (14/20 approvals, avg ≥ 6.5) caused the injected proposal to be
rejected. **This is the system working correctly.**

---

## Fixture Characteristics

| Fixture | Bars | Price Range | ADX Final | EMA Crossovers |
|---------|------|-------------|-----------|----------------|
| btc_bull_breakout_v1 | 350 | 62,749 – 72,351 | 98.1 (strong trend) | 2 |
| btc_bear_breakdown_v1 | 350 | 55,144 – 68,236 | 99.6 (very strong) | 2 |
| btc_ranging_v1 | 200 | 63,809 – 66,193 | 29.8 (weak) | 9 (whipsaw) |

All fixtures are fully deterministic: same seed → same bars every run.

---

## Usage

```python
from validation.fixtures.btc_replay_fixture import get_all_replay_fixtures
from validation.true_replay_harness import TrueReplayHarness

harness = TrueReplayHarness()
await harness.setup()

for fixture in get_all_replay_fixtures():
    report = await harness.run_fixture(fixture)
    print(report.honest_assessment)

await harness.teardown()
```
