# Runtime–UI Integration

**System:** BTC/Bybit Paper Trading — Management Console
**Phase:** 6
**Date:** 2026-03-29

---

## Overview

The management console connects to the actual runtime — not a mock, not a stub. When the runner is started from the UI, the process imports `BtcBybitPaperRunner`, calls its real `setup()` method, and attaches the `EventBridge` to its real `EventBus`. All data displayed in the UI comes from live Python object access (SystemState), real SQL queries (journal), or real EventBus callbacks (event stream).

This document describes exactly how each connection works, what is read vs written, and where the real boundaries are.

---

## RunnerManager: Lifecycle Design

File: `src/console/runner_manager.py`

`RunnerManager` is instantiated once at server startup and held in a module-level singleton (`_manager`). It manages one optional `BtcBybitPaperRunner` instance.

### Start sequence

```python
from runtime.runner import BtcBybitPaperRunner
self._runner = BtcBybitPaperRunner(
    simulation_mode=simulation_mode,
    journal_db_path=self._journal_db_path,
)
await self._runner.setup()
```

`setup()` is the runner's real initialisation method — it wires all groups, instantiates the panel, connects the journal writer, and attaches the JournalExtension learning layer. The console does not mock any of this. If `setup()` raises (e.g. due to a missing dependency or import error), the error is captured and returned to the UI.

In **simulation mode** (`simulation_mode=True`): the runner is fully set up but its bar-polling loop is not started. No Bybit connectivity is attempted. The runner sits idle until bars are injected or a replay runs against it.

In **live mode** (`simulation_mode=False`): the polling loop is launched as a background asyncio task via `asyncio.create_task(self._run_loop())`. This calls `runner.run_paper_loop()`, which attempts Bybit WebSocket connectivity. Live mode requires Bybit credentials and network access; it fails in the current development environment.

### Stop sequence

```python
if self._runner_task:
    self._runner_task.cancel()
    await self._runner_task
if self._runner:
    await self._runner.teardown()
self._runner = None
```

`teardown()` is the runner's real cleanup method. All group teardowns, journal flushes, and connection closures are performed by the runtime, not by the console.

### Group status reporting

`get_status()` reports group names from static constants (`ACTIVE_GROUPS`, `EXCLUDED_GROUPS`). These are the real group names from the Phase 3 architecture. When the runner is not started, active groups report "unknown". When started, they report "active". The console does not query individual group health at runtime — group-level health is observable via the event stream (SystemAlertEvent, DataQualityAlert).

---

## EventBridge: Design and Attachment

File: `src/console/event_bridge.py`

The EventBridge subscribes to the runner's real `EventBus` object after `start()` succeeds:

```python
# In server.py after RunnerManager.start():
bridge = get_bridge()
await bridge.attach(mgr.runner.bus)
```

`mgr.runner.bus` is the actual `EventBus` instance held by the runner. The bridge imports all 12 event types from `core.events` and calls `await bus.subscribe(event_type, callback)` for each. The callbacks are real async functions on the bridge.

### The 12 subscribed event types

1. `BarCloseEvent` — emitted when a bar closes in the market data pipeline
2. `FeatureReadyEvent` — emitted when the IndicatorsGroup produces a feature vector
3. `GroupSignalEvent` — emitted by any specialist group (CandlestickGroup, TechnicalStructureGroup, EntryGroup, etc.)
4. `CandidateTradeEvent` — emitted when EntryGroup produces a candidate setup
5. `PanelApprovedProposalEvent` — emitted when PanelDecisionGroup approves a proposal
6. `RiskDecisionEvent` — emitted by RiskLeverageGroup with approve/block decision
7. `PositionOpenEvent` — emitted when a position is opened
8. `PositionCloseEvent` — emitted when a position is closed
9. `JournalEntryEvent` — emitted by PerformanceJournalGroup when a record is written
10. `SystemAlertEvent` — emitted by any group on error or abnormal condition
11. `DataQualityAlert` — emitted by MarketDataGroup on data quality issues
12. `UniverseUpdateEvent` — emitted when the eligible symbol universe changes

