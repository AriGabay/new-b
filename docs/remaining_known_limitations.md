# Remaining Known Limitations

**Phase:** 3.5 Stabilization
**Date:** 2026-03-28

This is an honest inventory of what does not work, is incomplete, or carries
unresolved risk. It supersedes the equivalent section in
`PHASE_3_BTC_BYBIT_RUNTIME_HANDOFF.md` for anything added or changed in 3.5.

---

## Critical — Would Block Live Trading

**No live order execution (RESEARCH mode hardcoded)**
`EntryGroup._build_proposal()` hardcodes `mode_gate=ModeGate.RESEARCH`.
`RiskLeverageGroup` Rule 7 blocks all proposals in RESEARCH mode.
`ExecutionGroup` is design-only with no implementation. No order can be
placed by this system in its current state. This is intentional.

**ExitGroup._evaluate_position() raises NotImplementedError**
`ExitGroup` subscribes to `FeatureReadyEvent` and calls `_check_exits()`,
which calls `_evaluate_position()`, which immediately raises
`NotImplementedError`. Exceptions are caught by `BaseGroup.handle_event()`
and logged, not re-raised. The result is that positions opened in simulation
will never close through the event-driven path. `_check_stop_loss()` and
`_check_target()` contain correct logic but are not reachable.

**PerformanceJournalGroup._initialize_db() raises NotImplementedError**
`_setup()` calls `_initialize_db()`, which raises `NotImplementedError`.
This crashes group initialization. `PerformanceJournalGroup` cannot be
used in the event-driven runtime. Journal writes in `main_btc.py` bypass
this group and write directly to `JournalDB`.

**startup_load() does not populate last_close_by_symbol**
`MarketDataGroup.startup_load()` loads historical bars and computes
feature vectors but does not call `state.update_last_close()`. Only
`fetch_and_process()` does. If `EntryGroup` evaluates before
`fetch_and_process()` has run at least once, `entry_price` will be zero
and the proposal will be aborted with a warning.

**ExitGroup fires only on bar close (gap-open risk)**
`ExitGroup` subscribes to `FeatureReadyEvent`, which fires on bar close.
In live trading, a position can gap through its stop level at the open of
the next bar. `ExitGroup` will exit at the bar's low/high (not the gap
price), resulting in slippage beyond the stated stop. This is documented
and accepted for paper/simulation mode. It is not acceptable for live
execution without an intrabar price check.

**No WebSocket real-time feed**
All bar data comes from Bybit REST API polling. The system has no
intrabar price visibility. The polling interval determines latency.
For 1h bars, REST polling is acceptable; for shorter timeframes it is not.

---

## Significant — Affects Realism of Simulation Results

**BacktestEngine uses simplified EMA-crossover-only signals**
`BacktestEngine.run()` (`src/backtest/engine.py`) does not replay the full
group pipeline. It uses `FeatureComputer` directly and applies EMA crossover
logic (H3-002) only. Backtest results do not represent the behavior of
`EntryGroup`, `ChartPatternGroup`, `CandlestickGroup`, or any other group.
Do not cite Phase 3 backtest numbers as evidence for anything other than
H3-002 EMA crossover performance.

**_replay_bar() is a pass stub**
`BacktestEngine._replay_bar()` exists as a method stub but contains no
implementation. Full group pipeline replay in backtest is not wired.

**ChartPatternGroup all stubs**
H1-001 through H1-005 pattern detection is not implemented. H1-001 (H&S Top)
has a partial state machine framework. H1-002 through H1-005 are stubs
returning empty signal lists. Because `chart_pattern_quality` has a 0.35
weight in the composite score, and the maximum from indicator (0.20) and
candlestick (0.25) alone is 0.45, the composite score threshold of 0.50
**cannot be reached** in the current event-driven pipeline. No
`CandidateTradeProposal` events will be published until at least one chart
pattern group signal path is implemented.

**ExitGroup signal-reversal exit not implemented**
Exit priority item 5 (signal reversal — opposing ChartPattern/Indicator
signal triggers advisory exit) is not implemented. Items 1-4 (stop, target,
trailing, time stop) are partially implemented but blocked by
`_evaluate_position()` being a stub.

**No position tracking after startup_load**
`MarketDataGroup.startup_load()` does not seed `state.last_close_by_symbol`.
This is a latent inconsistency between the startup path and the polling path.

**_check_edge_decay, _check_hypothesis_validation, _run_weekly_summary are stubs**
All three methods in `PerformanceJournalGroup` raise `NotImplementedError`.
Edge decay detection and hypothesis promotion gates do not run. No automatic
hypothesis status transitions occur.

---

## Minor — Acceptable for Phase 3 Research Mode

**HistorianAgent and CriticAgent not wired**
`EntryGroup._historian` and `EntryGroup._critic` are `None`. The code
checks for `None` and skips safely. The `historian_win_rate` component of
the composite score is always `0.0`. The CriticAgent LLM call never runs.
Proposals are published without historical analog data.

**NewsMacroGroup all stubs**
`src/groups/news_macro/group.py` returns an empty `GroupSignalBundle` on
every bar. No news ingestion, no macro calendar, no sentiment signal. The
`0.0` contribution to composite score from news is intentional and documented.

**FeatureStore replaced by in-memory deques**
Feature history is stored in `collections.deque` objects in
`MarketDataGroup._bar_history`. There is no persistence across restarts.
On restart, the system must re-fetch 200 bars from Bybit to warm up.

**Performance metrics stubs in backtest/metrics.py**
Sharpe ratio in `BacktestResult` is always `0.0`. Bonferroni-corrected
p-values for hypothesis validation are not computed. Calmar ratio is
not computed. The `BacktestResult.summary()` method outputs a valid
summary, but the risk-adjusted return fields are meaningless.

**BinanceAdapter dead code**
`src/data/binance.py` exists but is not used anywhere in the Phase 3
codebase. Bybit is the sole data source. The BinanceAdapter was replaced
during Phase 2 and the file was retained but not removed.

**IndicatorsGroup signal quality scores hardcoded**
Signal quality scores in `src/groups/indicators/group.py` are hardcoded
rather than computed from FeatureVector values. This affects the
`indicator_quality` component (0.20 weight) of the composite score.

**RiskLeverageGroup LeverageGovernor not wired**
`LeverageGovernor.compute()` computes a leverage cap but the result is not
applied to `RiskApprovedOrder.leverage`. The leverage field on approved
orders is not set correctly.

**BacktestEngine sharpe_ratio always 0.0**
Requires maintaining a per-bar returns series, which is not implemented.
`BacktestResult.sharpe_ratio` is hardcoded to `0.0`.
