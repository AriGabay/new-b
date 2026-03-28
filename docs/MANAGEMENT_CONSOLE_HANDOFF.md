# Management Console — Handoff Document

**System:** BTC/Bybit Paper Trading — Management Console
**Phase:** 6
**Date:** 2026-03-29

---

## What Was Built

The management console is a complete operator interface for the BTC/Bybit paper trading system. It was built as 7 Python modules plus one launcher, with a single self-contained HTML/CSS/JS UI file.

### File inventory

| File | Role |
|---|---|
| `src/console/server.py` | FastAPI app — 35 routes, lifespan, WebSocket handler |
| `src/console/log_capture.py` | ConsoleLogHandler → 2000-line ring buffer |
| `src/console/event_bridge.py` | EventBus subscription → 1000-event ring buffer → WS broadcast |
| `src/console/journal_reader.py` | Read-only WAL SQLite access to journal.db |
| `src/console/runner_manager.py` | BtcBybitPaperRunner lifecycle (start/stop/status/state) |
| `src/console/test_runner.py` | pytest subprocess launcher, result storage |
| `src/console/replay_manager.py` | TrueReplayHarness + RuntimeReplayHarness launcher |
| `src/console/static/index.html` | Complete operator UI (HTML/CSS/JS, no framework, no build step) |
| `launch_console.py` | Root-level launcher: `python launch_console.py [--port 8765]` |

No external services are required. No build step. No npm. No separate database server. Single Python process.

---

## What Is Proven Working

The following was verified via smoke test on 2026-03-29:

### Server startup
- `python launch_console.py` starts cleanly on port 8765
- UI served at `http://localhost:8765` — HTML renders, all 9 sections accessible
- Log capture installed before any other import — startup logs captured immediately

### Runner lifecycle
- `POST /api/actions/start_runner` with `{"simulation_mode": true}` — runner starts successfully
- `BtcBybitPaperRunner` imported and `setup()` called with no errors
- `GET /api/status` — returns running=true, mode=simulation, event_bridge_attached=true
- `GET /api/state` — returns live SystemState with equity, portfolio, regime, risk (available=true)
- `POST /api/actions/stop_runner` — runner stopped cleanly, bridge detached

### EventBridge
- After runner start, bridge attaches to runner.bus
- 12 event types subscribed
- WebSocket `/ws/events` — ring buffer history delivered on connect
- Events visible in Live Events tab

### Log capture
- All Python log output flows to ring buffer
- `GET /api/logs` returns structured log lines
- Log lines visible in UI with level/name/message fields

### Journal reads
- `GET /api/journal/stats` — returns table list and counts
- All 10 journal endpoints return valid responses
- `src/data/journal.db` opened in WAL read-only mode

### Test runner
- `POST /api/tests/run` with `{"files": ["src/tests/test_entry_policy_viability.py"]}` — run started
- Output streamed to result object
- Result: 22 passed in 1.31s, return_code=0

### Replay
- `GET /api/replay/fixtures` — returns both fixture definitions
- `POST /api/replay/run` with `btc_bear_continuation` + `true_replay` — run completes
- Result: bars=8, proposals=0, approvals=0, opens=0 (expected — fixture does not meet entry threshold)

---

## UI-to-System Connection Matrix

