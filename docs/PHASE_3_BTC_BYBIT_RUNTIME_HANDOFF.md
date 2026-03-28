# Phase 3 BTC/Bybit Runtime Handoff

**Handoff date:** 2026-03-28
**Phase completed:** 3 — BTC/Bybit Vertical Slice (RESEARCH mode)
**Next phase:** 4 — Live Paper Trading (SHADOW mode with real-time data)
**Primary author:** Phase 3 engineering team
**Recipient:** Phase 4 engineer

---

## Executive Summary

Phase 3 delivered the first working end-to-end BTC/Bybit analysis slice. You can
run `python main_btc.py` today and get a real market regime assessment, signal
detection output, and a populated SQLite journal — all from live Bybit data.

However, Phase 3 is explicitly a research/analysis tool, not a trading system.
No orders are placed. The full group pipeline is partially wired but not
end-to-end operational. The backtest is a simplified EMA-crossover benchmark,
not a full strategy validation.

Phase 4 must complete the group pipeline, implement real-time WebSocket feeds,
and promote the mode gate from RESEARCH to SHADOW before paper trading begins.

---

## Current System State

### What runs today
```bash
cd /Users/arigabay/Code/new-b/src

# Live BTC analysis (fetches real Bybit data)
python main_btc.py

# 4h timeframe
python main_btc.py --timeframe 4h --bars 400

# EMA crossover backtest (H3-002 baseline)
python main_btc.py --backtest --start 2024-01-01 --end 2024-06-01

# Debug mode
LOG_LEVEL=DEBUG python main_btc.py

# Custom journal location
DB_PATH=/tmp/test.db python main_btc.py

# Custom Bybit endpoint (for testnet)
BYBIT_BASE_URL=https://api-testnet.bybit.com python main_btc.py
```

### What the output looks like
Running `python main_btc.py` produces structured log output including:
- Timestamp, OHLCV values for the latest closed bar
- All indicator values: EMA-20/50/200, RSI-14, ADX-14, ATR-14, BB width percentile
- Regime classification: macro (bull/bear/ranging), trending, volatility
- Any signals detected on the most recent bar (EMA crossover, RSI extremes, BB squeeze)
- A `data/journal.db` SQLite record of the analysis run

---

## What Phase 3 Achieved

1. **Bybit V5 integration**: Real REST API adapter with pagination. Confirmed
   working against live Bybit endpoints (mainnet and testnet).

2. **Feature computation pipeline**: All 11 indicators compute correctly on real BTC
   OHLCV data. 200-bar warmup is the main operational constraint.

3. **SQLite journal**: Append-only audit log with correct schema. Survives restarts,
   queryable with standard SQLite tools.

4. **EntryGroup implementation**: The signal aggregation and trade proposal logic is
   complete. It will produce `CandidateTradeProposal` events when upstream groups
   supply consistent-direction signals. The code is correct; the upstream signal
   sources are not yet operational.

5. **BacktestEngine (simplified)**: Provides a working baseline (H3-002: EMA
   crossover on 1h BTC) that can be used to validate the data pipeline and feature
   computation end-to-end.

6. **Risk sizing**: `ATRStopPlacer` and `RMultipleSizer` compute correct position
   sizes and stop levels. These will plug directly into the Phase 4 order path.

7. **20 trader evaluators + FinalDecisionGroup**: Panel evaluation logic complete.
   Will be the final gate before any Phase 4 order is placed.

---

## What Phase 4 Must Complete

### Priority 1 — Critical Path (Blocks All Trading)

**P4-1: Complete ChartPatternGroup state machines (H1-001 through H1-005)**
- Without chart pattern signals, the EntryGroup composite score can never reach
  the 0.50 threshold (maximum from indicators + candlestick alone is 0.45).
- File: `src/groups/chart_pattern/group.py`
- H1-001 (H&S Top) is partial. H1-002 through H1-005 are stubs.
- Estimated effort: 1-2 weeks per pattern with backtesting.

