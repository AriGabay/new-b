# Operator Actions and Safety

**System:** BTC/Bybit Paper Trading — Management Console
**Phase:** 6
**Date:** 2026-03-29

---

## Overview

The management console exposes a bounded set of operator actions. Each action is classified by its scope, reversibility, and potential impact. No action available from the console can place live orders, modify trading rules, or bypass the runtime safety gates. This document enumerates every action and its safety classification.

---

## Complete Action List

### 1. Start Simulation Runner

**Endpoint:** `POST /api/actions/start_runner` with `{"simulation_mode": true}`

**What it does:**
- Imports and instantiates `BtcBybitPaperRunner(simulation_mode=True, journal_db_path=...)`
- Calls `runner.setup()` — wires all 9 active groups, instantiates the 20-trader panel, connects the journal writer, and attaches JournalExtension
- Attaches `EventBridge` to the runner's `EventBus` (subscribes 12 event types)
- Does NOT start the bar-polling loop (simulation mode only)

**Exchange connectivity:** None. No Bybit credentials are read or used. No network calls to Bybit are made.

**Writes to DB:** No. `setup()` does not write to `journal.db`. Writes only occur when the pipeline processes a setup packet (which requires bar injection or a replay).

**Risk classification:** Safe. This is the recommended starting mode for all development and observation.

**Reversibility:** Fully reversible. Stop Simulation Runner tears down cleanly.

**Confirmation required:** No.

---

### 2. Start Live Runner

**Endpoint:** `POST /api/actions/start_runner` with `{"simulation_mode": false}`

**What it does:**
- Imports and instantiates `BtcBybitPaperRunner(simulation_mode=False, journal_db_path=...)`
- Calls `runner.setup()` — same as simulation mode
- Starts `runner.run_paper_loop()` as a background asyncio task
- `run_paper_loop()` attempts Bybit WebSocket connectivity for live price feeds

**Exchange connectivity:** Yes — attempts to connect to Bybit. Requires valid Bybit API credentials and network access. In the current development environment, this connection is restricted and will fail.

**Mode gate:** The runtime enforces `ModeGate.SHADOW`. This means the runner operates in paper trading mode only. No real order is placed on any exchange at any time. The system will simulate fills and manage a virtual portfolio but will not submit orders to Bybit's order management system.

**Writes to DB:** Yes — once the live polling loop is running and the pipeline processes setups, `journal.db` will be written to (same tables as replay).

**Risk classification:** Low risk (paper trading only). Requires Bybit connectivity which is unavailable in the current environment.

**Reversibility:** Fully reversible. Stop Runner cancels the polling task and calls `runner.teardown()`.

**Confirmation required:** Yes — the UI requires explicit confirmation before starting live mode.

---

### 3. Stop Runner

**Endpoint:** `POST /api/actions/stop_runner`

**What it does:**
- Detaches the `EventBridge` from the `EventBus` (unsubscribes all 12 callbacks)
- Cancels the runner's background task (if live mode)
- Calls `runner.teardown()` — the runtime's own shutdown sequence
- Nulls the runner reference in `RunnerManager`

**Exchange connectivity:** None initiated. If the runner had a live Bybit connection, teardown closes it.

**Writes to DB:** Teardown may flush any pending journal writes from the runtime's write buffer. This is a clean commit, not a truncation or deletion.

**Risk classification:** Safe. Can be run at any time. The runtime's teardown is designed to be called during a clean shutdown.

**Reversibility:** Fully reversible. The runner can be restarted immediately.

**Confirmation required:** No.

---

### 4. Refresh Journal Connection

**Endpoint:** `POST /api/actions/refresh_journal`

**What it does:**
- Closes the existing `JournalReader` SQLite connection
- Reopens the connection to `src/data/journal.db` in read-only WAL mode
- Returns `{"ok": true}` on success, `{"ok": false}` if the DB file is not found

**Writes to DB:** No. The reader opens with `mode=ro` (read-only). No writes are possible.

**Risk classification:** Safe. Purely a connection refresh for the console's read-only reader.

