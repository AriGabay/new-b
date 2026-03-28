# Runtime Wiring Reverification — Phase 4.75+

**Date:** 2026-03-28
**Status:** VERIFIED WITH REPAIRS
**Test suite:** `tests/test_runtime_verification.py` (12 tests, 12 passed)
**Combined suite:** `tests/test_runtime_wiring.py` + `tests/test_runtime_verification.py` (24 tests, 24 passed)

---

## Summary of Findings Before Repairs

A strict runtime audit was performed against the entire codebase.
Five structural defects were found and repaired. Two documented limitations remain (not repaired — require schema changes or Phase 5 work).

---

## Defects Found and Repaired

### Defect 1 — `simulate_bar()` did not populate `MarketDataGroup._feature_cache` [CRITICAL]

**Root cause:**
`simulate_bar()` published `FeatureReadyEvent` and updated `state.last_close_by_symbol` but did NOT populate `MarketDataGroup._feature_cache[(symbol, timeframe)]`.
`PanelDecisionGroup._evaluate_proposal()` reads from this cache to build `BTCSetupPacket`.
With the cache empty, PanelDecisionGroup logged a warning and returned early on every proposal.

**Impact:**
In simulation mode, `TraderEvaluatorPanel.evaluate()` and `FinalDecisionGroup.decide()` were NEVER called. Layer B and Layer C were architecturally wired but never executed.

**Fix applied (`runtime/runner.py`):**
```python
async def simulate_bar(self, fv: FeatureVector) -> None:
    # Mirror what fetch_and_process() does
    self._market_data._feature_cache[(fv.symbol, fv.timeframe)] = fv
    await self._state.update_last_close(fv.symbol, fv.close)
    await self._bus.publish(FeatureReadyEvent(source="runner_simulation", features=fv))
```

**Test proving fix:** `test_simulate_bar_populates_feature_cache`

---

### Defect 2 — `_finalize_learning_wiring()` never called from `setup()` [CRITICAL]

**Root cause:**
`setup()` called `_wire_learning_layer()` (only set `outcome_source`) but NOT `_finalize_learning_wiring()`.
`_finalize_learning_wiring()` was only called from `startup_load()` which is only called by `run_paper_loop()` (live mode only).
In simulation mode, `startup_load()` returned early without calling it.
The learning layer (JournalExtension, DecisionTraceLogger) was never instantiated in simulation.

**Evidence:**
The previous Phase 4.75 test for `test_full_simulation_smoke` manually called `await runner._finalize_learning_wiring()` after `setup()` — a workaround that only applied to that one test, not to actual runtime use.

**Fix applied (`runtime/runner.py`):**
Added `await self._finalize_learning_wiring()` at the end of `setup()`, after all groups complete their `_setup()` (which creates JournalDB in `PerformanceJournalGroup`). Removed the now-redundant call from `startup_load()` and from `main_btc.py`.

**Test proving fix:** `test_learning_layer_wired_after_setup_only`

---

### Defect 3 — `RiskLeverageGroup` subscribed to `CandidateTradeEvent`, bypassing the panel gate [ARCHITECTURE]

**Root cause:**
`RiskLeverageGroup._setup()` subscribed to both `PanelApprovedProposalEvent` AND `CandidateTradeEvent` "for legacy/backtest compatibility."
In the wired runtime, every `CandidateTradeEvent` from EntryGroup reached RiskLeverageGroup directly, bypassing PanelDecisionGroup entirely.
The 20-trader panel was not a gate — proposals could reach risk evaluation without panel approval.

**Note:** This was masked by Defect 4 (RESEARCH mode blocks all orders anyway). But the bypass was real.

**Fix applied (`groups/risk_leverage/group.py`):**
Added `set_panel_wired(True)` method. When called by the runner, `CandidateTradeEvent` events are silently ignored in `_handle_event()`. Only `PanelApprovedProposalEvent` triggers evaluation.
Runner calls `self._risk_leverage.set_panel_wired(True)` in `setup()`.

**Test proving fix:** `test_panel_gate_blocks_candidate_trade_bypass`

---

### Defect 4 — `SystemState` defaulted to `ModeGate.RESEARCH`, blocking all positions [CRITICAL]

**Root cause:**
`SystemState.__init__` defaulted to `mode=ModeGate.RESEARCH`.
`BtcBybitPaperRunner.__init__` used `SystemState()` with no mode override.
`RiskLeverageGroup` Risk Rule 1 rejects all proposals when `state.mode == ModeGate.RESEARCH`.
This meant NO positions could ever open through the runtime path.

**Fix applied (`runtime/runner.py`):**
```python
self._state = SystemState(mode=ModeGate.SHADOW)
```
`ModeGate.SHADOW` = "Paper trade with real-time data" — the correct mode for paper trading.