**P4-2: Wire IndicatorsGroup, CandlestickGroup, TechnicalStructureGroup to emit real signals**
- Current state: Groups subscribe to EventBus but emit signals with hardcoded
  quality scores and do not reliably populate `GroupSignalBundle.regime` or
  `GroupSignalBundle.structural`.
- Required: Integrate FeatureVector values into signal quality scoring.
- File: `src/groups/indicators/group.py`, `src/groups/candlestick/group.py`,
  `src/groups/technical_structure/group.py`

**P4-3: Implement WebSocket real-time feed (replace REST polling)**
- File: `src/data/bybit.py` (add WebSocket class)
- Bybit V5 WebSocket: `wss://stream.bybit.com/v5/public/linear`
- Subscribe to `kline.60.BTCUSDT` for 1-minute (or 1h) OHLCV updates.
- On bar close: emit `BarCloseEvent` to EventBus.
- REST polling is acceptable for initial Phase 4 testing but has 60s latency on 1h bars.

**P4-4: Wire position lifecycle to SystemState**
- `ExitGroup` must update `SystemState` when a position closes.
- `RiskLeverageGroup` rules reading `daily_pnl_pct`, `drawdown_pct`,
  `consecutive_losses` will return stale values until this is done.
- File: `src/groups/exit/group.py`, `src/core/state.py`

**P4-5: Promote ModeGate from RESEARCH to SHADOW**
- Change `SystemState(mode=ModeGate.SHADOW)` in the runner.
- Ensure `RiskLeverageGroup` Rule 7 passes for SHADOW mode.
- Implement paper order logging in ExecutionGroup (no real API call needed for SHADOW).

### Priority 2 — Important (Degrades Quality Without These)

**P4-6: Implement HistorianAgent**
- Query `JournalDB.query_hypothesis_trades(hypothesis_id, n=20)` to compute win rate.
- Return `HistoricalAnalog` to EntryGroup. Currently hardcoded to 0.0.
- Affects `historian_win_rate` component (0.10 weight in composite score).

**P4-7: Validate candlestick pattern quality scores against historical outcomes**
- H2-001 through H2-005 are all `HypothesisStatus.UNTESTED`.
- Run a focused backtest (or manual review) comparing quality scores against
  next-5-bar returns at structural levels.

**P4-8: Implement trailing stop in ExitGroup**
- `_update_trailing_stop()` is a stub. Required for trend-following positions.
- File: `src/groups/exit/group.py`

**P4-9: Compute Sharpe ratio in BacktestEngine**
- Requires maintaining a returns series per bar.
- `BacktestResult.sharpe_ratio` is always 0.0 today.

### Priority 3 — Phase 4+ (Deferred)

- **CriticAgent**: LLM integration. Only runs when composite_score >= 0.60. The
  EntryGroup injection hook exists (`self._critic`). Implement as an optional call.
- **NewsGroup/MacroGroup**: Static event calendar (FOMC dates, CPI releases) as
  a first step. Live news requires NLP pipeline.
- **Multi-symbol universe**: The universe filtering logic (volume thresholds, spread
  checks, correlation clustering) supports altcoins architecturally but is not
  tested. BTC-only is correct for Phase 4.
- **LeverageGovernor wiring**: Leverage cap is computed but not applied to
  `RiskApprovedOrder.leverage`. Wire `LeverageGovernor.compute()` into the risk path.
- **Per-hypothesis backtest breakdown**: `BacktestResult.per_hypothesis` requires
  tagging each trade with hypothesis IDs, which requires full group pipeline replay.

---

## Architecture Decisions Made in Phase 3

### ADR-P3-001: Simplified BacktestEngine (EMA crossover only)
**Decision**: BacktestEngine.run() uses FeatureComputer + EMA crossover signals
directly, not the full group pipeline.
**Rationale**: Full group pipeline requires asyncio event loops, EventBus, and
shared state that cannot be cleanly embedded in a synchronous bar loop without
major infrastructure work. A simplified engine provides faster time-to-value.
**Consequences**: Phase 3 backtest results are only valid for H3-002 validation.
All other hypothesis backtesting requires Phase 4 full-pipeline engine.

