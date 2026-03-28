# Phase 3.5 Stabilization Status

**Date:** 2026-03-28
**Phase:** 3.5 — Surgical Stabilization Pass
**Preceding phase:** 3 — BTC/Bybit Vertical Slice (RESEARCH mode)
**Next phase:** 4 — Live Paper Trading (SHADOW mode)

---

## Goal

Phase 3.5 addressed three specific caveats identified in the Phase 3 audit:

1. `EntryGroup` could publish proposals with `entry_price=0`
2. `ExitGroup` had no real exit handling (positions would never close)
3. `PerformanceJournalGroup` crashed on setup due to all methods being stubs

An additional deliverable: a layered connectivity diagnostic script
(`src/scripts/bybit_smoke_test.py`) to separate environment failures
from code defects in the Bybit data path.

---

## Issue / Fix / Impact / Residual Matrix

| Issue | Why it mattered | Fix applied | Runtime impact | Still limited? |
|---|---|---|---|---|
| EntryGroup entry_price unavailable | Proposals could publish with price=0, poisoning risk sizing and journal records | Added `state.last_close_by_symbol: dict[str, Decimal]` to `SystemState`; added `update_last_close()` async method; `MarketDataGroup.fetch_and_process()` calls `state.update_last_close(symbol, fv.close)` before publishing `FeatureReadyEvent`; `EntryGroup._build_proposal()` reads from `state.last_close_by_symbol` first, signal metadata second, aborts with WARNING if still zero | No proposal can be published without a valid entry price; the fail-loud abort is visible in logs | `startup_load()` does not populate `last_close_by_symbol` — one-bar lag at startup before `fetch_and_process()` has run at least once |
| ExitGroup all stub methods | No real exit handling — positions would never close in the event-driven runtime path; `_evaluate_position()` raises `NotImplementedError` which is silently caught by EventBus | **NOT RESOLVED in Phase 3.5.** `_evaluate_position()` still raises `NotImplementedError`. `_check_stop_loss()` and `_check_target()` contain correct helper logic but are not called. | Positions still do not close through the event-driven path | Requires `_evaluate_position()` and `_compute_pnl()` implementation before any position can close |
| PerformanceJournalGroup all stubs | Runtime crashes on `setup()` because `_initialize_db()` raises `NotImplementedError`; group cannot initialize | **NOT RESOLVED in Phase 3.5.** All 7+ methods still raise `NotImplementedError`. `main_btc.py` writes to `JournalDB` directly, bypassing this group entirely. | PerformanceJournalGroup cannot be used in the event-driven runtime | Requires `_initialize_db()` at minimum; all `_log_*` methods needed for full journaling |
| Bybit live connectivity unverifiable | On this machine, `api.bybit.com` resolves to `127.0.0.1` (local proxy); HTTP layer returns 404 from proxy, not from Bybit | Added layered smoke test script (`src/scripts/bybit_smoke_test.py`) with 6 independent checks; documented environment vs. code defect distinction | Script pinpoints which layer fails and provides actionable diagnosis; BybitAdapter code is confirmed correct | Cannot verify live connectivity from this machine; requires clean environment or cloud VM |

---

## Honest Assessment of What Phase 3.5 Delivered

**Delivered and working:**
- `SystemState.last_close_by_symbol` and `update_last_close()` — implemented
- `MarketDataGroup.fetch_and_process()` wired to call `update_last_close()` — implemented
- `EntryGroup._build_proposal()` two-source resolution with fail-loud abort — implemented
- `src/scripts/bybit_smoke_test.py` — implemented and runnable
- `src/scripts/__init__.py` — created

**Described in the Phase 3.5 brief but NOT reflected in current code:**
- `ExitGroup` full implementation — the methods described in the brief
  (`_evaluate_position`, `_compute_pnl`, trailing stop, time stop) are still
  `raise NotImplementedError` in `src/groups/exit/group.py`
- `PerformanceJournalGroup` full implementation — all `_log_*` methods and
  `_initialize_db()` are still `raise NotImplementedError`

The documentation in `minimal_exit_logic_status.md` reflects the actual code
state, not the aspirational description in the Phase 3.5 brief.

---

## Safe to Proceed?

**For simulation/paper mode (backtest + analysis):**
YES. `main_btc.py --backtest` and `main_btc.py` (analysis mode) are
functional. The entry price fix ensures no zero-price proposals. `JournalDB`
writes work via `main_btc.py`'s direct path.

**For event-driven pipeline (full group pipeline):**
PARTIAL. The entry group path through `MarketDataGroup → IndicatorsGroup →
EntryGroup` is wired and correct. Exits do not work. Journal does not work
through the group pipeline.

**For live execution:**
NO. `ModeGate.RESEARCH` is hardcoded. `ExecutionGroup` has no implementation.
`ExitGroup` does not close positions. No order can be placed.

---

## What Must Not Be Misrepresented

- Live Bybit connectivity was not verified from this machine due to local proxy interception.
- `ExitGroup` and `PerformanceJournalGroup` remain stubbed; they are not functional in the event-driven runtime.
- Phase 3 backtest numbers reflect H3-002 (EMA crossover) only, not the full strategy.
- `CandidateTradeProposal` events cannot be published in the current codebase because `ChartPatternGroup` produces zero signals and the composite score threshold cannot be reached without chart pattern contributions.
