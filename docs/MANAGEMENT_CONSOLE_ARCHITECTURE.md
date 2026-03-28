# Management Console Architecture

**System:** BTC/Bybit Paper Trading — Management Console
**Phase:** 6
**Date:** 2026-03-29

---

## Overview

The management console is a single-process web application that provides operator-level visibility into the BTC/Bybit paper trading system. It does not contain trading logic; all trading decisions remain inside the runtime. The console observes, reads, and launches — it never writes to trading state.

The server is a FastAPI application served by uvicorn. The UI is a single self-contained HTML file. There are no external frontend dependencies, no build step, and no external service requirements beyond FastAPI and uvicorn.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Browser (localhost:8765)                      │
│                   src/console/static/index.html                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ Overview │ │  Events  │ │ Journal  │ │  Tests / Replay  │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘   │
│       │             │             │                  │            │
│       └─────────────┴─────────────┴──────────────────┘           │
│               REST (fetch) + WebSocket /ws/events                │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP / WS (localhost only)
┌──────────────────────────────▼──────────────────────────────────┐
│              FastAPI + uvicorn (console.server:app)              │
│                   src/console/server.py                          │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  LogCapture │  │ EventBridge  │  │   JournalReader      │   │
│  │log_capture.py│  │event_bridge.py│  │ journal_reader.py   │   │
│  │ ring 2000   │  │  ring 1000   │  │ WAL read-only SQLite │   │
│  └──────┬──────┘  └──────┬───────┘  └──────────────────────┘   │
│         │                 │                                       │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌──────────────────────┐   │
│  │ /api/logs   │  │ /ws/events   │  │   TestRunner         │   │
│  └─────────────┘  └──────────────┘  │   test_runner.py     │   │
│                                      │  pytest subprocess   │   │
│  ┌──────────────────────────────┐    └──────────────────────┘   │
│  │       RunnerManager          │                                │
│  │    runner_manager.py         │  ┌──────────────────────┐     │
│  │  holds BtcBybitPaperRunner   │  │   ReplayManager      │     │
│  │  lifecycle start/stop        │  │  replay_manager.py   │     │
│  └──────────────┬───────────────┘  │ True+Runtime harness │     │
│                 │                   └──────────────────────┘     │
└─────────────────┼───────────────────────────────────────────────┘
                  │ Python object reference (same process)
┌─────────────────▼───────────────────────────────────────────────┐
│              BtcBybitPaperRunner  (runtime.runner)              │
│                                                                  │
│  EventBus ◄── EventBridge subscribes to 12 event types          │
│  SystemState ◄── RunnerManager.get_system_state() reads only    │
│  Journal DB ◄── JournalReader opens read-only (WAL)             │
└─────────────────────────────────────────────────────────────────┘
                  │
        src/data/journal.db  (SQLite WAL)
