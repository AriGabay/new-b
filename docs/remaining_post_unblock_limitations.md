# Remaining Post-Unblock Limitations

**Date:** 2026-03-28
**Context:** After Phase 3 execution unblock — honest accounting of what is still incomplete

---

## What Is Now Fully Working

| Capability | Status |
|-----------|--------|
| CandidateTradeEvent → 20-trader panel | ✅ ACTIVE |
| FinalDecisionGroup safety rails | ✅ ACTIVE |
| DecisionTraceLogger (23 DB rows per evaluation) | ✅ ACTIVE |
| Panel gate blocks bypass | ✅ ACTIVE |
| raw_target enrichment (Risk Rule 9 passes) | ✅ ACTIVE (Phase 3) |
| RiskLeverageGroup → state.open_position() | ✅ ACTIVE (Phase 3) |
| PositionOpenEvent published | ✅ ACTIVE (Phase 3) |
| ExitGroup detects stop/target/time stops | ✅ ACTIVE |
| PerformanceJournalGroup logs open + close | ✅ ACTIVE (composite_score fixed Phase 3) |
| OutcomeAttributor wired to PositionCloseEvent | ✅ ACTIVE (Phase 3) |
| Position carries learning DB IDs | ✅ ACTIVE (Phase 3) |
| SystemState in SHADOW mode | ✅ ACTIVE |

---

## Remaining Limitations

### L1 — OutcomeAttributor does not receive per-trader vote detail

**Location:** `groups/performance_journal/group.py` `_log_position_close()`

**Detail:** `OutcomeAttributor.process_closed_trade()` accepts a `trader_reviews` parameter (list of dicts with `trader_name`, `vote`, `score`, `confidence`). This is currently passed as `None`. The trader review data is stored in the `trader_reviews` DB table (keyed by `packet_id`), but is not re-queried at close time and passed to the attributor.

**Impact:** `TraderCalibrator.process_trade_outcome()` runs (incrementing vote counts, outcomes) but cannot do per-review linkage. Calibration records update correctly overall — the individual review rows in `trader_reviews` are not annotated with outcome.

**Fix path:** In `_log_position_close()`, if `pos.packet_id` is non-empty, query `trader_reviews WHERE packet_id = pos.packet_id` from the learning DB and pass to `process_closed_trade(trader_reviews=[...])`.

---

### L2 — OutcomeAttributor does not receive group_signals

**Location:** `groups/performance_journal/group.py` `_log_position_close()`

**Detail:** `OutcomeAttributor.process_closed_trade()` accepts a `group_signals` parameter (list of dicts with `group_id`, `quality_score`) for `SpecialistGroupTracker`. This is currently passed as `None`. Specialist group performance records (`specialist_group_records` table) are not updated.

**Impact:** `SpecialistGroupTracker.process_trade_outcome()` is never called. The `specialist_group_records` table stays empty.

**Fix path:** `CandidateTradeProposal.score_breakdown` carries per-group quality scores. These can be passed through `Position.metadata` (a dict field, currently unused) or via a new `setup_refs` convention.

---

### L3 — HistorianAgent still None in EntryGroup

**Location:** `groups/entry/group.py`

**Detail:** `self._historian = None` in `__init__`. `EntryGroup._build_proposal()` has the path `if self._historian is not None: analog = self._historian.query(...)` but it never executes. `CandidateTradeProposal.historian_analog` is always `None`. Composite score is ~0.10 lower than potential because the historian win-rate component is missing.

**Fix path:** Instantiate `HistorianAgent(self._performance_journal.query_historical_analogs)` and inject into `EntryGroup`. Requires `PerformanceJournalGroup` to have sufficient trade history first (minimum 30 trades per hypothesis).

---

### L4 — CriticAgent still None in EntryGroup

**Location:** `groups/entry/group.py`

**Detail:** `self._critic = None`. No LLM advisory on proposals. `CandidateTradeProposal.critic_report` is always `None`. No LLM calls are made for any proposal.

**Fix path:** Instantiate `CriticAgent` and inject when `composite_score >= 0.60`. Requires ADR-003 compliance (LLM permitted in EntryGroup critic path only).

---

### L5 — MACD values are zero in BTCSetupPacket

**Location:** `runtime/setup_packet_builder.py` `build_indicator_snapshot()`

**Detail:** `FeatureVector` does not include MACD. `IndicatorSnapshot.macd` defaults to `MACDValues(0, 0, 0, "neutral")`. All 20 trader evaluators that reference MACD see flat/neutral MACD regardless of actual market state.

**Fix path:** Add MACD computation to `FeatureVector` (requires 26+9 bar lookback). Add to `features/compute.py`.

---

### L6 — ChartPatternGroup excluded

**Location:** `runtime/runner.py` (not instantiated)

**Detail:** `ChartPatternGroup._process_features()` raises `NotImplementedError`. `ChartPatternSnapshot` in every `BTCSetupPacket` is empty (`confirmed_patterns=[]`). `PatternCompletionEvaluator` always sees no patterns.

**Impact:** `CandidateTradeProposal.raw_target` is never set to a chart pattern conservative target. The `raw_target` enrichment fallback (ATR 2R) is always used.

**Fix path:** Phase 5+ — implement `ChartPatternGroup.process_features()`.

---

### L7 — SummarizerAgent not implemented

**Location:** `groups/performance_journal/group.py`

**Detail:** `_run_weekly_summary()` is a no-op stub. `self._summarizer = None`. No weekly narrative report is generated.

**Impact:** No LLM narrative. No performance summary sent to human operator.

**Fix path:** Phase 5+ — implement `SummarizerAgent` (LLM permitted per ADR-003).

---

### L8 — Bybit connectivity not tested in CI

**Detail:** Live `BtcBybitPaperRunner.run_paper_loop()` requires Bybit HTTP connectivity. Dev environment has IP restriction (HTTP 404 from CDN). All tests use `simulation_mode=True`.

**Impact:** No CI test of real market data processing. Live mode path is structurally correct but not exercised.

---

## Summary Table

| Gap | Severity | Phase |
|----|----------|-------|
| trader_reviews not passed to OutcomeAttributor | Low — calibration runs, just without vote detail | Phase 5 |
| group_signals not passed to OutcomeAttributor | Low — specialist records stay empty | Phase 5 |
| HistorianAgent None | Medium — composite_score 0.10 lower | Phase 5 |
| CriticAgent None | Low — no LLM advisory | Phase 5 |
| MACD zeros in BTCSetupPacket | Medium — 4+ evaluators see neutral MACD | Phase 5 |
| ChartPatternGroup excluded | Medium — no pattern signals, raw_target uses ATR fallback | Phase 5+ |
| SummarizerAgent stub | Low — no narrative report | Phase 5+ |
| Bybit connectivity untested in CI | Info — simulation mode covers all logic | Phase 5+ |
