# Phase 2 Handoff to Core Build

## Status: READY FOR PHASE 3
## Date: 2026-03-28
## Prepared by: Systems Architect (Phase 2)
## Recipient: Core Build Team (Phase 3)

---

## What Phase 2 Produced

Phase 2 is complete. The system has a full production-grade architecture and skeleton codebase. **No working runtime exists yet.** Every group, module, and class has been designed, stubbed, and documented with `raise NotImplementedError()` markers exactly where Phase 3 implementation begins.

### Artifacts Produced

#### Research Corpus (Phase 1 → Phase 2)
| Artifact | Location | Content |
|----------|----------|---------|
| Research audit | `docs/research_audit.md` | Source-by-source quality assessment |
| Hypothesis registry | `research/hypotheses/hypothesis_registry.md` | 25 hypotheses (all UNTESTED) |
| Rejected ideas | `research/rejected_ideas/rejected_and_suspicious_ideas.md` | 18 hard rejections with reasons |
| Risk rules | `research/risk_rules/risk_management_rules.md` | 9 risk rules, implementation-ready |
| Pattern taxonomy | `research/pattern_taxonomy/pattern_taxonomy.md` | 3-tier taxonomy, priority matrix |
| Open questions | `research/open_questions/open_questions.md` | 20 unresolved architectural questions |

#### Architecture Documentation
| Document | Location | What it defines |
|----------|----------|----------------|
| System overview | `docs/architecture/system_overview.md` | 10 groups, mode gates, tech stack |
| Runtime model | `docs/architecture/runtime_model.md` | Process topology, event timing, state model |
| Decision flow | `docs/decision_flow/master_decision_flow.md` | 8-stage bar-close pipeline |
| Group registry | `docs/agent_registry/group_registry.md` | All 10 groups, full YAML spec |
| Role registry | `docs/agent_registry/role_registry.md` | All 10 roles, activation matrix |
| Data contracts | `docs/data_contracts/data_contracts.md` | All schemas, event bus, feature store API |
| Risk contract | `docs/risk_framework/risk_contract.md` | All 9 risk rules with pseudocode |
| Learning contract | `docs/learning_system/learning_contract.md` | Journal schema, edge decay, HypothesisValidator |
| Validation methodology | `docs/validation_methodology/validation_methodology.md` | Bonferroni, gates, anti-p-hacking |
| ADR-001 | `docs/adr/ADR-001-*.md` | Logical agents, not always-on LLM |
| ADR-002 | `docs/adr/ADR-002-*.md` | Deterministic pipelines first |
| ADR-003 | `docs/adr/ADR-003-*.md` | Where LLM is permitted (3 contexts only) |
| ADR-004 | `docs/adr/ADR-004-*.md` | Validation gates before live promotion |

