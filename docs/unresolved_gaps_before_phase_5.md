# Unresolved Gaps Before Phase 5

**Date:** 2026-03-28
**Purpose:** Honest enumeration of what is not finished and must be addressed before any live trading phase

This list is exhaustive for known gaps. Unknown gaps may exist.

---

## GAP 1 — Runtime Runner Does Not Exist

**Severity:** CRITICAL
**Status:** Not started
**Description:**
`main_btc.py` calls Bybit directly and runs standalone analysis. There is no
runner that instantiates all group classes, wires them to a shared EventBus,
calls `setup()` on each, and drives the polling loop.

Until this exists:
- No signals flow from IndicatorsGroup/CandlestickGroup/TechnicalStructureGroup to EntryGroup
- No CandidateTradeEvents are published
- No positions are opened
- No exits are evaluated
- No trades are logged by PerformanceJournalGroup
- No outcomes flow to the learning layer

**What's needed:** A `runner.py` or equivalent that wires the group pipeline.

---

## GAP 2 — Layer B and Layer C Not Connected to Runtime

**Severity:** HIGH
**Status:** Not started
**Description:**
`TraderEvaluatorPanel` and `FinalDecisionGroup` are implemented correctly but
are dead code. They are never called from any runtime entrypoint.

The intended flow:
`EntryGroup produces BTCSetupPacket → TraderEvaluatorPanel.evaluate() → FinalDecisionGroup.decide() → trade enters`

This flow is documented but not implemented in the runtime path.

**What's needed:**
Either (a) a new "Panel + Decision" group that sits between EntryGroup and
RiskLeverageGroup, or (b) direct integration in the runner.

---

## GAP 3 — ChartPatternGroup Raises NotImplementedError

**Severity:** MEDIUM
**Status:** Stubbed since Phase 1
**Description:**
`ChartPatternGroup._process_features()` raises `NotImplementedError`.
If the group is instantiated in a runner, it will crash when FeatureReadyEvent fires.

**What's needed:** Either implement the pattern detection or guard the group's
instantiation to skip if a stub flag is set.

---

## GAP 4 — NewsMacroGroup Raises NotImplementedError

**Severity:** MEDIUM
**Status:** Stubbed since Phase 1
**Description:**
`NewsMacroGroup._process_bar_close()` raises `NotImplementedError`.
Same risk as ChartPatternGroup.

**What's needed:** Implement macro regime classification or guard instantiation.

---

## GAP 5 — Learning Layer Not Wired to Runtime

**Severity:** MEDIUM
**Status:** Designed and implemented, not connected
**Description:**
`JournalExtension`, `DecisionTraceLogger`, and `OutcomeAttributor` exist as
correct implementations but are never called from any runtime path.

`PerformanceJournalGroup._log_position_close()` does not call `OutcomeAttributor`.
`FinalDecisionGroup.decide()` does not call `DecisionTraceLogger`.

**What's needed:** Wire attribution on trade close, wire trace logging on panel/decision events.

---

## GAP 6 — HistorianAgent Not Implemented

**Severity:** LOW (deferred)
**Status:** Not started
**Description:**
`EntryGroup._historian` is always None. `PerformanceJournalGroup.query_historical_analogs()`
returns empty dict. The historian_win_rate component of composite_score is always 0.0.

**Impact:** Composite score is effectively 0.10 lower than it would be with a functioning historian.
The 0.50 threshold may be calibrated incorrectly.

---

## GAP 7 — CriticAgent Not Implemented

**Severity:** LOW (deferred by design)
**Status:** Not started
**Description:**
`EntryGroup._critic` is always None. CriticReport is never generated.
CandidateTradeProposals are published without LLM critique regardless of composite score.

---

## GAP 8 — Bybit Live Connectivity Not Verified

**Severity:** HIGH for live operation
**Status:** Blocked by environment
**Description:**
Bybit API returns HTTP 404 from this machine's outbound IP. DNS and TLS pass.
This is a CDN IP-restriction issue, not a code defect.

**What's needed:** Run smoke test from clean deployment environment. See `bybit_connectivity_smoke_test.md`.

---

## GAP 9 — startup_load() Does Not Seed last_close_by_symbol

**Severity:** LOW
**Status:** Documented limitation
**Description:**
`MarketDataGroup.startup_load()` fetches initial bars but does not call
`state.update_last_close()`. The first call to `fetch_and_process()` that
returns a new bar will populate it. Until then, EntryGroup will abort any
proposal with `entry_price == 0`.

This means the first bar after startup cannot generate a valid proposal.

---

## GAP 10 — composite_score Hardcoded to 0.0 in Trade Open Journal Entry

**Severity:** LOW
**Status:** Known limitation
**Description:**
`PerformanceJournalGroup._log_position_open()` writes `composite_score=0.0`
because `PositionOpenEvent` does not carry the original proposal's composite_score.

**Impact:** Historical trade records in journal.db will show 0.0 for all composite scores,
making it impossible to correlate score quality with outcomes.

**What's needed:** Add `composite_score` to `PositionOpenEvent` schema or thread it through
`RiskApprovedOrder`.

---

## Summary Table

| Gap | Severity | Phase Required | Blocks Phase 5? |
|---|---|---|---|
| Runtime runner | CRITICAL | Before Phase 5 | YES |
| Layer B/C not wired | HIGH | Before Phase 5 | YES |
| ChartPatternGroup stub | MEDIUM | Phase 5+ (guard or implement) | NO (guard it) |
| NewsMacroGroup stub | MEDIUM | Phase 5+ (guard or implement) | NO (guard it) |
| Learning layer not wired | MEDIUM | Phase 5 | NO (Phase 5+) |
| HistorianAgent missing | LOW | Phase 5+ | NO |
| CriticAgent missing | LOW | Phase 5+ | NO |
| Bybit connectivity | HIGH | Before live | YES for live |
| startup_load() lag | LOW | Acceptable | NO |
| composite_score = 0.0 | LOW | Phase 5 | NO |
