# Management Console — Operator User Guide

**System:** BTC/Bybit Paper Trading — Management Console
**Phase:** 6
**Date:** 2026-03-29

---

## Quick Start

```bash
# 1. Navigate to the project root
cd /Users/arigabay/Code/new-b

# 2. Start the console
python launch_console.py

# 3. Open the UI in a browser
open http://localhost:8765
```

Optional arguments:
```bash
python launch_console.py --port 8080         # use a different port
python launch_console.py --host 0.0.0.0      # expose on all interfaces (use with caution)
python launch_console.py --reload            # enable auto-reload for development
```

The server binds to `127.0.0.1:8765` by default. All traffic stays on loopback.

---

## UI Layout

The console is a single-page application with a navigation bar at the top. Each section is accessed by clicking its tab. Sections that require the runner to be active are noted below.

Navigation tabs: **Overview** | **Live Events** | **Pipeline Trace** | **Groups Monitor** | **Panel Inspector** | **Replay Control** | **Test Runner** | **Journal Browser** | **Actions**

---

## Section Walkthroughs

### 1. Overview

The primary at-a-glance status panel. Loads automatically and polls every 5 seconds.

**7 stat cards:**
- Runner Status — running/stopped, simulation or live mode
- Mode — simulation / live / stopped
- Equity — current portfolio equity in USD (live when runner active, unavailable when stopped)
- Open Positions — count of currently open positions
- Daily P&L — today's realised + unrealised P&L in USD
- Drawdown — current drawdown from high-water mark as a percentage
- Consecutive Losses — count of consecutive losing trades

**Groups grid:** Shows all 13 groups (9 active, 4 excluded) with their current status. When the runner is stopped, active groups show "unknown". When running, they show "active".

**Regime / Risk / Journal stats:** Three additional stat rows showing the current market regime (btc_macro, trending, volatility regime, ADX), risk gate state (halted, halt reason, size reduction), and journal record counts (total trades, wins, losses, signals, events, panel summaries).

**What requires the runner:** Equity, positions, P&L, drawdown, regime, and risk stats all require the runner to be started. Journal stats are always available if the DB exists.

---

### 2. Live Events

Real-time stream of all EventBus events from the runtime, displayed as a scrolling list.

**Type filter:** A row of toggle buttons for each of the 12 event types. Click a type to show only that type. Click again to clear the filter. Multiple types can be selected.

**Search filter:** A text input that filters visible events by substring match on the serialised event content.

**Pause / Resume:** The Pause button freezes the display at the current scroll position. New events continue arriving in the background. Resume restores live scrolling.

**Event cards:** Each event shows its type (colour-coded), timestamp, source, and key fields. Click an event to expand and see the full JSON payload.

**On connect:** The WebSocket delivers up to 100 recent events immediately, so the stream is pre-populated even if you navigate to this tab after the runner has been running for a while.

**What requires the runner:** The live event stream only flows when the runner is active and the EventBridge is attached. The recent history (ring buffer) is always available.

---

### 3. Pipeline Trace

Shows the complete decision trace for each setup packet: from market data through panel voting through risk to position open/close.

**Packet list (left panel):** Lists setup packets from the journal ordered by most recent. Each entry shows packet ID, symbol, timeframe, and bar timestamp. Click a row to load its trace.

**Trader grid (centre):** When a packet is selected, a 20-trader grid appears. Each cell shows the trader name, vote (approve/reject/abstain), score (1–10), and confidence. Green = approve, red = reject, grey = abstain.

**Proposal detail (right panel):** Shows the panel summary for the selected packet: approve count, reject count, abstain count, average score, weighted score, panel recommendation, key risks, and key strengths. Below that, if a final decision exists, it shows the decision (enter/hold), safety rails triggered, rationale, and whether a trade was opened.

**How to trace a complete path:**
1. Select a packet from the list
2. Read the trader grid to understand which traders approved/rejected and why (hover or click a trader cell for their reasons)
3. Read the panel summary to see the aggregate decision
4. If the panel recommended "enter", check the final decision panel for safety rail outcomes
5. If a trade was opened, the packet row shows a trade ID — use the Journal Browser Trades tab to see the outcome

**What requires the runner/replay:** Setup packets only exist after the runner or a replay has run. An empty list means no packets have been generated yet.

---

### 4. Groups Monitor

