# Runtime Invocation Proof

**Date:** 2026-03-28
**Method:** Instrumented runtime trace + deep-verification test suite

This document provides concrete invocation evidence for each runtime component.
Evidence is either a log trace captured by a live instrumented run or a passing test that patches the actual method call.

---

## Layer A — Data and Signal Pipeline

### MarketDataGroup
- **Instantiated:** YES — `runner._market_data` is not None after `setup()` (test_runner_setup_and_teardown)
- **`_setup()` called:** YES — no EventBus subscription needed; adapter initialized during setup
- **`fetch_and_process()` invoked in live mode:** YES — called by `run_one_bar()` per poll cycle
- **`simulate_bar()` mirrors `fetch_and_process()` for testing:** YES — after fix, `_feature_cache` is populated
- **Feature cache populated:** VERIFIED by `test_simulate_bar_populates_feature_cache`
- **Evidence:**
  ```
  MarketDataGroup._feature_cache keys: [] → [("BTCUSDT", "1h")]
  after simulate_bar(fv) with fv.close=65000
  ```

### IndicatorsGroup
- **Instantiated:** YES
- **Subscribed to FeatureReadyEvent:** YES — confirmed by subscription map trace and `test_feature_ready_event_reaches_indicators`
- **Invoked:** YES — emits `GroupSignalEvent` on each FeatureReadyEvent; captured in `test_feature_ready_event_reaches_indicators`
- **Log trace:** `IndicatorsGroup: BTCUSDT/1h — 0 signal(s) | regime=unknown/normal`
- **Note:** Signals are only emitted on specific triggers (EMA cross, RSI extreme, BB squeeze). Standard bullish bars produce 0 directional signals.

### CandlestickGroup
- **Instantiated:** YES
- **Subscribed to FeatureReadyEvent and GroupSignalEvent:** YES
- **Invoked:** YES — emits `GroupSignalEvent` per FeatureReadyEvent

### TechnicalStructureGroup
- **Instantiated:** YES
- **Subscribed to FeatureReadyEvent:** YES
- **Invoked:** YES — emits `GroupSignalEvent` per FeatureReadyEvent

### EntryGroup
- **Instantiated:** YES
- **Subscribed to GroupSignalEvent:** YES
- **Emits CandidateTradeProposal:** CONDITIONAL — requires ≥2 confirming directional signals AND composite_score ≥ 0.50. With synthetic test bars, confirmation gate typically not met (L=0, S=0).
- **Log trace:** `EntryGroup: confirmation gate not met for BTCUSDT (L=0 S=0)`

---

## Layer B — 20-Trader Panel

### PanelDecisionGroup
- **Instantiated:** YES — `runner._panel_decision` is not None
- **Subscribed to CandidateTradeEvent:** YES — confirmed by `test_panel_decision_group_subscribed`
- **`_panel` instantiated:** YES — `TraderEvaluatorPanel()` created in `_setup()`
- **`_decision_group` instantiated:** YES — `FinalDecisionGroup()` created in `_setup()`
- **`_evaluate_proposal()` invoked:** PROVEN by `test_trader_evaluator_panel_actually_runs` (patched `panel.evaluate` called once)
- **Feature cache guard active:** YES — skips proposal safely when cache empty (`test_panel_decision_skips_without_feature_vector`)

### TraderEvaluatorPanel
- **Instantiated:** YES — inside `PanelDecisionGroup._setup()`
- **`evaluate()` actually called:** PROVEN
  - Test patches `panel.evaluate`, injects CandidateTradeEvent with feature cache populated
  - `panel_calls = [<PanelResult>]` → len == 1
- **20 traders run:** PROVEN
  - `panel_calls[0].approve_count + reject_count + abstain_count == 20`
  - Log: `Panel: 7 approve, 4 reject, 9 abstain | avg=5.5 | → hold`
- **Evidence test:** `test_trader_evaluator_panel_actually_runs`

### All 20 Trader Evaluators
- **All instantiated:** PROVEN — `test_all_20_traders_instantiated`
  - `len(panel._evaluators) == 20`
  - All have unique `trader_id` values
- **All produce verdicts when called:** YES — `TraderEvaluatorPanel.evaluate()` calls each in sequence with exception handling; 7+4+9=20 total verdicts observed

---

## Layer C — Final Decision

