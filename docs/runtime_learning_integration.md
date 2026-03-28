# Runtime Learning Integration

**Phase:** 4.75 Runtime Wiring
**Date:** 2026-03-28

---

## How the Learning Layer Is Wired

### 1. JournalExtension shares the DB connection

`PerformanceJournalGroup` creates a `JournalDB` instance with its own SQLite
connection during `_setup()`. After all groups are set up, the runner calls
`_finalize_learning_wiring()` which attaches `JournalExtension` to that same
connection:

```
JournalExtension(journal_db._conn)
→ adds 10 new learning tables to the existing journal.db
→ no data migration needed
→ old tables (trades, signals, journal_events) unchanged
```

### 2. DecisionTraceLogger is injected into PanelDecisionGroup

```
PanelDecisionGroup._trace_logger = DecisionTraceLogger(
    extension=journal_extension,
    outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
)
```

Every setup that passes Layer B+C evaluation is logged:
- `setup_packets` row: full BTCSetupPacket serialized to JSON
- `trader_reviews` rows: 20 rows per evaluation (one per trader)
- `panel_summaries` row: aggregate panel result
- `final_decisions` row: FinalDecisionGroup output + safety rails triggered

### 3. Source-of-outcome tagging

All runtime writes use `OutcomeSource.EVENT_DRIVEN_RUNTIME`.
All backtest writes use `OutcomeSource.SIMPLIFIED_BACKTEST`.
These are never mixed in calibration queries.

---

## What Is NOT Yet Wired (Deferred)

### OutcomeAttributor on trade close

When `PerformanceJournalGroup._log_position_close()` fires, it does NOT yet
call `OutcomeAttributor.process_closed_trade()`. This means:

- `outcome_attributions` table is never written from runtime
- `trader_calibration` records are never updated
- `setup_family_records` are never updated
- `RecommendationEngine` has no data to work with

**Why not wired yet:** The attribution requires linking `trade_id` back to
`packet_id` / `panel_id` / `decision_id`. This requires `PositionOpenEvent`
to carry those IDs from PanelDecisionGroup forward through RiskLeverageGroup.
That schema change is a Phase 5 task.

### composite_score in trade journal

`PerformanceJournalGroup._log_position_open()` writes `composite_score=0.0`
because `PositionOpenEvent` does not carry the original proposal's score.
Same schema extension needed as above.

---

## Current Learning Layer Status

| Table | Written by runtime? | Notes |
|---|---|---|
| `setup_packets` | YES (if trace logger wired) | One row per panel evaluation |
| `trader_reviews` | YES (if trace logger wired) | 20 rows per panel evaluation |
| `panel_summaries` | YES (if trace logger wired) | One row per panel evaluation |
| `final_decisions` | YES (if trace logger wired) | One row per panel evaluation |
| `outcome_attributions` | NO | Deferred — requires schema extension |
| `trader_calibration` | NO | Deferred — requires attributions |
| `setup_family_records` | NO | Deferred — requires attributions |
| `specialist_group_records` | NO | Deferred — requires attributions |
| `learning_recommendations` | NO | Deferred — requires calibration data |

---

## Learning Data Volume Expectations

At 1 bar per hour with BTC paper trading:
- ~24 bars per day
- Assuming 5-10% of bars trigger confirmation gate: ~1-2 CandidateTradeEvents per day
- Assuming 50-70% of those pass Layer C: ~1 panel evaluation per day
- 20 `trader_reviews` rows per evaluation: ~20-40 new learning rows per day

Time to 30-sample minimum per trader: 30+ panel evaluations = ~30+ days

This is why 30-sample gates exist. Do not attempt to draw calibration conclusions
in the first week of paper trading.