| UI section / widget | Real data source | Real action | Runtime dependency | Status | Limitations |
|---|---|---|---|---|---|
| Overview — Runner status | RunnerManager.get_status() | None | None | Working | Static group enumeration |
| Overview — Equity | runner.state.portfolio.equity | None | Runner must be active | Working when active | None when stopped |
| Overview — Positions | runner.state.portfolio.open_positions | None | Runner must be active | Working when active | None when stopped |
| Overview — Daily P&L | runner.state.portfolio.daily_pnl | None | Runner must be active | Working when active | None when stopped |
| Overview — Drawdown | runner.state.portfolio.drawdown_pct | None | Runner must be active | Working when active | None when stopped |
| Overview — Regime | runner.state.regime | None | Runner must be active | Working when active | None when stopped |
| Overview — Risk state | runner.state.risk_state | None | Runner must be active | Working when active | None when stopped |
| Overview — Journal stats | JournalReader.get_stats() | None | DB must exist | Working | Empty if no runs |
| Live Events — stream | EventBridge ring buffer + live queue | None | Runner for live; ring for history | Working | Live only when runner active |
| Live Events — ConsoleLogEvent | LogBuffer.recent() | None | None | Working | In-memory only |
| Pipeline Trace — packets | JournalReader.get_setup_packets() | None | Extension tables | Working structure | Empty until replay/live run |
| Pipeline Trace — trader grid | JournalReader.get_trader_reviews(packet_id) | None | Extension tables | Working structure | Empty until replay/live run |
| Pipeline Trace — panel | JournalReader.get_panel_summaries() | None | Extension tables | Working structure | Empty until replay/live run |
| Groups Monitor | RunnerManager.get_status().groups | None | None | Working | Static; no per-tick health |
| Panel Inspector | JournalReader.get_trader_reviews() + calibration | None | Extension tables | Working structure | Empty until replay/live run |
| Replay Control | ReplayManager | POST /api/replay/run | None | Working | 0 entries for current fixtures |
| Test Runner | TestRunner subprocess | POST /api/tests/run | None | Working | Results in-memory only |
| Journal Browser — trades | JournalReader.get_trades() | None | Base tables | Working | Empty until trades exist |
| Journal Browser — signals | JournalReader.get_signals() | None | Base tables | Working | Empty until signals exist |
| Journal Browser — events | JournalReader.get_journal_events() | None | Base tables | Working | Empty until events exist |
| Journal Browser — panels | JournalReader.get_panel_summaries() | None | Extension tables | Working structure | Empty until replay/live run |
| Journal Browser — decisions | JournalReader.get_final_decisions() | None | Extension tables | Working structure | Empty until replay/live run |
| Journal Browser — packets | JournalReader.get_setup_packets() | None | Extension tables | Working structure | Empty until replay/live run |
| Journal Browser — calibration | JournalReader.get_calibration_records() | None | Extension tables | Working structure | Empty until learning cycles run |
| Actions — Start Simulation | RunnerManager.start(simulation_mode=True) | POST /api/actions/start_runner | None | Working | None |
| Actions — Start Live | RunnerManager.start(simulation_mode=False) | POST /api/actions/start_runner | Bybit connectivity | Blocked (no Bybit access) | Requires network + credentials |
| Actions — Stop Runner | RunnerManager.stop() | POST /api/actions/stop_runner | Runner active | Working | None |
| Actions — Refresh Journal | JournalReader.reconnect() | POST /api/actions/refresh_journal | DB exists | Working | None |
| Actions — Clear Logs | LogBuffer.clear() | POST /api/actions/clear_logs | None | Working | None |
| Actions — Export Logs | /api/logs download | GET /api/logs | None | Working | None |

---

## What Requires the Runner to Be Active

The following features are only functional when the runner has been started:

- Equity, available capital, open positions, daily P&L, drawdown, consecutive losses (from SystemState)
- Current market regime (btc_macro, trending, volatility_regime, ADX)
- Current risk gate state (halted, halt_reason, size_reduction)
- Live event streaming via WebSocket (new events from the EventBus)
- Groups showing "active" instead of "unknown"
- Eligible symbols list

---

## What Works with Runner Stopped

The following features are fully functional regardless of runner state:

- Journal browser (all tabs) — reads from SQLite DB
- Test runner — launches pytest subprocess independently
- Replay control — launches harnesses independently
- Log display — ring buffer is always populated (server logs even with no runner)
- WebSocket ring buffer history — recent events from the last session
- Overview stat cards (graceful "unavailable" display)
- Actions — Refresh Journal, Clear Logs, Export Logs

---

## Known Gaps

### No authentication
The console has no login, no API keys, no session tokens. It is designed for local loopback access only. Default bind is `127.0.0.1`. Do not expose on `0.0.0.0` in any environment accessible to untrusted users without adding a reverse proxy with authentication.

### No live Bybit connectivity
The development environment does not have Bybit network access. "Start Live Runner" will fail at the connectivity step. Simulation mode works fully. Live mode requires Bybit API credentials configured in the runtime and network access to Bybit WebSocket endpoints.

### Journal tables empty until runs happen
On a fresh installation, `src/data/journal.db` may not exist, or may exist with only base tables from a previous session. The 6 learning extension tables (`setup_packets`, `trader_reviews`, `panel_summaries`, `final_decisions`, `outcome_attributions`, `calibration_records`) are only populated when:
- A `TrueReplayHarness` run completes with at least one setup packet evaluated, OR
- The live runner processes at least one bar that generates a candidate trade

Running `btc_bear_continuation` with `TrueReplayHarness` populates the tables structurally (rows are written) but produces 0 panel approvals (the fixture does not meet the entry threshold).

### No position P&L chart
There is no equity curve chart or position-level P&L time series. The Overview shows point-in-time snapshots. A chart would require a persistent time series store (not implemented).

### Test results and replay results reset on restart
All in-memory run history is lost when the server process is restarted. If result persistence is needed, the `TestRunResult` and `ReplayRunResult` objects would need to be written to a file or DB.

