# Runtime vs Backtest Mode Matrix

**Date:** 2026-03-28

This document describes the fundamental differences between all validation and
execution modes. Mixing modes in metrics is forbidden by `SourceEnforcer`.

---

## Mode Comparison Matrix

| Dimension | event_driven_runtime_simulation | event_driven_runtime_replay | simplified_backtest | synthetic_control_scenarios | live_exchange_fed_paper |
|-----------|--------------------------------|----------------------------|---------------------|----------------------------|------------------------|
| **Pipeline** | Full 9-group pipeline | Full 9-group pipeline | EMA-crossover only | Full pipeline (forced) | Full pipeline |
| **Bar source** | Synthetic FeatureVectors | Real historical bars | Historical OHLCV | Injected packets | Live Bybit feed |
| **Panel approval** | Real 20 traders (no forcing) | Real 20 traders (no forcing) | No panel | Forced approve | Real 20 traders |
| **Risk rules** | All 9 rules applied | All 9 rules applied | Not applied | Applied | All 9 rules |
| **Exit logic** | Real ExitGroup | Real ExitGroup | Simple stop/target | Real ExitGroup | Real ExitGroup |
| **Forcing** | ❌ None | ❌ None | N/A | ✅ Panel forced | ❌ None |
| **Edge evidence?** | ❌ No | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| **Calibration data?** | ❌ No | ✅ Yes | Limited | ❌ No | ✅ Yes |
| **Current status** | ✅ Available | ⚠️ Requires Bybit bars | N/A | ✅ Available | 🔜 Future |

---

## Signal Logic Differences

### event_driven_runtime (replay and simulation)

Signal flow:
```
FeatureVector
  → IndicatorsGroup (EMA, RSI, BB, ADX)
  → CandlestickGroup (pin bars, engulfing, etc.)
  → TechnicalStructureGroup (S/R levels)
  → EntryGroup (multi-signal aggregation, composite_score)
  → PanelDecisionGroup (20 traders evaluate BTCSetupPacket)
  → FinalDecisionGroup (6 safety rails)
  → RiskLeverageGroup (9 rules, position sizing)
  → ExitGroup (stop/target/trailing)
  → PerformanceJournalGroup (outcome recording)
```

This is the **full production signal chain**. Every component runs on every bar.
Win rates from this mode reflect the actual production decision-making process.

### simplified_backtest

Signal flow:
```
OHLCV data
  → EMA-crossover detection
  → Fixed stop/target rules
  → P&L calculation
```

The simplified backtest does **not** run:
- The 20-trader panel
- FinalDecisionGroup safety rails
- RiskLeverageGroup rules
- EntryGroup composite scoring

Results from `simplified_backtest` cannot be compared to runtime results.
They answer a different question: "Does a pure EMA-crossover rule produce positive expectancy?"
This is useful for benchmarking, not for evaluating the production system.

### synthetic_control_scenarios

Same pipeline as runtime, but with panel approval **forced**. Used for:
- Testing the execution path from PanelApprovedProposalEvent through to PositionOpenEvent
- Verifying position lifecycle mechanics
- Integration testing without requiring signal confluence

Results from `synthetic_control_scenarios` have inflated enter rates (100% by design).
They must never be mixed with real runtime results.

---

## What Each Mode Answers

| Question | Mode |
|----------|------|
| Does the execution path work? | `synthetic_control_scenarios` |
| Does the panel evaluate correctly on these scenarios? | `event_driven_runtime_simulation` |
| Do risk rules fire on bad proposals? | `event_driven_runtime_simulation` |
| What is the system's win rate? | `event_driven_runtime_replay` or `live_exchange_fed_paper` |
| Does the full pipeline produce positive expectancy? | `event_driven_runtime_replay` (minimum 30 trades) |
| How are individual traders calibrated? | `event_driven_runtime_replay` (minimum 30 trades per trader) |
| What does the EMA-crossover baseline look like? | `simplified_backtest` |

---

## Mixing Violations Detected By SourceEnforcer

```python
# ❌ ILLEGAL: Runtime win rate + backtest win rate
results = runtime_wins + backtest_wins  # SourceSeparationError

# ❌ ILLEGAL: Treating synthetic enter rate as edge evidence
assert simulation_enter_rate > 0.30  # not meaningful

# ❌ ILLEGAL: Mixing forced-approval (synthetic_control) with real panel runs
combined = forced_records + real_records  # SourceSeparationError

# ✅ LEGAL: Compute simulation metrics on simulation results only
simulation_enter_rate = sum(1 for r in simulation_records if r.decision == "enter") / n

# ✅ LEGAL: Compute edge metrics on replay results only
replay_win_rate = win_rate([r.outcome for r in replay_records])
```

---

## Current Validation Mode Status

| Mode | Status | Data Available |
|------|--------|----------------|
| `event_driven_runtime_simulation` | ✅ Active | 10 scenario evaluations |
| `synthetic_control_scenarios` | ✅ Active | Used in test suite (forced approval tests) |
| `event_driven_runtime_replay` | ⚠️ Requires Bybit data | 0 bars replayed |
| `simplified_backtest` | Not implemented in Phase 5 | N/A |
| `live_exchange_fed_paper` | 🔜 Future phase | 0 live trades |

The system is ready for real replay. Bybit connectivity (HTTP 404 in current dev environment
due to IP restriction) is the only blocker for obtaining real historical bar data.
