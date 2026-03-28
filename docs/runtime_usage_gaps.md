# Runtime Usage Gaps

## Date: 2026-03-28
## Purpose: Identify every break in the end-to-end runtime execution path

This document traces the actual runtime call graph from system startup through trade execution and journal persistence. At each step, it identifies exactly where execution breaks and why.

---

## How to Read This Document

Each section represents one runtime "lane" (data flow path). Under each lane, the call chain is shown with explicit status at each node. `→` means "calls". `⛔` means execution stops here.

---

## Lane 1: System Startup

```
python src/main.py
  → configure_logging()              ✅ WORKS
  → load_config()                    ✅ WORKS (env vars parsed)
  → reset_bus()                      ✅ WORKS
  → get_bus()                        ✅ WORKS
  → SystemState.__init__()           ✅ WORKS
  → FeatureStore.__init__()          ✅ WORKS (creates directory)
  → MarketDataGroup.__init__()       ✅ WORKS
  → MarketDataGroup.setup()
      → _setup()                     ✅ WORKS (logs initialization, no subscriptions)
  → PerformanceJournalGroup.setup()
      → _setup()
          → bus.subscribe(×6)        ✅ WORKS
          → _initialize_db()         ⛔ RAISES NotImplementedError
                                     (silently caught by BaseGroup.handle_event)
  → [remaining 8 groups setup...]    ✅ WORKS (subscription wiring only)
  → run_system() main loop           ⛔ RAISES NotImplementedError immediately
```

**Gap 1:** `PerformanceJournalGroup._initialize_db()` raises at startup. The exception is caught and logged by `BaseGroup.handle_event()`, but this means the DB is never initialized. All subsequent journal calls will also raise or fail.

**Gap 2:** The main loop in `run_system()` raises `NotImplementedError`. The system initializes groups and then immediately stops.

**Result: The system cannot start in any operational mode.**

---

## Lane 2: OHLCV Data Ingestion

```
Polling loop (not implemented)
  → BinanceAdapter.fetch_bars()      ⛔ STUB — NotImplementedError
  → BinanceAdapter._normalize_kline() ⛔ STUB
  → FeatureStore.append_bar()        ⛔ STUB — NotImplementedError
  → MarketDataGroup.ingest_bar()     ⛔ STUB — NotImplementedError
      → _compute_features()          ⛔ STUB
          → FeatureComputer.compute() ⛔ STUB (7 of 8 methods are stubs)
      → bus.publish(BarCloseEvent)   [never reached]
      → bus.publish(FeatureReadyEvent) [never reached]
```

**Gap 3:** `BinanceAdapter.fetch_bars()` is a stub. No data enters the system.

**Gap 4:** `FeatureComputer.compute()` cannot produce a `FeatureVector` because `_true_range`, `_atr_wilder`, `_ema`, `_rsi_wilder`, `_bollinger_bands`, `_bb_width_percentile`, and `_adx` are all stubs.

**Gap 5:** `impulse_flag` and `doji_flag` are declared as fields in `FeatureVector` but no logic populates them. They would always be default values.

**Result: No OHLCV bar ever enters the system. The EventBus never fires BarCloseEvent or FeatureReadyEvent.**

---

## Lane 3: Feature Distribution & Universe Refresh

```
MarketDataGroup.refresh_universe()   ⛔ STUB — NotImplementedError
  → [eligible_symbols never updated]
  → bus.publish(UniverseUpdateEvent) [never reached]
  → state.update_universe()          [never reached]
```

**Gap 6:** `eligible_symbols` in `SystemState` is always an empty set. This has a downstream consequence: `RiskLeverageGroup._check_liquidity()` always returns `RejectionCode.UNIVERSE_FILTER` for every symbol, because no symbol is ever added to the eligible set.

**Gap 7:** Volume-based universe filtering ($10M/day minimum) is documented in `MarketDataConfig.min_volume_usd` but never executed.

**Result: Even if data arrived, every trade proposal would be rejected by Rule 6 (empty universe).**

---