Shows the active and excluded group grids with their current status.

**Active groups (9):** MarketDataGroup, IndicatorsGroup, CandlestickGroup, TechnicalStructureGroup, EntryGroup, PanelDecisionGroup, RiskLeverageGroup, ExitGroup, PerformanceJournalGroup. Each shows its current status and a note.

**Excluded groups (4):** ChartPatternGroup, NewsMacroGroup, HistorianAgent, CriticAgent. These are excluded by design in Phase 3 and shown greyed out.

This section is informational. Group statuses update with the runner status; when the runner is not started all active groups show "unknown".

---

### 5. Panel Inspector

Provides a 20-trader grid with individual trader performance history.

**Trader grid:** All 20 traders displayed as cards. Each card shows the trader name, their most recent vote, score, and confidence from the last packet evaluation.

**Trader history:** Click any trader card to expand a history view showing all of that trader's reviews from the journal: per-packet vote, score, confidence, pro reason, anti reason, and execution concern. This allows tracking whether individual traders are consistently approve-biased, reject-biased, or well-calibrated.

**Calibration data:** If calibration records exist in the journal (populated after replay or live runs complete learning cycles), a calibration summary shows win rate, accuracy, and any recommended score adjustments per trader.

**What requires the runner/replay:** Trader history only populates after setup packets have been evaluated. A fresh installation shows empty grids.

---

### 6. Replay Control

Launches replay runs through the real runtime pipeline without exchange connectivity.

**Fixture selector:** Dropdown with available fixtures:
- `btc_bear_continuation` — 8-bar fixture used in Phase 5.75 viability audit. Expected: 0 natural entries (weak crossover-only setups).
- `ideal_short_synthetic` — Full-bear EMA alignment, evening_star pattern, R:R=3.5. Expected: 16/20 approve, avg=7.78 → ENTER.

**Harness selector:** Two harness types:
- `TrueReplayHarness` (true_replay) — runs the fixture through the full real pipeline. Writes to journal DB.
- `RuntimeReplayHarness` (simulation) — runs 8 synthetic bars through the runtime simulation mode. Produces 0 natural entries (Phase 6 limitation: H3-005 trigger not yet validated in replay fixtures).

**How to run a replay:**
1. Select a fixture from the dropdown
2. Select a harness type
3. Click "Run Replay"
4. The status card updates with run_id, status (pending → running → done), and progress
5. When done, the summary shows bars run, proposals generated, panel approvals, positions opened

**Live progress:** The progress display polls the `/api/replay/result/{run_id}` endpoint every 2 seconds.

**History:** Previous replay runs for the session are listed below the control panel.

**Important:** The `true_replay` harness writes entries to `src/data/journal.db`. After a successful replay, switch to the Journal Browser to inspect the results.

---

### 7. Test Runner

Runs the project test suite via pytest subprocess.

**File checkboxes:** Lists the 8 known test files. Each shows its path and whether the file exists on disk. Check/uncheck to select which files to run. "Run All" selects all existing files.

**How to run tests:**
1. Check the desired test files (default: all existing files selected)
2. Click "Run Tests"
3. A live output terminal appears, streaming pytest output line by line
4. When complete, a pass/fail summary card shows: passed count, failed count, return code

**Live output:** Output is streamed via polling `/api/tests/result/{run_id}` every 1 second during the run.

**Pass/fail summary:** Parsed from the final pytest summary line (e.g. "22 passed in 1.31s").

**History:** Previous runs for the session are listed with their summaries.

**Note:** Tests run in the same Python environment as the server, with `PYTHONPATH` set to `src/`. No mock data is injected; tests run against the real codebase.

---

### 8. Journal Browser

Read-only browser for all journal database tables. Organised into 7 tabs.

**Trades tab:**
- Shows all trades ordered by opened_at descending
- Columns: trade_id, symbol, direction, entry_price, stop_price, target_price, position_size_usd, outcome (win/loss/breakeven/open), opened_at, closed_at, pnl_r
- Filter by outcome using the dropdown (win / loss / breakeven / open)
- Pagination: use Previous/Next buttons, adjustable page size

**Signals tab:**
- All signals from all groups ordered by timestamp descending
- Filter by group_id using the dropdown
- Columns: signal_id, group_id, symbol, timeframe, direction, signal_type, signal_subtype, quality_score, trade_id

