# Missing Capabilities by Group

## Date: 2026-03-28
## Purpose: Per-group breakdown of what is missing, what must be fixed, and in what order

This document is the actionable output of the implementation coverage audit. For each group, it specifies:
- Current state (brutal assessment)
- What is missing
- What the minimum viable implementation requires
- What must NOT be implemented yet (scope discipline)
- Dependencies that must exist first

---

## Group 1: Market Data (MARKET_DATA)

### Current State
**The group is a named shell.** It initializes, sets up state variables, and then does nothing. The entire data ingestion, feature computation, and universe management pipeline is stubbed.

### What Is Missing

| Capability | Required By | Missing Element |
|-----------|-------------|----------------|
| HTTP REST client for Binance klines | All groups | `BinanceAdapter.fetch_bars()` + `setup()` + rate limiter |
| OHLCV normalization from Binance format | All groups | `BinanceAdapter._normalize_kline()` |
| Bar gap detection | Data quality | `FeatureStore.append_bar()` gap check (also stub) |
| Parquet persistence of bars | All groups (history) | `FeatureStore.append_bar()` + `get_bars()` |
| Warm-up bar loading at startup | All groups | Not mentioned in code at all |
| Feature computation (7 indicators) | All downstream groups | `FeatureComputer._true_range()`, `_atr_wilder()`, `_ema()`, `_rsi_wilder()`, `_bollinger_bands()`, `_bb_width_percentile()`, `_adx()` |
| `impulse_flag` and `doji_flag` population | Indicators, Candlestick | Logic to compute and set these FeatureVector fields |
| BarCloseEvent publication | All groups | `bus.publish(BarCloseEvent(...))` call |
| FeatureReadyEvent publication | All groups | `bus.publish(FeatureReadyEvent(...))` call |
| Universe refresh ($10M volume filter) | RiskLeverageGroup (eligible_symbols) | `refresh_universe()` + `state.update_universe()` call |
| DataQualityAlert for gaps | PerformanceJournalGroup | `bus.publish(DataQualityAlert(...))` call |
| Polling loop / scheduler | System | Not in MarketDataGroup; must be in main.py |

### Minimum Viable Implementation (in order)

1. Implement `FeatureComputer._candle_anatomy()` is done ✅; implement all other methods
2. Implement `BinanceAdapter.fetch_bars()` and `_normalize_kline()`
3. Implement `FeatureStore.append_bar()` and `get_bars()` (in-memory cache acceptable for Phase 2; Parquet is optional)
4. Implement `MarketDataGroup.ingest_bar()` (validate → store → compute features → publish events)
5. Implement `MarketDataGroup.refresh_universe()` (volume filter → update state)
6. Implement polling loop in `main.py`

### Must Not Implement Yet
- WebSocket streaming (Phase 3)
- TimescaleDB backend (Phase 3)
- Multi-timeframe support (4h, 1h) until daily bar pipeline proven

---

## Group 2: News & Macro (NEWS_MACRO)

### Current State
**Mostly cosmetic.** Subscribes to BarCloseEvent. All business logic stubs. Implementation priority is lowest (5) — correct for Phase 2.

### What Is Missing

| Capability | Required By | Missing Element |
|-----------|-------------|----------------|
| Static CSV calendar loading | EntryGroup (event risk context) | `_load_event_calendar()` |
| High-impact event check (next 48h) | RiskLeverageGroup._check_event_risk() | `_has_high_impact_event_next_48h()` |
| BTC macro regime classification | SystemState.regime | `_classify_btc_macro()` — currently in IndicatorsGroup too (conflict) |
| GroupSignalBundle publication | EntryGroup | `bus.publish(GroupSignalEvent(...))` |

### Design Conflict
`_classify_btc_macro()` is declared in **both** NewsMacroGroup and IndicatorsGroup. There is an architectural inconsistency: who owns BTC regime classification? The architecture doc says IndicatorsGroup computes regime (because it has FeatureVector data). NewsMacroGroup should augment with macro context (MVRV, event calendar), not re-classify regime from price data. This needs resolution before implementation.

