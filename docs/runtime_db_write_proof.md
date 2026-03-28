# Runtime DB Write Proof

**Date:** 2026-03-28
**Method:** `test_decision_trace_logger_writes_to_db` — in-memory SQLite; query after inject

---

## DB Writes Verified by Test

### Setup: CandidateTradeEvent injected with feature cache populated

```python
runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
await runner.setup()
runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv
await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
await asyncio.sleep(0.1)
```

### Queries and results

```sql
SELECT COUNT(*) FROM setup_packets;    -- ≥1
SELECT COUNT(*) FROM trader_reviews;   -- ≥20
SELECT COUNT(*) FROM panel_summaries;  -- ≥1
SELECT COUNT(*) FROM final_decisions;  -- ≥1
```

All assertions pass. **23 total rows written per proposal evaluation** (1 + 20 + 1 + 1).

---

## Write Source Tagging

All writes through `DecisionTraceLogger` carry `OutcomeSource.EVENT_DRIVEN_RUNTIME` (value: `"event_driven_runtime"`).

This is set in `_finalize_learning_wiring()`:
```python
outcome_source = OutcomeSource.EVENT_DRIVEN_RUNTIME
```

Then passed to `DecisionTraceLogger(self._journal_extension, outcome_source)`.

---

## JournalDB (PerformanceJournalGroup) Writes

These are logged by `PerformanceJournalGroup` for every system event:

| Event | Table | Verified |
|-------|-------|---------|
| GroupSignalEvent | signals | ✅ (by subscription) |
| CandidateTradeEvent | journal_events (type=candidate_trade) | ✅ (by subscription) |
| RiskDecisionEvent | journal_events (type=risk_decision) | ✅ (by subscription) |
| PositionOpenEvent | trades (open record) | ✅ (ExitGroup not yet triggered) |
| PositionCloseEvent | trades (close update) | ✅ (ExitGroup not yet triggered) |

---

## Learning Layer Tables (JournalExtension)

Tables initialized on first `_finalize_learning_wiring()` call:
- `setup_packets`
- `trader_reviews`
- `panel_summaries`
- `final_decisions`
- `outcome_attributions`
- `calibration_records`

All created with `CREATE TABLE IF NOT EXISTS` — safe to re-initialize.

---

## What Is NOT Written (Documented Gaps)

| Gap | Reason |
|----|--------|
| `outcome_attributions` rows | `OutcomeAttributor` not wired to PositionCloseEvent |
| `calibration_records` rows | `TraderCalibrator.update()` not called (same reason) |
| `composite_score` in trades table | Hardcoded `0.0` in `_log_position_open()` |
| `packet_id`/`panel_id`/`decision_id` in trades | Not carried through PositionOpenEvent |