### ADR-P3-002: EntryGroup triggers on indicators bundle (not all-groups quorum)
**Decision**: EntryGroup fires `_evaluate_trade_opportunity` when an indicators
bundle arrives, not when all 5 upstream groups have reported.
**Rationale**: Waiting for all groups would deadlock if any group produces no
signals for a bar (which is common for ChartPatternGroup and NewsGroup in Phase 3).
**Consequences**: EntryGroup may evaluate a proposal without CandlestickGroup or
ChartPatternGroup bundles. In practice this is safe because missing signal types
contribute 0.0 to composite score, pushing it below the 0.50 threshold.

### ADR-P3-003: Mode gate hardcoded to RESEARCH in EntryGroup
**Decision**: `CandidateTradeProposal.mode_gate = ModeGate.RESEARCH` is hardcoded
in `EntryGroup._build_proposal()`.
**Rationale**: Phase 3 must never execute real orders. Hardcoding at the source
(not just at RiskLeverageGroup) provides defence-in-depth.
**Consequences**: Phase 4 must change this line and ensure the full risk gate is
calibrated before SHADOW promotion.

### ADR-P3-004: REST polling instead of WebSocket
**Decision**: All bar data comes from Bybit REST API polling.
**Rationale**: WebSocket requires connection management, heartbeat, reconnect
logic, and significantly more engineering. REST is sufficient for 1h bars where
60-second latency is acceptable.
**Consequences**: Phase 3 cannot trade intrabar. Any signals require a full bar
to close before detection. WebSocket is required for < 1h timeframes.

---

## Known Bugs and Risks

### Bug: `FeatureVector.atr14_sma20` can equal `atr14` if history is insufficient
When fewer than 20 ATR14 values are available, `atr14_sma20 = atr14`. This means
`atr14_vs_sma20` will always be 1.0 during warmup. Not a crash, but regime
classification (volatility) will be inaccurate for the first 220 bars.

### Bug: `_collect_bundle` may process stale bundles across bar boundaries
If two bars close in rapid succession (e.g., in a backtest replay), bundles from
bar N-1 may still be in `_pending_bundles` when bar N's bundles arrive. The
`self._pending_bundles[symbol] = {}` clear at the start of `_evaluate_trade_opportunity`
mitigates this but does not guarantee atomicity.

### Risk: ChartPatternGroup produces zero signals in Phase 3
With chart_pattern_quality = 0.0, the maximum composite score is 0.45
(0.25 × candlestick + 0.20 × indicator). This is below the 0.50 threshold.
**Result: No `CandidateTradeProposal` events will be published in Phase 3.**
The system is analysis-only, not trade-proposal-generating.

### Risk: Memory growth from `_pending_bundles` if symbols never fire
If `IndicatorsGroup` never publishes a bundle for a symbol (e.g., during warmup),
`_pending_bundles[symbol]` will accumulate bundles from other groups indefinitely.
Add a TTL cleanup mechanism in Phase 4.

### Risk: Bybit API rate limits under pagination
Fetching 500 bars requires 3 API requests. The `asyncio.sleep(0.2)` delay between
pages is a courtesy only. Under load (many symbols), this will need rate-limit
tracking. Bybit allows ~120 requests/minute on public endpoints.

---

## File Map — All Key Components

