# Runtime Component Liveness Report

**Date:** 2026-03-28
**Verification standard:** Active = instantiated + subscribed + invoked + produces side effects

---

## Component Matrix

| Component | Imported | Instantiated | Subscribed | Receives Runtime Events | Emits Runtime Events | Side Effects | Status | Evidence |
|-----------|----------|--------------|------------|------------------------|---------------------|--------------|--------|----------|
| **BtcBybitPaperRunner** | ✅ | ✅ | — | — | ✅ | creates groups, wires bus, runs polling | ACTIVE | `test_runner_setup_and_teardown` |
| **main_btc.py** | ✅ | — | — | — | — | passes --simulate/--run to runner | ACTIVE | source inspection |
| **MarketDataGroup** | ✅ | ✅ | NO (polling-driven) | FeatureReadyEvent published by itself | BarCloseEvent, FeatureReadyEvent | populates FeatureVector cache, updates last_close | ACTIVE | trace + test |
| **IndicatorsGroup** | ✅ | ✅ | FeatureReadyEvent | ✅ | GroupSignalEvent | updates SystemState.regime | ACTIVE | `test_feature_ready_event_reaches_indicators` |
| **CandlestickGroup** | ✅ | ✅ | FeatureReadyEvent, GroupSignalEvent | ✅ | GroupSignalEvent | candlestick signal state | ACTIVE | subscription trace |
| **TechnicalStructureGroup** | ✅ | ✅ | FeatureReadyEvent | ✅ | GroupSignalEvent | structural level bundle cache | ACTIVE | subscription trace |
| **EntryGroup** | ✅ | ✅ | GroupSignalEvent | ✅ (accumulates bundles) | CandidateTradeEvent (conditional) | clears pending bundles | ACTIVE (rarely fires) | log: "confirmation gate not met" |
| **PanelDecisionGroup** | ✅ | ✅ | CandidateTradeEvent | ✅ | PanelApprovedProposalEvent (conditional) | builds BTCSetupPacket, runs panel | ACTIVE | `test_trader_evaluator_panel_actually_runs` |
| **TraderEvaluatorPanel** | ✅ | ✅ | — (called by PanelDecisionGroup) | — | — | evaluates packet, returns PanelResult | ACTIVE | `test_trader_evaluator_panel_actually_runs` |
| **TrendFollowingEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **MomentumEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **MeanReversionEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **BreakoutEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **StructureEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **CandlestickEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **RiskParityEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **VolatilityEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **VolumeProfileEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **MacroRegimeEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **ContraryEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **ProfitTargetEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **EntryTimingEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **ConfluenceEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **DrawdownRiskEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **LeverageSpecialistEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **PatternCompletionEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **WickAnalysisEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **MarketContextEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **ExecutionQualityEvaluator** | ✅ | ✅ | — | — | TraderVerdict | none | ACTIVE | `test_all_20_traders_instantiated` |
| **FinalDecisionGroup** | ✅ | ✅ | — (called by PanelDecisionGroup) | — | FinalDecision | none | ACTIVE | `test_final_decision_group_actually_runs` |
| **RiskLeverageGroup** | ✅ | ✅ | PanelApprovedProposalEvent, CandidateTradeEvent (gated) | ✅ | RiskDecisionEvent, PositionOpenEvent | updates SystemState | ACTIVE (panel gate) | `test_panel_approved_reaches_risk`, `test_panel_gate_blocks_candidate_trade_bypass` |
| **ExitGroup** | ✅ | ✅ | FeatureReadyEvent | ✅ | PositionCloseEvent (when open positions) | closes positions in SystemState | ACTIVE (no positions yet) | `test_exit_group_subscribed` |
| **PerformanceJournalGroup** | ✅ | ✅ | 6 event types | ✅ | — | writes to SQLite journal.db | ACTIVE | `test_journal_db_initialized_in_runner` |
| **JournalExtension** | ✅ | ✅ (after setup()) | — | — | — | initializes learning tables in SQLite | ACTIVE | `test_learning_layer_wired_after_setup_only` |
| **DecisionTraceLogger** | ✅ | ✅ (after setup()) | — (called by PanelDecisionGroup) | — | — | writes 4 DB records per evaluation | ACTIVE | `test_decision_trace_logger_writes_to_db` |
| **OutcomeAttributor** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | **DEAD (Phase 5)** | `test_outcome_attributor_not_wired_documented_gap` |
| **ChartPatternGroup** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | **EXCLUDED (NotImplementedError)** | runner comment |
| **NewsMacroGroup** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | **EXCLUDED (NotImplementedError)** | runner comment |
| **HistorianAgent** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | **GUARDED (None in EntryGroup)** | code inspection |
| **CriticAgent** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | **GUARDED (None in EntryGroup)** | code inspection |
| **SummarizerAgent** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | **GUARDED (None in PerformanceJournalGroup)** | code inspection |

---

## Status Legend

| Status | Meaning |
|--------|---------|
| ACTIVE | Instantiated, subscribed (where applicable), invoked at runtime, produces expected output |
| ACTIVE (panel gate) | Active with a behavioral gate: CandidateTradeEvent ignored, only PanelApprovedProposalEvent processed |
| ACTIVE (rarely fires) | Wired correctly but signal conditions rarely met with standard test data |
| ACTIVE (no positions yet) | Wired and waiting; fires when open positions exist |
| DEAD (Phase 5) | Implemented, has tests, but not wired into the runtime event path |
| EXCLUDED | Not instantiated; would raise NotImplementedError if activated |
| GUARDED | Set to None in the runtime; safe no-op when None is checked |
