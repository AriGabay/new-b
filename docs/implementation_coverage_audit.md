# Implementation Coverage Audit

## Date: 2026-03-28
## Auditor: Systems Architect
## Scope: All Python source files in src/ vs all documented design contracts in docs/ and research/

---

## Audit Methodology

This audit cross-references three layers:

1. **Research layer** — what was learned from source material (Phase 1 markdown corpus)
2. **Design layer** — what was specified as contracts (Phase 2 docs/architecture docs)
3. **Implementation layer** — what actually exists in Python code as real logic (not stubs)

**Standard:** A feature is "implemented" only if it has working Python logic. A method that contains `raise NotImplementedError(...)` is a **stub**, not an implementation. Documentation of intent is not implementation.

---

## Executive Summary

| Layer | Count | Notes |
|-------|-------|-------|
| Researched concepts | 47 | From Phase 1 audit sources |
| Selected for implementation | 32 | Per architecture contracts |
| Actually implemented in code | 11 | Methods with real logic |
| Wired into runtime execution | 0 | Main loop is a stub |
| Stubbed only (NotImplementedError) | ~140 | Methods across all modules |
| Missing entirely from code | 4 | No file, no class, no stub |
| Intentionally excluded | 15 | Per rejected_ideas registry |

**Overall implementation completeness: ~8% of selected concepts have real, executable Python logic.**

The system is a correct and well-structured architecture specification. It is not a functioning trading system.

---

## Module-Level Coverage Table

| Module | Methods Total | Stubs | Real Logic | % Real |
|--------|--------------|-------|------------|--------|
| `src/core/schemas.py` | 4 | 0 | 4 | **100%** |
| `src/core/events.py` | 6 | 0 | 6 | **100%** |
| `src/core/registry.py` | 4 | 0 | 4 | **100%** |
| `src/core/state.py` | 7 | 0 | 7 | **100%** |
| `src/agents/base/agent.py` | 4 | 1* | 3 | 75% |
| `src/agents/base/roles.py` | 10 | 10 | 0 | **0%** |
| `src/agents/base/group.py` | 5 | 2* | 3 | 60% |
| `src/groups/market_data/group.py` | 5 | 3 | 2 | 40% |
| `src/groups/news_macro/group.py` | 6 | 4 | 2 | 33% |
| `src/groups/indicators/group.py` | 7 | 5 | 2 | 29% |
| `src/groups/candlestick/group.py` | 7 | 6 | 1 | 14% |
| `src/groups/chart_pattern/group.py` | 6 | 2 | 4 | 67% |
| `src/groups/chart_pattern/state_machine.py` | 10 | 4 | 6 | 60% |
| `src/groups/technical_structure/group.py` | 8 | 5 | 3 | 38% |
| `src/groups/entry/group.py` | 7 | 4 | 3 | 43% |
| `src/groups/exit/group.py` | 9 | 7 | 2 | 22% |
| `src/groups/risk_leverage/group.py` | 13 | 7 | 6 | 46% |
| `src/groups/performance_journal/group.py` | 12 | 10 | 2 | 17% |
| `src/features/compute.py` | 9 | 7 | 2 | 22% |
| `src/data/store.py` | 7 | 6 | 1 | 14% |
| `src/data/binance.py` | 5 | 5 | 0 | **0%** |
| `src/risk/sizing.py` | 4 | 3 | 1 | 25% |
| `src/risk/checks.py` | 9 | 4 | 5 | 56% |
| `src/journal/db.py` | 9 | 7 | 2 | 22% |
| `src/backtest/engine.py` | 5 | 3 | 2 | 40% |
| `src/backtest/holdout.py` | 4 | 0 | 4 | **100%** |
| `src/backtest/metrics.py` | 8 | 3 | 5 | 63% |
| `src/config/settings.py` | 16 | 1 | 15 | 94% |
| `src/main.py` | 3 | 1 | 2 | 67% |
| **TOTAL** | **226** | **119** | **107** | **47%** |

*Abstract methods (`_execute`, `_setup`, `_handle_event`) are counted as stubs where subclasses must provide logic.

---

## What "Real Logic" Means

Methods counted as "real logic" are those that execute meaningful computation without delegating to a NotImplementedError stub. They include:

- `OHLCVBar.__post_init__()` — validates OHLC invariants
- `ChartPatternSignal.__post_init__()` — enforces conservative target = 50% measured move
- `EventBus.publish()` — actual pub/sub delivery with exception handling
- `SystemState.close_position()` — equity, HWM, drawdown, consecutive_loss updates
- `SystemState.open_position()` — available capital deduction
- `AgentRole.run()` — timing wrapper with exception catch
- `HoldoutManager` (all 4 methods) — boundary enforcement
- `DrawdownController.get_size_reduction()` — tiered size reduction
- `LeverageGovernor.check()` — leverage ceiling enforcement
- `RiskLeverageGroup._check_mode_gate()` — RESEARCH mode block
- `RiskLeverageGroup._check_daily_loss_limit()` — daily loss check
- `RiskLeverageGroup._check_max_drawdown()` — drawdown halt
- `RiskLeverageGroup._reject()` — publishes RiskRejectedEvent
- `PerformanceMetrics.check_gate1()` — IS backtest gate criteria
- `PerformanceMetrics.check_gate2()` — OOS gate criteria
- `PerformanceMetrics.check_oos_retention()` — 60% retention check
- `PerformanceMetrics.compute_win_rate()` — win count / total count
- `FeatureComputer._candle_anatomy()` — body, range, shadows
- `load_config()` — environment variable parsing
- `PatternStateMachine._check_expiry()` — max_bars enforcement
- `PatternStateMachine.reset()` — state clear
- `get_correlation_cluster()` — lookup in CORRELATION_CLUSTERS dict
- `SystemState` (all mutation methods) — asyncio-locked state changes

**Everything else in the system raises NotImplementedError or is an empty event dispatcher.**

---

## Group-by-Group Audit

### Group 1: Market Data (MARKET_DATA)

**Documented responsibility:** Ingest, normalize, validate, distribute OHLCV. Compute features. Refresh universe hourly.

**What exists in code:**
- Class initialized ✓
- EventBus subscription: none (driven externally) ✓
- `ingest_bar()` — STUB
- `refresh_universe()` — STUB
- `_compute_features()` — STUB (delegates to FeatureComputer which is also stubbed)

**What works at runtime:** The group initializes. Nothing else.

**Verdict: COSMETIC. MarketDataGroup is a class skeleton with no executable data processing.**

---

### Group 2: News & Macro (NEWS_MACRO)

**Documented responsibility:** Load static event calendar. Classify BTC macro regime. Flag high-impact events.

**What exists in code:**
- Class initialized ✓
- Subscribes to BarCloseEvent ✓
- `_process_bar_close()` — STUB
- `_load_event_calendar()` — STUB
- `_has_high_impact_event_next_48h()` — STUB
- `_classify_btc_macro()` — STUB

**What works at runtime:** Subscription wired. Handler dispatches. All payload logic raises NotImplementedError.

**Verdict: COSMETIC. Publishes no signals. The EventBus receives the BarCloseEvent and the call chain immediately hits NotImplementedError.**

---

### Group 3: Indicators (INDICATORS)

**Documented responsibility:** Detect EMA crossover (H3-002), RSI divergence (H3-001), BB squeeze (H3-004). Compute regime.

**What exists in code:**
- Subscribes to FeatureReadyEvent ✓
- Cross-bar history buffers declared ✓
- `_detect_ema_crossover()` — STUB (H3-002)
- `_detect_rsi_divergence()` — STUB (H3-001)
- `_detect_bb_squeeze_breakout()` — STUB (H3-004)
- `_compute_regime()` — STUB (regime classification)
- H3-003 (ATR vs fixed stops Sharpe comparison) — **not mentioned anywhere in code**

**What works at runtime:** Group initializes and subscribes. On FeatureReadyEvent → `_process_features()` raises NotImplementedError immediately.

**Verdict: COSMETIC. No indicator signal is ever produced.**

---

### Group 4: Candlestick (CANDLESTICK)

**Documented responsibility:** Detect 5 candlestick patterns (H2-001 through H2-005).

**What exists in code:**
- Subscribes to FeatureReadyEvent ✓
- Feature history buffer (last 3 bars) declared ✓
- Structural cache declared ✓
- `_detect_engulfing()` — STUB (H2-001)
- `_detect_morning_evening_star()` — STUB (H2-002)
- `_detect_three_black_crows()` — STUB (H2-003)
- `_detect_inverted_hammer()` — STUB (H2-004)
- `_detect_doji()` — STUB (H2-005)

**Critical gap:** The `_structural_cache` is declared but never populated. There is no subscriber or method that receives StructuralLevelBundle from TechnicalStructureGroup and stores it in this cache. Both groups subscribe to `FeatureReadyEvent`, but neither publishes to the other. The structural context dependency is documented but the wiring doesn't exist even at the stub level.

**What works at runtime:** Nothing. Process hits NotImplementedError at `_process_features()`.