```

---

## Component Descriptions

### `server.py` — FastAPI Application

The central HTTP and WebSocket server. Implements all 35 routes. Owns the FastAPI lifespan context which:
- Instantiates `RunnerManager` with the journal DB path
- Opens the `JournalReader` connection
- Initialises the `TestRunner` with the project root
- Installs log capture on the root Python logger
- Tears down all components cleanly on shutdown

Uses `asyncio` throughout. All blocking operations (pytest subprocess, replay harness) run as asyncio tasks. The log capture handler is installed before any other import so that even import-time log lines are captured.

### `log_capture.py` — Python Logging Intercept

`ConsoleLogHandler` is installed on the root Python logger at startup (level DEBUG). Every `logging.LogRecord` emitted anywhere in the process is intercepted and written to the global `LogBuffer` — a thread-safe `deque` with a maximum of 2000 entries.

Each captured line is stored as a dict with fields: `ts` (ISO8601 UTC), `level`, `name` (logger name), `message`, `lineno`.

`/api/logs` reads from this buffer. The WebSocket endpoint also replays the 50 most recent log lines to new clients as `ConsoleLogEvent` messages, and subsequent log lines may be injected as events via `EventBridge.inject_log_event`.

The buffer is in-memory only. It is not persisted to disk by this module. On server restart the buffer is empty.

### `event_bridge.py` — EventBus Subscription to WebSocket Broadcast

`EventBridge` subscribes to 12 event types on the runtime `EventBus` when the runner starts. Each subscription creates an async handler that:
1. Converts the event object to a JSON-safe dict via `_event_to_dict`
2. Appends it to a 1000-entry ring buffer (`deque`)
3. Places it on every active WebSocket client queue via `put_nowait`

JSON serialisation handles `Decimal` → `float`, `datetime` → ISO8601 string, enums via `.value`, and dataclass/object `__dict__` recursion. Private fields (prefixed `_`) are excluded.

When a new WebSocket client connects, it immediately receives up to 100 recent events from the ring buffer before live streaming begins. This allows late-joining clients to see recent context.

The bridge detaches cleanly when the runner stops, unsubscribing all callbacks. It can reattach to a new runner instance.

### `journal_reader.py` — Read-Only SQLite Access

`JournalReader` opens `src/data/journal.db` using SQLite URI mode (`file:path?mode=ro`) with WAL journal mode. This allows the console to read the database concurrently with the runner writing to it without locking conflicts.

It gracefully falls back to a normal read-write connection if the read-only URI mode fails (e.g. DB file does not yet exist). All queries go through `_query()`, which also JSON-parses known blob fields (`payload`, `metadata`, `packet_json`, `calibration_json`, etc.) before returning rows.

The reader covers both the 3 base tables (`trades`, `signals`, `journal_events`) and the 6 Phase 4 learning extension tables (`setup_packets`, `trader_reviews`, `panel_summaries`, `final_decisions`, `outcome_attributions`, `calibration_records`). Extension table queries check `sqlite_master` first and return empty lists if the table does not exist, preventing errors on a fresh or partial database.

### `runner_manager.py` — BtcBybitPaperRunner Lifecycle

`RunnerManager` holds a single optional `BtcBybitPaperRunner` instance. It exposes:
- `start(simulation_mode=True)` — imports and instantiates the runner, calls `runner.setup()`, and in non-simulation mode launches `runner.run_paper_loop()` as a background asyncio task
- `stop()` — cancels the background task if running, calls `runner.teardown()`, nulls the reference
- `get_status()` — returns a JSON-safe dict with running state, mode, group statuses, bars processed, and any error
- `get_system_state()` — reads live values from `runner.state` (portfolio equity, positions, regime, risk state) without writing anything

In simulation mode the runner is set up but its polling loop is not started. Bar injection via `simulate_bar()` is available but not exposed in the current UI.

Group status is static enumeration: 9 active groups and 4 excluded groups as defined in `ACTIVE_GROUPS` / `EXCLUDED_GROUPS` constants.

### `test_runner.py` — pytest Subprocess Launcher

`TestRunner` maintains a list of 8 known test file paths relative to the project root. It launches pytest via `asyncio.create_subprocess_exec` using the current Python interpreter (`sys.executable`), setting `PYTHONPATH` to `src/`. Output is streamed line-by-line into a `TestRunResult` object keyed by a short UUID run ID.

The final summary line is parsed with a regex to extract pass/fail/error counts. Results are stored in memory for the session. Each result includes up to the last 500 output lines.

### `replay_manager.py` — Replay Harness Launcher

`ReplayManager` supports two harness types:
- `true_replay` — uses `TrueReplayHarness` from `validation.true_replay_harness` with the `btc_bear_continuation` fixture
- `simulation` — uses `RuntimeReplayHarness` from `validation.replay_harness`, running 8 synthetic bars on BTCUSDT

Both run as background asyncio tasks. Results are stored in memory as `ReplayRunResult` objects containing counts of bars run, proposals generated, panel approvals, positions opened/closed, and any errors. The raw harness report object is serialised to a string dict.

Two fixtures are registered: `btc_bear_continuation` and `ideal_short_synthetic`.

---

## Data Flow: EventBus to Browser

```
BtcBybitPaperRunner
  └─ EventBus.publish(event)
       └─ EventBridge._make_handler() [async callback]
            ├─ _event_to_dict(event)  → JSON-safe dict
            ├─ EventBridge._ring.append(d)  → ring buffer
            └─ for q in _queues: q.put_nowait(d)
                 └─ WebSocket loop: await q.get()
                      └─ websocket.send_json(event_dict)
                           └─ Browser JS WebSocket.onmessage
                                └─ UI event stream / pipeline trace
