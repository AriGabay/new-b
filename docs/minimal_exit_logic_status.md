# Minimal Exit Logic — Status

**Phase:** 3.5 Stabilization
**Date:** 2026-03-28
**File:** `src/groups/exit/group.py`, `src/groups/performance_journal/group.py`

---

## Actual Code State (As of 2026-03-28)

This document records the honest state of ExitGroup and PerformanceJournalGroup
as found in the codebase after the Phase 3.5 stabilization pass.

### ExitGroup (`src/groups/exit/group.py`)

| Method | Status |
|---|---|
| `_setup()` | IMPLEMENTED — subscribes to `FeatureReadyEvent` |
| `_handle_event()` | IMPLEMENTED — calls `_check_exits()` |
| `_check_exits()` | IMPLEMENTED — iterates open positions, calls `_evaluate_position()` |
| `_evaluate_position()` | **STUBBED** — `raise NotImplementedError` |
| `_check_stop_loss()` | IMPLEMENTED — correct long/short price comparison |
| `_check_target()` | IMPLEMENTED — correct long/short price comparison |
| `_check_trailing_stop()` | **STUBBED** — `raise NotImplementedError` |
| `_update_trailing_stop()` | **STUBBED** — `raise NotImplementedError` |
| `_compute_pnl()` | **STUBBED** — `raise NotImplementedError` |
| `_execute_exit()` | IMPLEMENTED — calls `state.close_position()`, publishes `PositionCloseEvent` |

**Effect at runtime:** `_check_exits()` iterates open positions and calls
`_evaluate_position()`, which immediately raises `NotImplementedError`.
This exception is caught by `BaseGroup.handle_event()` (subscriber exceptions
are caught by EventBus and logged, not re-raised). In practice, ExitGroup
produces no exit events. Positions opened in simulation will never close
through the event-driven path.

The two helper methods `_check_stop_loss()` and `_check_target()` contain
correct logic but are not called by any live code path — they exist as
building blocks for the `_evaluate_position()` implementation that has not
been written.

### PerformanceJournalGroup (`src/groups/performance_journal/group.py`)

| Method | Status |
|---|---|
| `_setup()` | IMPLEMENTED — subscribes to 6 event types, calls `_initialize_db()` |
| `_handle_event()` | IMPLEMENTED — routes to correct handler |
| `_initialize_db()` | **STUBBED** — `raise NotImplementedError` |
| `_log_signal_event()` | **STUBBED** — `raise NotImplementedError` |
| `_log_candidate_trade()` | **STUBBED** — `raise NotImplementedError` |
| `_log_risk_decision()` | **STUBBED** — `raise NotImplementedError` |
| `_log_position_open()` | **STUBBED** — `raise NotImplementedError` |
| `_log_position_close()` | **STUBBED** — `raise NotImplementedError` |
| `_log_system_alert()` | **STUBBED** — `raise NotImplementedError` |
| `_check_edge_decay()` | **STUBBED** — `raise NotImplementedError` |
| `_check_hypothesis_validation()` | **STUBBED** — `raise NotImplementedError` |
| `_run_weekly_summary()` | **STUBBED** — `raise NotImplementedError` |
| `query_historical_analogs()` | **STUBBED** — `raise NotImplementedError` |

**Effect at runtime:** `_setup()` calls `_initialize_db()`, which raises
`NotImplementedError`. This will propagate through `BaseGroup._setup()` and
crash the group's initialization. `PerformanceJournalGroup` cannot be used
in the event-driven runtime path as currently coded.

Note: `JournalDB` (`src/journal/db.py`) is separately implemented and
functional. The stub is specifically in `PerformanceJournalGroup` — the
event-driven wrapper group around `JournalDB`. `main_btc.py` writes to
`JournalDB` directly, bypassing `PerformanceJournalGroup` entirely.

---

## What the Phase 3 Handoff Said vs. What the Code Contains

The Phase 3 handoff (`implemented_vs_stubbed.md`) listed:
- ExitGroup: "PARTIAL — Stop/target/time-stop checks present; trailing stop stub; not wired to SystemState"
- PerformanceJournalGroup: "PARTIAL — Writes to journal, no metrics"

The actual code does not match the "PARTIAL" designation for either group
in the ways that matter at runtime:
- ExitGroup's `_evaluate_position()` raises `NotImplementedError`, blocking all exits
- PerformanceJournalGroup's `_initialize_db()` raises `NotImplementedError`,
  blocking all journaling through this group

---

## What Is Required to Make These Groups Functional

### To make ExitGroup produce exits

Minimum viable implementation requires:
1. `_compute_pnl(position, exit_price)` — straightforward arithmetic
2. `_evaluate_position(position, features)` — call `_check_stop_loss()`,
   `_check_target()`, and time stop (bars held), build and return `ExitSignal`
3. `_execute_exit()` is already implemented

Trailing stop (`_update_trailing_stop`, `_check_trailing_stop`) can remain
stubbed without breaking the stop/target/time-stop path.

### To make PerformanceJournalGroup operational

Minimum viable implementation requires `_initialize_db()` to create the
SQLite connection (using the existing `JournalDB` class). The `_log_*`
methods can be implemented incrementally, but `_initialize_db()` must
succeed for `_setup()` to complete.

---

## What Is Verified Working

- `JournalDB` (`src/journal/db.py`): fully implemented SQLite backend with
  correct schema, WAL mode, and CRUD methods. Used directly by `main_btc.py`.
- `state.close_position()`: implemented and correct.
- `_execute_exit()` in ExitGroup: implemented and will work once
  `_evaluate_position()` returns a real `ExitSignal`.
- `_check_stop_loss()` and `_check_target()`: implemented with correct
  directional logic.

---

## Deferred Items (Not Needed for Basic Journaling)

The following are deferred to Phase 4 and are not blocking:
- `_check_edge_decay()` — requires 50-trade window of outcomes
- `_check_hypothesis_validation()` — requires 30-trade sample size
- `_run_weekly_summary()` — requires LLM integration (SummarizerAgent)
- `query_historical_analogs()` — requires HistorianAgent integration
