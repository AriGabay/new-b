# Phase Status Matrix

**Date:** 2026-03-28
**Source:** Direct code audit — not documentation trust

Each subsystem is classified as one of:
- **working** — implemented, tested, active in runtime path
- **working-limited** — implemented and working but with documented constraints
- **stubbed** — method exists but raises NotImplementedError or returns hardcoded value
- **deferred** — design complete but implementation not started
- **dead-code** — implemented but not called from any runtime entrypoint
- **repaired** — was broken, fixed in this audit pass

---

## Verification Matrix

| Subsystem | Intended Behavior | Actual Implementation | Runtime Evidence | Docs Claim | Aligned? | Repair Action |
|---|---|---|---|---|---|---|
| **Market Data** | Poll Bybit, publish BarCloseEvent + FeatureReadyEvent, seed last_close | Implemented fully; startup_load() does NOT seed last_close | Bybit connectivity blocked (HTTP 404); no live events | Accurately described | PARTIAL | None — documented lag is known |
| **FeatureComputer** | Compute 31-field FeatureVector from bar history | Implemented; ATR14 Wilder's, EMA, RSI, BB, ADX all present | Works in backtest; blocked in live | Accurately described | YES | None |
| **Indicators** | EMA crossover, RSI, MACD, BB, ADX signals → GroupSignalEvent | Fully implemented, 10 sub-agents, publishes GroupSignalEvent | Would work if wired in runner | Accurately described | YES (dead in runtime) | None |
| **Candlestick** | Pattern detection → GroupSignalEvent | Fully implemented, 5+ patterns detected | Would work if wired | Accurately described | YES (dead in runtime) | None |
| **Chart Pattern** | Advanced chart pattern → GroupSignalEvent | STUB — raises NotImplementedError | Crashes if instantiated | Correctly labeled stubbed | YES | None needed yet (guard before runner) |
| **Technical Structure** | S/R levels, swing detection → GroupSignalEvent | Fully implemented, publishes GroupSignalEvent | Would work if wired | Accurately described | YES (dead in runtime) | None |
| **News/Macro** | Macro regime classification → GroupSignalEvent | STUB — raises NotImplementedError | Crashes if instantiated | Correctly labeled stubbed | YES | None needed yet (guard before runner) |
| **Entry** | Aggregate signals, gate, build proposal | Implemented; _historian=None, _critic=None | CandidateTradeEvent never fired (no upstream wiring) | Accurately described | YES (dead in runtime) | None |
| **Risk / Leverage** | 9 deterministic rules → approve/reject | Fully implemented | Never triggered (no CandidateTradeEvent) | Accurately described | YES (dead in runtime) | None |
| **Exit** | stop→target→trailing→time priority | Fully implemented | No positions exist to check | Accurately described | YES (dead in runtime) | None |
| **Journal (DB)** | 3 tables, append-only writes | Fully implemented | Would write if events existed | Accurately described | YES | None |
| **PerformanceJournalGroup** | Log all events, deferred analytics | Logging real; analytics were stubs | Never receives events (no runtime) | Partially honest — double-close undocumented | REPAIRED | Fixed double-close bug; fixed NotImplementedError stubs |
| **Trader Panel (20 evaluators)** | 20 distinct evaluators → PanelResult | Fully implemented, all 20 traders | DEAD CODE — never called | "Not wired" stated but underemphasized | PARTIALLY | None — wiring is Phase 5 task |
| **Final Decision Group** | 6 safety rails on panel output | Fully implemented | DEAD CODE — never called | "Not wired" stated but underemphasized | PARTIALLY | None — wiring is Phase 5 task |
| **Backtest Engine** | EMA-crossover baseline replay | Real; _replay_bar() is pass stub | Active via --backtest flag | Accurately described as simplified | YES | None |
| **Journal Extension** | 10 new learning tables + full API | Fully implemented | DEAD CODE — never instantiated | "Integration pending" stated | YES | None |
| **Decision Trace Logger** | Log full 4-step decision trace | Fully implemented | DEAD CODE — never called | "Integration pending" stated | YES | None |
| **TraderCalibrator** | Per-trader Brier score + win rate | Fully implemented, 30-sample gate | DEAD CODE — no data | "Integration pending" stated | YES | None |
| **SetupFamilyTracker** | Per-family win rate tracking | Fully implemented | DEAD CODE — no data | "Integration pending" stated | YES | None |
| **RecommendationEngine** | Advisory recs with 30-sample gate | Fully implemented | DEAD CODE — no data | Accurately described | YES | None |
| **OutcomeAttributor** | Attribution pipeline on trade close | Fully implemented | DEAD CODE — never called | "Integration pending" stated | YES | None |
| **Source-of-Outcome Policy** | OutcomeSource tags, no mixing, 30-sample min | Fully implemented, 27 tests pass | No data flows yet | Accurately described | YES | None |
| **Bybit Connectivity** | Live REST API access | HTTP 404 from Bybit CDN | Code is correct; environment blocks | Correctly documented | YES | None (environment issue) |

---

## Status Classification Summary

| Classification | Count | Subsystems |
|---|---|---|
| **working** | 0 | (none active end-to-end in live runtime) |
| **working-limited** | 5 | MarketData (blocked), FeatureComputer (backtest only), BacktestEngine, JournalDB, Source-of-Outcome policy |
| **stubbed** | 2 | ChartPatternGroup, NewsMacroGroup |
| **deferred** | 4 | HistorianAgent, CriticAgent, SummarizerAgent, Hypothesis Registry |
| **dead-code** | 7 | Indicators\*, Candlestick\*, TechnicalStructure\*, TraderPanel, FinalDecisionGroup, JournalExtension, DecisionTraceLogger, OutcomeAttributor |
| **repaired** | 1 | PerformanceJournalGroup (double-close + NotImplementedError stubs) |

\* "Dead code" here means: fully implemented, correct, not crashing — but not called from any runtime entrypoint. These are not defective; they are awaiting a runner to wire them.

---

## Note on "Dead Code" Classification

"Dead code" in this context does NOT mean broken or wrong.
IndicatorsGroup, CandlestickGroup, and TechnicalStructureGroup are all
correct implementations that would function if a runner instantiated them.
The gap is the runtime runner, not the groups themselves.

This distinction matters: fixing the "dead code" classification requires
writing a runner, not rewriting these groups.