### Group health is static enumeration
The Groups Monitor shows "active" for all 9 active groups when the runner is running, but does not poll individual group health or error state per tick. Errors surface via `SystemAlertEvent` in the event stream.

### Log persistence
The 2000-line log ring buffer is not written to disk. For persistent logs, redirect uvicorn's output: `python launch_console.py 2>&1 | tee console.log`.

---

## What Was NOT Done

This is an explicit record of what was intentionally excluded:

- **No mock data.** Every data source is the real runtime, the real journal DB, or a real test execution. There are no hardcoded example responses, no synthetic data in the UI, no fake event generators.
- **No fake wiring.** The EventBridge subscribes to the real EventBus. The JournalReader queries the real journal.db. The RunnerManager instantiates the real runner class.
- **No artificial bypasses.** The console cannot lower the panel threshold, skip the risk gate, or force-enter a trade. The runtime safety gates are untouched.
- **No UI framework.** The frontend is plain HTML/CSS/JS. No React, Vue, Angular, or any build tooling.
- **No database beyond what already exists.** The console uses the existing `journal.db`. No additional databases or caches.

---

## Next Steps for Serious Operational Use

If this console is to be used as a serious operational tool beyond development:

1. **Add authentication.** A simple token-based middleware on the FastAPI app, or a reverse proxy (nginx + basic auth), is sufficient for local network use.

2. **Persist logs.** Add a file handler to the root logger in `launch_console.py` alongside the existing ConsoleLogHandler.

3. **Persist test/replay results.** Write `TestRunResult` and `ReplayRunResult` to the journal DB or a separate SQLite file on completion.

4. **Add a P&L equity curve.** Store periodic snapshots of `portfolio.equity` with a timestamp in a lightweight time-series table. The Overview section can then render a chart.

5. **Wire live Bybit connectivity.** Configure `BYBIT_API_KEY` and `BYBIT_API_SECRET` in the environment. Test the live runner in simulation mode first (which attempts connectivity but trades on paper), then confirm ModeGate.SHADOW is enforced before any further promotion.

6. **Validate `ideal_short_synthetic` fixture end-to-end.** This fixture is designed to produce a panel approval (16/20, avg=7.78). Running it through `TrueReplayHarness` and confirming a `PanelApprovedProposalEvent` appears in the event stream would verify the full pipeline from bar to panel approval.

7. **Add group-level health polling.** Expose a `health()` method on each group and surface it in the Groups Monitor with per-tick timestamps.

8. **Add a risk rule hit dashboard.** Aggregate `RiskDecisionEvent.rule_results` over time to show which rules are triggering most frequently.

---

## How to Verify the Connection Is Real

Follow these steps to confirm the console is connected to the actual runtime (not displaying cached or fake data):

### Step 1 — Start the server and check status

```bash
python launch_console.py
# Open http://localhost:8765
# Navigate to Actions → Start Simulation Runner → click Start
```

Expected: the Overview tab immediately shows `mode: simulation`, `running: true`, and displays a non-zero equity value (the runner initialises with a paper portfolio of default starting equity).

### Step 2 — Watch the event stream

Navigate to **Live Events**. The ring buffer history should appear immediately (server startup logs as ConsoleLogEvent). After clicking "Start Simulation Runner", you should see log events from `console.runner_manager` confirming `runner started. simulation=True` and `EventBridge attached`.

### Step 3 — Check SystemState is live

Navigate to **Overview**. The equity value, available capital, and regime fields should be populated. Refresh the page — the equity value stays consistent (it is the runner's live `portfolio.equity`, not a cache).

### Step 4 — Run a replay and watch the journal populate

1. Navigate to **Replay Control**
2. Select `btc_bear_continuation`, harness `TrueReplayHarness`
3. Click "Run Replay"
4. Wait for status = done
5. Navigate to **Actions** → click "Refresh Journal"
6. Navigate to **Journal Browser** → **Packets** tab

Expected: rows appear in the packets tab. Each row corresponds to one setup packet evaluated by the pipeline during the replay. The `outcome_source` column shows "TrueReplayHarness". This proves the replay ran through the real pipeline and wrote to the real journal.

### Step 5 — Verify log capture is real

Navigate to **Actions** → click "Clear Logs". Navigate to **Overview** to trigger an API call. Navigate back to the log view (Live Events, filter ConsoleLogEvent). Server request logs should appear immediately, confirming that the log capture is live and not cached.

### Step 6 — Verify test runner is real

Navigate to **Test Runner**. Select only `test_entry_policy_viability.py`. Click "Run Tests". Watch the live output — you should see pytest's normal output including the test file names, progress dots, and the final summary line (`22 passed in N.NNs`). The output is real pytest output, streamed in real time from a subprocess.