### Minimum Viable Implementation (Phase 2)
1. Implement `_load_event_calendar()` from CSV
2. Implement `_has_high_impact_event_next_48h()` with simple date comparison
3. Publish a GroupSignalBundle with event_risk flag as metadata
4. Remove `_classify_btc_macro()` from NewsMacroGroup — delegate to IndicatorsGroup

### Must Not Implement Yet
- Live NewsAPI feed (Phase 3)
- MVRV live data integration (Phase 3)
- LLM-powered news parsing (Phase 3)

---

## Group 3: Indicators (INDICATORS)

### Current State
**All signal logic is stub.** The group subscribes correctly and maintains the right cross-bar state (RSI history, squeeze active flag). Zero signals are ever produced.

### What Is Missing

| Capability | Required By | Missing Element |
|-----------|-------------|----------------|
| EMA crossover detection (H3-002) | EntryGroup | `_detect_ema_crossover()` |
| RSI divergence detection (H3-001) | EntryGroup | `_detect_rsi_divergence()` with pivot detection |
| BB squeeze + breakout (H3-004) | EntryGroup | `_detect_bb_squeeze_breakout()` |
| BTC regime computation | SystemState | `_compute_regime()` |
| `state.update_regime()` call | All groups that use RegimeContext | Must be called inside `_process_features()` when symbol = BTC |
| `bus.publish(GroupSignalEvent(...))` | EntryGroup | Must be called at end of `_process_features()` |
| RSI pivot detection | H3-001 divergence | Need to identify price/RSI pivot pairs from `_rsi_history` + `_price_history` |
| Squeeze state machine | H3-004 | `_squeeze_active[symbol]` flag must persist across bars (not reset per-bar) |

### Specific Logic Required for RSI Divergence (H3-001)
- Maintain last `DIVERGENCE_LOOKBACK=10` bars of price and RSI
- Identify swing highs (price) and corresponding RSI values
- Identify swing lows (price) and corresponding RSI values
- Bullish divergence: price lower low + RSI higher low
- Suppress if `features.impulse_flag == True` on signal bar
- Require `features.adx14 > 25`
- Require 2 matching pivot points

### Architectural Note on H3-003
H3-003 (ATR-scaled stops improve Sharpe vs fixed % stops) is in the hypothesis registry but has no place in IndicatorsGroup. This is a backtest parameter comparison, not a signal. It should be removed from the IndicatorsGroup's `active_hypotheses` list in GROUP_REGISTRY and handled as a backtest config comparison.

### Minimum Viable Implementation (in order)
1. Implement `_compute_regime()` first (needed by Entry and downstream groups)
2. Implement `_detect_ema_crossover()` (simplest signal logic)
3. Implement `_detect_bb_squeeze_breakout()` (state-based but straightforward)
4. Implement `_detect_rsi_divergence()` last (most complex — requires pivot detection)
5. Wire `_process_features()` to call all four and publish GroupSignalEvent

---

## Group 4: Candlestick (CANDLESTICK)

### Current State
**All detection is stub. Structural cache is permanently empty.** Even if all 5 detectors were implemented, the patterns that require structural level context (H2-001, H2-002, H2-005) would produce no signals because `_structural_cache` is never populated.

### What Is Missing

| Capability | Required By | Missing Element |
|-----------|-------------|----------------|
| Structural cache population | H2-001, H2-002, H2-005 | Mechanism to receive StructuralLevelBundle from TechnicalStructureGroup |
| H2-001: Engulfing detection | EntryGroup | `_detect_engulfing()` |
| H2-002: Morning/Evening Star | EntryGroup | `_detect_morning_evening_star()` |
| H2-003: Three Black Crows | EntryGroup | `_detect_three_black_crows()` |
| H2-004: Inverted Hammer (bearish) | EntryGroup | `_detect_inverted_hammer()` — must produce SHORT, not LONG |
| H2-005: Doji | EntryGroup | `_detect_doji()` |
| `bus.publish(GroupSignalEvent(...))` | EntryGroup | Must be called at end of `_process_features()` |