**Verdict: COSMETIC. Structural cache wiring is entirely absent even as a stub.**

---

### Group 5: Chart Pattern (CHART_PATTERN)

**Documented responsibility:** Advance H1-001 through H1-005 state machines per bar. Emit ChartPatternSignal only at CONFIRMED.

**What exists in code:**
- Subscribes to FeatureReadyEvent ✓
- State machine registry with 5 entries ✓
- `_initialize_machines_for_symbol()` — IMPLEMENTED ✓ (creates machine instances)
- `_is_in_failure_cooldown()` — IMPLEMENTED ✓ (RJ-007 check)
- `PatternStateMachine._check_expiry()` — IMPLEMENTED ✓
- `PatternStateMachine.reset()` — IMPLEMENTED ✓
- `PatternStateMachine.is_terminal` property — IMPLEMENTED ✓
- `_process_features()` — STUB
- `_signal_from_machine()` — STUB
- `HeadAndShouldersMachine.advance()` — STUB (H1-001, H1-002)
- `DoubleBottomMachine.advance()` — STUB (H1-003)
- `DescendingTriangleMachine.advance()` — STUB (H1-004)
- `TripleBottomMachine.advance()` — STUB (H1-005)

**H1-006 through H1-009** (Bull flag, High & Tight Flag, Falling Wedge, Pipe Bottom) — **not present at all.** No stub, no class, no placeholder. These are documented in HYPOTHESIS_REGISTRY but have zero code presence.

**Wiring gap:** ChartPatternGroup does not interact with TechnicalStructureGroup at all. H&S and Double Bottom require neckline detection (a structural concept), but no mechanism exists to receive S/R data.

**What works at runtime:** State machines are instantiated. Immediately raises NotImplementedError at `_process_features()`.

**Verdict: PARTIAL SKELETON. State machine infrastructure exists. All trading logic is stub. H1-006 through H1-009 have zero code presence.**

---

### Group 6: Technical Structure (TECHNICAL_STRUCTURE)

**Documented responsibility:** Swing high/low detection. Horizontal S/R clustering. at_resistance / at_support flags.

**What exists in code:**
- Subscribes to FeatureReadyEvent ✓
- Bar history, resistance/support level lists declared ✓
- Constants: FRACTAL_BARS=2, MAX_LEVELS=10, MIN_TOUCHES=2, AT_LEVEL_ATR_MULT=1.0 ✓
- `_detect_swing_high()` — STUB
- `_detect_swing_low()` — STUB
- `_merge_pivot_into_levels()` — STUB
- `_build_bundle()` — STUB (supposed to produce StructuralLevelBundle)

**Critical gap:** No publisher. Even if all methods were implemented, TechnicalStructureGroup has no code that calls `bus.publish(GroupSignalEvent(...))`. The `_process_features()` stub presumably would do this, but there is no explicit wiring to CandlestickGroup's `_structural_cache`.

**What works at runtime:** Nothing beyond initialization.

**Verdict: COSMETIC. Even the publication hook is absent.**

---

### Group 7: Entry (ENTRY)

**Documented responsibility:** Aggregate signals from 5 upstream groups. Apply confirmation gate (≥2 groups). Compute composite score. Invoke CriticAgent if score ≥ 0.60. Build CandidateTradeProposal.

**What exists in code:**
- Subscribes to GroupSignalEvent ✓
- `_pending_bundles` defaultdict ✓
- `_historian` and `_critic` declared as None (injection points) ✓
- Constants: thresholds documented ✓
- `_collect_bundle()` — STUB (pending bundles never populated)
- `_evaluate_trade_opportunity()` — STUB
- `_compute_composite_score()` — STUB (formula: 35%/25%/20%/10%/10% defined in docs, absent in code)
- `_build_proposal()` — STUB

**Critical gap:** HistorianAgent and CriticAgent are declared as `None` with no injection mechanism. There is no method, factory, or startup hook that creates and wires them. They would be undefined when EntryGroup tries to call them.

**What works at runtime:** Subscription wired. First `GroupSignalEvent` → hits NotImplementedError immediately.

**Verdict: COSMETIC. The injection pattern for Historian/Critic is declared but has no implementation path.**

---

### Group 8: Exit (EXIT)

**Documented responsibility:** Check stop loss, target, trailing stop, time stop on every FeatureReadyEvent. Publish PositionCloseEvent.

**What exists in code:**
- Subscribes to FeatureReadyEvent ✓
- `_check_exits(features)` — PARTIAL: iterates `state.portfolio.open_positions`, calls `_evaluate_position()`
- `_evaluate_position()` — STUB
- `_check_stop_loss()` — STUB
- `_check_target()` — STUB
- `_check_trailing_stop()` — STUB
- `_update_trailing_stop()` — STUB
- `_compute_pnl()` — STUB
- `_execute_exit()` — STUB

