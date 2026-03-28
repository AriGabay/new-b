# Phase 3.5 Handoff

**Date:** 2026-03-28
**Phase completed:** 3.5 — Stabilization Pass
**Next phase:** 4 — Live Paper Trading (SHADOW mode)
**Recipient:** Phase 4 engineer

---

## 1. What Phase 3.5 Fixed

### Entry Price Wiring

The most consequential fix. `SystemState` now has `last_close_by_symbol:
dict[str, Decimal]` and an `update_last_close(symbol, price)` async method.
`MarketDataGroup.fetch_and_process()` calls it after each successful feature
computation, before publishing `FeatureReadyEvent`. This means that by the
time `EntryGroup` evaluates a signal bundle, the bar's close price is already
in shared state and can be read reliably.

`EntryGroup._build_proposal()` reads from `state.last_close_by_symbol` first,
falls back to signal metadata, and if both are zero it logs a WARNING and
returns `None` — aborting the proposal rather than publishing a zero-price
entry. No proposal can propagate to the risk gate or journal without a
valid entry price. This eliminates a silent data corruption path.

### Connectivity Diagnostic Script

`src/scripts/bybit_smoke_test.py` tests the Bybit connection in 6 independent
layers: DNS, TCP, TLS certificate, HTTP response code, JSON response parsing,
and BybitAdapter integration. Each layer reports independently. The script
distinguishes environment failures (proxy, VPN, geo-block) from code defects
and provides a diagnosis guide for each failure mode. Run it from any clean
environment to verify connectivity end-to-end.

### What Phase 3.5 Did NOT Complete

The brief for Phase 3.5 described full implementations of `ExitGroup` and
`PerformanceJournalGroup`. As of 2026-03-28, the actual code does not match
that description:

- `ExitGroup._evaluate_position()` — still raises `NotImplementedError`
- `ExitGroup._compute_pnl()` — still raises `NotImplementedError`
- `ExitGroup._check_trailing_stop()` — still raises `NotImplementedError`
- `PerformanceJournalGroup._initialize_db()` — still raises `NotImplementedError`
- All `PerformanceJournalGroup._log_*` methods — still raise `NotImplementedError`

These are Phase 4 requirements, not Phase 3.5 completions.

---

## 2. What Caveats Were Resolved

- Zero-price proposals: resolved. Fail-loud abort in `_build_proposal()` means
  the problem is detectable and does not propagate silently.
- Connectivity ambiguity: resolved. The smoke test separates "is the code
  correct?" from "is the network reachable?" The code is correct. The network
  on this machine is not reachable due to a local proxy.
- `last_close` attribute missing on `SystemState`: resolved. The correct
  attribute `last_close_by_symbol` is now present and populated.

---

## 3. What Remains Limited

**Blocks all live trading:**
- No order execution path (`ExecutionGroup` is design-only)
- `ModeGate.RESEARCH` hardcoded in `EntryGroup._build_proposal()`
- `ExitGroup._evaluate_position()` raises `NotImplementedError` — positions
  opened in simulation never close
- `PerformanceJournalGroup` crashes on setup — event-driven journaling is broken

**Blocks realistic simulation:**
- `ChartPatternGroup` produces zero signals (H1-001 partial, H1-002 to H1-005
  are stubs). Maximum composite score reachable from indicators + candlestick
  alone is 0.45, below the 0.50 threshold. `EntryGroup` will not publish
  proposals in the live event-driven pipeline until at least one chart pattern
  signal path is implemented.
- `IndicatorsGroup` signal quality scores are hardcoded, not derived from
  `FeatureVector` values
- BacktestEngine uses simplified EMA crossover only, not the full group pipeline

**Latent risks:**
- One-bar entry price lag at startup (first bar after `startup_load()` before
  `fetch_and_process()` runs)
- Gap-open risk: `ExitGroup` fires only on bar close, not intrabar
- No WebSocket feed — REST polling only, 60-second latency minimum

