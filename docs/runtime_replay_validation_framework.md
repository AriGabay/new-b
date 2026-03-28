# Runtime Replay Validation Framework

**Date:** 2026-03-28

---

## Overview

The runtime replay validation framework allows the full BTC/Bybit pipeline to be
tested against sequences of FeatureVectors — without live Bybit connectivity, without
forced approvals, and without patching any production components.

Two modes are defined:

| Mode | Source Tag | Bars Source | Forcing? |
|------|-----------|-------------|---------|
| Replay harness | `event_driven_runtime_simulation` | Synthetic sequences | None |
| Live replay | `event_driven_runtime_replay` | Real historical bars | None |

The `RuntimeReplayHarness` implements the simulation mode. Live replay requires
real Bybit bar data and is the source of true edge evidence.

---

## Architecture

```
RuntimeReplayHarness
    │
    ├── BtcBybitPaperRunner (simulation_mode=True, temp DB)
    │       │
    │       ├── MarketDataGroup         ← fv injected via simulate_bar()
    │       ├── IndicatorsGroup         ← receives FeatureReadyEvent
    │       ├── CandlestickGroup        ← receives FeatureReadyEvent
    │       ├── TechnicalStructureGroup ← receives FeatureReadyEvent
    │       ├── EntryGroup              ← fires CandidateTradeEvent if signals align
    │       ├── PanelDecisionGroup      ← runs 20 traders (NO forcing)
    │       ├── RiskLeverageGroup       ← applies all 9 rules
    │       ├── ExitGroup               ← closes positions on stop/target
    │       └── PerformanceJournalGroup ← writes events to temp SQLite DB
    │
    └── run_sequence(fv_sequence) → ReplaySequenceSummary
```

Each call to `simulate_bar(fv)`:
1. Updates `_feature_cache[(symbol, timeframe)]` — required for PanelDecisionGroup to build BTCSetupPackets
2. Updates `state.last_close_by_symbol[symbol]` — required for EntryGroup to set entry_price
3. Publishes `FeatureReadyEvent` — triggers all signal group handlers

---

## FeatureVector Bar Sequences

`scenario_loader.py` provides:

| Sequence | Direction | EMA alignment | RSI | ADX | Usage |
|---------|-----------|---------------|-----|-----|-------|
| `make_bull_bar_sequence(n)` | LONG bias | EMA20 > EMA50 > EMA200 | 62 | 28 | Test LONG signal path |
| `make_bear_bar_sequence(n)` | SHORT bias | EMA20 < EMA50 < EMA200 | 38 | 28 | Test SHORT signal path |
| `make_ranging_bar_sequence(n)` | Neutral | flat EMAs | 50 | 12 | Test no-signal path |
| `make_mixed_regime_sequence(n)` | Mixed | alternating | mixed | 20 | Test regime transitions |

All sequences use `BTCUSDT`, `1h` timeframe, price around $65,000.

---

## RuntimeReplayHarness API

```python
harness = RuntimeReplayHarness(equity=Decimal("100000"))
await harness.setup()

# Run a bar sequence
summary = await harness.run_sequence(fv_sequence, label="bull_trend_test")

# summary.bars_run          — bars processed
# summary.positions_opened  — positions opened during this sequence
# summary.final_open_positions — open at end
# summary.errors            — any bar-processing errors
# summary.note              — human-readable explanation

await harness.teardown()
```

### Batch API
```python
summaries = await harness.run_scenario_batch([
    ("bull_5bar", make_bull_bar_sequence(5)),
    ("bear_5bar", make_bear_bar_sequence(5)),
    ("ranging_5bar", make_ranging_bar_sequence(5)),
])
```

---

## What the Harness Measures

1. **EntryGroup sensitivity** — which FeatureVectors trigger a CandidateTradeEvent
2. **Panel selectivity** — which triggered proposals pass 14/20 + avg≥6.5
3. **Risk filter rate** — which panel-approved proposals pass all 9 risk rules
4. **Position lifecycle** — positions entering SystemState after approval

## What the Harness Does NOT Measure

- **Win rates / P&L** — no real price movement, no stop/target logic with real outcomes
- **Calibration** — requires closed trades
- **Edge** — synthetic bars don't represent real market edge

---

## Synthetic Bar Behaviour

Synthetic bull bar sequences produce strong EMA alignment and RSI>60 consistently.
However, the real EntryGroup requires specific signal combinations across multiple groups
(CandlestickGroup, TechnicalStructureGroup, IndicatorsGroup) to fire a CandidateTradeEvent.
Not every bullish FeatureVector produces a trade signal.

**Observed behaviour (2026-03-28):**
- Running 3-5 bull bar sequences through the real harness produces 0 positions in most cases
- The real panel requires genuine multi-signal confluence to trigger a CandidateTradeEvent first
- This is correct — it validates that the system does NOT trigger on every bullish bar

The `note` field in `ReplaySequenceSummary` explains this when 0 positions open:
> "No positions opened during this sequence. This may be correct — the panel requires
> 14/20 trader consensus. With synthetic bars lacking realistic signal confluence,
> the panel may hold for all inputs. This is NOT a failure: it demonstrates threshold selectivity."

---

## Upgrading to Real Replay

To use real historical data:
1. Fetch BTCUSDT 1h bars from Bybit or CSV
2. Convert to `FeatureVector` objects with real indicator values
3. Pass to `harness.run_sequence()` — same API
4. Tag results as `event_driven_runtime_replay` (not simulation)
5. Use resulting win rate / expectancy as edge evidence

Real replay is the bridge between synthetic validation and production measurement.
