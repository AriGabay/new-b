# EventBus Subscription Map — Runtime State

**Date:** 2026-03-28
**Source:** Live instrumented trace from `BtcBybitPaperRunner(simulation_mode=True)`

This map was captured by printing `runner.bus._subscribers` after `setup()` completes.

---

## Subscription Table

| Event | Subscribers | Notes |
|-------|-------------|-------|
| `FeatureReadyEvent` | IndicatorsGroup, CandlestickGroup, TechnicalStructureGroup, ExitGroup | 4 subscribers |
| `GroupSignalEvent` | CandlestickGroup, EntryGroup, PerformanceJournalGroup | CandlestickGroup reads structural context from TechnicalStructureGroup's signal |
| `CandidateTradeEvent` | PanelDecisionGroup, RiskLeverageGroup, PerformanceJournalGroup | RiskLeverageGroup subscription is GATED — ignored when `_panel_wired=True` |
| `PanelApprovedProposalEvent` | RiskLeverageGroup | Only emitted when panel (14/20) + FinalDecisionGroup approve |
| `RiskDecisionEvent` | PerformanceJournalGroup | Logs approval/rejection to journal |
| `PositionOpenEvent` | PerformanceJournalGroup | Logs trade open to journal |
| `PositionCloseEvent` | PerformanceJournalGroup | Logs trade close to journal |
| `SystemAlertEvent` | PerformanceJournalGroup | Logs system alerts to journal |

---

## Wiring Correctness

### ✅ Correct paths
- `FeatureReadyEvent` → IndicatorsGroup → `GroupSignalEvent` → EntryGroup (signal accumulation)
- `CandidateTradeEvent` → PanelDecisionGroup (panel evaluation) → `PanelApprovedProposalEvent` → RiskLeverageGroup
- `RiskDecisionEvent` → PerformanceJournalGroup (logging)

### ✅ Panel bypass blocked
`CandidateTradeEvent` → RiskLeverageGroup is GATED by `_panel_wired=True`. When the panel is wired (always in `BtcBybitPaperRunner`), RiskLeverageGroup drops `CandidateTradeEvent` silently and waits for `PanelApprovedProposalEvent`.

### ⚠️ Subscriptions absent from map
The following events have no current subscribers (not an error — they are published but not consumed by any active group):
- `BarCloseEvent` — published by MarketDataGroup; no consumer wired in current runtime
- `JournalEntryEvent` — defined but never published in current code

---

## Excluded Groups (Not Subscribed, Not Instantiated)

| Group | Reason |
|-------|--------|
| ChartPatternGroup | Raises NotImplementedError; safely excluded from runner |
| NewsMacroGroup | Raises NotImplementedError; safely excluded from runner |

---

## Unsubscribed Components (Exist But Not in EventBus)

| Component | Why Not Subscribed |
|-----------|-------------------|
| OutcomeAttributor | Not wired to PositionCloseEvent; Phase 5 work |
| HistorianAgent | Not instantiated; EntryGroup._historian is always None |
| CriticAgent | Not instantiated; EntryGroup._critic is always None |
| SummarizerAgent | Not instantiated; PerformanceJournalGroup._summarizer is None |