```

On WebSocket connect:
1. `bridge.recent_events(limit=100)` is sent immediately (ring buffer replay)
2. `get_log_buffer().recent(limit=50)` is sent as `ConsoleLogEvent` messages
3. Live events flow from the asyncio queue as they arrive
4. A heartbeat `{"event_type": "Heartbeat", "ts": ...}` is sent every 30 seconds on idle

Client-side filtering: the browser may send `{"cmd": "filter", "types": [...]}` to restrict which event types are forwarded.

---

## Data Flow: Browser to Runtime

```
Browser (fetch POST)
  └─ /api/actions/start_runner  {simulation_mode: true}
       └─ RunnerManager.start(simulation_mode=True)
            ├─ BtcBybitPaperRunner.__init__()
            ├─ await runner.setup()
            └─ EventBridge.attach(runner.bus)
                 └─ EventBus.subscribe(event_type, callback) × 12

Browser (fetch GET)
  └─ /api/state
       └─ RunnerManager.get_system_state()
            └─ runner.state.portfolio / regime / risk_state  [read only]

Browser (fetch GET)
  └─ /api/journal/trades?limit=50
       └─ JournalReader.get_trades()
            └─ sqlite3 SELECT FROM trades  [read only WAL]
```

---

## Technology Choices

| Choice | Rationale |
|---|---|
| FastAPI | Async-first, type-annotated, automatic OpenAPI docs, WebSocket support built-in |
| uvicorn | ASGI server, asyncio native, single process, zero configuration |
| Vanilla JS + single HTML file | No build step, no npm, no framework version conflicts; operator console does not need SPA complexity |
| SQLite WAL read-only | Allows concurrent read while runner writes; no separate DB process; zero setup |
| asyncio.Queue for WS broadcast | Non-blocking fanout to N WebSocket clients; dead queues detected and removed on QueueFull |
| Python subprocess for pytest | Test runner uses the same interpreter and environment; no test framework API to maintain |
| deque(maxlen=N) ring buffers | O(1) append, bounded memory, late-joiner support without persistence |

---

## The 35-Route API Surface

### Static
| Method | Path | Description |
|---|---|---|
| GET | `/` | Serve console UI (index.html) |

### Status and State
| Method | Path | Description |
|---|---|---|
| GET | `/api/status` | Runner status, bridge attached, architecture constants |
| GET | `/api/state` | Live SystemState snapshot (equity, positions, regime, risk) |
| GET | `/api/groups` | Group status list |

### Logs
| Method | Path | Description |
|---|---|---|
| GET | `/api/logs` | Recent log lines; supports `limit`, `level`, `search` query params |

### Journal (10 endpoints)
| Method | Path | Description |
|---|---|---|
| GET | `/api/journal/stats` | DB row counts across all tables |
| GET | `/api/journal/trades` | Trade records; supports `limit`, `offset`, `outcome` |
| GET | `/api/journal/signals` | Signal records; supports `limit`, `offset`, `group_id` |
| GET | `/api/journal/events` | Journal events; supports `limit`, `offset`, `event_type` |
| GET | `/api/journal/panels` | Panel summaries; supports `limit`, `offset` |
| GET | `/api/journal/decisions` | Final decisions; supports `limit`, `offset` |
| GET | `/api/journal/reviews` | Trader reviews; supports `packet_id`, `limit` |
| GET | `/api/journal/packets` | Setup packet list; supports `limit`, `offset` |
| GET | `/api/journal/packets/{packet_id}` | Single packet + all trader reviews |
| GET | `/api/journal/attributions` | Outcome attributions; supports `limit` |
| GET | `/api/journal/calibration` | Calibration records (all traders) |

### Tests (4 endpoints)
| Method | Path | Description |
|---|---|---|
| GET | `/api/tests/list` | Available test files with existence check |
| POST | `/api/tests/run` | Start test run; body: `{files: [...]}` optional |
| GET | `/api/tests/results` | All test run results for session |
| GET | `/api/tests/result/{run_id}` | Single test run result |

### Replay (4 endpoints)
| Method | Path | Description |
|---|---|---|
| GET | `/api/replay/fixtures` | Available fixture definitions |
| POST | `/api/replay/run` | Start replay; body: `{fixture_id, harness_type}` |
| GET | `/api/replay/results` | All replay results for session |
| GET | `/api/replay/result/{run_id}` | Single replay result |

### Actions (4 endpoints)
| Method | Path | Description |
|---|---|---|
| POST | `/api/actions/start_runner` | Start runner; body: `{simulation_mode: bool}` |
| POST | `/api/actions/stop_runner` | Stop runner and detach EventBridge |
| POST | `/api/actions/refresh_journal` | Reconnect JournalReader |
| POST | `/api/actions/clear_logs` | Clear in-memory log buffer |

### WebSocket
| Protocol | Path | Description |
|---|---|---|
| WS | `/ws/events` | Real-time event stream |

---

## WebSocket Protocol

```
Client connects to ws://localhost:8765/ws/events

