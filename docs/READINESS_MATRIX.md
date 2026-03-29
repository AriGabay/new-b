# READINESS MATRIX — Phase 7 Gate
**Date:** 2026-03-29
**Audit verdict: GO**

| Area | Status | Evidence | Blocker? | Severity | Must Fix Before Phase 7? | Notes |
|------|--------|---------|---------|----------|--------------------------|-------|
| **Runtime path** | COMPLETE | 27 runtime_wiring tests pass; full pipeline wired in runner.py | NO | — | NO | 10 groups instantiated, EventBus subscriptions confirmed |
| **Setup packet** | COMPLETE | build_btc_setup_packet reads fv + structural + candlestick + chart_pattern | NO | — | NO | All 4 data sources wired via cache injection |
| **Panel** | COMPLETE | 16/20 naturally @ V3, 14/20 @ V2, 0/20 @ V1 (regression locked) | NO | — | NO | 20 deterministic evaluators; all fixture tests pass |
| **Final decision** | COMPLETE | FinalDecisionGroup.decide() wired in PanelDecisionGroup; 6 rails active | NO | — | NO | V3 proposal passes all 6 rails |
| **Risk path** | COMPLETE | All 9 rules pass on V3 natural proposal; PositionOpenEvent fired | NO | — | NO | Panel gate engaged; CandidateTradeEvent bypass blocked |
| **Open lifecycle** | COMPLETE | PositionOpenEvent published; SystemState.portfolio.open_positions updated | NO | — | NO | Position has entry/stop/target/learning IDs |
| **Close lifecycle** | COMPLETE | PositionCloseEvent fired; total_trades=1 after V3 fixture run | NO | — | NO | ExitGroup processes stop/target/trailing/time conditions |
| **Journaling** | COMPLETE | JournalDB writes on open, close, signal, panel, decision events | NO | — | NO | Append-only SQLite; all tables present |
| **Learning hooks** | COMPLETE | DecisionTraceLogger writes setup_packets, reviews, panels, decisions | NO | — | NO | packet_id/panel_id/decision_id threaded into Position |
| **Outcome attribution** | COMPLETE | OutcomeAttributor wired to PerformanceJournalGroup._outcome_attributor | NO | — | NO | Runs on PositionCloseEvent; updates calibration tables |
| **Console** | COMPLETE | FastAPI server + WebSocket + HTML frontend + journal endpoints | NO | — | NO | Real endpoints; reads live DB and SystemState |
| **Replay** | COMPLETE | RuntimeReplayHarness runs real pipeline with real panel + risk | NO | — | NO | 3 fixture variants; no forced approvals |
| **Source separation** | COMPLETE | backtest tags simplified_backtest; runtime tags EVENT_DRIVEN_RUNTIME | NO | — | NO | source_separation tests all pass |
| **Docs consistency** | MOSTLY CORRECT | Code matches docs except 2 stale comments | NO | LOW | NO | runner.py docstring says ChartPatternGroup EXCLUDED (wrong); entry/group.py comment says "Phase 4+" (imprecise) |
| **Entry composite score** | CORRECT BY DESIGN | ACTIVE_COMPOSITE_WEIGHT_SUM=0.55 is correct given ChartPatternGroup no GroupSignalEvent | NO | — | NO | Chart patterns enrich panel only (via cache), not EntryGroup score |
| **ChartPatternGroup activation** | COMPLETE | Wired in runner; DoubleBottomMachine reaches CONFIRMED at bar 249; +2 approvals vs V2 | NO | — | NO | Feeds PanelDecisionGroup via _signals_cache; not via GroupSignalEvent (by design) |
| **Bybit connectivity** | BLOCKED FROM DEV IP | HTTP 404 from current IP; --simulate works fully | NO | ENV ONLY | NO | Use --simulate or deploy from clean network |
| **NewsMarcoGroup** | STUB | Raises NotImplementedError; not wired | NO | LOW | NO | Not required for Phase 7 |
| **HistorianAgent** | NOT WIRED | historian_win_rate always 0.0 | NO | LOW | NO | Weight unused until wired |
| **Calibration DB data** | EMPTY | No live trades yet | NO | EXPECTED | NO | Accumulate 50+ outcomes before data-driven evaluator tuning |
| **Panel threshold tuning** | ELIGIBLE | 14/20 baseline proven; fixtures lock regressions | — | — | — | Safe to tune in Phase 7 |
| **Evaluator weight tuning** | ELIGIBLE (with data) | 20 evaluators deterministic; scoring logic auditable | — | — | — | Prefer data-driven changes after calibration data accumulates |
| **Entry weight tuning** | ELIGIBLE | Normalization correct; composite_score formula audited | — | — | — | Must update ACTIVE_COMPOSITE_WEIGHT_SUM if weights change |
| **Risk parameter tuning** | ELIGIBLE | 9 rules verified; sizing logic audited | — | — | — | Do not loosen risk limits without justification |
| **Exit parameter tuning** | ELIGIBLE | ExitGroup logic verified; trailing stop wired | — | — | — | Tune after accumulating position outcome data |
| **Fixture expansion** | ELIGIBLE | V1/V2/V3 regression suite in place | — | — | — | Add SHORT/ranging/bear fixtures for broader coverage |
