# Observability and Event Streaming

**System:** BTC/Bybit Paper Trading — Management Console
**Phase:** 6
**Date:** 2026-03-29

---

## Overview

The management console provides three observability channels:

1. **Real-time event stream** — WebSocket `/ws/events` bridging the runtime EventBus to the browser
2. **Log capture** — All Python log output captured to a ring buffer, accessible via REST and WebSocket
3. **Journal queries** — Read-only SQLite access to all historical records

This document covers the event stream and log capture in detail, including the 12 event types, their fields, the ring buffer mechanics, and how to correlate events across the full trade lifecycle.

---

## The 12 Event Types Bridged to the WebSocket

The `EventBridge` subscribes to exactly these event types from `core.events`:

### 1. BarCloseEvent

Emitted by `MarketDataGroup` when a price bar closes.

Key fields:
- `symbol` — e.g. "BTCUSDT"
- `timeframe` — e.g. "1h", "4h"
- `bar_timestamp` — ISO8601 UTC
- `open`, `high`, `low`, `close` — OHLC prices (float)
- `volume` — bar volume
- `source` — "MarketDataGroup"

Frequency: one per bar close per symbol per timeframe.

---

### 2. FeatureReadyEvent

Emitted by `IndicatorsGroup` when the full feature vector for a bar is ready.

Key fields:
- `symbol`, `timeframe`, `bar_timestamp`
- `feature_vector` — serialised `FeatureVector` dict containing all computed indicators (EMA values, ADX, ATR, RSI, etc.)
- `source` — "IndicatorsGroup"

Frequency: one per bar close after indicators are computed.

---

### 3. GroupSignalEvent

Emitted by any specialist group that detects a signal condition.

Key fields:
- `symbol`, `timeframe`, `bar_timestamp`
- `group_id` — e.g. "CandlestickGroup", "TechnicalStructureGroup", "EntryGroup"
- `signal_type` — e.g. "indicator", "candlestick", "entry_candidate"
- `signal_subtype` — e.g. "evening_star", "ema_crossover", "h3_005"
- `direction` — "LONG" or "SHORT"
- `quality_score` — float 0.0–1.0
- `hypothesis_ref` — research hypothesis identifier (e.g. "H3-005")
- `source` — group name

Frequency: variable; only when a group detects a qualifying condition.

---

### 4. CandidateTradeEvent

Emitted by `EntryGroup` when a candidate setup passes the entry policy filter.

Key fields:
- `proposal_id` — UUID linking this event to later panel/risk events
- `symbol`, `timeframe`, `bar_timestamp`
- `direction` — "LONG" or "SHORT"
- `entry_price`, `stop_price`, `target_price` — float
- `r_amount` — risk amount in USD
- `rr_ratio` — reward-to-risk ratio
- `composite_score` — float, aggregate signal quality
- `hypothesis_refs` — list of contributing hypothesis IDs
- `setup_refs` — list of contributing signal IDs
- `source` — "EntryGroup"

Frequency: rare; only when the full entry policy conditions are met.

---

### 5. PanelApprovedProposalEvent

Emitted by `PanelDecisionGroup` when a proposal clears the panel vote threshold.

Key fields:
- `proposal_id` — matches `CandidateTradeEvent.proposal_id`
- `packet_id` — links to `setup_packets` table
- `approve_count` — integer, must be ≥ 14
- `reject_count`, `abstain_count` — integers
- `avg_score` — float, must be ≥ 6.5
- `weighted_score` — float
- `panel_recommendation` — "enter" or "hold"
- `key_risks` — list of strings
- `key_strengths` — list of strings
- `source` — "PanelDecisionGroup"

Frequency: rare; only when approve_count ≥ 14 AND avg_score ≥ 6.5.

---

### 6. RiskDecisionEvent

Emitted by `RiskLeverageGroup` for every proposal that reaches risk evaluation.

Key fields:
- `proposal_id`
- `decision` — "approve" or "block"
- `rule_results` — dict of rule name → pass/fail
- `halt_triggered` — bool
- `halt_reason` — string or null
- `size_reduction` — float 0.0–1.0 (1.0 = no reduction)
- `leverage` — computed leverage
- `position_size_usd` — float
- `source` — "RiskLeverageGroup"

Frequency: one per approved panel proposal.

---

### 7. PositionOpenEvent

Emitted when a position is opened in the portfolio.

Key fields:
- `trade_id` — UUID; links to `trades` table
- `proposal_id` — links back to the originating candidate
- `symbol`, `direction`
- `entry_price`, `stop_price`, `target_price` — float
- `position_size_usd`, `leverage`, `r_amount`
- `opened_at` — ISO8601 UTC
- `source` — "ExitGroup" or "PerformanceJournalGroup"

Frequency: rare; one per actual position open.

---

### 8. PositionCloseEvent

Emitted when a position is closed.