## Lane 4: Technical Structure Computation

```
FeatureReadyEvent fires (never fires — see Lane 2)
  → TechnicalStructureGroup._handle_event()   ✅ dispatch works
      → _process_features(features)           ⛔ STUB — NotImplementedError
          → _detect_swing_high()              ⛔ STUB
          → _detect_swing_low()               ⛔ STUB
          → _merge_pivot_into_levels()        ⛔ STUB
          → _build_bundle() → StructuralLevelBundle  ⛔ STUB
          → bus.publish(GroupSignalEvent)     [never reached]
```

**Gap 8:** No `StructuralLevelBundle` is ever produced. This breaks CandlestickGroup (which requires structural context) and indirectly breaks ChartPatternGroup (H&S and Double Bottom need neckline detection which relies on S/R levels).

**Gap 9:** There is no explicit mechanism for `TechnicalStructureGroup` to publish its bundle to `CandlestickGroup._structural_cache`. Even if TechnicalStructureGroup published a `GroupSignalEvent`, CandlestickGroup subscribes to `FeatureReadyEvent`, not `GroupSignalEvent`. The inter-group data flow for structural context is **not wired**.

**Result: No structural levels are ever computed. CandlestickGroup will never have structural context.**

---

## Lane 5: Indicator Signal Generation

```
FeatureReadyEvent fires (never fires — see Lane 2)
  → IndicatorsGroup._handle_event()           ✅ dispatch works
      → _process_features(features)           ⛔ STUB — NotImplementedError
          → _detect_ema_crossover()           ⛔ STUB (H3-002)
          → _detect_rsi_divergence()          ⛔ STUB (H3-001)
          → _detect_bb_squeeze_breakout()     ⛔ STUB (H3-004)
          → _compute_regime()                 ⛔ STUB
          → state.update_regime()             [never reached]
          → bus.publish(GroupSignalEvent)     [never reached]
```

**Gap 10:** `RegimeContext` in `SystemState` is never updated. It was initialized to `btc_macro="unknown"` and stays there forever. This means:
- EntryGroup would block all longs (if it ran) because `btc_macro` is not "bull" or "bear"
- IndicatorsGroup cannot apply regime filters to signals

**Gap 11:** H3-003 (ATR vs fixed stop Sharpe comparison) has no implementation path in IndicatorsGroup. It is a meta-hypothesis that should be evaluated in the backtest engine, but no backtest method exists for comparing stop strategies.

**Result: No indicator signals are ever produced. The regime is permanently "unknown".**

---

## Lane 6: Candlestick Signal Generation

```
FeatureReadyEvent fires (never fires — see Lane 2)
  → CandlestickGroup._handle_event()          ✅ dispatch works
      → _process_features(features)           ⛔ STUB — NotImplementedError
          → _detect_engulfing()               ⛔ STUB (H2-001)
          → _detect_morning_evening_star()    ⛔ STUB (H2-002)
          → _detect_three_black_crows()       ⛔ STUB (H2-003)
          → _detect_inverted_hammer()         ⛔ STUB (H2-004)
          → _detect_doji()                    ⛔ STUB (H2-005)
```

**Gap 12:** `_structural_cache` in CandlestickGroup is always empty. No mechanism populates it (see Lane 4, Gap 9).

**Gap 13:** H2-004 (Inverted Hammer as bearish signal) has no test to verify the correct implementation of the Bulkowski inversion. If implemented naively (standard textbook direction = bullish), it would produce the wrong direction signal.

**Result: No candlestick signals are ever produced.**

---

## Lane 7: Chart Pattern Signal Generation

```
FeatureReadyEvent fires (never fires — see Lane 2)
  → ChartPatternGroup._handle_event()         ✅ dispatch works
      → _process_features(features)           ⛔ STUB — NotImplementedError
          → _initialize_machines_for_symbol() ✅ works (creates machine objects)
          → machine.advance(features)         ⛔ STUB — NotImplementedError (all 4 machines)
          → _signal_from_machine()            ⛔ STUB
          → bus.publish(GroupSignalEvent)     [never reached]
```