**Test proving fix:** `test_runner_uses_shadow_mode`

---

### Defect 5 — `EntryGroup` hardcoded `mode_gate=ModeGate.RESEARCH` on proposals [MINOR]

**Root cause:**
`EntryGroup._build_proposal()` set `mode_gate=ModeGate.RESEARCH` as metadata on `CandidateTradeProposal`. While `mode_gate` on the proposal is not checked by `RiskLeverageGroup` (which checks `state.mode`), the field was misleading and contradicted the runner's mode.

**Fix applied (`groups/entry/group.py`):**
Changed to `mode_gate=ModeGate.SHADOW`.

**Test proving fix:** `test_entry_group_proposal_uses_shadow_mode`

---

## Remaining Limitations (Not Repaired — Require Phase 5)

### Limitation 1 — `OutcomeAttributor` not wired to `PositionCloseEvent`

`OutcomeAttributor.process_closed_trade()` exists in `learning/attribution.py` and has unit tests.
It is NOT called from `PerformanceJournalGroup._log_position_close()`.
When a position closes, the full attribution pipeline (trader calibration, panel calibration, setup family tracking, specialist group tracking) does NOT run.

**Why not fixed here:** Requires carrying `packet_id`/`panel_id`/`decision_id` through `PositionOpenEvent` → `Position` → `PositionCloseEvent`. This is a schema extension requiring coordinated changes across 4 files.

**Documented by test:** `test_outcome_attributor_not_wired_documented_gap`

### Limitation 2 — `composite_score=0.0` in `PerformanceJournalGroup._log_position_open()`

Hardcoded in `_log_position_open()` because `CandidateTradeProposal.composite_score` is not in `PositionOpenEvent`. Same root cause as Limitation 1.

### Limitation 3 — Risk Rule 9 (`raw_target=0`) blocks approved proposals in standard flow

`CandidateTradeProposal.raw_target` defaults to `Decimal("0")`. EntryGroup does not compute a target price. The `build_setup_proposal()` helper computes stop/target for `BTCSetupPacket`, but this is internal to Layer B and is not written back to the `CandidateTradeProposal`. When `PanelDecisionGroup` publishes `PanelApprovedProposalEvent`, the original proposal (with `raw_target=0`) is forwarded to `RiskLeverageGroup`. Rule 9 then rejects it with `INCOMPLETE_TRADE_PLAN`.

**Impact:** Even with SHADOW mode and panel approval, positions cannot open until EntryGroup computes a `raw_target` or PanelDecisionGroup enriches the forwarded proposal.

### Limitation 4 — EntryGroup confirmation gate rarely met with synthetic bars

The confirmation gate requires ≥2 signals agreeing on direction. IndicatorsGroup only emits signals on strict condition triggers (EMA cross, RSI < 30 or > 70, BB squeeze, MACD cross). Standard bullish test feature vectors (ema20 < price but no cross, RSI=62) produce zero directional signals. This means the end-to-end path from `simulate_bar()` → EntryGroup → panel is never exercised through the full organic signal chain in automated tests — only by direct `CandidateTradeEvent` injection.

### Limitation 5 — HistorianAgent, CriticAgent, SummarizerAgent not wired

All three are `None` in runtime. EntryGroup skips historian/critic (explicit None check). PerformanceJournalGroup's `_check_edge_decay`, `_check_hypothesis_validation`, `_run_weekly_summary` are deferred no-ops.

### Limitation 6 — ChartPatternGroup, NewsMacroGroup excluded from runner

Both raise `NotImplementedError` in their processing methods. Correctly excluded from `_create_groups()`. EntryGroup's `composite_score` formula allocates 0.35 weight to `chart_pattern_quality`, which is always 0.0 in the runtime.

---

## What Changed Between Phase 4.75 and This Reverification

| File | Change |
|------|--------|
| `src/runtime/runner.py` | `simulate_bar()` now populates `_feature_cache`; `setup()` calls `_finalize_learning_wiring()`; uses `ModeGate.SHADOW`; calls `set_panel_wired(True)` on risk group; removed redundant `_finalize_learning_wiring()` from `startup_load()` |
| `src/groups/risk_leverage/group.py` | Added `_panel_wired` flag and `set_panel_wired()` method; `_handle_event()` ignores `CandidateTradeEvent` when panel is wired |
| `src/groups/entry/group.py` | Changed `mode_gate=ModeGate.RESEARCH` → `mode_gate=ModeGate.SHADOW` |
| `src/main_btc.py` | Removed explicit `_finalize_learning_wiring()` call from `run_simulation_mode()` (now handled in `setup()`) |
| `src/tests/test_runtime_verification.py` | NEW: 12 deep-verification tests proving invocation, side effects, and bypass prevention |