Key fields:
- `trade_id` — matches `PositionOpenEvent.trade_id`
- `exit_reason` — e.g. "stop_loss", "target_hit", "manual"
- `exit_price` — float
- `pnl_usd`, `pnl_r` — float
- `outcome` — "win", "loss", "breakeven"
- `bars_held` — integer
- `closed_at` — ISO8601 UTC
- `source`

Frequency: one per position close.

---

### 9. JournalEntryEvent

Emitted by `PerformanceJournalGroup` when a record is written to the journal.

Key fields:
- `record_type` — "trade_open", "trade_close", "signal", "event"
- `record_id` — ID of the written record
- `table_name` — destination table name
- `source` — "PerformanceJournalGroup"

Frequency: every journal write operation.

---

### 10. SystemAlertEvent

Emitted by any group when an error, warning, or abnormal condition occurs.

Key fields:
- `severity` — "error", "warning", "info"
- `message` — description of the alert
- `component` — which group or component raised the alert
- `context` — additional context dict
- `source`

Frequency: variable; only on exceptional conditions.

---

### 11. DataQualityAlert

Emitted by `MarketDataGroup` when data quality issues are detected.

Key fields:
- `symbol`, `timeframe`
- `issue_type` — e.g. "missing_bars", "stale_data", "outlier_price"
- `severity` — "error", "warning"
- `details` — dict with specifics
- `source` — "MarketDataGroup"

Frequency: variable; only when data quality checks fail.

---

### 12. UniverseUpdateEvent

Emitted when the set of eligible trading symbols changes.

Key fields:
- `added` — list of newly added symbols
- `removed` — list of removed symbols
- `current_universe` — full current set of eligible symbols
- `reason` — why the universe changed
- `source`

Frequency: infrequent; on universe recalculation events.

---

## Event Ring Buffer

The `EventBridge` maintains a `deque(maxlen=1000)` ring buffer of serialised event dicts. This serves two purposes:

1. **Late-joiner support:** When a new WebSocket client connects, it immediately receives up to 100 recent events from the ring buffer (via `bridge.recent_events(limit=100)`). The client sees context from before it connected without polling.

2. **Short-term history:** The ring holds the last 1000 events. At 1 event per second sustained throughput this covers ~16 minutes of history. At typical trading activity (1 bar per minute with sparse signals) it covers hours.

The ring buffer is in-memory only. It is not persisted across server restarts. Events older than 1000 are evicted automatically by the deque.

The ring buffer is also shared with the log capture layer: the `EventBridge.inject_log_event()` method can push log lines as `ConsoleLogEvent` messages into the same ring, making them available to WebSocket clients alongside real events.

---

## Log Capture

### Architecture

`ConsoleLogHandler` is installed on Python's root logger at server startup (level DEBUG). Every `logging.LogRecord` from any module in the process is intercepted.

```
Any logger.*(...)
  └─ root logger handlers
       └─ ConsoleLogHandler.emit(record)
            └─ LogLine(record) → LogBuffer._buf.append()
                                    [deque maxlen=2000, thread-safe Lock]
```

`LogLine` captures: `ts` (ISO8601 UTC), `level` (DEBUG/INFO/WARNING/ERROR), `name` (Python logger name, e.g. "runtime.runner", "console.server"), `message`, `lineno`.

### Ring Buffer Size

2000 lines. At typical log volume (50–100 lines/minute during active operation) this covers 20–40 minutes of history.

### Access Paths

- **REST:** `GET /api/logs?limit=200&level=WARNING&search=RiskGate` — returns filtered recent lines
- **WebSocket:** On connect, the 50 most recent log lines are sent as `ConsoleLogEvent` objects. Subsequent log lines can be injected into the event stream via `inject_log_event`.
- **Clear:** `POST /api/actions/clear_logs` clears the buffer (in-memory only)

### ConsoleLogEvent

When log lines are injected into the WebSocket stream, they appear as:

```json
{
  "event_type": "ConsoleLogEvent",
  "ts": "2026-03-29T10:00:00.000Z",
  "level": "INFO",
  "name": "console.runner_manager",
  "message": "RunnerManager: runner started. simulation=True",
  "lineno": 104
}
```

These are visually distinct in the Live Events tab (grey colour coding) and can be filtered in or out using the event type filter.

---

## Correlating Events Across the Trade Lifecycle

A complete trade trace uses four linking identifiers:

| Identifier | Where it appears | Links |
|---|---|---|
| `proposal_id` | CandidateTradeEvent, PanelApprovedProposalEvent, RiskDecisionEvent, PositionOpenEvent | The life of one trade proposal |
| `packet_id` | PanelApprovedProposalEvent, setup_packets, trader_reviews, panel_summaries, final_decisions | The stored decision record |
| `trade_id` | PositionOpenEvent, PositionCloseEvent, trades, outcome_attributions | The opened and closed position |
| `event_id` | All events | Unique event instance |

### Full Correlation Example

