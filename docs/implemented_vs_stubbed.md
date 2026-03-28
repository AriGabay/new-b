# Implemented vs Stubbed — Component Status Table

**Updated:** 2026-03-28
**Phase:** 3 (BTC/Bybit Vertical Slice)

Legend:
- **IMPLEMENTED**: Real working code. No `NotImplementedError`. Tested or testable.
- **PARTIAL**: Core logic present but some methods stubbed or quality scores hardcoded.
- **STUBBED**: `raise NotImplementedError` or `pass` — produces no useful output.
- **DESIGN-ONLY**: Architecture defined, no code written yet.

---

| Component | File | Status | Notes |
|---|---|---|---|
| BybitAdapter | `src/data/bybit.py` | IMPLEMENTED | Full Bybit V5 REST, pagination, OHLCVBar construction |
| FeatureComputer | `src/features/compute.py` | IMPLEMENTED | All 11 methods: ATR, EMA-20/50/200, RSI, BB, ADX, Volume, Candle anatomy |
| FeatureVector | `src/core/schemas.py` | IMPLEMENTED | Frozen dataclass, all fields present including prev_ema20/50 |
| JournalDB | `src/journal/db.py` | IMPLEMENTED | Real SQLite DDL, 3 tables, WAL mode, all CRUD methods |
| ATRStopPlacer | `src/risk/stop_placer.py` | IMPLEMENTED | ATR-scaled stops with round-number protection |
| RMultipleSizer | `src/risk/sizer.py` | IMPLEMENTED | Real R-multiple math, returns PositionSizeResult |
| BacktestEngine | `src/backtest/engine.py` | PARTIAL | EMA crossover only (H3-002). Full group pipeline NOT replayed. |
| BacktestConfig | `src/backtest/engine.py` | IMPLEMENTED | All config fields present |
| BacktestResult | `src/backtest/engine.py` | IMPLEMENTED | summary() method works; sharpe_ratio always 0.0 |
| EntryGroup | `src/groups/entry/group.py` | IMPLEMENTED | _collect_bundle, _evaluate_trade_opportunity, _compute_composite_score, _build_proposal all implemented |
| IndicatorsGroup | `src/groups/indicators/group.py` | PARTIAL | Regime classification works; signal quality scores hardcoded; EMA/RSI/BB signals outlined |
| TechnicalStructureGroup | `src/groups/technical_structure/group.py` | PARTIAL | Swing detection present; at_resistance/at_support flags computed; level quality uncertain |
| CandlestickGroup | `src/groups/candlestick/group.py` | PARTIAL | Engulfing, Doji, Hammer, Star patterns implemented; H2-004 Inverted Hammer missing; quality unvalidated |
| ChartPatternGroup | `src/groups/chart_pattern/group.py` | STUBBED | State machine framework present; H1-001 partial; H1-002 through H1-005 are stubs |
| MarketDataGroup | `src/groups/market_data/group.py` | PARTIAL | REST polling implemented; WebSocket not implemented; BTCUSDT hardwired |
| ExitGroup | `src/groups/exit/group.py` | PARTIAL | Stop/target/time-stop checks present; trailing stop stub; not wired to SystemState |
| RiskLeverageGroup | `src/groups/risk_leverage/group.py` | PARTIAL | 9 rules coded; Rule 7 (mode gate) always blocks in RESEARCH mode; leverage not applied to order |
| NewsGroup / MacroGroup | `src/groups/news_macro/group.py` | STUBBED | Returns empty bundle; no news ingestion; no macro calendar |
| PerformanceJournalGroup | `src/groups/performance_journal/group.py` | PARTIAL | Writes to JournalDB; edge decay detection stubbed; metrics return zeros |
| FinalDecisionGroup | `src/decision/` | IMPLEMENTED | Panel aggregation, quorum threshold, FinalDecision output |
| 20 Trader Evaluators | `src/traders/` | IMPLEMENTED | All 20 evaluators with real scoring logic per persona |
| EventBus | `src/core/events.py` | IMPLEMENTED | asyncio pub/sub, never raises, subscriber exceptions caught |
| SystemState | `src/core/state.py` | IMPLEMENTED | Portfolio state, risk state, regime, asyncio.Lock for mutations |
| OHLCVBar | `src/core/schemas.py` | IMPLEMENTED | Frozen dataclass, invariants enforced in __post_init__ |
| CandidateTradeProposal | `src/core/schemas.py` | IMPLEMENTED | Full dataclass with all fields |
| RegimeContext | `src/core/schemas.py` | IMPLEMENTED | Dataclass; computed in IndicatorsGroup and main_btc.py |
| GroupSignalBundle | `src/core/schemas.py` | IMPLEMENTED | Dataclass with signals list, regime, structural bundle |
| BTCSetupPacket | `src/core/setup_packet.py` | IMPLEMENTED | Dataclass definition complete; not yet assembled in live pipeline |
| SetupProposal | `src/core/setup_packet.py` | IMPLEMENTED | Dataclass definition complete |
| GroupRegistry | `src/core/registry.py` | IMPLEMENTED | All 10 groups registered with metadata |
| HypothesisRegistry | `src/core/registry.py` | IMPLEMENTED | 22 hypotheses with status, sprint, priority, acceptance criteria |
| LeverageGovernor | `src/risk/` | PARTIAL | Compute method implemented; NOT wired to order sizing |
| HistorianAgent | `src/agents/historian/` | DESIGN-ONLY | Interface defined; no implementation; EntryGroup skips safely |
| CriticAgent | `src/agents/critic/` | DESIGN-ONLY | Interface defined; LLM integration deferred to Phase 4 |
| ConflictAgent | `src/agents/conflict/` | DESIGN-ONLY | EntryGroup uses direction counting instead |
| ExecutionGroup | `src/execution/` | DESIGN-ONLY | Placeholder files; no order routing |
| WebSocket Feed | `src/data/` | DESIGN-ONLY | Not implemented; Phase 4 deliverable |
| main_btc.py | `src/main_btc.py` | IMPLEMENTED | Analysis and backtest modes; regime classification; signal detection; journal write |
| main.py | `src/main.py` | PARTIAL | Original entrypoint; may reference stale paths |