#### Python Skeleton
| Module | Location | Status |
|--------|----------|--------|
| Core schemas | `src/core/schemas.py` | **COMPLETE** — all dataclasses, enums |
| Core events | `src/core/events.py` | **COMPLETE** — EventBus, all event types |
| Core registry | `src/core/registry.py` | **COMPLETE** — all 10 groups, 25 hypotheses |
| Core state | `src/core/state.py` | **COMPLETE** — SystemState with asyncio.Lock |
| Agent base classes | `src/agents/base/` | **COMPLETE** — AgentRole, all 10 role base classes |
| Group base class | `src/agents/base/group.py` | **COMPLETE** — BaseGroup with event timing |
| MarketDataGroup | `src/groups/market_data/group.py` | Stub — `ingest_bar()`, `_compute_features()` |
| NewsMacroGroup | `src/groups/news_macro/group.py` | Stub — `_process_bar_close()`, calendar loading |
| IndicatorsGroup | `src/groups/indicators/group.py` | Stub — EMA, RSI, BB squeeze detectors |
| CandlestickGroup | `src/groups/candlestick/group.py` | Stub — 5 pattern detectors |
| ChartPatternGroup | `src/groups/chart_pattern/group.py` | Stub — 5 state machine drivers |
| Pattern state machines | `src/groups/chart_pattern/state_machine.py` | Stub — H1-001 through H1-005 |
| TechnicalStructureGroup | `src/groups/technical_structure/group.py` | Stub — fractal S/R detection |
| EntryGroup | `src/groups/entry/group.py` | Stub — signal aggregation, proposal builder |
| ExitGroup | `src/groups/exit/group.py` | Stub — stop/target/trailing/time stop |
| RiskLeverageGroup | `src/groups/risk_leverage/group.py` | **PARTIAL** — Rules 1, 2, 3, 6, 9 implemented |
| PerformanceJournalGroup | `src/groups/performance_journal/group.py` | Stub — event routing wired |
| FeatureComputer | `src/features/compute.py` | Stub — all indicator formulas |
| FeatureStore | `src/data/store.py` | Stub — Parquet read/write |
| BinanceAdapter | `src/data/binance.py` | Stub — REST polling |
| ATRStopPlacer | `src/risk/sizing.py` | Stub |
| RMultipleSizer | `src/risk/sizing.py` | Stub |
| PortfolioExposureChecker | `src/risk/checks.py` | Stub |
| DrawdownController | `src/risk/checks.py` | **COMPLETE** — size reduction ladder |
| PumpDetector | `src/risk/checks.py` | Stub |
| JournalDB | `src/journal/db.py` | Stub — schema defined |
| BacktestEngine | `src/backtest/engine.py` | Stub |
| HoldoutManager | `src/backtest/holdout.py` | **COMPLETE** — raises on violation |
| PerformanceMetrics | `src/backtest/metrics.py` | **PARTIAL** — gate checks complete |
| SystemConfig | `src/config/settings.py` | **COMPLETE** — all config fields |
| Main runner | `src/main.py` | Stub — group initialization wired |

---

## Phase 3 Build Order

Build in this order. Each item depends on items above it.

### Sprint 1: Data Foundation (Weeks 1–2)
**Goal:** Get real bars flowing into FeatureStore with correct features.

1. **`FeatureComputer.compute()`** — Implement all indicators (ATR, EMA, RSI, BB, ADX).
   - Unit test each indicator against known reference values (pandas-ta or TA-Lib).
   - Test: `compute(bars[:199])` returns `None`; `compute(bars[:200])` returns FeatureVector.
   - Test: impulse_flag correct; doji_flag correct.

2. **`BinanceAdapter.fetch_bars()`** — REST polling for OHLCV.
   - Test with BTCUSDT 1d, 250 bars. Validate all OHLCVBar invariants pass.
   - Implement rate limiter.

3. **`FeatureStore.append_bar()` and `get_bars()`** — Parquet persistence.
   - Test: write 300 bars, read back 250. Verify chronological order.
   - Test: append bar with `is_closed=False` raises ValueError.

4. **`MarketDataGroup.ingest_bar()` and `refresh_universe()`** — Wire adapter → store → event bus.
   - Integration test: mock Binance response → verify BarCloseEvent and FeatureReadyEvent published.

**Sprint 1 done when:** BTCUSDT daily bars flow from Binance through FeatureStore with correct FeatureVector. All unit tests pass.

---

### Sprint 2: Risk Engine (Week 3)
**Goal:** RiskLeverageGroup fully operational. All 9 rules enforce correctly.

1. **`ATRStopPlacer.compute()`** — With round-number anti-gaming shift.
   - Test: LONG at 50000, ATR=1000 → stop at 48000. If 48000 near round number → shift.
   - Test: SHORT mirror.

2. **`RMultipleSizer.compute()`** — R-multiple position sizing.
   - Test: equity=100000, risk=1%, entry=50000, stop=48000 → verify R amount and size.
   - Test: max_position_fraction cap applied.

3. **`PortfolioExposureChecker.check()`** — Rules 4 and 5.
   - Test: 3 open positions totaling 26% → reject. 24% → approve.
   - Test: BTC cluster at 16% → reject rule 5.

4. **`PumpDetector.is_pump_active()`** — Rule 7.
   - Test: volume_ratio = 6.0 in last bar → pump detected.

5. **`RiskLeverageGroup._compute_order()`** — Full order computation.
   - Integration test: proposal with valid entry/stop/target → RiskApprovedOrder with correct size.