```
BarCloseEvent (symbol=BTCUSDT, bar_timestamp=T)
  → FeatureReadyEvent (bar_timestamp=T)
      → GroupSignalEvent (group_id=CandlestickGroup, signal_type=evening_star)
          → GroupSignalEvent (group_id=EntryGroup, signal_type=h3_005)
              → CandidateTradeEvent (proposal_id=P1, entry=94500, stop=93000, target=99750)
                  → PanelApprovedProposalEvent (proposal_id=P1, packet_id=K1, approve=16, avg=7.78)
                      → RiskDecisionEvent (proposal_id=P1, decision=approve, size=500_usd)
                          → PositionOpenEvent (trade_id=T1, proposal_id=P1)
                              → PositionCloseEvent (trade_id=T1, outcome=win, pnl_r=2.8)
                                  → JournalEntryEvent (record_type=trade_close, record_id=T1)
```

In the **Journal Browser**: trades table shows T1; setup_packets shows K1; trader_reviews for K1 shows all 20 verdicts; panel_summaries shows the K1 aggregate; final_decisions links K1 to the enter decision; outcome_attributions links T1 back to K1.

In the **Pipeline Trace**: clicking K1 in the packet list loads the trader grid and panel summary. The trade_id column shows T1 for completed packets.

In the **Live Events**: filter to `proposal_id=P1` using the search box to see the full event chain for that proposal.

---

## The Pipeline Trace View

The Pipeline Trace section in the UI implements this correlation path through the journal:

```
setup_packets (packet_id = K1)
  └─ trader_reviews WHERE packet_id = K1  →  20 trader verdicts
  └─ panel_summaries WHERE packet_id = K1  →  aggregate vote
  └─ final_decisions WHERE packet_id = K1  →  enter/hold + safety rails
  └─ trades WHERE trade_id = packet.trade_id  →  outcome
```

The UI loads this via `/api/journal/packets/{packet_id}` (returns packet + reviews) and separate calls to `/api/journal/panels`, `/api/journal/decisions`, and `/api/journal/trades` filtered by packet_id or trade_id.

This view is only populated after the learning extension tables have data (after at least one replay or live run with JournalExtension active).

---

## Source Separation in Observability

The `source` field on every event and journal record identifies which component produced it and under what execution context. This allows distinguishing replay data from live data:

| Source value | Meaning |
|---|---|
| "MarketDataGroup" | Live runtime bar |
| "IndicatorsGroup" | Live runtime feature computation |
| "EntryGroup" | Live runtime entry candidate |
| "PanelDecisionGroup" | Live runtime panel vote |
| "RiskLeverageGroup" | Live runtime risk evaluation |
| "TrueReplayHarness" | Replay run (btc_bear_continuation fixture) |
| "RuntimeReplayHarness" | Simulation replay |
| "event_driven_runtime_simulation" | ideal_short_synthetic fixture |
| "console.server" | Console server log |
| "console.runner_manager" | Runner manager log |

In the Journal Browser, the `outcome_source` column on setup_packets, trader_reviews, panel_summaries, and final_decisions uses the same convention. This prevents mixing live trade data with replay validation data in statistics.

---

## Heartbeat

The WebSocket endpoint sends a heartbeat every 30 seconds when no event has been received from the queue:

```json
{"event_type": "Heartbeat", "ts": 1743249600.123}
```

The `ts` field is the asyncio event loop time (float seconds since loop start), not wall clock time. The browser uses this to detect connection health. If 3 consecutive heartbeats are missed, the UI attempts to reconnect.

---

## What Is NOT Observable Yet

The following observability features are not implemented in the current console:

| Missing capability | Notes |
|---|---|
| Per-evaluator time series | Each trader's score history plotted over time; only available via journal queries today |
| Histogram of composite scores | Distribution of proposal scores that passed/failed the panel gate |
| Live P&L chart | Equity curve over time; only a point-in-time snapshot is available |
| Per-symbol event frequency | Event rate by symbol; no aggregation endpoint |
| Risk rule hit rate | Which risk rules are triggering most frequently; no aggregation endpoint |
| Position-level drawdown | Unrealised P&L on open positions; not tracked separately from portfolio equity |
| Group signal frequency | Signals per group per hour; no aggregation endpoint |
| Alert history | SystemAlertEvent history beyond the ring buffer |
| WebSocket reconnect metrics | How often clients disconnect/reconnect |

---

## Honest Statement on Real-Time vs Historical

**Real-time event streaming is only available when the runner is active.**

When the runner is stopped:
- The WebSocket ring buffer (last 1000 events from the previous session) is available immediately on connect
- No new runtime events flow until the runner is started again
- Log lines continue to be captured (server startup logs, API request logs, etc.)
- The journal browser shows all historical data from the DB at any time

**Historical data from SQLite is always available** (when the DB file exists) regardless of runner state. Journal browser queries, pipeline trace, panel inspector history, and calibration data all come from SQLite and do not require the runner to be running.