### Critical Wiring Gap
CandlestickGroup subscribes to `FeatureReadyEvent`. TechnicalStructureGroup also subscribes to `FeatureReadyEvent`. Both process bars at the same time. TechnicalStructureGroup needs to publish its `StructuralLevelBundle` **before** CandlestickGroup processes the same bar.

**Solution options (choose one):**
1. CandlestickGroup subscribes to `GroupSignalEvent` from TechnicalStructureGroup and uses that to update `_structural_cache`.
2. TechnicalStructureGroup publishes a new event type (`StructuralReadyEvent`) that CandlestickGroup subscribes to.
3. CandlestickGroup processes structural context from the **previous bar** (always one bar behind, which is acceptable for daily bar processing).

Option 3 is simplest and avoids ordering dependencies. Must be chosen and documented before implementation.

### Minimum Viable Implementation (in order)
1. Resolve and implement structural cache population mechanism
2. Implement `_detect_engulfing()` (simplest 2-bar pattern)
3. Implement `_detect_three_black_crows()` (no S/R required; simpler entry point)
4. Implement `_detect_doji()` (uses `doji_flag` from FeatureVector)
5. Implement `_detect_morning_evening_star()` (3-bar; needs S/R context)
6. Implement `_detect_inverted_hammer()` last — requires explicit test that direction=SHORT

---

## Group 5: Chart Pattern (CHART_PATTERN)

### Current State
**State machine infrastructure exists. All trading logic is stub.** H1-006 through H1-009 have zero code presence despite appearing in the hypothesis registry.

### What Is Missing

| Capability | Required By | Missing Element |
|-----------|-------------|----------------|
| H1-001/H1-002: H&S advance() | EntryGroup | Neckline computation, shoulder symmetry check |
| H1-003: Double Bottom advance() | EntryGroup | Trough detection, neckline break confirmation |
| H1-004: Descending Triangle advance() | EntryGroup | Horizontal support + declining resistance detection |
| H1-005: Triple Bottom advance() | EntryGroup | Three-trough detection, neckline break |
| `_signal_from_machine()` | EntryGroup | Convert CONFIRMED machine → ChartPatternSignal |
| `_process_features()` | EntryGroup | Advance all machines; collect CONFIRMED signals; publish |
| H1-006: Bull Flag | Future sprint | No class at all |
| H1-007: High & Tight Flag | Future sprint | No class at all |
| H1-008: Falling Wedge | Future sprint | No class at all |
| H1-009: Pipe Bottom | Future sprint | No class at all |
| Neckline detection | H1-001, H1-002, H1-003, H1-005 | Requires structural level data from TechnicalStructureGroup |

### Same Structural Level Dependency
H&S and Double Bottom patterns require identifying the neckline — a structural level concept. This again requires TechnicalStructureGroup to have published S/R data before ChartPatternGroup can advance certain patterns.

### Registry Inconsistency
`GROUP_REGISTRY[CHART_PATTERN].active_hypotheses` includes `["H1-001", "H1-002", "H1-003", "H1-004", "H1-005"]`. But the `PATTERN_MACHINES` dict in ChartPatternGroup also maps H1-001 and H1-002 to the same `HeadAndShouldersMachine` class. The `direction` of H1-001 vs H1-002 (bearish vs bullish) is not encoded in the machine class — only in the signal emitted. This needs explicit handling in `_signal_from_machine()`.

### Minimum Viable Implementation (in order)
1. Implement `HeadAndShouldersMachine.advance()` for H1-002 (Inverse H&S, bullish — easiest to validate)
2. Implement `DoubleBottomMachine.advance()` for H1-003 (well-defined, Bulkowski best data)
3. Implement `_signal_from_machine()` to produce ChartPatternSignal with correct direction
4. Implement `_process_features()` to drive machines and publish
5. Implement H1-001, H1-004, H1-005 machines
6. Add H1-006 through H1-009 machine stubs to PATTERN_MACHINES (Sprint 3+)

---