**`_check_exits()` is the only non-stub method in the exit logic chain**, but it immediately calls `_evaluate_position()` which raises NotImplementedError. So it does not function.

**What works at runtime:** Iterates open positions list. Immediately raises NotImplementedError.

**Verdict: COSMETIC. The iteration scaffolding is real. All exit condition logic is stub.**

---

### Group 9: Risk & Leverage (RISK_LEVERAGE)

**Documented responsibility:** Final non-overridable gate. Apply 9 risk rules. Size position. Emit RiskApprovedOrder or RiskRejectedEvent.

**What exists in code:**
- Subscribes to CandidateTradeEvent ✓
- `_evaluate_proposal()` — IMPLEMENTED ✓ (sequential 9-rule pipeline with early exit)
- `_check_mode_gate()` — IMPLEMENTED ✓ (Rule 1: blocks RESEARCH mode)
- `_check_daily_loss_limit()` — IMPLEMENTED ✓ (Rule 2: −2% block)
- `_check_max_drawdown()` — IMPLEMENTED ✓ (Rule 3: 10% halt)
- `_check_liquidity()` — IMPLEMENTED ✓ (Rule 6: eligible_symbols check)
- `_check_plan_completeness()` — IMPLEMENTED ✓ (Rule 9: validates entry/target/score)
- `_reject()` — IMPLEMENTED ✓ (builds and publishes RiskRejectedEvent)
- `_check_portfolio_exposure()` — STUB (Rule 4)
- `_check_correlated_exposure()` — STUB (Rule 5)
- `_check_pump_signal()` — STUB (Rule 7)
- `_check_event_risk()` — STUB (Rule 8: returns size reduction multiplier)
- `_compute_order()` — STUB (position sizing formula)
- `_approve()` — STUB (publishes approval and opens position)

**Critical gap:** Rule ordering in code does not match risk_contract.md. The contract specifies 10 sequential steps; the code has 9 checks. Rule 6 in code is "liquidity" but in the contract Rule 6 is "spread/liquidity" (vol_usd > $10M). The code checks only `eligible_symbols` membership, not the vol_usd directly.

**Secondary gap:** `_check_event_risk()` is called but its return value (`event_risk_reduction`) is passed to `_compute_order()` which is a stub, so the reduction is never applied.

**What works at runtime:** Rules 1, 2, 3, 6, 9 fire correctly and can reject. Rules 4, 5, 7, 8 always pass (stubs return or are skipped). No trade is ever approved because `_approve()` raises NotImplementedError.

**Verdict: PARTIAL. The rejection path partially works. The approval path does not work.**

---

### Group 10: Performance/Journal/Learning (PERFORMANCE_JOURNAL)

**Documented responsibility:** Log all events. Compute metrics. Detect edge decay. Run SummarizerAgent weekly. Update hypothesis status.

**What exists in code:**
- Subscribes to 6 event types ✓
- Event dispatch routing implemented ✓
- `_initialize_db()` — STUB
- All `_log_*()` methods — STUB (10 total)
- `query_historical_analogs()` — STUB
- `_check_edge_decay()` — STUB
- `_check_hypothesis_validation()` — STUB
- `_run_weekly_summary()` — STUB

**Critical gap:** `_initialize_db()` is called in `_setup()`, meaning the first thing that happens at startup is a NotImplementedError. The group then crashes silently (BaseGroup.handle_event catches exceptions), but the DB is never initialized, so no event is ever logged.

**What works at runtime:** Subscription setup immediately raises NotImplementedError in `_initialize_db()`. The exception is swallowed. The group then exists but cannot log anything.

**Verdict: COSMETIC. The event routing structure is real. Every substantive call raises NotImplementedError, including the one called at startup.**

---

## Critical Missing Pieces (Not Stubbed, Not Mentioned in Code)

These are concepts that appear in docs/research but have **zero code presence**:

1. **H1-006 Bull Flag** — In HYPOTHESIS_REGISTRY (code), GROUP_REGISTRY (docs), but no state machine class, no stub, no comment.

2. **H1-007 High & Tight Flag** — Same: in hypothesis registry but no code.

3. **H1-008 Falling Wedge** — Same.

4. **H1-009 Pipe Bottom** — Same.

5. **HistorianAgent concrete implementation** — EntryGroup declares `self._historian = None`. No concrete HistorianAgent class exists anywhere. No factory. No injection point that works.

