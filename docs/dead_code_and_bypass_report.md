# Dead Code and Bypass Report

**Date:** 2026-03-28
**Audit scope:** All runtime components in `BtcBybitPaperRunner` pipeline

---

## Bypasses Found and Fixed

### Bypass 1 — `CandidateTradeEvent` → `RiskLeverageGroup` (direct path, FIXED)

**Was:** `RiskLeverageGroup` subscribed to both `CandidateTradeEvent` AND `PanelApprovedProposalEvent`.
Every `CandidateTradeEvent` from EntryGroup reached `RiskLeverageGroup` directly, bypassing the 20-trader panel and FinalDecisionGroup.

**Rationale cited:** "Backward compat for backtest path." This was incorrect — the backtest uses `BacktestEngine` directly (not the group pipeline) and never sends events to the bus.

**Fix:** Added `_panel_wired` flag to `RiskLeverageGroup`. When `set_panel_wired(True)` is called by the runner, `CandidateTradeEvent` is silently dropped in `_handle_event()`. Only `PanelApprovedProposalEvent` triggers evaluation.

**Test:** `test_panel_gate_blocks_candidate_trade_bypass`

---

### Bypass 2 — `simulate_bar()` skipped feature cache (Layer B dead in simulation, FIXED)

**Was:** `simulate_bar()` published `FeatureReadyEvent` but did not populate `MarketDataGroup._feature_cache`.
`PanelDecisionGroup._evaluate_proposal()` reads this cache to build `BTCSetupPacket`.
With empty cache → warning logged → proposal skipped → Layer B+C never ran in simulation.

**Fix:** `simulate_bar()` now calls `self._market_data._feature_cache[(fv.symbol, fv.timeframe)] = fv`.

**Test:** `test_simulate_bar_populates_feature_cache`, `test_trader_evaluator_panel_actually_runs`

---

### Bypass 3 — Learning layer not wired in simulation (FIXED)

**Was:** `_finalize_learning_wiring()` only called from `startup_load()`, which only runs in live mode.
In simulation, `JournalExtension` and `DecisionTraceLogger` were never instantiated.
The previous smoke test manually called `_finalize_learning_wiring()` after `setup()` — a workaround.

**Fix:** `setup()` now calls `_finalize_learning_wiring()` after all group setups complete.

**Test:** `test_learning_layer_wired_after_setup_only`

---

## Dead Code (Not Repaired — Require Phase 5)

### Dead 1 — `OutcomeAttributor.process_closed_trade()`

**Location:** `learning/attribution.py`
**Status:** Implemented, has unit tests (`tests/test_learning_layer.py`)
**Problem:** Never called from `PerformanceJournalGroup._log_position_close()` or anywhere in the runtime path.

**What is lost:**
- Trader calibration not updated on trade close
- Panel calibration not updated
- Setup family performance not tracked
- Specialist group records not updated

**Root cause:** `PositionCloseEvent` does not carry `packet_id`/`panel_id`/`decision_id` (assigned by PanelDecisionGroup during evaluation). Without these IDs, `OutcomeAttributor` cannot link trade outcomes back to specific panel/decision records.

**Fix path (Phase 5):** Extend `PositionOpenEvent` to carry `packet_id`/`panel_id`/`decision_id` from `PanelApprovedProposalEvent`. These flow into `Position` object, then into `PositionCloseEvent`. Then wire `OutcomeAttributor.process_closed_trade()` from `_log_position_close()`.

**Test documenting gap:** `test_outcome_attributor_not_wired_documented_gap`

---

### Dead 2 — `HistorianAgent` (EntryGroup)

**Location:** `groups/entry/group.py` — `self._historian = None`
**Status:** EntryGroup has code path for historian (`if self._historian is not None: ...`) but agent is never instantiated.
**Impact:** `historian_analog` is always None → `historian_win_rate = 0.0` → `composite_score` is 0.10 lower than its potential.

---

### Dead 3 — `CriticAgent` (EntryGroup)

**Location:** `groups/entry/group.py` — `self._critic = None`
**Status:** EntryGroup calls critic if `composite_score >= 0.60` and critic is not None. Critic is never instantiated.
**Impact:** No LLM advisory on trade proposals.

---

### Dead 4 — `SummarizerAgent` (PerformanceJournalGroup)

**Location:** `groups/performance_journal/group.py` — `self._summarizer = None`
**Status:** `_run_weekly_summary()` is a no-op stub.
**Impact:** No weekly narrative report.

---

### Dead 5 — `composite_score=0.0` in journal

**Location:** `groups/performance_journal/group.py` — `_log_position_open()`
**Status:** `composite_score=0.0` hardcoded. Actual proposal score not in `PositionOpenEvent`.
**Impact:** All journal trade records show `composite_score=0.0`.

---

## Guarded Components (Safe No-ops, Not Dead Code)

| Component | Guard | Behavior |
|-----------|-------|----------|
| ChartPatternGroup | Not instantiated by runner | Excluded at instantiation time |
| NewsMacroGroup | Not instantiated by runner | Excluded at instantiation time |
| _check_edge_decay | `logger.debug(...)` stub | Logs deferred message, returns None |
| _check_hypothesis_validation | `logger.debug(...)` stub | Logs deferred message, returns None |
| _run_weekly_summary | `logger.debug(...)` stub | Logs deferred message |
| query_historical_analogs | Returns `{}` | Returns empty dict |

---

## `--analyze` mode (main_btc.py)

`run_analysis_mode()` in `main_btc.py` bypasses the entire group pipeline and calls Bybit directly.
This is intentional (legacy diagnostic mode) and clearly documented with `# no group pipeline`.
It does NOT affect the paper trading runtime.
