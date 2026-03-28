# BTC/Bybit Vertical Slice — Phase 3 Status

**As of:** 2026-03-28
**Mode:** RESEARCH only (no order execution)
**Symbol:** BTCUSDT on Bybit V5 REST API

---

## Phase 3 Goal

Deliver the first working end-to-end BTC/Bybit paper trading slice: a system that
can fetch real market data from Bybit, compute technical features, detect signals,
assemble a trade proposal, and log everything to an audit-quality SQLite database —
all without executing any real orders.

Phase 3 is a vertical slice: it proves the data plumbing works and the signal logic
is wired. It is explicitly NOT production-ready. Trade execution, order management,
live WebSocket feeds, and position lifecycle are all deferred to Phase 4.

---

## What IS Implemented (Working Code)

### Data Layer
- **BybitAdapter** (`src/data/bybit.py`): Full Bybit V5 REST implementation. Fetches
  OHLCV bars from `/v5/market/klines`, handles pagination, converts timestamps from
  Bybit's millisecond epoch format, validates OHLCV invariants on construction.
  Supports 1h / 4h / 1d timeframes. No API key required (public endpoint).

### Feature Computation
- **FeatureComputer** (`src/features/compute.py`): All 11 indicator methods fully
  implemented. Outputs a complete `FeatureVector` after 200-bar warmup. Computes:
  ATR14 (Wilder), ATR14 SMA-20, EMA-20/50/200 (exponential), prev-bar EMA values,
  RSI-14 (Wilder), Bollinger Bands (20-period, 2σ), BB width percentile rank
  (100-bar lookback), ADX-14, volume SMA-20 and ratio, candle anatomy (body/shadow
  ratios), impulse flag, doji flag. All pure functions — no state, no I/O.

### Storage
- **JournalDB** (`src/journal/db.py`): Real SQLite implementation. Three tables:
  `trades`, `signals`, `journal_events`. WAL mode enabled. All DDL present and
  creates tables on first run. Methods: `insert_trade_open`, `update_trade_close`,
  `insert_signal`, `insert_journal_event`, `query_hypothesis_trades`,
  `query_recent_outcomes`. Append-only contract enforced (single UPDATE exception
  for trade close).

### Risk Sizing
- **ATRStopPlacer** (`src/risk/stop_placer.py`): Computes ATR-scaled stop levels
  with round-number protection. Implemented.
- **RMultipleSizer** (`src/risk/sizer.py`): Computes position size in base units
  given risk fraction, account equity, and stop distance. Real R-multiple math.

### Signal Evaluation
- **20 trader evaluators** (`src/traders/`): All 20 evaluators implemented with
  scoring logic based on configurable criteria per evaluator persona.
- **FinalDecisionGroup** (`src/decision/`): Aggregates panel results into
  enter/hold/skip decision. Implemented.
- **EntryGroup** (`src/groups/entry/group.py`): `_collect_bundle` and
  `_evaluate_trade_opportunity` fully implemented with confirmation gate (>= 2
  signals), direction voting, regime filter (bear macro blocks LONG), composite
  score formula, and CandidateTradeProposal assembly.

### Backtesting
- **BacktestEngine** (`src/backtest/engine.py`): Simplified bar-by-bar backtest.
  Uses FeatureComputer, detects EMA-20/50 crossovers (H3-002 baseline), manages
  one open position (stop/target/time-stop exits), tracks equity curve and max
  drawdown.

### Entrypoint
- **main_btc.py** (`src/main_btc.py`): Runnable script. Fetches bars from Bybit,
  computes features, logs regime and signals. Supports `--backtest` mode, timeframe
  selection, bar count, date range.

---

## What IS STUBBED (Be Honest)

- **Most group signal detection internals**: `IndicatorsGroup._process_features`,
  `TechnicalStructureGroup._detect_levels`, `CandlestickGroup._detect_patterns`,
  `ChartPatternGroup._update_state_machines` are all partially or fully stubbed with
  `NotImplementedError`. Signal bundles do not flow automatically in the live runtime.
- **RiskLeverageGroup**: 9 rules are defined but several rely on `SystemState` fields
  that are not populated in Phase 3 (e.g., `daily_pnl_pct` requires real position
  lifecycle).
- **NewsGroup / MacroGroup**: All stubs. No live news ingestion.
- **ExitGroup**: Partial. Stop/target checks defined but not fully wired to position
  lifecycle.
- **LeverageGovernor**: Not wired to execution path.
- **WebSocket real-time feed**: Not implemented. Phase 3 is REST polling only.
- **Live order execution**: By design — RESEARCH mode only. No orders placed.
- **BacktestEngine full pipeline**: Only EMA crossover (H3-002). Full group pipeline
  backtest requires Phase 4.

---

## Runnable Commands

```bash
cd /Users/arigabay/Code/new-b/src

# Live analysis (last 500 1h bars)
python main_btc.py

# 4-hour timeframe analysis
python main_btc.py --timeframe 4h

# Quick 300-bar fetch
python main_btc.py --bars 300

# Backtest: EMA crossover on BTC 2024 H1
python main_btc.py --backtest

# Backtest with custom dates
python main_btc.py --backtest --start 2024-03-01 --end 2024-09-01

# Debug logging
LOG_LEVEL=DEBUG python main_btc.py
```

---

## NOT Production Ready

This system is in RESEARCH mode only. It:
- Logs proposed trades but does not execute them
- Has no real-time price feed (REST polling only)
- Does not manage positions or account state
- Has not been validated against holdout data
- Has not been reviewed for edge cases in extreme market conditions

Promotion to SHADOW (paper trading with real-time data) and LIVE requires
completing Phase 4 deliverables. See `PHASE_3_BTC_BYBIT_RUNTIME_HANDOFF.md`.