---

## Coverage by Hypothesis Sprint

| Sprint | Hypotheses | Code Coverage | Status |
|---|---|---|---|
| S1 | H3-002 (EMA crossover), H3-003 (ATR stops), H4-001 (volume filter), H5-002 (pump filter) | Partial | H3-002 in BacktestEngine; H3-003 in ATRStopPlacer; H4-001 / H5-002 not tested |
| S2 | H1-001 through H1-005 (chart patterns) | Low | State machine framework only; H1-001 partial |
| S3 | H1-006 through H1-009 (flags, wedges), H3-001 (RSI divergence) | Minimal | H3-001 check in main_btc.py only |
| S4 | H2-001 through H2-005 (candlestick patterns) | Partial | Basic patterns implemented; not validated |
| S5 | H1-007, H2-004, H3-004 (BB squeeze), H4-002/003, H5-001 | Minimal | H3-004 BB squeeze check in main_btc.py |

---

## Risk Summary

The components most likely to cause silent incorrect behavior (as opposed to
visible crashes) are:

1. **ChartPatternGroup**: Fully stubbed. composite_score chart_pattern_quality = 0.0
   always. Trades will never pass the 0.50 threshold unless indicator + candlestick
   scores alone total >= 0.50 (maximum possible = 0.45 with current weights).
   **Result: EntryGroup will produce zero proposals in the live pipeline.**

2. **RiskLeverageGroup Rule 7**: Mode gate is always RESEARCH. Even if EntryGroup
   publishes a proposal, RiskLeverageGroup will reject it before any order is placed.
   This is correct and intentional but means no SHADOW/LIVE promotion path exists
   until this is reconfigured.

3. **BacktestEngine simplified**: Results are for H3-002 only. Do not cite Phase 3
   backtest numbers as evidence for chart pattern or candlestick hypothesis performance.