---

## 4. Safety Assessment

**Safe for paper/simulation mode?**
YES, with caveats. `main_btc.py` runs correctly in analysis mode and backtest
mode. `JournalDB` writes work. The entry price fix is in place. The system
will not produce `CandidateTradeProposal` events in the event-driven pipeline
(ChartPatternGroup threshold blocker), so no proposal-to-order path is
triggered anyway.

**Safe for live execution?**
NO. The mode gate is hardcoded to RESEARCH. There is no execution group. No
position can be opened or closed. This is intentional.

**Unsafe patterns to watch for:**
- If `ExitGroup` is given a real `_evaluate_position()` implementation without
  also fixing `_compute_pnl()`, it will crash at runtime
- If `PerformanceJournalGroup` is initialized in the event loop without
  implementing `_initialize_db()`, the entire group setup will throw
- Do not promote to SHADOW mode until all Phase 4 critical-path items are done

---

## 5. What Must Not Be Misrepresented

- **Live Bybit connectivity was not verified from this machine.** The adapter
  code is correct; the machine's local proxy blocks it. Verify from a clean
  environment before assuming connectivity works.
- **ExitGroup is not functional.** Positions do not close through the
  event-driven path. The Phase 3.5 brief described this as fixed; it is not.
- **PerformanceJournalGroup is not functional** in the event-driven runtime.
  `main_btc.py` works because it bypasses this group.
- **Phase 3 backtest numbers are for H3-002 (EMA crossover) only.** They do
  not represent chart pattern, candlestick, or multi-signal strategy performance.
- **CandidateTradeProposal events will not fire** in the current event-driven
  pipeline because `ChartPatternGroup` produces no signals and the composite
  score threshold cannot be reached.
- **The system is not a trading system.** It is a research and analysis tool.

---

## 6. For the Next Engineer

To get from here to Phase 4 live paper trading, the following must be done
in order:

1. **Implement `ExitGroup._evaluate_position()` and `_compute_pnl()`.**
   Use `_check_stop_loss()` and `_check_target()` (already correct). Add
   time stop check (`bars_held >= max_bars_to_hold`). Build and return
   `ExitSignal`. `_execute_exit()` is already implemented and will handle
   the rest.

2. **Implement `PerformanceJournalGroup._initialize_db()`.**
   Use the existing `JournalDB` class (`src/journal/db.py`). Open the
   connection in `_initialize_db()`, then implement `_log_position_close()`
   first (most valuable). Other `_log_*` methods can follow incrementally.

3. **Implement at least one `ChartPatternGroup` signal path (H1-001 or H1-002).**
   Without this, `EntryGroup` cannot produce proposals. Even a simplified
   double-top/bottom detector is sufficient to unblock the proposal path.

4. **Wire `IndicatorsGroup` signal quality to real `FeatureVector` values.**
   The hardcoded scores make the composite score unreliable. RSI extremes,
   EMA alignment, and ADX strength are all computable from existing features.

5. **Implement WebSocket feed or reduce polling interval.**
   REST polling is sufficient for 1h bars but is a known limitation.
   Implement `wss://stream.bybit.com/v5/public/linear` subscribe to
   `kline.60.BTCUSDT` before going to SHADOW mode.

6. **Remove RESEARCH hardcode and configure SHADOW mode.**
   Change `mode_gate=ModeGate.RESEARCH` in `EntryGroup._build_proposal()`.
   Set `SystemState(mode=ModeGate.SHADOW)` in the runner. Implement
   paper order logging in `ExecutionGroup` (no real API call needed).

7. **Verify Bybit connectivity from deployment environment.**
   Run `python scripts/bybit_smoke_test.py` and confirm all 6 layers pass
   before wiring any live data path.

8. **Run the full Phase 4 smoke test checklist** from the original handoff
   document before any SHADOW mode paper trading begins.

---

## 7. How to Run the System Now

