# OBSERVABILITY AND CONSOLE READINESS
**Date:** 2026-03-29

---

## MANAGEMENT CONSOLE ASSESSMENT

**Verdict: REAL and sufficiently functional for Phase 7 work.**

The management console is not mock infrastructure. It is a running FastAPI server with
real endpoints that read real system state, real DB records, and real runtime events.

---

## CONSOLE COMPONENTS

### FastAPI Server
**File:** src/console/server.py
**Entry point:** launch_console.py

Endpoints verified to exist (read code directly):
- `GET /api/status` — RunnerManager status + mode
- `GET /api/state` — SystemState snapshot (equity, positions, mode)
- `GET /api/groups` — per-group running status
- `GET /api/logs` — ring buffer of recent log lines (log_capture.py)
- `GET /api/journal/stats` — DB row counts per table
- `GET /api/journal/trades` — closed trade records
- `GET /api/journal/signals` — signal emission records
- `GET /api/journal/panels` — panel summary records
- `GET /api/journal/decisions` — final decision records
- `GET /api/journal/reviews` — trader verdict records (by packet_id)
- `GET /api/journal/packets` — setup packet records
- `GET /api/journal/attributions` — outcome attribution records
- `GET /api/journal/calibration` — trader calibration records
- `GET /api/tests/list` — available test files
- `POST /api/tests/run` — execute a test file, return results
- `GET /api/replay/fixtures` — available replay fixtures
- `POST /api/replay/run` — execute a fixture through real pipeline
- `POST /api/actions/start_runner` — start BtcBybitPaperRunner
- `POST /api/actions/stop_runner` — stop runner
- `WS /ws/events` — real-time event stream via WebSocket

### HTML Frontend
**File:** src/console/static/index.html (confirmed to exist)

### Real-time Event Bridge
**File:** src/console/event_bridge.py
Subscribes to EventBus and forwards events to WebSocket clients.

### Journal Reader
**File:** src/console/journal_reader.py
Queries live JournalDB for all journal endpoint responses.
Reads the same SQLite DB that PerformanceJournalGroup writes to.

### Runner Manager
**File:** src/console/runner_manager.py
Manages BtcBybitPaperRunner lifecycle (start, stop, status).
Provides runner state to /api/status and /api/state.

### Test Runner
**File:** src/console/test_runner.py
Executes pytest on specified test files.
Captures results and makes them queryable via /api/tests/* endpoints.

### Replay Manager
**File:** src/console/replay_manager.py
Manages RuntimeReplayHarness execution.
Feeds fixtures through real runner with real panel + risk logic.
No forced approvals.

### Log Capture
**File:** src/console/log_capture.py
Installs a Python logging handler on import.
Ring buffer available to /api/logs endpoint.

---

## WHAT THE CONSOLE CAN DO FOR PHASE 7

For Phase 7 (calibration/tuning), the console supports:

| Task | Capability | How |
|------|-----------|-----|
| Check system status | YES | /api/status |
| View live portfolio state | YES | /api/state |
| Watch live events | YES | WS /ws/events |
| Inspect panel decisions | YES | /api/journal/panels, /api/journal/decisions |
| Inspect trader verdicts (all 20) | YES | /api/journal/reviews |
| Inspect setup packets | YES | /api/journal/packets |
| Inspect outcome attributions | YES | /api/journal/attributions |
| Inspect trader calibration | YES | /api/journal/calibration |
| Run replay fixtures | YES | /api/replay/run |
| Compare fixture variants | YES | Run multiple, compare in journal |
| Run tests | YES | /api/tests/run |
| Browse closed trade journal | YES | /api/journal/trades |
| Observe log stream | YES | /api/logs |

---

## LIMITATIONS

1. **No graphical charts** — journal data is raw JSON, no visualization layer.
   Acceptable for Phase 7 (data can be extracted and analyzed externally).

2. **Single runner instance** — can only run one replay at a time via the console.
   Multiple replays can be run directly via CLI.

3. **No parameter change UI** — console does not modify thresholds or weights.
   This is by design: parameters are changed in code and validated via test/replay.

4. **Bybit live mode requires clean network** — --run mode cannot be started from dev IP.
   --simulate and replay work fully.

---

## PHASE 7 USABILITY VERDICT

The console is sufficient for Phase 7 operator use. A Phase 7 engineer can:
- Launch replays and observe results
- Inspect panel decision data and trader calibration
- Monitor the runner during paper simulation
- Access all journal data needed for parameter tuning decisions
- Run validation tests before and after tuning changes

The console does not need to be rebuilt or extended before Phase 7 begins.