**Gap 14:** `HeadAndShouldersMachine.advance()` is a stub, but even if implemented, it would need neckline detection which requires structural level data (from TechnicalStructureGroup). That data is not available (see Lane 4, Gap 9).

**Gap 15:** H1-006 through H1-009 have no state machine classes. If ChartPatternGroup.PATTERN_MACHINES were extended to include them, it would immediately fail because the classes do not exist.

**Result: No chart pattern signals are ever produced.**

---

## Lane 8: Entry Signal Aggregation

```
GroupSignalEvent fires (never fires — see Lanes 5, 6, 7)
  → EntryGroup._handle_event()                ✅ dispatch works
      → _collect_bundle(bundle)               ⛔ STUB — NotImplementedError
          → _pending_bundles[symbol][...]     [never populated]
          → _evaluate_trade_opportunity()     ⛔ STUB
              → _compute_composite_score()    ⛔ STUB
              → _historian.query()            ⛔ _historian is None
              → _critic.critique()            ⛔ _critic is None
              → _build_proposal()             ⛔ STUB
              → bus.publish(CandidateTradeEvent) [never reached]
```

**Gap 16:** Even if all upstream signals arrived, `self._historian` and `self._critic` are `None`. There is no dependency injection mechanism — no factory method, no startup hook that creates concrete HistorianAgent/CriticAgent instances and assigns them to these fields.

**Gap 17:** The bundle collection mechanism has no flush timeout implementation. The docstring mentions "50ms timeout-based flush," but this timer is not implemented. Without it, bundles that arrive individually would never trigger evaluation unless all expected groups report.

**Gap 18:** The confirmation gate requires ≥2 groups but also requires "at least 1 chart pattern or candlestick." This second condition is documented in the docstring but no code enforces it. If implemented naively, an all-indicator signal could pass the gate.

**Result: No trade proposals are ever produced.**

---

## Lane 9: Risk Evaluation

```
CandidateTradeEvent fires (never fires — see Lane 8)
  → RiskLeverageGroup._handle_event()         ✅ dispatch works
      → _evaluate_proposal(proposal)          ✅ WORKS (orchestration)
          → _check_mode_gate()                ✅ WORKS — RESEARCH mode blocks here
          → _check_daily_loss_limit()         ✅ WORKS — checks portfolio.daily_pnl_pct
          → _check_max_drawdown()             ✅ WORKS — checks portfolio.drawdown_pct
          → _check_portfolio_exposure()       ⛔ STUB — NotImplementedError
          → _check_correlated_exposure()      ⛔ STUB — NotImplementedError
          → _check_liquidity()               ✅ WORKS — but always rejects (empty universe)
          → _check_pump_signal()              ⛔ STUB — NotImplementedError
          → _check_event_risk()               ⛔ STUB — NotImplementedError
          → _check_plan_completeness()        ✅ WORKS — validates fields
          → _compute_order()                  ⛔ STUB — NotImplementedError
          → _approve()                        ⛔ STUB — NotImplementedError
          → _reject() [on failure]            ✅ WORKS — publishes RiskRejectedEvent
```

**Gap 19:** In RESEARCH mode, `_check_mode_gate()` rejects every proposal. This is correct for RESEARCH mode but means Rules 4-9 are **never even reached** during any current execution. Bugs in Rules 4-9 would not be discovered through running the system in RESEARCH mode.

**Gap 20:** `LeverageGovernor.check()` is implemented in `src/risk/checks.py` but is **not imported or called** in `RiskLeverageGroup`. It exists in isolation. This is a dead code path.

**Gap 21:** `DrawdownController.get_size_reduction()` is implemented but its output is never used — it is not called in `_evaluate_proposal()`. The `RiskState.size_reduction` field exists but is never set by the drawdown controller.

**Gap 22:** `_check_event_risk()` returns a `size_reduction` multiplier that is passed to `_compute_order()`. Since `_compute_order()` is a stub, this multiplier is computed (when implemented) but never applied. The chain is designed correctly but both ends are stubs.

