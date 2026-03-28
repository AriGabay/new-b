# Phase 4.5 Alignment Audit Report

**Date:** 2026-03-28
**Audit Scope:** All work through Phase 4 (research → coverage → architecture → BTC/Bybit slice → Phase 3.5 stabilization → Phase 4 learning layer)
**Method:** Direct code reading, grep, runtime path tracing — not doc trust

---

## Executive Summary

**Overall Verdict: PARTIAL ALIGNMENT — INTEGRATION GAPS CONFIRMED**

The system's individual components are largely implemented correctly and honestly.
The architecture documentation accurately describes the 3-layer design intent.
However, the connection between layers is not wired in the main runtime path.

Layer A (specialist groups) → Layer B (20 trader panel) → Layer C (final decision)
exists as a documented design and as isolated working code. It does NOT exist
as an active runtime pipeline in `main_btc.py`.

This is not a documentation fraud — the docs do state that wiring is pending —
but the framing is inconsistent in places. This audit corrects that.

---

## System Truth Check

### 3-Layer Architecture: Does it match code reality?

| Claim | Code Reality | Status |
|---|---|---|
| Layer A: 10 specialist groups | 5 real (MarketData, Indicators, Candlestick, TechnicalStructure, Entry), 3 deferred stubs (ChartPattern, NewsMacro, Exit/Risk as Layer A outputs), EntryGroup aggregates | PARTIAL |
| Layer B: 20 trader evaluators | All 20 implemented in `traders/evaluators.py`, `TraderEvaluatorPanel` functional | REAL BUT NOT WIRED |
| Layer C: FinalDecisionGroup | Implemented in `decision/final_group.py`, 6 safety rails active | REAL BUT NOT WIRED |
| Panel: score, vote, confidence, reasons | All fields in TraderVerdict dataclass | YES |
| FinalDecision: trader outputs + hard rails only | Verified — no fresh discretionary thesis in decide() | YES |
| BTC only | main_btc.py hardcoded to BTCUSDT | YES |
| Bybit only | Only BybitAdapter used | YES |
| Paper/sim first | ModeGate.RESEARCH set in proposal builder | YES |
| Not live-ready | Bybit HTTP 404 from CDN, no positions opened in runtime | YES |

### Specialist Groups: Real vs Stub

| Group | Status | Emits GroupSignalEvent? | Notes |
|---|---|---|---|
| MarketDataGroup | REAL | N/A (publishes BarCloseEvent/FeatureReadyEvent) | Polling-driven |
| IndicatorsGroup | REAL | YES | 10 sub-agents implemented, no stubs |
| CandlestickGroup | REAL | YES | 10 pattern methods, no stubs |
| TechnicalStructureGroup | REAL | YES | Swing detection, S/R clustering, proximity flags |
| ChartPatternGroup | STUB | NO | `_process_features()` raises NotImplementedError |
| NewsMacroGroup | STUB | NO | `_process_bar_close()` raises NotImplementedError |
| EntryGroup | REAL | Publishes CandidateTradeEvent | _historian=None, _critic=None always |
| RiskLeverageGroup | REAL | N/A (risk gate) | 9 rules verified |
| ExitGroup | REAL | N/A (exits) | Priority logic: stop→target→trailing→time |
| PerformanceJournalGroup | REAL + REPAIRED | N/A (logging) | Double-close bug fixed |

### Pipeline Connectivity

```
MarketDataGroup.fetch_and_process()
  → publishes BarCloseEvent + FeatureReadyEvent

IndicatorsGroup (subscribes to FeatureReadyEvent)
  → publishes GroupSignalEvent ✓

CandlestickGroup (subscribes to FeatureReadyEvent)
  → publishes GroupSignalEvent ✓

TechnicalStructureGroup (subscribes to FeatureReadyEvent)
  → publishes GroupSignalEvent ✓

ChartPatternGroup (subscribes to FeatureReadyEvent)
  → raises NotImplementedError ✗ (STUB)

NewsMacroGroup (subscribes to BarCloseEvent)
  → raises NotImplementedError ✗ (STUB)

EntryGroup (subscribes to GroupSignalEvent)
  → collects from the 3 real groups above
  → confirmation gate: needs >=2 signals same direction
  → publishes CandidateTradeEvent ✓ (IF confirmation gate met)

RiskLeverageGroup (subscribes to CandidateTradeEvent)
  → runs 9 risk rules
  → publishes RiskDecisionEvent + (if approved) PositionOpenEvent

ExitGroup (subscribes to FeatureReadyEvent)
  → checks open positions each bar
  → publishes PositionCloseEvent when exit triggered

PerformanceJournalGroup (subscribes to all events)
  → logs to SQLite journal.db

--- NOT IN RUNTIME ---
TraderEvaluatorPanel — not called from any runtime path
FinalDecisionGroup — not called from any runtime path
JournalExtension — not instantiated from any runtime path
```

