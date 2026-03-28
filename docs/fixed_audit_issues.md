# Audit Issue Fix Status

**Source audit:** `implementation_coverage_audit.md`
**Updated:** 2026-03-28

This document tracks all P0/P1/P2 issues identified in the Phase 2 coverage audit
and their current fix status after Phase 3 implementation work.

---

## P0 Issues (System Cannot Start / Always Throws)

### FIXED

**JournalDB._create_tables() — was `raise NotImplementedError`**
- File: `src/journal/db.py`
- Fix: Full SQL DDL implemented. Three tables (`trades`, `signals`, `journal_events`)
  with correct column types, PRIMARY KEYs, and DEFAULT values. WAL mode enabled.
  `insert_trade_open`, `update_trade_close`, `insert_signal`, `insert_journal_event`
  all implemented with real SQL. Table creation is idempotent (`IF NOT EXISTS`).

**BybitAdapter — was a placeholder referencing Binance**
- File: `src/data/bybit.py`
- Fix: Full Bybit V5 REST implementation. Endpoint: `/v5/market/klines`. Correct
  parameter names (`category=linear`, `symbol`, `interval`, `limit`, `end`).
  Response parsing handles Bybit's nested `result.list` array format. Timestamps
  converted from milliseconds. OHLCV invariants validated at construction. Teardown
  closes the httpx.AsyncClient properly.

**RMultipleSizer.compute() — was `raise NotImplementedError`**
- File: `src/risk/sizer.py`
- Fix: Real R-multiple math. `position_size_base = risk_amount / stop_distance_base`.
  Handles both LONG and SHORT correctly. Returns `PositionSizeResult` with base
  units, USD value, and R-amount. Validates that stop distance > 0.

**ATRStopPlacer.compute() — was `raise NotImplementedError`**
- File: `src/risk/stop_placer.py`
- Fix: ATR-scaled stops with round-number avoidance. For LONG: stop = entry - (atr_multiplier * atr14); for SHORT: stop = entry + (atr_multiplier * atr14). Rounds away from entry to avoid getting stopped at obvious levels. Returns `StopResult`.

### P0 STILL BROKEN

**EntryGroup._collect_bundle / _evaluate_trade_opportunity — previously full stubs**
- Status: NOW IMPLEMENTED in Phase 3.
- Caveat: The group receives bundles via EventBus only when upstream groups
  (`IndicatorsGroup`, `CandlestickGroup`, etc.) publish `GroupSignalEvent`. Those
  upstream groups still have stubbed signal detection internals, so the end-to-end
  live pipeline does not fire automatically. The EntryGroup code is complete and
  correct; it simply has no upstream signal sources yet.

**Most group signal detection methods — `NotImplementedError`**
- File: `src/groups/indicators/group.py`, `src/groups/candlestick/group.py`,
  `src/groups/technical_structure/group.py`, `src/groups/chart_pattern/group.py`
- Status: STILL BROKEN (partially implemented in some groups, fully stubbed in others)
- Impact: Live group pipeline does not produce signals. Backtest uses FeatureComputer
  directly and bypasses groups entirely.

**No live order execution**
- Status: BY DESIGN — RESEARCH mode only. Will remain broken until Phase 4.

---

## P1 Issues (Core Logic Incorrect / Misleading Output)

### FIXED

**RegimeContext was not computed from real features**
- File: `src/groups/indicators/group.py` (`_compute_regime`)
- Fix: `IndicatorsGroup._compute_regime` now computes macro classification from
  real FeatureVector values: bull if close > EMA200 and ADX > 20; bear if close
  < EMA200; ranging otherwise. Volatility regime from ATR/SMA20 ratio.
  `main_btc.py` also computes regime inline for the analysis output.

**BTC was not in eligible_symbols — analysis pipeline silently skipped**
- File: `src/groups/market_data/group.py`
- Fix: `MarketDataGroup` hardwires `BTCUSDT` into `eligible_symbols` on startup
  and never filters it out. The universe update logic preserves BTC unconditionally.

**FeatureVector missing `prev_ema20` / `prev_ema50` fields**
- File: `src/features/compute.py` and `src/core/schemas.py`
- Fix: `FeatureVector` dataclass has `prev_ema20` and `prev_ema50` fields.
  `FeatureComputer._ema()` returns `(current_ema, prev_ema)` tuple. Used by
  `BacktestEngine` for crossover detection.

---

## P2 Issues (Feature Missing / Incomplete)

### FIXED

**20 trader evaluators — all returned 0.5 unconditionally**
- File: `src/traders/`
- Fix: All 20 evaluators implemented with real scoring logic based on evaluator
  persona and configurable signal criteria.

**FinalDecisionGroup — was a stub**
- File: `src/decision/`
- Fix: Implemented. Aggregates panel votes, applies quorum threshold, outputs
  `FinalDecision(enter/hold/skip)` with reasoning.

**BacktestEngine.run() — was `raise NotImplementedError`**
- File: `src/backtest/engine.py`
- Fix: Simplified bar-by-bar implementation. Not full-pipeline, but functional
  for H3-002 (EMA crossover) validation. See `remaining_stubbed_components.md`.

**main_btc.py — did not exist**
- Fix: Created. Full runnable entrypoint with analysis and backtest modes.

### P2 STILL OPEN

**Sharpe ratio not computed** — `BacktestResult.sharpe_ratio` remains `0.0`.
Requires a returns series. Deferred to Phase 4.

**Per-hypothesis backtest breakdown** — `BacktestResult.per_hypothesis` always
empty dict. Requires full group pipeline wiring to tag trades with hypothesis IDs.

**WebSocket real-time feed** — No streaming data. Phase 4 deliverable.

**CriticAgent / HistorianAgent not implemented** — EntryGroup has injection hooks
for both but neither agent is implemented. They are set to `None` and skipped.