6. **CriticAgent concrete implementation** — Same. `self._critic = None`. The LLM call method raises NotImplementedError. No Claude API integration exists.

7. **SummarizerAgent concrete implementation** — PerformanceJournalGroup declares `self._summarizer = None`. Not wired.

8. **TechnicalStructureGroup → CandlestickGroup data flow** — No mechanism exists for TechnicalStructureGroup to update `CandlestickGroup._structural_cache`. This wiring is absent even as a stub.

9. **NewsAPI / live news feed** — Referenced in architecture (Phase 3), correctly excluded from Phase 2. But the static CSV calendar is also not implemented (stub).

10. **Composite scoring formula** — Documented precisely (35%/25%/20%/10%/10%) in entry/group.py docstring and architecture docs. Not implemented. Not even a constant declaration for the weights.

---

## Intentionally Excluded (Per Research Rejection Registry)

These concepts were researched and explicitly rejected:

| Concept | Rejection Code | Reason |
|---------|---------------|--------|
| Hanging Man pattern | RJ-001 | 33% reversal rate — below viability |
| Shooting Star standalone | RJ-002 | 60% reversal without S/R context |
| Elliott Wave counting | RJ-003 | Unfalsifiable, subjective |
| Wyckoff phases | RJ-004 | No testable rules |
| Harmonic patterns (Gartley, Butterfly) | RJ-005 | No empirical validation |
| CNBC reverse indicator | RJ-006 | Not systematic |
| Failed breakout retry < 5 bars | RJ-007 | Repeated failure trap |
| Tight stops < 0.5× ATR | RJ-008 | Stop-hunt risk |
| Any pattern in ranging market (ADX<20) | RJ-009 | Noise trading |
| Hammer standalone long | RJ-010 | No confirmation |
| Halving cycle trading | N/A | Not falsifiable in any reasonable timeframe |
| DOGE/meme cycle | N/A | No systematic basis |
| Fibonacci retracements | N/A | Mysticism |
| CME expiry manipulation | N/A | No consistent empirical backing |
| MVRV > 3.0 as trade signal | N/A | Too coarse; macro filter only |

All of these are correctly absent from implementation. Their absence is intentional and correct.

---

## Issues Requiring Fix Before Architecture Repair

The following 18 issues were identified that must be addressed. They are ordered by severity.

### P0 — System Cannot Execute At All

1. **`FeatureComputer.compute()` and all indicator methods are stub.** No features means no signals, no risk checks, no trades. This is the absolute foundation.

2. **`BinanceAdapter.fetch_bars()` is stub.** No data source means no bars to process.

3. **`FeatureStore.append_bar()` and `get_bars()` are stub.** No persistence means even if data were fetched, nothing would be stored or retrieved.

4. **`MarketDataGroup.ingest_bar()` is stub.** The entry point for all OHLCV data never executes.

5. **`PerformanceJournalGroup._initialize_db()` raises NotImplementedError in `_setup()`.** This means the group silently crashes at startup, before any bar is processed.

6. **Main polling loop is stub.** `main.py` initializes groups but never starts the data loop.

### P1 — Signal Generation Path Broken

7. **All pattern state machine `advance()` methods are stub.** No chart pattern signals are ever emitted.

8. **All candlestick detector methods are stub.** No candlestick signals are ever emitted.

9. **All indicator detector methods are stub.** No indicator signals are ever emitted.

10. **TechnicalStructureGroup → CandlestickGroup data flow is absent.** The `_structural_cache` in CandlestickGroup is never populated. This dependency is documented but not wired.

### P2 — Decision Path Broken

11. **`EntryGroup._collect_bundle()` is stub.** Signal bundles accumulate nowhere; proposals are never built.

12. **`HistorianAgent` and `CriticAgent` have no concrete implementations.** They are declared as `None`. Even if EntryGroup ran, it would crash on first use.

13. **`RiskLeverageGroup._compute_order()` is stub.** Even if a proposal passed all rules, no order would be produced.

14. **`RiskLeverageGroup._approve()` is stub.** Even a fully-approved proposal never results in a PositionOpenEvent.

15. **`RiskLeverageGroup.Rules 4, 5, 7, 8` are stub.** Portfolio exposure and pump detection are silently bypassed.

### P3 — Learning/Persistence Broken

16. **`JournalDB._create_tables()` is stub.** The journal never initializes. All events are silently lost.

17. **All `PerformanceJournalGroup._log_*()` methods are stub.** Zero event history is ever recorded.

18. **`BacktestEngine.run()` is stub.** No in-sample or OOS validation is possible.