## Group 6: Technical Structure (TECHNICAL_STRUCTURE)

### Current State
**Entirely cosmetic.** No swing pivots are ever detected. No S/R levels ever exist. The group that all pattern groups depend on produces nothing.

### What Is Missing

| Capability | Required By | Missing Element |
|-----------|-------------|----------------|
| Swing high detection (5-bar fractal) | All pattern groups | `_detect_swing_high(bars, index)` |
| Swing low detection (5-bar fractal) | All pattern groups | `_detect_swing_low(bars, index)` |
| S/R level clustering | Candlestick, ChartPattern | `_merge_pivot_into_levels()` |
| Broken level pruning | S/R accuracy | Must remove levels where price has closed through decisively |
| StructuralLevelBundle assembly | Candlestick, Entry, ChartPattern | `_build_bundle()` |
| at_resistance / at_support flags | CandlestickGroup, EntryGroup | Proximity check: price within `AT_LEVEL_ATR_MULT × ATR14` of level |
| nearest_resistance / nearest_support | CandlestickGroup | Identify closest level above/below |
| Publication mechanism | Downstream groups | Must define HOW bundle is made available (event or shared state) |

### 5-Bar Fractal Algorithm
```
def _detect_swing_high(bars, i):
    # Requires bars[i-2], bars[i-1], bars[i], bars[i+1], bars[i+2]
    # i.e., bar i cannot be determined until bar i+2 is closed
    # For daily bars: swing high on day T is confirmed on day T+2
    return all(bars[i].high > bars[j].high for j in [i-2, i-1, i+1, i+2])
```
This look-forward requirement means TechnicalStructureGroup always processes bars with a 2-bar lag. This is acceptable but must be explicitly implemented and documented.

### Minimum Viable Implementation (in order)
1. Implement `_detect_swing_high()` and `_detect_swing_low()`
2. Implement `_merge_pivot_into_levels()` with clustering tolerance = 1× ATR14
3. Implement `_build_bundle()` with proximity flags
4. Implement `_process_features()` — update history, detect pivots (on bar N-2), merge, build, publish
5. Decide and implement the publication mechanism (new event type recommended)

---

## Group 7: Entry (ENTRY)

### Current State
**Bundle collection is stub. Proposal building is stub. HistorianAgent and CriticAgent are permanently None.** The group cannot function until all upstream groups produce signals.

### What Is Missing

| Capability | Required By | Missing Element |
|-----------|-------------|----------------|
| Bundle collection with flush timeout | Proposal generation | `_collect_bundle()` + async timeout (asyncio.wait_for or similar) |
| Confirmation gate (≥2 groups, ≥1 chart/candle) | Proposal quality | `_evaluate_trade_opportunity()` gate logic |
| Direction conflict detection | Proposal quality | ConflictReport assembly logic |
| Conflict resolution (highest score wins) | Proposal quality | Requires composite scores from both conflicting signals |
| Composite score formula | Proposal quality | 35%/25%/20%/10%/10% formula not even encoded as constants |
| Structural alignment scoring | Composite score | Must read at_resistance/at_support from bundle |
| HistorianAgent concrete implementation | `historian_analog` on proposal | No class anywhere in codebase |
| HistorianAgent injection | EntryGroup | No factory, no startup hook |
| CriticAgent concrete implementation | CriticReport on high-score proposals | `_call_llm()` raises NotImplementedError |
| CriticAgent injection | EntryGroup | No factory, no startup hook |
| Regime filter for longs | Signal suppression | Not mentioned in code at all |
| CandidateTradeProposal assembly | RiskLeverageGroup | `_build_proposal()` must populate all fields |
| CandidateTradeEvent publication | RiskLeverageGroup | Must call `bus.publish(CandidateTradeEvent(...))` |

### Composite Score Formula — Must Be Made Explicit in Code
```python
# Currently only in docstring — must become code:
SCORE_WEIGHTS = {
    "chart_pattern":      0.35,
    "candlestick":        0.25,
    "indicator":          0.20,
    "structural_alignment": 0.10,
    "historian_win_rate": 0.10,
}
```