**Result: In RESEARCH mode, every proposal is rejected at Rule 1 (correctly). No position is ever opened. Rules 4-9 are effectively dead code paths during current development.**

---

## Lane 10: Position Exit

```
FeatureReadyEvent fires (never fires — see Lane 2)
  → ExitGroup._handle_event()                 ✅ dispatch works
      → _check_exits(features)
          → iterates state.portfolio.open_positions  ✅ WORKS (empty dict)
          → _evaluate_position(position, features)   ⛔ STUB (if any positions existed)
              → _check_stop_loss()            ⛔ STUB
              → _check_target()               ⛔ STUB
              → _check_trailing_stop()        ⛔ STUB
              → _update_trailing_stop()       ⛔ STUB
              → _compute_pnl()               ⛔ STUB
          → _execute_exit()                   ⛔ STUB
              → state.close_position()        ✅ WORKS (if called)
              → bus.publish(PositionCloseEvent) ✅ WORKS (if called)
```

**Gap 23:** `state.close_position()` is fully implemented and correctly updates equity, drawdown, and consecutive losses. But it is never called because `_execute_exit()` is a stub.

**Gap 24:** There is no trailing stop state persistence. The `_update_trailing_stop()` method is supposed to update `position.trailing_stop_price`, but `Position.trailing_stop_price` is an `Optional[Decimal]` with no automatic persistence between bar closes. The ExitGroup would need to maintain a separate trailing stop cache or update the position object in SystemState.

**Result: No positions ever exit. If a position were somehow opened, it would stay open forever.**

---

## Lane 11: Journal Persistence

```
Any event fires → PerformanceJournalGroup._handle_event()  ✅ dispatch works
  → _log_signal_event()                       ⛔ STUB — NotImplementedError
  → _log_candidate_trade()                    ⛔ STUB
  → _log_risk_decision()                      ⛔ STUB
  → _log_position_open()                      ⛔ STUB
  → _log_position_close()                     ⛔ STUB
  → _log_system_alert()                       ⛔ STUB

JournalDB.initialize()                        ✅ WORKS (opens connection)
  → _create_tables()                          ⛔ STUB — NotImplementedError
```

**Gap 25:** The `JournalDB._create_tables()` stub means no SQLite tables ever exist. All `insert_trade_open()`, `update_trade_close()`, etc. calls would fail with `sqlite3.OperationalError: no such table`.

**Gap 26:** All `_log_*()` methods are stubs, so even if the DB were initialized, no events would be recorded.

**Gap 27:** `query_historical_analogs()` is a stub, so `HistorianAgent` cannot retrieve trade history even if it existed.

**Result: Zero events are ever persisted. The journal is permanently empty.**

---

## Lane 12: Learning & Decay Detection

```
Position closes → _log_position_close()       ⛔ STUB (never fires)
  → _check_edge_decay()                       ⛔ STUB
  → _check_hypothesis_validation()            ⛔ STUB
      → HYPOTHESIS_REGISTRY[id].status = ... [mutation never happens]
  → _run_weekly_summary()                     ⛔ STUB (SummarizerAgent is None)
```

**Gap 28:** There is no mechanism to mutate `HYPOTHESIS_REGISTRY[id].status`. The registry is a module-level dict; changing a HypothesisEntry's status field would work in Python (dataclass is mutable), but no code path does this. Hypothesis status is permanently `UNTESTED` for all 25 hypotheses.

**Gap 29:** `SummarizerAgent` is declared as `self._summarizer = None` in PerformanceJournalGroup, with no injection mechanism.

**Result: Hypothesis statuses never change. No learning report is ever produced.**

---

## Lane 13: Backtest

```
BacktestEngine.run(bars)                      ⛔ STUB — NotImplementedError
  → HoldoutManager.assert_training_access()   ✅ WORKS
  → _replay_bar()                             ⛔ STUB
  → _apply_commission_and_slippage()          ⛔ STUB
  → PerformanceMetrics.compute()              ⛔ STUB
```

