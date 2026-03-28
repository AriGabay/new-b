# Replay Input Data Contract

**Phase:** 5.5
**Component:** btc_replay_fixture.py + indicator_engine.py

---

## What Is a ReplayFixture

```python
@dataclass
class ReplayFixture:
    name: str                          # unique ID (e.g., "btc_bull_breakout_v1")
    description: str                   # human-readable summary
    feature_vectors: list[FeatureVector]  # all bars in order, with computed indicators
    validation_source: str             # always "event_driven_runtime_replay"
```

Each `FeatureVector` in the list represents one 1-hour bar with all indicator fields
populated from real OHLCV computation (not constant offsets).

---

## FeatureVector Field Contract

All fields required to be non-None for replay bars:

### Price Fields
| Field | Type | Computed From | Example |
|-------|------|---------------|---------|
| `symbol` | str | constant BTCUSDT | "BTCUSDT" |
| `timeframe` | str | constant "1h" | "1h" |
| `timestamp` | datetime | sequential from 2024-01-01 | 2024-01-15 04:00:00+00:00 |
| `open` | Decimal | price series | Decimal("64123.45") |
| `high` | Decimal | price + ATR/4 | Decimal("64456.78") |
| `low` | Decimal | price - ATR/4 | Decimal("63890.12") |
| `close` | Decimal | price series | Decimal("64200.00") |
| `volume` | Decimal | base × multiplier | Decimal("1234.56789") |

### Indicator Fields (computed from OHLCV)
| Field | Type | Computation | Notes |
|-------|------|-------------|-------|
| `ema20` | Decimal | EMA(close, 20) | Seeded from SMA of first 20 bars |
| `ema50` | Decimal | EMA(close, 50) | Seeded from SMA of first 50 bars |
| `ema200` | Decimal | EMA(close, 200) | Seeded from SMA of first 200 bars |
| `prev_ema20` | Decimal | ema20[i-1] | Required for crossover detection |
| `prev_ema50` | Decimal | ema50[i-1] | Required for crossover detection |
| `rsi14` | float | RSI(close, 14) Wilder | 0–100 |
| `atr14` | Decimal | ATR(H,L,C, 14) Wilder | Always > 0 |
| `atr_sma20` | Decimal | SMA(atr14, 20) | 20-period moving avg of ATR |
| `adx14` | float | ADX(H,L,C, 14) | 0–100, Wilder with running-avg smoothing |
| `volume_ratio` | Decimal | volume / SMA(volume, 20) | 1.0 = average |
| `bb_upper` | Decimal | SMA(20) + 2σ | Bollinger upper |
| `bb_middle` | Decimal | SMA(close, 20) | Bollinger middle |
| `bb_lower` | Decimal | SMA(20) - 2σ | Bollinger lower |
| `bb_width` | Decimal | bb_upper - bb_lower | Absolute band width |
| `bb_width_pct` | Decimal | bb_width / bb_middle × 100 | Band width as % of price |

### Structural Fields (always default — not derived from price)
| Field | Value | Notes |
|-------|-------|-------|
| `support_level` | close × 0.97 | Approximate, not real S/R |
| `resistance_level` | close × 1.03 | Approximate, not real S/R |
| `trend_direction` | "up" or "down" or "sideways" | From EMA slope |
| `market_regime` | "trending" or "ranging" | From ADX |

---

## Indicator Computation Fidelity

### EMA
- Seed: SMA of first `period` prices (not "start from first price")
- This means EMA values for early bars are influenced by the warmup region
- Fixtures include 220 bars of warmup before the "analysis window"
- EMA200 requires 200 bars to stabilize → warmup provides this

### ADX Note (important)
The ADX implementation uses two different Wilder smoothing variants:
- DM+ and TR smoothing: **SUM-accumulating form** (Wilder industry convention for DM)
  - `smoothed[i] = smoothed[i-1] × (N-1)/N + value[i]`
  - Produces values that can exceed 100 during accumulation phase
- ADX smoothing: **running-average form** (ensures ADX stays in [0, 100])
  - `adx[i] = (adx[i-1] × (N-1) + dx[i]) / N`
  - Seeded with average of first N DX values (not sum)
- DI values are capped at 100 after division

### RSI Edge Cases
- Flat price series: avg_loss → 0 → RSI → 100.0 (not 50.0)
- This is mathematically correct Wilder behavior
- Tests check range [0, 100] rather than specific values for flat series

---

## Fixture Design Principles

1. **Deterministic**: identical inputs → identical outputs on every run
2. **Sufficient warmup**: 220 bars before analysis window for EMA200 stability
3. **Realistic dynamics**: prices follow sinusoidal + trend + noise patterns (not random walk)
4. **Named scenarios**: each fixture designed to exhibit specific market behavior
5. **No live data**: these are synthetic-but-realistic; they are NOT actual BTC prices

---

## What These Fixtures Are NOT

- NOT recordings of actual Bybit historical data
- NOT representative of any specific date range
- NOT calibrated to actual BTC volatility (ATR/price ratios are approximate)
- NOT suitable for making historical performance claims

The `event_driven_runtime_replay` source tag reflects that these fixtures:
- Use the **same real runner pipeline** that would process live Bybit data
- Feed bars in the same format that live Bybit data would use
- Produce indicator values using the same algorithms as production

The tag does NOT mean these fixtures represent actual market history.

---

## Adding New Fixtures

To add a new fixture to the replay validation set:

1. Write a deterministic price-generation function in `btc_replay_fixture.py`
2. Include at least 220 bars of warmup before the analysis window
3. Call `_build_ohlcv_series(prices)` to get OHLCV arrays
4. Call `_series_to_feature_vectors(...)` to get FeatureVector list
5. Return a `ReplayFixture` with `validation_source=REPLAY_SOURCE`
6. Register in `get_all_replay_fixtures()`
7. Add tests to `test_replay_validation.py`:
   - Bar count ≥ expected minimum
   - Indicators in valid ranges
   - Fixture-specific crossover presence

---

## Live Data Integration (Future)

When actual Bybit historical OHLCV data is available:

```python
def build_fixture_from_bybit_csv(csv_path: str) -> ReplayFixture:
    """
    Load historical Bybit OHLCV data and build a replay fixture.
    Same indicator_engine functions apply.
    Source: still "event_driven_runtime_replay" — same pipeline.
    """
    ...
```

The indicator_engine functions (pure Python, no numpy) can process any OHLCV source.
The FeatureVector format is unchanged. The harness is unchanged.