### HistorianAgent — Creation Path Required
The cleanest solution is to make HistorianAgent a dependency of EntryGroup, passed in `__init__()`:
```python
class EntryGroup(BaseGroup):
    def __init__(self, state, bus, config=None, historian=None, critic=None):
        ...
        self._historian = historian  # ConcreteHistorianAgent(journal_db)
        self._critic = critic        # ConcreteCriticAgent(llm_client) or None
```
This requires a `ConcreteHistorianAgent` class in a new file (e.g., `src/agents/historian.py`) and a `ConcreteCriticAgent`.

### Minimum Viable Implementation (in order)
1. Declare SCORE_WEIGHTS constant in code
2. Implement `_compute_composite_score()` with zero historian_win_rate (historian pending)
3. Implement `_collect_bundle()` with timeout-based flush
4. Implement `_evaluate_trade_opportunity()` with confirmation gate
5. Implement `_build_proposal()` without CriticReport (RESEARCH mode skips critic)
6. Create concrete `HistorianAgent` once JournalDB queries are implemented
7. Create concrete `CriticAgent` with Claude API call (Phase 3)

---

## Group 8: Exit (EXIT)

### Current State
**All exit logic is stub.** The group iterates open positions (which are always empty because no positions are ever opened), then immediately raises NotImplementedError.

### What Is Missing

| Capability | Required By | Missing Element |
|-----------|-------------|----------------|
| Stop loss check (LONG: low ≤ stop; SHORT: high ≥ stop) | Position management | `_check_stop_loss()` |
| Target check (LONG: high ≥ target; SHORT: low ≤ target) | Position management | `_check_target()` |
| Trailing stop activation (at +1R) | Position management | `_check_trailing_stop()` + `_update_trailing_stop()` |
| Time stop check (bars_held ≥ max_bars_to_hold) | Position management | In `_evaluate_position()` |
| PnL computation (USD and R-multiple) | Journal, state.close_position | `_compute_pnl()` |
| Exit execution (state + event) | Journal | `_execute_exit()` |
| Trailing stop state persistence | Trailing stop | `Position.trailing_stop_price` field exists; update mechanism needed |

### Trailing Stop State Problem
`position.trailing_stop_price` is an `Optional[Decimal]` field on the `Position` dataclass. But `Position` is stored in `SystemState.portfolio.open_positions`. To update `trailing_stop_price`, the ExitGroup would need to either:
1. Mutate the Position object in-place (dataclasses allow this since they are not frozen)
2. Replace the Position object in `open_positions` with an updated copy

Option 1 is simpler but requires `SystemState` to expose a `update_position_trailing_stop()` method (or ExitGroup directly mutates the field, which violates the "only Risk and Journal write state" rule).

This is a design conflict that must be resolved before implementation.

### Minimum Viable Implementation (in order)
1. Resolve trailing stop state persistence design
2. Implement `_compute_pnl()` (arithmetic only)
3. Implement `_check_stop_loss()` and `_check_target()` (simple comparisons)
4. Implement `_evaluate_position()` with priority order
5. Implement `_execute_exit()` (calls state.close_position + publishes event)
6. Implement `_check_trailing_stop()` and `_update_trailing_stop()` last

---

## Group 9: Risk & Leverage (RISK_LEVERAGE)

### Current State
**Rules 1, 2, 3, 6, 9 are implemented. Rules 4, 5, 7, 8 are stubs. No trade is ever approved because `_approve()` is stub and `_compute_order()` is stub.** The rejection path works correctly. The approval path does not.

### What Is Missing