**Sprint 2 done when:** RiskLeverageGroup correctly approves/rejects synthetic proposals for all 9 rules. Unit test coverage ≥ 80% for risk module.

---

### Sprint 3: Chart Pattern State Machines (Weeks 4–6)
**Goal:** H1-001 through H1-005 state machines functional. Signal confirmed only at CONFIRMED state.

Priority order: H1-003 (Double Bottom) → H1-002 (Inverse H&S) → H1-001 (H&S Top) → H1-005 (Triple Bottom) → H1-004 (Descending Triangle).

For each pattern:
1. Implement `PatternStateMachine.advance(features)`.
2. Write state transition unit tests (INACTIVE → FORMING → ... → CONFIRMED).
3. Write "false breakout" test: price approaches neckline but does not close through → stays BREAKOUT_PENDING.
4. Write expiry test: pattern not confirmed after `max_bars` → EXPIRED, machine resets.
5. Integration test: feed historical BTCUSDT bars containing a known H&S pattern → verify CONFIRMED signal emitted on correct bar.

**Hard rule to test for every pattern:**
```python
assert signal.pattern_state == "CONFIRMED"    # Never emit on BREAKOUT_PENDING
assert signal.conservative_target == signal.measured_move * Decimal("0.50")  # Always 50%
```

**Sprint 3 done when:** All 5 pattern state machines reach CONFIRMED correctly on synthetic bar sequences. Zero premature signal emissions.

---

### Sprint 4: Indicator and Candlestick Signals (Weeks 7–8)
**Goal:** H3-001, H3-002, H3-004 and H2-001 through H2-005 operational.

1. **IndicatorsGroup:** Implement EMA crossover, RSI divergence, BB squeeze.
   - Test crossover: golden cross bar → IndicatorSignal emitted; next bar (no crossover) → no signal.
   - Test RSI divergence: impulse_flag=True on signal bar → signal suppressed.
   - Test BB squeeze: bb_width_pct=15 → squeeze active. Close outside band with volume_ratio=2.0 → breakout signal.

2. **CandlestickGroup:** Implement all 5 pattern detectors.
   - Test each with minimal synthetic bars.
   - Test Inverted Hammer: direction=SHORT (not LONG — this is the Bulkowski interpretation).
   - Test that blocked patterns (Hanging Man, Shooting Star standalone) produce zero signals.
   - Test RJ-009: adx14=15 → all candlestick signals suppressed.

3. **TechnicalStructureGroup:** Implement fractal S/R detection.
   - Test: swing high correctly identified at bar[i] after bar[i+2] closes.
   - Test: level with 2 touches qualifies; 1 touch does not.
   - Test: at_resistance flag when price within 1×ATR14 of resistance level.

**Sprint 4 done when:** All indicator and candlestick detectors produce signals on synthetic test sequences. Blocked patterns produce zero signals in all test cases.

---

### Sprint 5: Entry, Exit, Journal (Weeks 9–11)
**Goal:** Full bar-close cycle works end-to-end in RESEARCH mode.

1. **JournalDB:** Implement all table creation, insert, and query methods.
   - Test: insert_trade_open → update_trade_close → query_hypothesis_trades returns correct record.
   - Test: double insert on same trade_id → raises (unique constraint).

2. **EntryGroup:** Implement `_collect_bundle()` and `_evaluate_trade_opportunity()`.
   - Test: 2 bundles with same direction → proposal emitted.
   - Test: 2 bundles with opposing directions → conflict detected, skip (tie rule).
   - Test: composite_score < 0.50 → no proposal.
   - Test: composite_score >= 0.60 → CriticAgent invoked (mock it).

3. **ExitGroup:** Implement all exit condition checks.
   - Test: LONG position, bar.low ≤ stop_price → stop loss exit.
   - Test: LONG position, bar.high ≥ target_price → target exit.
   - Test: bars_held ≥ max_bars_to_hold → time stop exit.
   - Test: trailing stop activates at +1R, moves correctly with price.

4. **PerformanceJournalGroup:** Implement DB logging for all event types.
   - Integration test: full pipeline, one trade open → close → verify journal has trade record with correct outcome.

