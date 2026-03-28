# Runtime Runner Design

**Phase:** 4.75 Runtime Wiring
**Date:** 2026-03-28
**File:** `src/runtime/runner.py`

---

## Purpose

`BtcBybitPaperRunner` is the central runtime orchestrator for the BTC/Bybit
paper trading pipeline. It instantiates all active groups, wires them to a
shared EventBus and SystemState, and drives the bar-close polling loop.

Before this runner existed, the system's groups were isolated functional units
that shared no runtime path. `main_btc.py` called Bybit directly and bypassed
the entire group architecture.

---

## Architecture

```
BtcBybitPaperRunner
│
├── SystemState (shared)
├── EventBus (shared)
│
├── Layer A — Data + Signal Generation
│   ├── MarketDataGroup         → BarCloseEvent, FeatureReadyEvent
│   ├── IndicatorsGroup         → GroupSignalEvent
│   ├── CandlestickGroup        → GroupSignalEvent
│   └── TechnicalStructureGroup → GroupSignalEvent
│
├── Layer A — Aggregation
│   └── EntryGroup              → CandidateTradeEvent (if confirmation gate met)
│
├── Layer B+C — Panel + Decision
│   └── PanelDecisionGroup      → PanelApprovedProposalEvent (if enter decision)
│       ├── TraderEvaluatorPanel (20 traders)
│       └── FinalDecisionGroup  (6 safety rails)
│
├── Risk Gate
│   └── RiskLeverageGroup       → RiskDecisionEvent, PositionOpenEvent
│
├── Exit Monitoring
│   └── ExitGroup               → PositionCloseEvent
│
└── Journal + Learning
    └── PerformanceJournalGroup → SQLite journal.db
        └── JournalExtension   → 10 learning tables (wired post-setup)
            └── DecisionTraceLogger → decision traces
```

---

## Excluded Groups (Stubbed)

| Group | Reason Excluded |
|---|---|
| ChartPatternGroup | `_process_features()` raises `NotImplementedError`. Would crash on FeatureReadyEvent. |
| NewsMacroGroup | `_process_bar_close()` raises `NotImplementedError`. Would crash on BarCloseEvent. |

These groups are NOT instantiated by the runner. Their absence means:
- `chart_pattern_quality = 0.0` in composite scoring (EntryGroup)
- No macro event-calendar signals (NewsMacro regime derived from EMA200 position instead)

---

## Run Modes

### `--run` (live paper trading)
Requires Bybit connectivity. Calls `MarketDataGroup.fetch_and_process()` every 60 seconds.
Currently blocked in this environment (HTTP 404 from Bybit CDN).

### `--simulate N` (integration testing)
Injects N synthetic `FeatureReadyEvent` objects directly onto the EventBus.
Does NOT require Bybit. Exercises the full pipeline including panel and decision.

### `--backtest` (EMA-crossover baseline)
Uses `BacktestEngine` directly. Does NOT use the group pipeline.
Results tagged `simplified_backtest`. Must NOT be mixed with runtime outcomes.

### `--analyze` (legacy)
Calls Bybit directly, runs `FeatureComputer` standalone. No group pipeline.

---

## Cross-Group Cache Wiring

The runner injects cache references between groups after instantiation
but before `setup()` (which registers EventBus subscriptions):

```
MarketDataGroup._feature_cache → PanelDecisionGroup._feature_cache
TechnicalStructureGroup._structural_cache → PanelDecisionGroup._structural_cache
TechnicalStructureGroup instance → CandlestickGroup (via set_technical_structure_group)
```

This eliminates re-fetching data that is already computed.

---

## Learning Layer Wiring

The JournalExtension is wired AFTER all groups have called `setup()`,
because `PerformanceJournalGroup._initialize_db()` runs during `setup()`:

```
1. runner.setup()
   → all groups setup()
   → PerformanceJournalGroup creates JournalDB + opens SQLite connection

2. runner._finalize_learning_wiring()
   → JournalExtension(journal_db._conn)  ← shares the live connection
   → JournalExtension.initialize()  ← creates 10 new learning tables
   → PanelDecisionGroup._trace_logger = DecisionTraceLogger(extension, source)
```

If learning wiring fails (import error, DB not ready), the runner logs a warning
and continues. Learning is advisory — its failure must not crash the runtime.