**Events tab:**
- All `journal_events` records ordered by timestamp descending
- Filter by event_type
- Columns: event_id, timestamp, event_type, source, severity, payload (JSON)

**Panels tab:**
- Panel summaries from the learning extension (requires at least one replay or live run)
- Columns: panel_id, packet_id, approve_count, reject_count, abstain_count, avg_score, panel_recommendation, evaluated_at, trade_id
- Empty if no replay has run

**Decisions tab:**
- Final decisions from the learning extension
- Columns: decision_id, packet_id, panel_id, decision, safety_rails_triggered, rationale, decided_at
- Empty if no replay has run

**Packets tab:**
- Setup packets from the learning extension
- Columns: packet_id, symbol, timeframe, bar_timestamp, stored_at, outcome_source, trade_id
- Click a row to navigate to the Pipeline Trace for that packet

**Calibration tab:**
- Trader calibration records (UPSERT table — one row per trader per outcome_source)
- Shows win rate, accuracy, suggested score adjustments
- Only populated after learning cycles have run

**Refresh:** The "Refresh Journal" button (also in the Actions section) reconnects the JournalReader to pick up any new data written since the server started or since the last reconnect.

---

### 9. Actions

The control panel for system-level operations.

**Start Simulation Runner:**
- Starts `BtcBybitPaperRunner` in `simulation_mode=True`
- No exchange connectivity; in-memory state; safe at all times
- Button is disabled when the runner is already running

**Start Live Runner:**
- Starts `BtcBybitPaperRunner` in `simulation_mode=False`
- Requires Bybit connectivity (restricted in the current development environment)
- Paper trading only: system enforces `ModeGate.SHADOW` — no real orders are placed
- Button is disabled when the runner is already running

**Stop Runner:**
- Gracefully stops the runner and detaches the EventBridge
- Safe; can be run at any time when the runner is active

**Refresh Journal:**
- Reconnects the `JournalReader` to `src/data/journal.db`
- Safe; read-only operation; useful after a replay has written new data

**Clear Logs:**
- Clears the in-memory log ring buffer
- Safe; only affects the console's in-memory view; does not affect any DB or file

**Export Logs:**
- Downloads the current log buffer as a JSON file
- Safe; file download only

---

## Starting the Runner from the UI

1. Navigate to the **Actions** tab
2. Click **Start Simulation Runner**
3. The status card shows "starting..." and then transitions to "running (simulation)"
4. Navigate to the **Overview** tab — equity, positions, and regime stats are now live
5. Navigate to **Live Events** — the event stream is now active

If the runner fails to start (import error, configuration error), the error message is displayed in the status card and written to the log buffer. Check the **Live Events** tab (filter for ConsoleLogEvent) or the **Actions** tab status area for details.

---

## Running a Replay from the UI

1. Navigate to **Replay Control**
2. Select fixture: `btc_bear_continuation` or `ideal_short_synthetic`
3. Select harness: `TrueReplayHarness` for a full pipeline run with journal writes
4. Click **Run Replay**
5. Watch the status card: `pending` → `running` → `done`
6. When done, read the summary (bars, proposals, approvals, opens)
7. Click **Refresh Journal** in Actions, then navigate to **Journal Browser** to see the written records
8. Navigate to **Pipeline Trace** to inspect the packet-level decision trail

---

## Running Tests from the UI

1. Navigate to **Test Runner**
2. Leave all checkboxes checked (default: all existing files)
3. Click **Run Tests**
4. Watch the live output terminal — pytest output streams in real time
5. When done, the summary card shows pass/fail counts
6. To run a single file, uncheck all others first

A passing full run produces output similar to: `244 passed in N.NNs`

---

## How to Read the Event Stream

The event stream in **Live Events** uses colour coding to distinguish event types:

| Colour | Event types |
|---|---|
| Blue | BarCloseEvent, FeatureReadyEvent |
| Green | PositionOpenEvent, PanelApprovedProposalEvent |
| Red | PositionCloseEvent, RiskDecisionEvent (block) |
| Yellow | SystemAlertEvent, DataQualityAlert |
| Grey | GroupSignalEvent, JournalEntryEvent, UniverseUpdateEvent, ConsoleLogEvent |

To focus on trade decisions: filter to `CandidateTradeEvent`, `PanelApprovedProposalEvent`, `RiskDecisionEvent`, `PositionOpenEvent`, `PositionCloseEvent`.