**Sprint 5 done when:** Full research-mode pipeline produces a JournalEntryEvent for every signal, proposal, and trade. Zero events dropped.

---

### Sprint 6: Backtest Engine (Weeks 12–14)
**Goal:** Replay 2017–2022 BTCUSDT daily bars through full pipeline. Produce IS backtest for H1-002 and H3-002.

1. **BacktestEngine.run()** — Bar-by-bar replay.
   - Enforce: at bar T, groups see only bars 0..T (no lookahead).
   - Apply commission (0.1%) and slippage (0.05%) to all fills.
   - Write results to backtest_journal.db (not live journal.db).

2. **PerformanceMetrics.compute()** — All metric computations.
   - Test: compute_profit_factor, compute_max_drawdown, compute_sharpe on known sequences.
   - Test: check_gate1() accepts/rejects correctly for each threshold.

3. **HoldoutManager** — Enforce holdout boundary.
   - Test: `assert_training_access(end_date=2023-01-15)` raises HoldoutViolationError.
   - Test: `assert_holdout_access("H1-001", "untested")` raises HoldoutViolationError.
   - Test: `assert_holdout_access("H1-001", "in_sample_tested")` passes.

4. **Parameter sensitivity grid** — Run IS backtest with ±20% parameter variations.

**Sprint 6 done when:** BacktestEngine produces a BacktestResult for BTCUSDT 2017–2022 with per-hypothesis breakdown. HoldoutManager prevents any holdout access.

---

### Sprint 7+: Live Integration, Shadow Mode (Post-validation)
These sprints are gated on Sprint 6 producing Gate 1 pass for at least one hypothesis.

- **Shadow mode:** Wire RiskApprovedOrder to paper-trade execution (no real API calls, just log fills).
- **Live mode:** Wire to Binance Futures API (requires API key, separate security review).
- **News/Macro:** Implement live news feed parser (Phase 3: NewsAPI or similar).
- **CriticAgent:** Implement actual Claude API call via claude_agent_sdk.
- **SummarizerAgent:** Implement weekly narrative summary via Claude API.
- **Redis migration:** Replace in-process asyncio EventBus with Redis Streams for multi-process deployment.

---

## Non-Negotiable Implementation Rules

These rules are not suggestions. Violating them invalidates the validation framework.

### 1. Bar-Close Only — Zero Exceptions
All group processing happens AFTER bar closes. The `is_closed` field on `OHLCVBar` must be `True`. Any signal computed from an open bar is **invalid**.

```python
# FeatureStore.append_bar() already enforces this:
if not bar.is_closed:
    raise ValueError("Cannot store unclosed bar")
```

### 2. Pattern State Machine Must Reach CONFIRMED
No `ChartPatternSignal` may be emitted with `pattern_state != "CONFIRMED"`.

```python
# ChartPatternGroup enforces this — never bypass:
if machine.state != PatternState.CONFIRMED:
    continue   # Do not emit signal
```

### 3. Conservative Target = 50% of Measured Move
This is enforced in `ChartPatternSignal.__post_init__()`. Do not override it.

```python
# Enforced automatically:
self.conservative_target = self.measured_move * Decimal("0.50")
```

### 4. Risk Rules Are Non-Overridable
No code path, no configuration flag, no LLM output may bypass the RiskLeverageGroup. If the entry group produces a proposal that fails Rule 1 (RESEARCH mode), the order does not execute. This is not configurable.

### 5. LLM Output Is Always Advisory
CriticReport fields (`recommendation`, `bearish_case`, etc.) are **never** read by `RiskLeverageGroup`. The only allowed LLM actions are in `CriticAgent`, `SummarizerAgent`, and `ParserAgent` (News/Macro). See ADR-003.

### 6. HoldoutManager Raises, Not Warns
The holdout is protected by exception, not a log warning. Any code that calls `HoldoutManager.assert_holdout_access()` and catches `HoldoutViolationError` and continues is wrong.

### 7. Journal is Append-Only (Except One UPDATE)
The `trades` table allows one UPDATE per `trade_id` (close data). The `signals` and `journal_events` tables are INSERT-only. No DELETE operations on any journal table.