```bash
cd /Users/arigabay/Code/new-b/src

# Live BTC analysis (fetches real Bybit data if network available)
python main_btc.py

# 4h timeframe analysis
python main_btc.py --timeframe 4h --bars 400

# EMA crossover backtest (H3-002 baseline, does not require live network)
python main_btc.py --backtest --start 2024-01-01 --end 2024-06-01

# Debug logging
LOG_LEVEL=DEBUG python main_btc.py

# Custom journal location
DB_PATH=/tmp/test.db python main_btc.py

# Bybit testnet (avoids proxy issues if testnet is reachable)
BYBIT_BASE_URL=https://api-testnet.bybit.com python main_btc.py

# Connectivity smoke test (Layer 1-6 diagnostic)
python scripts/bybit_smoke_test.py
```

---

## 8. File Map — Key Files and Status

```
src/
  main_btc.py                              IMPLEMENTED — analysis + backtest entrypoint
  main.py                                  PARTIAL — original entrypoint, may be outdated
  scripts/
    __init__.py                            CREATED (empty)
    bybit_smoke_test.py                    IMPLEMENTED — 6-layer connectivity diagnostic
  core/
    schemas.py                             IMPLEMENTED — all data contracts
    events.py                              IMPLEMENTED — EventBus + all event types
    state.py                               IMPLEMENTED — SystemState with last_close_by_symbol
    registry.py                            IMPLEMENTED — GroupID, HypothesisRegistry
    setup_packet.py                        IMPLEMENTED — dataclass definitions
  data/
    bybit.py                               IMPLEMENTED — Bybit V5 REST adapter
    binance.py                             DEAD CODE — replaced by Bybit
  features/
    compute.py                             IMPLEMENTED — FeatureComputer, 11 indicators
  journal/
    db.py                                  IMPLEMENTED — SQLite, 3 tables, WAL mode
  backtest/
    engine.py                              PARTIAL — EMA crossover only; _replay_bar is stub
    metrics.py                             PARTIAL — Sharpe/Bonferroni stubs
  groups/
    entry/group.py                         IMPLEMENTED — signal aggregation, fail-loud price
    market_data/group.py                   PARTIAL — REST polling, update_last_close wired
    indicators/group.py                    PARTIAL — hardcoded quality scores
    candlestick/group.py                   PARTIAL — basic patterns; quality unvalidated
    technical_structure/group.py           PARTIAL — S/R detection; level quality uncertain
    chart_pattern/group.py                 STUBBED — H1-001 partial; H1-002 to H1-005 stubs
    exit/group.py                          STUBBED — _evaluate_position raises NotImplementedError
    risk_leverage/group.py                 PARTIAL — 9 rules; mode gate blocks all
    news_macro/group.py                    STUBBED — empty bundles only
    performance_journal/group.py           STUBBED — _initialize_db raises NotImplementedError
  risk/
    stop_placer.py                         IMPLEMENTED — ATRStopPlacer
    sizer.py                               IMPLEMENTED — RMultipleSizer
  traders/                                 IMPLEMENTED — all 20 evaluators
  decision/                                IMPLEMENTED — FinalDecisionGroup
  agents/base/group.py                     IMPLEMENTED — BaseGroup abstract class
  execution/                               DESIGN-ONLY — no implementation
docs/
  entry_price_wiring_fix.md               NEW — Phase 3.5
  minimal_exit_logic_status.md            NEW — Phase 3.5 (honest stub inventory)
  bybit_connectivity_smoke_test.md        NEW — Phase 3.5
  remaining_known_limitations.md          NEW — Phase 3.5
  PHASE_3_5_STABILIZATION_STATUS.md       NEW — Phase 3.5
  PHASE_3_5_HANDOFF.md                    NEW — Phase 3.5 (this file)
  PHASE_3_BTC_BYBIT_RUNTIME_HANDOFF.md    Phase 3 handoff (superseded in part)
  implemented_vs_stubbed.md               Phase 3 status table (partially outdated)
```