To see market data flow: filter to `BarCloseEvent`, `FeatureReadyEvent`, `GroupSignalEvent`.

To see system health: filter to `SystemAlertEvent`, `DataQualityAlert`.

Use the search box to find a specific symbol, proposal ID, or trade ID across all visible events.

---

## Reading the Journal Browser

**If all tables are empty:** The runner has never run, no replay has been executed, and no tests have written to the DB. Run a replay using the Replay Control tab, then click Refresh Journal.

**Trades table empty but journal_events has rows:** The pipeline has processed bars but no proposals reached the entry threshold. This is the expected state for the `btc_bear_continuation` fixture with `TrueReplayHarness`.

**Panel / Decision / Packet tabs empty:** The learning extension tables (`setup_packets`, `trader_reviews`, `panel_summaries`, `final_decisions`) are only written by the `JournalExtension` component, which is wired by the runner when it starts. They are populated during replay runs that use `TrueReplayHarness` or during live simulation.

**Calibration tab empty:** Calibration records accumulate over multiple runs. They are empty on first use.

---

## What the Panel Inspector Shows

The Panel Inspector provides per-trader granularity that is not visible in the Overview or Events sections.

Each of the 20 traders is a named specialist agent in the `PanelDecisionGroup`. They review each setup packet independently and produce a verdict (approve/reject/abstain), a score (1–10), and a confidence value (0.0–1.0), along with pro/anti reasons and execution concerns.

The panel passes a proposal if: approve_count >= 14 AND avg_score >= 6.5.

The inspector allows you to see:
- Which traders are systematically optimistic or pessimistic
- Which traders tend to abstain (indicating low confidence in a setup type)
- Whether individual traders' concerns align with actual trade outcomes (via outcome column in history)

This is the primary tool for understanding why the panel approved or blocked a specific trade.

---

## Keyboard and UX Tips

- The Overview section auto-refreshes every 5 seconds. No manual refresh needed during active runs.
- The Live Events section auto-scrolls to new events unless paused. Use Pause when reading a specific event.
- In the Journal Browser, use pagination for tables with many rows. Default page size is 50 rows.
- In the Pipeline Trace, clicking a packet row also updates the URL with the packet_id for bookmarking.
- The Test Runner live output scrolls automatically. The output is preserved for the session even after the run completes.
- Replay results persist for the server session. If you restart the server, history is cleared.

---

## Runner Stopped vs Running

| Feature | Runner stopped | Runner running |
|---|---|---|
| Overview stat cards | Equity/positions/regime: unavailable | All live |
| Live Events stream | Ring buffer history only | Live events |
| Pipeline Trace | Journal records (if any) | Journal + live events |
| Groups Monitor | All active groups: "unknown" | Groups: "active" |
| Panel Inspector | Journal records (if any) | Journal + live |
| Replay Control | Available (self-contained) | Available (concurrent) |
| Test Runner | Available (self-contained) | Available (concurrent) |
| Journal Browser | Available (reads DB) | Available (reads DB) |
| Actions: Start | Available | Disabled |
| Actions: Stop | Disabled | Available |

---

## Known Limitations and Caveats

- **Live Bybit connectivity:** The "Start Live Runner" action requires Bybit API access. In the current development environment, Bybit is not reachable. Simulation mode always works.
- **Journal tables empty on first run:** `setup_packets`, `trader_reviews`, `panel_summaries`, `final_decisions`, and `calibration_records` are empty until a replay or live run generates decisions. The base tables (`trades`, `signals`, `journal_events`) may also be empty before any run.
- **Replay produces 0 entries for btc_bear_continuation:** This is expected and correct. The 8-bar bear continuation fixture does not produce setups that clear the entry threshold. This is a validation result, not a bug.
- **Simulation harness (RuntimeReplayHarness) produces 0 entries:** The H3-005 trigger is not validated in current replay fixtures. Expected by design.
- **Log buffer is in-memory:** The log buffer is lost on server restart. For persistent logs, redirect uvicorn output to a file.
- **No P&L chart:** A position-level P&L time series chart is not implemented. The equity value in the Overview is a point-in-time snapshot.
- **No authentication:** The console has no login requirement. It should only be accessible on loopback (default) or a trusted network.
- **Test results and replay results reset on server restart:** All in-memory run history is lost when the server restarts.
