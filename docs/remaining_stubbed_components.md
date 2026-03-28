# Remaining Stubbed / Incomplete Components

**Updated:** 2026-03-28

This document is an honest, exhaustive list of every component that is either
entirely stubbed (`raise NotImplementedError`), partially implemented, or known
to be unreachable/non-functional in Phase 3. It is intended to prevent the next
engineer from being surprised by silent failures.

---

## Group Pipeline (Signal Generation Path)

### IndicatorsGroup — `src/groups/indicators/group.py`
**Status:** Partially implemented
- `_setup()`: Subscribes to `FeatureReadyEvent`. IMPLEMENTED.
- `_handle_event()`: Dispatches to `_process_features`. IMPLEMENTED.
- `_process_features(features)`: Partially implemented. Regime classification
  works. EMA crossover detection present. RSI and BB squeeze detection present
  in outline but signal quality scores are hardcoded (0.7, 0.65, etc.) rather
  than dynamically computed from the feature values. Hypothesis refs are static
  strings, not cross-referenced against the live `HYPOTHESIS_REGISTRY`.
- `_emit_bundle()`: IMPLEMENTED — builds `GroupSignalBundle` and publishes
  `GroupSignalEvent`.
- **Risk:** Signals will be generated but with static quality scores. The entry
  group composite score will not accurately reflect signal strength.

### TechnicalStructureGroup — `src/groups/technical_structure/group.py`
**Status:** Partially implemented
- `_detect_levels()`: Swing high/low detection present. Horizontal S/R level
  clustering partially implemented. `at_resistance` / `at_support` flag computation
  uses a 1% threshold proximity check — may need tuning for BTC's volatility.
- `_compute_trend_direction()`: Higher-highs / higher-lows logic implemented but
  uses a simplistic 5-bar lookback. Not validated against known trend periods.
- **Risk:** Structural levels may be noisy. `at_resistance` / `at_support` flags
  will affect EntryGroup composite score (structural_alignment component).

### CandlestickGroup — `src/groups/candlestick/group.py`
**Status:** Partially implemented
- `_detect_patterns()`: Engulfing, Doji, Hammer, Shooting Star, Morning Star,
  Evening Star pattern detection implemented. Three Black Crows partially implemented.
  Inverted Hammer (H2-004) missing — needs Bulkowski's direction (bearish, not bullish).
- Quality scores are not validated against historical outcomes yet (H2-001 through
  H2-005 are UNTESTED in hypothesis registry).
- **Risk:** Pattern detection at structural levels requires `StructuralLevelBundle`
  from TechnicalStructureGroup. If that group's bundle is absent or late, the
  `pattern_at_structure` flag will be False and the signal quality will be understated.

### ChartPatternGroup — `src/groups/chart_pattern/group.py`
**Status:** Mostly stubbed
- State machine framework present (WATCHING → FORMING → CONFIRMED → INVALIDATED).
- H1-001 (H&S Top) state machine: partially implemented, no confirmed test.
- H1-002 (Inverse H&S): stub.
- H1-003 (Double Bottom): stub.
- H1-004 (Descending Triangle): stub.
- H1-005 (Triple Bottom): stub.
- **Risk:** ChartPatternGroup will produce zero confirmed signals in Phase 3.
  The entry group's `chart_pattern_quality` component will be 0.0 for all bars,
  meaning maximum composite score from indicators + candlestick alone is 0.45
  (below the 0.50 threshold). No trades will be proposed unless chart patterns
  are completed.

### EntryGroup — `src/groups/entry/group.py`
**Status:** IMPLEMENTED (Phase 3)
- `_collect_bundle`: Implemented. Accumulates bundles, triggers on indicators bundle.
- `_evaluate_trade_opportunity`: Implemented. Confirmation gate, regime filter,
  composite score, proposal assembly, event publish.
- **Caveat:** Will not fire in practice until at least 2 upstream groups produce
  signals. With ChartPatternGroup stubbed and CandlestickGroup partial, the
  confirmation gate will rarely be met.

### ExitGroup — `src/groups/exit/group.py`
**Status:** Partial
- Stop loss and target hit checks present.
- Time stop implemented (20-bar max hold).
- Trailing stop: NOT implemented (method stub only).
- Position lifecycle integration: NOT wired to `SystemState.open_positions`.
  The group checks if bars breach stop/target but does not update system state
  or emit `PositionCloseEvent` reliably.

