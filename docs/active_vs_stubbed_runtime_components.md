# Active vs Stubbed Runtime Components

**Phase:** 4.75 Runtime Wiring
**Date:** 2026-03-28

---

## Active in Runtime (instantiated by BtcBybitPaperRunner)

| Component | Type | Status | What it does in runtime |
|---|---|---|---|
| MarketDataGroup | Group | ACTIVE | Fetches Bybit bars, publishes FeatureReadyEvent |
| IndicatorsGroup | Group | ACTIVE | Processes FeatureReadyEvent → GroupSignalEvent |
| CandlestickGroup | Group | ACTIVE | Processes FeatureReadyEvent → GroupSignalEvent |
| TechnicalStructureGroup | Group | ACTIVE | Processes FeatureReadyEvent → GroupSignalEvent |
| EntryGroup | Group | ACTIVE | Aggregates GroupSignalEvents → CandidateTradeEvent |
| PanelDecisionGroup | Group | ACTIVE (NEW) | Runs 20 traders + FinalDecisionGroup → PanelApprovedProposalEvent |
| TraderEvaluatorPanel | Layer B | ACTIVE (NEW) | 20 evaluators called per CandidateTradeEvent |
| FinalDecisionGroup | Layer C | ACTIVE (NEW) | 6 safety rails called after panel |
| RiskLeverageGroup | Group | ACTIVE | 9 deterministic risk rules → PositionOpenEvent |
| ExitGroup | Group | ACTIVE | Checks open positions on FeatureReadyEvent |
| PerformanceJournalGroup | Group | ACTIVE | Logs all events to SQLite |
| JournalExtension | Learning | ACTIVE (NEW) | 10 learning tables on same DB connection |
| DecisionTraceLogger | Learning | ACTIVE (NEW) | Logs full decision traces from PanelDecisionGroup |

---

## Excluded from Runtime (Stubbed)

| Component | Type | Status | Why Excluded |
|---|---|---|---|
| ChartPatternGroup | Group | EXCLUDED-STUB | `_process_features()` raises NotImplementedError |
| NewsMacroGroup | Group | EXCLUDED-STUB | `_process_bar_close()` raises NotImplementedError |
| HistorianAgent | Agent | EXCLUDED-DEFERRED | Not implemented; EntryGroup._historian = None |
| CriticAgent | Agent | EXCLUDED-DEFERRED | Not implemented; EntryGroup._critic = None |
| SummarizerAgent | Agent | EXCLUDED-DEFERRED | Not implemented; weekly summary = no-op |
| OutcomeAttributor | Learning | EXCLUDED-NOT-WIRED | Implemented but not called on trade close yet |
| TraderCalibrator | Learning | EXCLUDED-NOT-WIRED | Accumulates data only after close attribution |

---

## Impact of Excluded Components

### ChartPatternGroup excluded
- `chart_pattern_quality = 0.0` in composite score formula (weight 0.35)
- Maximum achievable composite score = 0.65 (candlestick + indicator + structural + historian)
- The 0.50 threshold is reachable with strong candlestick + indicator signals

### NewsMacroGroup excluded
- No news event calendar
- Macro regime (`btc_macro`) derived from FeatureVector EMA200 position only
- Event risk reduction (Rule 8) always returns multiplier 1.0

### HistorianAgent missing
- `historian_win_rate = 0.0` in composite score (weight 0.10)
- Maximum achievable composite score = 0.55 without chart patterns or historian

### OutcomeAttributor not wired
- Calibration tables (`trader_calibration`, `setup_family_records`) will not be updated
- This will be wired in a follow-up task when the position-close path is confirmed working

---

## Runtime Signal Flow

```
FeatureReadyEvent
  → IndicatorsGroup.handle_event()
  → publishes GroupSignalEvent(indicators bundle)

  → CandlestickGroup.handle_event()
  → publishes GroupSignalEvent(candlestick bundle)

  → TechnicalStructureGroup.handle_event()
  → publishes GroupSignalEvent(structural bundle)

  → ExitGroup.handle_event()
  → checks open positions, may publish PositionCloseEvent

GroupSignalEvent(s)
  → EntryGroup._collect_bundle()
  → confirmation gate: needs >=2 agreeing signals
  → if gate met: publishes CandidateTradeEvent

CandidateTradeEvent
  → PanelDecisionGroup._evaluate_proposal()
  → builds BTCSetupPacket
  → TraderEvaluatorPanel.evaluate(packet)
  → FinalDecisionGroup.decide(packet, panel)
  → if enter: publishes PanelApprovedProposalEvent
  → DecisionTraceLogger.log_*() (if wired)

PanelApprovedProposalEvent
  → RiskLeverageGroup._evaluate_proposal()
  → 9 risk rules
  → if approved: publishes PositionOpenEvent

PositionOpenEvent + PositionCloseEvent
  → PerformanceJournalGroup logs to SQLite
```