```
/Users/arigabay/Code/new-b/
├── src/
│   ├── main_btc.py                          # RUNNABLE — Phase 3 entrypoint
│   ├── main.py                              # Original entrypoint (may be outdated)
│   ├── core/
│   │   ├── schemas.py                       # All data contracts (OHLCVBar, FeatureVector, etc.)
│   │   ├── events.py                        # EventBus + all event types
│   │   ├── state.py                         # SystemState (portfolio, risk, regime)
│   │   ├── registry.py                      # GroupID, GroupRegistry, HypothesisRegistry
│   │   └── setup_packet.py                  # BTCSetupPacket (assembled by EntryGroup)
│   ├── data/
│   │   └── bybit.py                         # IMPLEMENTED — Bybit V5 REST adapter
│   ├── features/
│   │   └── compute.py                       # IMPLEMENTED — FeatureComputer (11 methods)
│   ├── journal/
│   │   └── db.py                            # IMPLEMENTED — SQLite journal (3 tables)
│   ├── backtest/
│   │   └── engine.py                        # PARTIAL — EMA crossover only
│   ├── groups/
│   │   ├── entry/
│   │   │   └── group.py                     # IMPLEMENTED — signal aggregation
│   │   ├── indicators/
│   │   │   └── group.py                     # PARTIAL — hardcoded quality scores
│   │   ├── technical_structure/
│   │   │   └── group.py                     # PARTIAL — S/R detection present
│   │   ├── candlestick/
│   │   │   └── group.py                     # PARTIAL — basic patterns implemented
│   │   ├── chart_pattern/
│   │   │   └── group.py                     # STUBBED — H1-001 partial, rest stubs
│   │   ├── market_data/
│   │   │   └── group.py                     # PARTIAL — REST polling, no WebSocket
│   │   ├── exit/
│   │   │   └── group.py                     # PARTIAL — stop/target checks, no trailing
│   │   ├── risk_leverage/
│   │   │   └── group.py                     # PARTIAL — 9 rules, mode gate blocks all
│   │   ├── news_macro/
│   │   │   └── group.py                     # STUBBED — empty bundles only
│   │   └── performance_journal/
│   │       └── group.py                     # PARTIAL — writes journal, no metrics
│   ├── risk/
│   │   ├── stop_placer.py                   # IMPLEMENTED — ATRStopPlacer
│   │   └── sizer.py                         # IMPLEMENTED — RMultipleSizer
│   ├── traders/                             # IMPLEMENTED — all 20 evaluators
│   ├── decision/                            # IMPLEMENTED — FinalDecisionGroup
│   ├── agents/
│   │   └── base/
│   │       └── group.py                     # IMPLEMENTED — BaseGroup abstract class
│   └── execution/                           # DESIGN-ONLY — no implementation
├── docs/
│   ├── PHASE_3_BTC_BYBIT_RUNTIME_HANDOFF.md  # THIS FILE
│   ├── BTC_BYBIT_VERTICAL_SLICE_STATUS.md    # Overall status
│   ├── fixed_audit_issues.md                # P0/P1/P2 audit fix tracker
│   ├── remaining_stubbed_components.md      # Honest stub inventory
│   ├── runtime_path_btc_bybit.md            # Data flow documentation
│   ├── implemented_vs_stubbed.md            # Component status table
│   ├── validated_vs_unvalidated.md          # Evidence quality assessment
│   └── implementation_coverage_audit.md    # Original audit (Phase 2)
└── research/                                # Hypothesis research documents
```

---

## Handoff Checklist for Phase 4 Engineer

Before writing a single line of Phase 4 code, verify the following:

- [ ] `python main_btc.py` runs without errors and logs BTC analysis output
- [ ] `python main_btc.py --backtest` completes and shows non-zero trade count
- [ ] `data/journal.db` is created and contains at least one `journal_events` record
- [ ] You have read `remaining_stubbed_components.md` in full
- [ ] You have read `validated_vs_unvalidated.md` in full
- [ ] You understand that no `CandidateTradeProposal` events will fire until
  ChartPatternGroup is implemented (P4-1 above)
- [ ] You have a plan for WebSocket implementation before going to SHADOW mode
- [ ] You have confirmed that `ModeGate.RESEARCH` will remain until Phase 4
  risk gate calibration is complete