### RiskLeverageGroup — `src/groups/risk_leverage/group.py`
**Status:** 9 rules implemented, some non-functional due to missing state
- Rule 1 (daily loss limit): Reads `portfolio.daily_pnl_pct` — works if state updated.
- Rule 2 (max drawdown): Reads `portfolio.drawdown_pct` — works if state updated.
- Rule 3 (portfolio exposure): Reads `portfolio.available` — partially functional.
- Rule 4 (correlated exposure): BTC cluster logic present but simplified.
- Rule 5 (spread check): ATR-based spread proxy. Functional.
- Rule 6 (pump detection): Volume ratio check. Functional.
- Rule 7 (mode gate): `ModeGate.RESEARCH` always blocks execution. Functional.
- Rule 8 (incomplete plan): Checks for zero entry/stop/target. Functional.
- Rule 9 (leverage cap): LeverageGovernor called but not wired to actual order size.
- **Risk:** In Phase 3, Rule 7 (mode gate) will always reject live execution.
  This is correct and intentional. However, if mode gate is elevated without
  completing Phase 4, the other rules may allow unsafe trades.

### NewsGroup / MacroGroup — `src/groups/news_macro/group.py`
**Status:** ALL STUBS
- No live news ingestion. No macro calendar implemented.
- Returns empty bundle with no signals.
- Regime context from this group is always `None`.

### PerformanceJournalGroup — `src/groups/performance_journal/group.py`
**Status:** Partial
- Subscribes to `PositionOpenEvent`, `PositionCloseEvent`, `CandidateTradeEvent`.
- Writes to `JournalDB` (now implemented).
- Edge decay detection: stub (`_check_edge_decay` raises NotImplementedError).
- Performance metric aggregation: returns zeros.

---

## Backtest Engine

### BacktestEngine.run() — `src/backtest/engine.py`
**Status:** Simplified scaffold — NOT full pipeline
- Uses EMA-20/50 crossover signals only (H3-002 baseline strategy).
- Does NOT replay the full group pipeline. Groups require asyncio event loops,
  EventBus subscriptions, and shared state that cannot be easily replicated in
  a synchronous bar-by-bar loop without significant refactoring.
- Position sizing uses simplified 2-ATR stop, 4-ATR target (2:1 R:R).
- No per-hypothesis breakdown (all trades tagged as generic).
- Sharpe ratio not computed (returns 0.0).
- Single symbol only. Multi-symbol portfolio simulation not supported.
- **What this IS useful for:** Validating H3-002 (EMA crossover baseline) and
  confirming that FeatureComputer produces sensible values on real BTC data.
- **What this is NOT:** A production backtest. Do not use for strategy validation
  claims before Phase 4.

### BacktestEngine._replay_bar() — `src/backtest/engine.py`
**Status:** Empty pass
- Exists as a hook for future full-pipeline replay. Not used in Phase 3.

---

## Agents

### HistorianAgent
**Status:** NOT IMPLEMENTED. `EntryGroup._historian = None` (skipped safely).

### CriticAgent
**Status:** NOT IMPLEMENTED. `EntryGroup._critic = None` (skipped safely). LLM
integration deferred to Phase 4.

### ConflictAgent
**Status:** NOT IMPLEMENTED. EntryGroup uses simple direction counting instead of
a formal ConflictAgent. Adequate for Phase 3.

---

## Infrastructure

### WebSocket Real-Time Feed
**Status:** NOT IMPLEMENTED. All data comes from REST API polling.
Bybit WebSocket (`wss://stream.bybit.com/v5/public/linear`) not implemented.
Required for Phase 4 (SHADOW mode with real-time data).

### Order Execution
**Status:** NOT IMPLEMENTED. By design in Phase 3 (RESEARCH mode).
`execution/` directory has placeholder files only.

### LeverageGovernor
**Status:** Class exists, compute method implemented, but NOT wired to the order
sizing path. Leverage cap is computed but not applied to actual `RiskApprovedOrder`.

### Multi-Symbol Universe
**Status:** Only BTCUSDT is hardwired. The full universe filtering (volume thresholds,
spread checks, correlation clustering) is not functional for altcoins in Phase 3.