### 8. EventBus.publish() Never Raises
All subscriber exceptions are caught and logged. No subscriber failure should stop the event bus. This is already implemented in `EventBus.publish()`.

---

## First Working Runtime Checklist

The minimum set of features required for the first end-to-end research-mode run on historical data:

- [ ] FeatureComputer produces correct FeatureVector for BTCUSDT
- [ ] FeatureStore reads/writes bars from Parquet correctly
- [ ] BinanceAdapter fetches 250 bars for BTCUSDT 1d
- [ ] MarketDataGroup publishes BarCloseEvent and FeatureReadyEvent
- [ ] IndicatorsGroup detects and publishes at least one EMA crossover signal (H3-002)
- [ ] ChartPatternGroup advances state machines without crashing
- [ ] EntryGroup produces at least one CandidateTradeProposal in research mode
- [ ] RiskLeverageGroup rejects all proposals (MODE_GATE = RESEARCH) and logs rejections
- [ ] PerformanceJournalGroup writes all events to SQLite without data loss
- [ ] System runs cleanly on 1 year of daily BTCUSDT bars with no crashes and no unhandled exceptions

---

## Testing Strategy

### Unit Tests (required before Sprint integration)
- All deterministic functions (FeatureComputer, risk checks, metrics) → parametrized pytest
- All state machine transitions → synthetic bar sequences
- All schema invariants (OHLCVBar.__post_init__, ChartPatternSignal.__post_init__) → edge cases

### Integration Tests (required per Sprint)
- Each group: mock upstream events → verify correct downstream events published
- RiskLeverageGroup: synthetic CandidateTradeProposal → verify approval/rejection logic

### Simulation Tests (Sprint 6)
- Full pipeline on historical data → deterministic output (same seed = same result)
- Verify no lookahead violations

### What NOT to Test
- Do not write tests that validate a hypothesis produces profit (that's the backtest, not a unit test)
- Do not mock the HoldoutManager for convenience (it must raise on violation)
- Do not test LLM output determinism (LLMs are non-deterministic by design)

---

## Known Gaps and Open Questions

These issues were documented in Phase 1 research and remain unresolved. They require investigation before the relevant Sprint.

| ID     | Issue | Relevant Sprint |
|--------|-------|----------------|
| OQ-001 | Which Binance endpoint: Spot, Futures, or Coin-M? | Sprint 1 |
| OQ-002 | Daily bar close time: UTC 00:00 or 08:00? | Sprint 1 |
| OQ-004 | How to handle delisted assets in historical data? | Sprint 1 |
| OQ-007 | Minimum 2 S/R touches: sliding window or all-time? | Sprint 4 |
| OQ-008 | Structural level proximity: fixed price or ATR-relative? | Sprint 4 |
| OQ-010 | Sample size sufficient for Bonferroni p < 0.002 in crypto (volatile data)? | Sprint 6 |
| OQ-012 | Should H&S right shoulder asymmetry be tolerated and by how much? | Sprint 3 |
| OQ-017 | Does Inverted Hammer bearish hypothesis hold in crypto? May not transfer from Bulkowski. | Sprint 4 |

Full list: `/research/open_questions/open_questions.md`

---

## Decision Reference

All major architecture decisions are recorded in ADRs. Before modifying any structural behavior, check these first:

| ADR | Decision | Never Change Without Review |
|-----|----------|---------------------------|
| ADR-001 | Logical agents, not always-on LLM processes | Group/role architecture |
| ADR-002 | Deterministic pipelines first | Adding any non-determinism to signal detection |
| ADR-003 | Where LLM is permitted (CriticAgent, SummarizerAgent, ParserAgent only) | Expanding LLM usage |
| ADR-004 | Validation gates before live promotion | Holdout rules, gate thresholds |

---

## Phase 2 is Complete

**What exists:** Full architecture, all schemas, all contracts, all stubs, all registries, all ADRs.

**What does NOT exist yet:** Any working runtime logic (all `raise NotImplementedError()` stubs await implementation).

**Next action:** Begin Sprint 1. Implement `FeatureComputer.compute()` first. Test it against known reference values before proceeding to any group integration. The entire validation framework depends on correct feature computation.