**Gap 30:** `BacktestEngine.run()` never executes. In-sample validation for any of the 25 hypotheses is impossible.

**Gap 31:** Even if the backtest engine ran, it uses the same group classes as the live system — which are all stubs. There is no mock or lightweight alternative for backtesting.

**Result: No in-sample or OOS validation is possible. Gate 1 can never be passed. No hypothesis can progress from UNTESTED.**

---

## Summary Table: All Runtime Gaps

| Gap # | Severity | Location | Gap Description |
|-------|----------|----------|----------------|
| 1 | P0 | PerformanceJournalGroup._setup() | _initialize_db() raises at startup |
| 2 | P0 | main.py::run_system() | Main loop raises NotImplementedError |
| 3 | P0 | BinanceAdapter.fetch_bars() | No data source |
| 4 | P0 | FeatureComputer.compute() | 7/8 indicator methods are stubs |
| 5 | P1 | FeatureVector | impulse_flag and doji_flag never populated |
| 6 | P1 | MarketDataGroup.refresh_universe() | eligible_symbols always empty |
| 7 | P1 | MarketDataGroup.refresh_universe() | Volume filter ($10M) never applied |
| 8 | P1 | TechnicalStructureGroup._process_features() | No StructuralLevelBundle produced |
| 9 | P1 | CandlestickGroup / TechnicalStructureGroup | Inter-group structural data flow not wired |
| 10 | P1 | IndicatorsGroup._process_features() | RegimeContext never updated; stays "unknown" |
| 11 | P1 | IndicatorsGroup | H3-003 has no implementation path in any group |
| 12 | P1 | CandlestickGroup._structural_cache | Never populated; structural-dependent patterns cannot function |
| 13 | P2 | CandlestickGroup._detect_inverted_hammer() | No test to prevent bullish-direction bug |
| 14 | P1 | HeadAndShouldersMachine.advance() | Requires structural levels (not available) |
| 15 | P2 | ChartPatternGroup.PATTERN_MACHINES | H1-006 through H1-009 have no state machine classes |
| 16 | P1 | EntryGroup | _historian and _critic are permanently None |
| 17 | P1 | EntryGroup._collect_bundle() | Bundle flush timeout not implemented |
| 18 | P2 | EntryGroup | Confirmation gate "≥1 chart/candle" not enforced |
| 19 | P2 | RiskLeverageGroup | RESEARCH mode rejects at Rule 1; Rules 4-9 unreachable |
| 20 | P2 | LeverageGovernor | Implemented but not wired into RiskLeverageGroup |
| 21 | P2 | DrawdownController | Implemented but not wired into RiskLeverageGroup |
| 22 | P2 | RiskLeverageGroup._check_event_risk() | Return value passed to stub; never applied |
| 23 | P1 | ExitGroup._execute_exit() | state.close_position() implemented but never called |
| 24 | P2 | ExitGroup._update_trailing_stop() | No trailing stop state persistence mechanism |
| 25 | P0 | JournalDB._create_tables() | Tables never created; all inserts would fail |
| 26 | P0 | PerformanceJournalGroup | All _log_*() methods are stubs |
| 27 | P1 | JournalDB.query_historical_analogs() | Stub; HistorianAgent cannot retrieve history |
| 28 | P1 | HYPOTHESIS_REGISTRY | Hypothesis status never mutated; all permanently UNTESTED |
| 29 | P1 | PerformanceJournalGroup._summarizer | SummarizerAgent permanently None |
| 30 | P0 | BacktestEngine.run() | No in-sample or OOS validation possible |
| 31 | P2 | BacktestEngine | Would use same stub groups; no mock alternative |

---

## P0 Issues (System Cannot Run)

These 6 gaps mean the system cannot execute in any mode:

1. **Gap 2:** Main loop is a stub
2. **Gap 3:** No data source
3. **Gap 4:** No feature computation
4. **Gap 1:** Journal crashes at startup
5. **Gap 25:** Journal tables never created
6. **Gap 30:** Backtest cannot run