**Use case:** After a replay run or after the runner has been active for a session, click this to ensure the JournalReader picks up any new tables or rows.

**Confirmation required:** No.

---

### 5. Clear Log Buffer

**Endpoint:** `POST /api/actions/clear_logs`

**What it does:**
- Calls `LogBuffer.clear()` on the global in-memory ring buffer
- All previously captured log lines are discarded from the console's memory

**Writes to DB:** No.

**Affects files:** No. The log buffer is entirely in-memory. This does not affect uvicorn's own console output, any log files, or the journal.

**Risk classification:** Safe. Has no effect on the runtime, journal, or any external system.

**Reversibility:** Not reversible — cleared lines are gone from the console buffer. New lines continue to be captured immediately.

**Confirmation required:** No.

---

### 6. Export Logs

**Endpoint:** Triggered by the "Export Logs" button in the UI, which downloads `/api/logs?limit=2000` as a JSON file.

**What it does:**
- Fetches the current log buffer (up to 2000 lines) as a JSON array
- Triggers a browser file download

**Writes to DB:** No.

**Risk classification:** Safe. File download only.

**Confirmation required:** No.

---

### 7. Run Tests

**Endpoint:** `POST /api/tests/run` with optional `{"files": [...]}`

**What it does:**
- Launches `python -m pytest --tb=short -q` as a subprocess
- Runs against the specified test files (or all 8 known test files)
- Sets `PYTHONPATH=src/`
- Streams output to in-memory `TestRunResult`

**Exchange connectivity:** None. Tests use the real codebase but do not initiate Bybit connections.

**Writes to DB:** Some tests use in-memory SQLite fixtures. The test suite does not write to `src/data/journal.db` unless a specific test explicitly targets it (the current 8 test files do not do this; they use isolated fixtures).

**Risk classification:** Safe. Read-only against the real codebase. The subprocess runs tests that were already validated as passing (244 tests, all green).

**Parallelism:** The test subprocess is independent of the running runner. Both can run simultaneously.

**Confirmation required:** No.

---

### 8. Run Replay

**Endpoint:** `POST /api/replay/run` with `{"fixture_id": "...", "harness_type": "..."}`

**What it does (TrueReplayHarness):**
- Imports and instantiates `TrueReplayHarness`
- Calls `harness.setup()` — sets up the full real pipeline (same components as the live runner)
- Loads the specified fixture (e.g. `btc_bear_continuation`)
- Calls `harness.run_fixture(fixture)` — processes all fixture bars through the complete pipeline
- Calls `harness.teardown()`

**What it does (RuntimeReplayHarness):**
- Imports and instantiates `RuntimeReplayHarness`
- Calls `harness.run_sequence(n_bars=8, symbol="BTCUSDT")` — runs 8 synthetic bars

**Exchange connectivity:** None. Neither harness connects to Bybit. Market data comes from the fixture, not a live feed.

**Writes to DB:** Yes — `TrueReplayHarness` runs the full pipeline including `JournalExtension`, which writes to `src/data/journal.db` (same tables as a live run: `setup_packets`, `trader_reviews`, `panel_summaries`, `final_decisions`). `RuntimeReplayHarness` may also write if it reaches the journal path.

**Risk classification:** Low risk. No exchange interaction. The journal writes are real and expected — they populate the tables that the Journal Browser and Pipeline Trace display. The writes follow the same append-only policy as live runs.

**Current known results:**
- `btc_bear_continuation` + `TrueReplayHarness`: 0 positions opened (expected — fixture does not meet entry threshold)
- `RuntimeReplayHarness`: 0 positions opened (H3-005 trigger not validated in replay fixtures)

**Confirmation required:** No.

---

## Actions NOT Available from the Console

The following actions do not exist in the console and cannot be added without modifying the runtime:

| Action | Why not available |
|---|---|
| Place a live order | Runtime enforces ModeGate.SHADOW; no order submission path exists |
| Modify panel threshold (approve_threshold, min_avg_score) | Threshold is a runtime configuration constant; not an API parameter |
| Override a trader's vote or score | Trader evaluations are produced by the runtime's deterministic logic |
| Modify risk rules | Risk rules (9 active rules) are compile-time logic in RiskLeverageGroup |
| Bypass Layer B (panel gate) | Panel gate is enforced by PanelDecisionGroup; no bypass endpoint exists |
| Bypass Layer C (risk gate) | Risk gate is enforced by RiskLeverageGroup; no bypass endpoint exists |
| Delete journal records | JournalReader is read-only; writer follows append-only policy |
| Modify eligible symbols | Universe is determined by the runtime's UniverseGroup logic |
| Change the runner's position sizing | Position sizing is computed by RiskLeverageGroup; not configurable at runtime |
| Cancel a running position | No position management endpoint exists; positions are managed by ExitGroup |

---

## Safety Gates in the Runtime (Enforced by Runtime, Not Console)

These are runtime protections that exist regardless of console actions:

### ModeGate.SHADOW

The runner operates in `SHADOW` mode, not `LIVE` mode. In SHADOW mode the system simulates fills using the current market price but does not submit any order to the Bybit OMS. This gate is enforced at the order submission layer and cannot be changed from the console.

### Panel Gate (Layer B)

A proposal only proceeds to risk evaluation if:
- At least 14 of 20 traders vote "approve" (`approve_threshold = 14`)
- The average trader score is at least 6.5 (`min_avg_score = 6.5`)

If either condition fails, the proposal is blocked and no position is considered. This gate is enforced by `PanelDecisionGroup`. The console cannot lower these thresholds.

### Risk Gate (Layer C) — 9 Rules

`RiskLeverageGroup` enforces 9 independent risk rules. A position is only opened if all applicable rules pass. The console cannot bypass, disable, or modify any rule. The rules cover:

1. Maximum position count (no more than N open positions)
2. Daily loss limit (halt if daily P&L exceeds drawdown threshold)
3. Maximum drawdown (halt if portfolio drawdown exceeds limit)
4. Consecutive loss limit (reduce size after N consecutive losses)
5. Risk per trade limit (maximum % of equity at risk per position)
6. Leverage limit (maximum leverage multiplier)
7. Regime gate (no entries in unfavourable macro regime)
8. Volatility gate (no entries when volatility is outside acceptable range)
9. Cooldown rule (minimum time between entries after a loss)

### Append-Only Journal Policy

The journal DB enforces append-only semantics at the application layer. `JournalDB` and `JournalExtension` only issue `INSERT` statements (and `UPSERT` for calibration/family/specialist records). The console's `JournalReader` is additionally constrained to `mode=ro` at the SQLite connection level.

---

## Confirmation Requirements

| Action | Confirmation required | Reason |
|---|---|---|
| Start Simulation Runner | No | Fully safe, no exchange connectivity |
| Start Live Runner | Yes | Initiates Bybit connectivity (even though paper only) |
| Stop Runner | No | Safe teardown |
| Refresh Journal | No | Read-only |
| Clear Logs | No | In-memory only |
| Export Logs | No | File download |
| Run Tests | No | Subprocess, no state modification |
| Run Replay | No | Real pipeline, no exchange connectivity |

The "Start Live Runner" confirmation dialog in the UI displays the current mode gate status and reminds the operator that connectivity to Bybit is required.

---

## What Cannot Be Done from the Console (by Design)

The console's design philosophy is:

> **Observe, read, and launch. Never write trading state. Never bypass safety gates.**

The console is an observability and orchestration layer. The runtime is the source of truth for all trading decisions. The boundary between the two is enforced by the code: `RunnerManager` only calls `setup()`, `teardown()`, and attribute reads. `JournalReader` only issues `SELECT`. `EventBridge` only subscribes to events. No console module imports or calls any trading-decision function directly.

This design means that a bug in the console (e.g. a malformed API response, a WebSocket disconnect, a crashed test run) cannot corrupt trading state, misfire an order, or alter the pipeline's behaviour. The runtime operates independently of whether the console is connected.