| Capability | Priority | Missing Element |
|-----------|----------|----------------|
| Rule 4: Portfolio exposure check | P1 | `PortfolioExposureChecker.check()` + import in group |
| Rule 5: Correlated cluster exposure | P1 | `PortfolioExposureChecker` cluster check |
| Rule 7: Pump detection | P1 | `PumpDetector.is_pump_active()` + feature history access |
| Rule 8: Event risk size reduction | P2 | `_check_event_risk()` — reads from NewsMacroGroup output |
| Position sizing formula | P0 | `RMultipleSizer.compute()` |
| ATR stop placement | P0 | `ATRStopPlacer.compute()` |
| `_compute_order()` | P0 | Combines position sizing + stop placement into RiskApprovedOrder |
| `_approve()` | P0 | Calls state.open_position() + publishes PositionOpenEvent |
| LeverageGovernor wiring | P2 | Import and call `LeverageGovernor.check()` in `_evaluate_proposal()` |
| DrawdownController wiring | P2 | Import and call `DrawdownController.get_size_reduction()` |

### Dead Code Issue
`LeverageGovernor` and `DrawdownController` are implemented in `src/risk/checks.py` but are not imported in `src/groups/risk_leverage/group.py`. They are dead code. They must be:
1. Imported in `risk_leverage/group.py`
2. Wired into `_evaluate_proposal()`

### Minimum Viable Implementation (in order)
1. Implement `RMultipleSizer.compute()` (pure arithmetic)
2. Implement `ATRStopPlacer.compute()` (with round-number shift)
3. Implement `_compute_order()` (wires sizer + placer + size cap)
4. Implement `_approve()` (state.open_position + bus.publish)
5. Implement `PortfolioExposureChecker.check()` (Rules 4 and 5)
6. Implement `PumpDetector.is_pump_active()` (Rule 7)
7. Wire LeverageGovernor and DrawdownController

---

## Group 10: Performance/Journal/Learning (PERFORMANCE_JOURNAL)

### Current State
**Completely non-functional despite having the most event subscriptions.** `_initialize_db()` raises at startup. If the exception weren't silently caught, the group would crash before subscribing to any events.

### What Is Missing

| Capability | Priority | Missing Element |
|-----------|----------|----------------|
| SQLite table creation | P0 | `JournalDB._create_tables()` |
| Trade open logging | P0 | `JournalDB.insert_trade_open()` + `_log_position_open()` |
| Trade close logging | P0 | `JournalDB.update_trade_close()` + `_log_position_close()` |
| Signal logging | P1 | `JournalDB.insert_signal()` + `_log_signal_event()` |
| Risk decision logging | P1 | `_log_risk_decision()` |
| System alert logging | P2 | `_log_system_alert()` |
| Historical analog query | P1 | `query_historical_analogs()` — blocks HistorianAgent |
| Edge decay detection | P2 | `_check_edge_decay()` (50 vs 200 trades) |
| Hypothesis validation check | P2 | `_check_hypothesis_validation()` (Gate 1 criteria) |
| Hypothesis status mutation | P2 | No method mutates `HYPOTHESIS_REGISTRY[id].status` anywhere |
| Weekly LLM summary | P3 | `_run_weekly_summary()` — requires SummarizerAgent |

### Design Issue: Exception Swallowing
`BaseGroup.handle_event()` catches all exceptions from `_handle_event()`. When `_initialize_db()` raises NotImplementedError, it is caught and logged, but the group continues running. This means the system appears to be working (no crash) but is silently non-functional.

**Fix:** Add a `is_healthy` flag to BaseGroup. Groups that fail `_setup()` should set `is_healthy = False` and not process any events.

### Minimum Viable Implementation (in order)
1. Implement `JournalDB._create_tables()` (SQL DDL)
2. Implement `_initialize_db()` in PerformanceJournalGroup to call `JournalDB.initialize()`
3. Implement `insert_trade_open()` and `update_trade_close()`
4. Implement `_log_position_open()` and `_log_position_close()`
5. Implement `query_hypothesis_trades()` and `query_recent_outcomes()`
6. Implement `query_historical_analogs()` to enable HistorianAgent
7. Implement `_check_edge_decay()` and `_check_hypothesis_validation()`

---

## Cross-Group: Wiring Gaps That Must Be Fixed

These gaps span multiple groups and cannot be fixed by working on one group alone:

### Wiring Gap W1: TechnicalStructure → Candlestick Structural Context
**Problem:** CandlestickGroup._structural_cache is never populated.
**Fix:** Define a resolution (previous-bar S/R cache, new event type, or shared state). Implement it.

### Wiring Gap W2: RegimeContext Never Updated
**Problem:** SystemState.regime stays at `btc_macro="unknown"` forever.
**Fix:** IndicatorsGroup._compute_regime() must call `state.update_regime()` for BTC symbol bars.

### Wiring Gap W3: HistorianAgent Not Injected
**Problem:** EntryGroup._historian is always None.
**Fix:** Create `ConcreteHistorianAgent` class that wraps JournalDB queries. Wire it via EntryGroup constructor.

### Wiring Gap W4: DrawdownController Not Applied to Position Sizing
**Problem:** DrawdownController.get_size_reduction() exists but is not called.
**Fix:** Call it in `RiskLeverageGroup._evaluate_proposal()` and pass result to `_compute_order()`.

### Wiring Gap W5: LeverageGovernor Not in Risk Gate
**Problem:** LeverageGovernor.check() exists but is not imported or called in RiskLeverageGroup.
**Fix:** Import and call it in `_evaluate_proposal()` after Rule 7.

### Wiring Gap W6: Hypothesis Status Mutation Mechanism
**Problem:** HYPOTHESIS_REGISTRY statuses never change.
**Fix:** Add `update_hypothesis_status(hypothesis_id, new_status)` function to registry.py. Call it from `_check_hypothesis_validation()`.

### Wiring Gap W7: eligible_symbols Always Empty
**Problem:** RiskLeverageGroup._check_liquidity() always rejects because eligible_symbols is never populated.
**Fix:** Implement `MarketDataGroup.refresh_universe()` and ensure it calls `state.update_universe()`.

---

## Implementation Priority Order (Consolidated)

**Phase A — System Can Run (no signals, no trades)**
1. `JournalDB._create_tables()` — fix startup crash
2. `FeatureComputer` — all 7 indicator methods
3. `BinanceAdapter.fetch_bars()` and `_normalize_kline()`
4. `FeatureStore.append_bar()` and `get_bars()`
5. `MarketDataGroup.ingest_bar()` and `refresh_universe()`
6. Main polling loop in `main.py`

**Phase B — Signals Flow (but no trades yet)**
7. `TechnicalStructureGroup` — all 5 detection methods
8. Resolve and implement TechnicalStructure → Candlestick wiring (W1)
9. `IndicatorsGroup._compute_regime()` + regime update (W2)
10. `IndicatorsGroup._detect_ema_crossover()`
11. All 4 chart pattern `advance()` methods
12. All 5 candlestick detectors
13. `EntryGroup._collect_bundle()` with timeout flush

**Phase C — Trades Approved and Opened**
14. `RMultipleSizer.compute()` and `ATRStopPlacer.compute()`
15. `RiskLeverageGroup._compute_order()` and `_approve()`
16. `PortfolioExposureChecker.check()` (Rules 4 and 5)
17. `PumpDetector.is_pump_active()` (Rule 7)
18. Wire DrawdownController and LeverageGovernor (W4, W5)

**Phase D — Positions Close and Journal Records**
19. `ExitGroup` — all exit condition checks
20. Resolve trailing stop state persistence design
21. `JournalDB` — all insert and query methods
22. `PerformanceJournalGroup` — all `_log_*()` methods
23. `ConcreteHistorianAgent` implementation and injection (W3)

**Phase E — Learning and Validation**
24. `EntryGroup._compute_composite_score()` with historian data
25. `PerformanceJournalGroup._check_edge_decay()`
26. `_check_hypothesis_validation()` + hypothesis status mutation (W6)
27. `BacktestEngine.run()` — full replay
28. `PerformanceMetrics.compute()` — all metric computations

**Phase F — Advanced (Sprint 3+, post-validation)**
29. H1-006 through H1-009 state machines
30. H4-003, H4-004 detectors
31. CriticAgent with actual LLM integration
32. SummarizerAgent weekly report
33. Static calendar for NewsMacroGroup
