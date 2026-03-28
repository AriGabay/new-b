# Replay vs Simulation vs Backtest — Mode Comparison Matrix

**Phase:** 5.5
**Updated from:** runtime_vs_backtest_mode_matrix.md (Phase 5)

---

## Full Mode Comparison

| Property | event_driven_runtime_replay | event_driven_runtime_simulation | simplified_backtest | synthetic_control_scenarios | live_exchange_fed_paper |
|----------|----------------------------|--------------------------------|--------------------|-----------------------------|------------------------|
| **Source tag** | event_driven_runtime_replay | event_driven_runtime_simulation | simplified_backtest | synthetic_control_scenarios | live_exchange_fed_paper |
| **Input source** | Deterministic fixture bars (OHLCV) | Synthetic FeatureVector sequences | Historical OHLCV + lookup | Hand-crafted BTCSetupPackets | Live Bybit WebSocket feed |
| **Indicator computation** | Real: EMA/RSI/ATR/ADX/BB from prices | Constant offsets on price | Depends on backtest engine | Manual field values | Real-time from exchange bars |
| **EMA crossover fidelity** | Real crossovers occur at correct bars | Crossovers forced/simulated | Depends on engine | Manual field | Real crossovers from live data |
| **Pipeline used** | Full BtcBybitPaperRunner | Full BtcBybitPaperRunner | Separate backtester | Direct panel/risk component calls | Full BtcBybitPaperRunner |
| **EntryGroup fires?** | No (ceiling 0.4875 in Phase 3) | No (same ceiling) | N/A | No (panel called directly) | Unknown — untested |
| **Panel evaluated?** | No (EntryGroup never fires) | No | No | Yes (directly) | Unknown |
| **Risk gates evaluated?** | No | No | Depends | Yes (directly) | Unknown |
| **Positions opened?** | No (0 in Phase 5.5) | No | Depends | No (scenarios only) | Unknown |
| **Positions closed?** | No | No | Depends | No | Unknown |
| **Lifecycle tracking?** | Yes (harness subscribes to events) | Partial | No | No | Would use same harness |
| **In EDGE_EVIDENCE_SOURCES** | YES | YES | NO | NO | YES |
| **Suitable for calibration** | YES (if trades close) | YES (if trades close) | NO | NO | YES |
| **Can mix with other runtime?** | Yes (both RUNTIME_SOURCES) | Yes (both RUNTIME_SOURCES) | NO | NO | Yes (RUNTIME_SOURCES) |
| **Deterministic?** | YES (fixed seed) | YES (fixed synthetic bars) | Depends on engine | YES | NO (live market) |
| **Current status** | Active (Phase 5.5) | Active (Phase 5) | Not implemented | Active (Phase 5) | Blocked (HTTP 404 in dev) |

---

## Lifecycle Control Comparison

| Property | event_driven_runtime_replay_lifecycle_assist | Other modes |
|----------|---------------------------------------------|-------------|
| Source tag | event_driven_runtime_replay_lifecycle_assist | (as above) |
| In EDGE_EVIDENCE_SOURCES | NO | (varies) |
| What it tests | Open/close mechanics, panel selectivity | (varies) |
| Entry injection | One CandidateTradeEvent injected (panel evaluates normally) | N/A |
| Suitable for win rate | NO | (varies) |

---

## Key Distinction: Replay vs Simulation

Both `event_driven_runtime_replay` and `event_driven_runtime_simulation` use the full
`BtcBybitPaperRunner`. The difference is in how bars are constructed:

**Simulation** (`RuntimeReplayHarness` from Phase 5):
```python
# Bars built from FeatureVector sequences with constant indicator offsets
fv = FeatureVector(
    close=Decimal("65000"),
    ema20=Decimal("64800"),   # manually set: close - 200
    ema50=Decimal("64500"),   # manually set: close - 500
    rsi14=55.0,               # manually set: fixed value
    ...
)
```

**Replay** (`TrueReplayHarness` from Phase 5.5):
```python
# Bars computed from real OHLCV series using indicator_engine.py
closes = [price_series]
ema20 = compute_ema(closes, 20)   # real formula, seeds from SMA
rsi14 = compute_rsi(closes, 14)   # Wilder smoothing
adx14 = compute_adx(highs, lows, closes, 14)  # DM+ / DX / ADX chain
```

**Why this matters**: In simulation, EMA crossovers can be forced by setting
`prev_ema20 < prev_ema50` and `ema20 > ema50` in the same bar's fields.
In replay, crossovers emerge from actual EMA computation — they occur only when
the price series produces a genuine crossing.

---

## Why All Modes Show Zero Natural Entries

The structural barrier applies equally to all pipeline-based modes:

```
composite_score_ceiling = 0.4875
entry_threshold = 0.50
shortfall = 0.0125
```

This ceiling applies regardless of how bars are constructed, because it is a function
of which signal groups are implemented — not what the indicators show.

The panel's 30% enter rate in Phase 5 (synthetic_control) is irrelevant to this question:
those scenarios used pre-computed BTCSetupPackets that bypass EntryGroup entirely.

---

## Path to Non-Zero Natural Entries (Any Mode)

| Option | Mode | What Changes |
|--------|------|--------------|
| Implement ChartPatternGroup | Any pipeline mode | composite_score += 0.35 × chart_quality |
| Lower COMPOSITE_SCORE_THRESHOLD | Any pipeline mode | Threshold change, not signal change |
| Feed live Bybit data | live_exchange_fed_paper | May get real chart patterns from live bars |
| Use pre-built BTCSetupPackets | synthetic_control | Bypass EntryGroup — not edge evidence |

---

## Source Separation Summary

```
CANNOT MIX:
  replay    + backtest            → SourceSeparationError
  replay    + synthetic_control   → SourceSeparationError
  simulation + backtest           → SourceSeparationError
  any       + unknown_source      → SourceSeparationError

CAN MIX (both RUNTIME_SOURCES):
  replay + simulation             → OK (different fixture provenance)

SEPARATED AUTOMATICALLY:
  lifecycle_assist ∉ EDGE_EVIDENCE_SOURCES → can never pollute edge claims
```