### FinalDecisionGroup
- **Instantiated:** YES — inside `PanelDecisionGroup._setup()`
- **`decide()` actually called:** PROVEN
  - Test patches `dg.decide`, injects CandidateTradeEvent with feature cache populated
  - `dg_calls = [<FinalDecision>]` → len == 1
  - `fd.decision == "hold"` (correct: 7/20 < 14/20 threshold)
  - `fd.avg_score == 5.5`, `fd.approve_count == 7`
- **Evidence test:** `test_final_decision_group_actually_runs`
- **Rail check only uses panel output + BTCSetupPacket:** CONFIRMED — no LLM, no raw market data access

---

## Risk Gate

### RiskLeverageGroup
- **Instantiated:** YES
- **Subscribed to PanelApprovedProposalEvent:** YES — `test_risk_group_subscribed_to_panel_approved`
- **Subscribed to CandidateTradeEvent (gated):** YES — subscription exists but IGNORED when `_panel_wired=True`
- **Panel gate engaged by runner:** YES — `runner._risk_leverage._panel_wired == True` after `setup()`
- **Bypass blocked:** PROVEN — `test_panel_gate_blocks_candidate_trade_bypass`
  - Panel holds proposal (7/20) → no `PanelApprovedProposalEvent` → no `RiskDecisionEvent`
  - Direct `CandidateTradeEvent` → RiskLeverageGroup path is silently dropped
- **Receives and processes approved proposals:** PROVEN — `test_panel_approved_reaches_risk`
  - Mock panel forces 14/20 approve, `avg_score=7.0`
  - `RiskDecisionEvent` emitted (rejected by Rule 9: `raw_target=0` — known limitation)
- **Positions actually open:** NOT YET — blocked by Risk Rule 9 (`raw_target=0` on proposals from EntryGroup)

---

## Exit and Journal

### ExitGroup
- **Instantiated:** YES
- **Subscribed to FeatureReadyEvent:** YES — `test_exit_group_subscribed`
- **Processes position exits:** YES — evaluates open positions on each FeatureReadyEvent; no positions open yet in standard simulation

### PerformanceJournalGroup
- **Instantiated:** YES
- **JournalDB initialized:** YES — `test_journal_db_initialized_in_runner`
  - `runner._performance_journal._journal_db is not None`
  - `runner._performance_journal._journal_db._conn is not None`
- **Subscribed to:** GroupSignalEvent, CandidateTradeEvent, RiskDecisionEvent, PositionOpenEvent, PositionCloseEvent, SystemAlertEvent
- **Writes to DB:** YES — every event logged to `journal_events` table
- **Log trace:** `PerformanceJournalGroup ready. Journal DB initialized.`

---

## Learning Layer

### JournalExtension
- **Instantiated:** YES — by `_finalize_learning_wiring()` called from `setup()`
- **Wired without manual call:** PROVEN — `test_learning_layer_wired_after_setup_only`
  - After `await runner.setup()` only (no explicit `_finalize_learning_wiring()`)
  - `runner._journal_extension is not None` ✓
- **6 learning tables initialized:** YES — `JournalExtension: 6 learning-layer tables initialized`

### DecisionTraceLogger
- **Instantiated:** YES — injected into `PanelDecisionGroup._trace_logger` by `_finalize_learning_wiring()`
- **Not None after setup():** PROVEN — `test_learning_layer_wired_after_setup_only`
  - `runner._panel_decision._trace_logger is not None` ✓
- **Writes 4 DB records per proposal evaluation:** PROVEN — `test_decision_trace_logger_writes_to_db`
  - setup_packets table: ≥1 row
  - trader_reviews table: ≥20 rows
  - panel_summaries table: ≥1 row
  - final_decisions table: ≥1 row
- **Log trace:**
  ```
  DecisionTraceLogger: archived setup packet <uuid>
  DecisionTraceLogger: archived 20 trader reviews for packet <uuid>
  DecisionTraceLogger: archived panel summary <uuid>
  DecisionTraceLogger: archived final decision <uuid>
  ```

### OutcomeAttributor
- **Exists:** YES — `learning/attribution.py`, class `OutcomeAttributor`
- **Wired to PositionCloseEvent:** NO
- **Called at runtime:** NO
- **Status:** Implemented, has unit tests, but NOT in the runtime event path. Phase 5 work.
- **Documented by test:** `test_outcome_attributor_not_wired_documented_gap`