### Critical Gap: main_btc.py

`main_btc.py` does NOT instantiate any group class.
It calls `BybitAdapter.fetch_bars()` directly and runs `FeatureComputer` standalone.
The EventBus-driven group pipeline described above is NOT active in any entrypoint.

This means:
- Signals from IndicatorsGroup, CandlestickGroup, TechnicalStructureGroup never fire
- EntryGroup never aggregates signals
- TraderEvaluatorPanel never evaluates a setup
- FinalDecisionGroup never makes a decision
- No positions are ever opened in the current runtime

The EventBus pipeline exists as functional code ready for a runner that wires it,
but that runner does not exist yet.

---

## Bugs Found and Repaired

### BUG 1 — Double-Close in PerformanceJournalGroup (FIXED)

**File:** `src/groups/performance_journal/group.py`
**Severity:** HIGH — would corrupt SystemState.portfolio equity and total_trades

**Problem:**
`ExitGroup._execute_exit()` calls `state.close_position(position_id, pnl_usd)`.
Then it publishes `PositionCloseEvent`.
`PerformanceJournalGroup._log_position_close()` listens to `PositionCloseEvent`
and also calls `state.close_position(position_id, pnl_usd)`.

`state.close_position()` uses `pop(position_id, None)` which silently returns None
on the second call, but STILL executes `equity += pnl_usd` and `total_trades += 1`.
Result: PnL double-counted, trade count doubled.

**Fix:** Removed the `state.close_position()` call from `_log_position_close()`.
Journal group's responsibility is logging only; state management belongs to ExitGroup.

### BUG 2 — NotImplementedError Stubs Could Crash Live Code (FIXED)

**File:** `src/groups/performance_journal/group.py`
**Severity:** MEDIUM — would raise unhandled exception if any caller invokes these

**Problem:**
Four methods raised `NotImplementedError("Phase 2 pending")`:
- `_check_edge_decay()`
- `_check_hypothesis_validation()`
- `_run_weekly_summary()`
- `query_historical_analogs()`

If called (e.g., from a future periodic scheduler), these would propagate an
uncaught exception through the event loop.

**Fix:** Changed to safe logged no-ops that return None/{} with debug logging.
"Deferred" semantics are documented in docstrings.

---

## Alignment Findings — No Repair Needed (Correctly Documented)

- ChartPatternGroup stubbed: documented in `remaining_stubbed_components.md` ✓
- NewsMacroGroup stubbed: documented ✓
- HistorianAgent = None: documented ✓
- CriticAgent = None: documented ✓
- BacktestEngine EMA-only: documented ✓
- Bybit connectivity blocked: documented in `bybit_connectivity_smoke_test.md` ✓
- startup_load() one-bar lag: documented in `entry_price_wiring_fix.md` ✓
- Layer B/C not wired to runtime: documented in `PHASE_4_LEARNING_STATUS.md` ✓

---

## Alignment Findings — Docs Required Update

The Phase 4 documentation stated "No existing files were modified."
This created false confidence that the learning layer was integrated.
The audit confirmed it was not. Documentation has been updated to reflect
this more clearly in `PHASE_4_LEARNING_STATUS.md` and the handoff doc.

---

## Summary of Repairs Made in This Audit

| Issue | File | Repair |
|---|---|---|
| Double-close bug | performance_journal/group.py | Removed redundant state.close_position() call |
| NotImplementedError stubs (4 methods) | performance_journal/group.py | Changed to safe logged no-ops |

No other repairs were needed. All other limitations were correctly documented.
