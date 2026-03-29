# REMAINING BLOCKERS OR OPTIMIZATION SURFACE
**Date:** 2026-03-29
**Verdict:** GO

There are NO blockers to Phase 7. This document lists remaining non-blocking issues
and defines the optimization surface available for Phase 7 work.

---

## SECTION A: NON-BLOCKING ISSUES

These issues exist but do not prevent Phase 7 from starting. They should be addressed
at the next natural opportunity but are not required before Phase 7 begins.

### A1: runner.py Docstring Stale (Severity: LOW)

**File:** src/runtime/runner.py, lines 19-22
**Issue:** Docstring says:
```
Excluded groups (stubbed — raise NotImplementedError if triggered):
  ChartPatternGroup       — EXCLUDED: _process_features raises NotImplementedError
```
**Reality:** ChartPatternGroup is fully instantiated, wired, and active. The docstring
was not updated when Phase 6.4 activated ChartPatternGroup.
**Impact:** Misleading to a new reader. No runtime impact.
**Fix:** Update docstring to remove ChartPatternGroup from the excluded list and add
it to the active groups list.

---

### A2: EntryGroup Comment Says "Phase 4+" (Severity: LOW)

**File:** src/groups/entry/group.py, lines 110-111
**Issue:** Comment says:
```python
# "chart_pattern":  0.35,   # Phase 4+ (ChartPatternGroup not yet implemented)
# "historian":      0.10,   # Phase 4+ (HistorianAgent not yet wired)
```
**Reality:** Phase 4+ is now (Phase 6.4). ChartPatternGroup IS implemented and wired,
but it feeds the panel via cache rather than GroupSignalEvent. The 0.55 denominator
is correct by design, but the comment is misleading.
**Impact:** None to runtime. Confusing to a reader.
**Fix:** Update comment to explain the architecture clearly: ChartPatternGroup is active
but feeds only PanelDecisionGroup via cache wiring. EntryGroup composite_score does not
include chart_pattern_quality because no GroupSignalEvent is emitted. This is intentional.

---

### A3: Bybit Connectivity from Dev IP (Severity: ENVIRONMENT ONLY)

**Issue:** --run mode returns HTTP 404 from current dev IP (Bybit CDN restriction).
**Impact:** Live paper loop cannot run from this environment.
**Workaround:** --simulate mode works fully and exercises the complete pipeline.
**Fix:** Deploy from a clean network environment or use a VPN/proxy with Bybit access.
**Phase 7 impact:** None. --simulate and replay are sufficient for Phase 7 tuning work.

---

### A4: NewsMarcoGroup Not Implemented (Severity: LOW)

**Issue:** NewsMarcoGroup raises NotImplementedError and is not wired.
**Impact:** No macro event filter active. All proposals pass the macro filter trivially.
**Phase 7 impact:** None. Phase 7 does not require macro filtering. When NewsMarcoGroup
is eventually implemented, its influence weight will be a Phase 7+ calibration item.

---

### A5: HistorianAgent Not Wired (Severity: LOW)

**Issue:** HistorianAgent returns None/0.0 (not wired in runner).
**Impact:** historian_win_rate = 0.0 in all composite scores. The 0.10 weight is unused.
**Phase 7 impact:** None until HistorianAgent is implemented. When wired, its weight
becomes part of the tuning surface.

---

### A6: Calibration DB Empty (Severity: EXPECTED)

**Issue:** No live trades have been executed yet, so outcome_attributions, trader_calibration,
and setup_family tables are empty.
**Impact:** Outcome-driven evaluator tuning is not yet possible.
**Phase 7 plan:** Accumulate ≥50 paper trade outcomes via --simulate or replay, then
begin data-driven calibration. Start with fixture-based parameter exploration first.

---

## SECTION B: OPTIMIZATION SURFACE SUMMARY

The following are all eligible for Phase 7 tuning. See PHASE_7_TUNING_ELIGIBILITY.md
for full parameter ranges and guardrails.

| Category | Parameters | Current Values | Phase 7 Eligible |
|----------|-----------|----------------|-----------------|
| Panel thresholds | APPROVE_THRESHOLD, AVG_SCORE_THRESHOLD | 14/20, 6.5 | YES |
| Safety rails | min_avg, max_rejects, min_rr | 5.0, 12, 1.5 | YES |
| Entry weights | candlestick, indicator, structural | 0.25, 0.20, 0.10 | YES |
| Entry threshold | COMPOSITE_SCORE_THRESHOLD | 0.50 | YES |
| Evaluator scoring | 20 evaluators, condition-based adjustments | varies | YES (with data) |
| Risk sizing | risk_fraction, position_cap | 1%, 10% | YES |
| Exit parameters | trailing_activation, ATR_mult, time_stop | +1R, 2.0, 20 bars | YES |
| Fixture regime balance | SHORT/ranging/bear fixtures | none yet | YES |
| Abstain handling | Treat abstain as weak reject or neutral | neutral | YES |
| Hold vs enter sensitivity | composite_score gate, panel margin | 0.50, 14 | YES |

---

## SECTION C: WHAT MUST NOT BE TUNED IN PHASE 7

These are structural elements that must not be changed during Phase 7:

- The core EventBus pub/sub wiring
- The CandidateTradeEvent → PanelDecisionGroup → PanelApprovedProposalEvent flow
- The panel gate on RiskLeverageGroup (set_panel_wired = True)
- Source separation policy (EVENT_DRIVEN_RUNTIME vs simplified_backtest tagging)
- The 9 risk rules (can tune thresholds within them, but not remove rules)
- The FinalDecisionGroup structure (6 rails, not reducible to 0)
- The ModeGate.SHADOW vs RESEARCH distinction

---

## SECTION D: SHORTEST PATH TO FIRST DATA-DRIVEN TUNING

1. Run --simulate 500 or replay all 3 fixtures repeatedly to accumulate outcomes
2. Check /api/journal/calibration for trader calibration records
3. Identify evaluators with poor prediction accuracy (high vote counts, low hit rate)
4. Adjust those evaluators' scoring logic with documented justification
5. Re-run fixture suite to verify regressions hold
6. Repeat for next category

Estimated minimum outcomes before meaningful calibration: 50 closed trades.