Server → Client:
  [connect]  recent events (up to 100) from ring buffer, each as JSON object
  [connect]  recent log lines (up to 50) as {event_type: "ConsoleLogEvent", ...}
  [stream]   new events as they arrive, each as JSON object
  [idle]     every 30s: {"event_type": "Heartbeat", "ts": <float>}

Client → Server (optional):
  {"cmd": "filter", "types": ["CandidateTradeEvent", "PanelApprovedProposalEvent"]}
  {"cmd": "clear_filter"}
  {"cmd": "ping"}

Disconnect:
  WebSocketDisconnect caught; client queue removed from bridge
```

All event objects include at minimum: `event_type`, `event_id`, `timestamp`, `source`.

---

## Log Capture Pipeline

```
Any Python logger.info/warning/error/debug(...)
  └─ root logger
       └─ ConsoleLogHandler.emit(record)
            └─ LogLine(record)  →  LogBuffer._buf.append()
                                       [deque maxlen=2000, thread-safe]

/api/logs (GET)
  └─ LogBuffer.recent(limit)  →  list[dict]

/ws/events (connect)
  └─ LogBuffer.recent(50)  →  sent as ConsoleLogEvent

/api/actions/clear_logs (POST)
  └─ LogBuffer.clear()
```

The handler is installed at level DEBUG before any other module import in `server.py`. This means import-time logging, startup messages, and all runtime component logs are captured. The handler never raises exceptions to avoid interfering with the application.

---

## Security Model

The console is designed for local operator use only:

- Default bind address: `127.0.0.1` (loopback only)
- No authentication, no session management, no API keys
- CORS set to `allow_origins=["*"]` (acceptable for loopback-only binding)
- No HTTPS (loopback transport is not exposed to the network by default)
- Paper trading only: `ModeGate.SHADOW` enforced by the runtime; no live order placement possible from the console
- All console-initiated write actions (start runner, run replay, run tests) are scoped to in-process state; no external systems are modified
- The journal is opened read-only; the console cannot corrupt trading records

To expose the console on a non-loopback interface, use `--host 0.0.0.0` explicitly and add appropriate network-level access controls.

---

## Deployment Model

```
python launch_console.py [--port 8765] [--host 127.0.0.1]
```

- Single Python process
- Single asyncio event loop (uvicorn manages it)
- No external services required (no Redis, no message broker, no separate DB server)
- The runner, event bridge, journal reader, test runner, and replay manager all run in the same process
- Background asyncio tasks handle the live runner polling loop, test subprocess, and replay harness
- The console can run with or without the runner being active
- Restart is clean: all state is in-memory and reconstructed from the journal DB on reconnect

Dependencies: `fastapi`, `uvicorn`, `websockets` (or `websockets` via uvicorn extras). All other dependencies are already present for the trading system.