### Handler mechanics

For each event, the handler does:
1. `_event_to_dict(event)` — serialises the real event object to a JSON-safe dict using `vars(event)` and type-specific conversions
2. Appends to the 1000-entry ring buffer
3. `put_nowait(d)` on every active WebSocket client queue

The serialisation handles `Decimal` → `float`, `datetime` → ISO8601, enums via `.value`, and nested dataclasses via `__dict__` recursion. Private attributes (prefixed `_`) are excluded. This is a read-only extraction; the event object is never modified.

### Detach

When the runner stops, `bridge.detach()` calls `bus.unsubscribe(event_type, callback)` for all 12 subscriptions. The bridge can reattach to a new runner instance after a restart.

---

## How SystemState Is Read

`RunnerManager.get_system_state()` directly accesses attributes on the running runner's state object:

```python
state = self._runner.state
portfolio = state.portfolio
regime = state.regime
risk_state = state.risk_state
```

This is a synchronous attribute read. The console never calls any setter, never modifies `portfolio`, `regime`, `risk_state`, or `eligible_symbols`. It reads `portfolio.equity`, `portfolio.open_positions`, `portfolio.daily_pnl`, etc. and converts them to JSON-safe types (float for Decimal, str for enums).

The `open_positions` dict is iterated to produce a list of position snapshots. Each position snapshot is a copy, not a reference. The runner's internal position objects are not modified.

`/api/state` returns `{"available": false, "reason": "Runner not started."}` when the runner is not active, which the UI renders as "unavailable" stats.

---

## How the Journal Is Read

File: `src/console/journal_reader.py`

The `JournalReader` opens `src/data/journal.db` using the SQLite URI read-only mode:

```python
self._conn = sqlite3.connect(
    f"file:{self._db_path}?mode=ro",
    uri=True,
    check_same_thread=False,
)
self._conn.execute("PRAGMA journal_mode=WAL")
```

The `mode=ro` URI parameter makes the connection read-only at the SQLite level. The `check_same_thread=False` flag is safe because all reads go through FastAPI's async handlers running in the event loop — no concurrent threading on this connection.

WAL mode is set on the connection so that the reader can see committed rows while the runner's writer is mid-transaction in a WAL frame. This is the correct SQLite concurrency pattern for one writer + multiple readers.

The writer (the running `BtcBybitPaperRunner` via its `JournalDB` and `JournalExtension`) has its own separate `sqlite3.Connection`. The two connections never share state.

All queries are read-only `SELECT` statements. No INSERT, UPDATE, or DELETE is ever issued by `JournalReader`.

The reader gracefully falls back to a normal connection if the read-only URI fails (e.g. if the DB file does not yet exist and SQLite cannot open it read-only). In this fallback case the connection technically has write capability but no writes are issued by the reader code.

---

## How the EventBus Subscription Works

The runtime `EventBus` supports async pub/sub. When `bus.subscribe(event_type, callback)` is called, the callback is registered to receive all future events of that type published to the bus.

From the bridge perspective:
1. `await bus.subscribe(BarCloseEvent, handler)` — registers the async handler
2. When the runner's market data pipeline calls `await bus.publish(BarCloseEvent(...))`, the bus calls `await handler(event)` as part of the publish coroutine
3. The handler runs in the same asyncio event loop as the runner
4. `q.put_nowait(d)` is non-blocking; if a client queue is full (maxsize=500), it is removed from the active set

The subscription is per-event-type, per-callback. The bridge creates 12 separate handlers (one per event type). Each handler captures its event type name in a closure for logging purposes.

---

## Graceful Degradation When Runner Is Not Started

Every API endpoint that accesses runner state is guarded:

```python
# /api/state
if self._runner is None:
    return {"available": False, "reason": "Runner not started."}

# /api/groups
status = mgr.get_status()  # returns "unknown" for all active groups

# /api/status
bridge.is_attached  # returns False
```

The UI renders these states explicitly:
- Stat cards show "—" or "unavailable" instead of numeric values
- Groups show "unknown" status badges
- The event stream shows only the ring buffer history (which may be empty)

No part of the UI crashes or shows uncaught errors when the runner is stopped. The journal browser, test runner, and replay control are fully functional regardless of runner state.

---

## How Learning Extension Tables Get Populated

The 6 learning extension tables (`setup_packets`, `trader_reviews`, `panel_summaries`, `final_decisions`, `outcome_attributions`, `calibration_records`) are written by `JournalExtension`, which is wired by the runner during `setup()`.

The population path is:
1. `BtcBybitPaperRunner.setup()` instantiates `JournalExtension` and wires it to the relevant groups
2. When `PanelDecisionGroup` evaluates a setup, it fires events that `JournalExtension` intercepts
3. `JournalExtension` inserts rows into `setup_packets`, `trader_reviews`, `panel_summaries`, `final_decisions`
4. When a trade closes, `JournalExtension` inserts into `outcome_attributions` and upserts `calibration_records`

The console's `JournalReader` will see these rows as soon as they are committed (WAL mode). After a replay run completes, clicking "Refresh Journal" in the Actions tab reconnects the reader to pick up any new rows.

In simulation mode with no bars injected, none of these tables are populated. They require the pipeline to have evaluated at least one setup packet.

---

## Source Separation: Read-Only Console

This is a strict architectural boundary:

| Console action | What it does to trading state |
|---|---|
| `/api/state` (GET) | Reads SystemState. Never writes. |
| `/api/journal/*` (GET) | Reads SQLite. Never writes. |
| `/api/logs` (GET) | Reads log buffer. Never writes. |
| `/api/actions/start_runner` | Calls runner.setup() — initialises runtime state |
| `/api/actions/stop_runner` | Calls runner.teardown() — cleans up runtime state |
| `/api/actions/refresh_journal` | Reconnects SQLite reader. Never writes to DB. |
| `/api/actions/clear_logs` | Clears in-memory console log buffer only |
| `/api/tests/run` | Launches pytest subprocess. No trading state modified. |
| `/api/replay/run` | Launches replay harness. Harness writes to journal DB via `JournalExtension` (same as live runner would). No exchange connectivity. |

The console never places orders, never modifies the portfolio, never overrides risk state, never writes to the panel threshold, and never bypasses the ModeGate. All such mutations are properties of the runtime's own internal logic, triggered only by the runner's processing of real (or simulated) market data.

---

## What IS Real vs What Is NOT Real

| Component | Real | Not real / caveated |
|---|---|---|
| BtcBybitPaperRunner instance | Yes — actual class, actual setup() | Bybit connectivity requires network access |
| EventBus subscriptions | Yes — 12 real event types subscribed | Only active when runner is running |
| EventBridge serialisation | Yes — real event objects serialised | Private fields excluded by convention |
| SystemState reads | Yes — direct attribute access on live state | State is None when runner not started |
| Journal SQLite reads | Yes — real WAL read-only queries | Extension tables empty until runs execute |
| Journal SQLite writes | N/A — console never writes | Writes are by runner/harness only |
| Replay pipeline | Yes — runs real TrueReplayHarness | btc_bear_continuation produces 0 entries by design |
| Simulation replay | Yes — runs real RuntimeReplayHarness | Produces 0 entries (H3-005 not validated in fixtures) |
| Test suite | Yes — real pytest on real codebase | Results held in memory, cleared on restart |
| Group health per-tick | Not live | Static enumeration; group internals not polled |
| Per-trader live voting | Only via journal (post-hoc) | Not streamed in real time as individual events |
| P&L chart | Not implemented | Equity is point-in-time snapshot only |
| Log persistence | Not implemented | In-memory ring buffer only |
