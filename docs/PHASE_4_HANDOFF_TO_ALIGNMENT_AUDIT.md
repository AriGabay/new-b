# Phase 4 Handoff to Alignment Audit

**Phase:** 4 → Alignment Audit
**Date:** 2026-03-28
**Document Purpose:** Complete handoff record for incoming alignment audit

---

## System State Summary

### Architecture
3-layer decision system (BTC/Bybit only, paper/simulation mode):

```
Layer A (10 specialist groups) → BTCSetupPacket
Layer B (20 trader evaluators) → PanelResult
Layer C (FinalDecisionGroup, 6 safety rails) → enter/hold
```

### Phase Completion Status
| Phase | Status | Notes |
|---|---|---|
| Phase 1 (Architecture) | ✅ Complete | Full group registry, ADRs, contracts |
| Phase 2 (Risk) | ✅ Complete | All 9 risk rules, deterministic |
| Phase 3 (BTC/Bybit Vertical Slice) | ✅ Complete | Entry price wired, exit logic done, journal writing |
| Phase 3.5 (Stabilization) | ✅ Complete | 5 critical fixes verified |
| Phase 4 (Learning Layer) | ✅ Code Complete | Integration not yet wired |
| Phase 5 (Live Exchange) | ❌ Not started | Requires clean network environment |

---

## What Is Verified vs. Unverified

### Verified (Code Correctness)
- BybitAdapter endpoint, parameter format, response parsing (code review)
- FeatureComputer: ATR14, EMA20/50/200, RSI14, BB, ADX14, volume metrics
- RiskLeverageGroup: all 9 rules, position sizing formula
- ExitGroup: stop/target/trailing/time priority logic
- JournalDB: schema, insert/update operations
- EntryGroup: entry price wiring, proposal building
- Learning layer: all calibration/tracking/attribution modules (unit tested)

### Unverified (Environment Limitations)
- **Bybit live API connectivity**: HTTP 404 from Bybit CDN (IP restriction).
  DNS resolves to real IP (3.169.71.104), TLS genuine. Code is correct.
  Must verify from clean deployment environment.
- **Full runtime paper trading**: MarketDataGroup.startup_load() and
  fetch_and_process() work correctly in code but cannot produce live bar data
  in this environment.
- **Panel wired into runtime**: Layer B (20 traders) and Layer C (final decision)
  are complete as code but not yet wired into main_btc.py loop.

---

## Known Limitations and Stubs

| Component | Status | Impact |
|---|---|---|
| ChartPatternGroup | STUBBED — emits no signals | chart_pattern_quality = 0.0 always |
| HistorianAgent | Not wired | historian_win_rate = 0.0 always |
| CriticAgent | Not wired | No LLM critique on proposals |
| BacktestEngine._replay_bar() | Intentional stub | Phase 4 integration hook |
| Rule 8 (event risk) | Returns 1.0 always | No news event system yet |
| Panel wiring | Not in main runtime | Layer B/C not live |
| DecisionTraceLogger wiring | Not in runtime | Learning tables not populated from live runs |

---

## Critical Architectural Invariants (Must Not Be Changed Without ADR)

1. **RiskLeverageGroup never reads LLM output.** ADR-003. Non-negotiable.
2. **CompositeScore threshold = 0.50** to pass confirmation gate.
3. **CriticAgent only invoked at score >= 0.60.** ADR-003.
4. **Position sizing: R-amount = equity × 1%, capped at 10% equity.**
5. **Trailing stop activates at +1R, ratchets only (never widens).**
6. **OutcomeSource must never be mixed in calibration metrics.**
7. **30-sample minimum for all calibration conclusions.**
8. **Journal is append-only** (one UPDATE exception on trade close).

---

## Files Created / Modified in Phase 4

### New Files
```
src/learning/__init__.py
src/learning/outcome_source.py
src/learning/schemas.py
src/learning/journal_extension.py
src/learning/decision_logger.py
src/learning/calibration.py
src/learning/tracking.py
src/learning/attribution.py
src/learning/recommendation_engine.py
src/learning/reports.py
src/tests/test_learning_layer.py
docs/journal_schema.md
docs/source_of_outcome_policy.md
docs/learning_logic.md
docs/trader_calibration_framework.md
docs/panel_consensus_framework.md
docs/specialist_group_reliability_framework.md
docs/example_learning_reports.md
docs/PHASE_4_LEARNING_STATUS.md
docs/PHASE_4_HANDOFF_TO_ALIGNMENT_AUDIT.md
```

### No Existing Files Were Modified
Phase 4 was implemented as a clean addition to `src/learning/`.
No existing group files, schema files, or runtime files were changed.

---

## Next Steps (Phase 5 Prerequisites)

Before going live with any real capital:

1. **Verify Bybit connectivity from deployment environment** — run
   `python scripts/bybit_smoke_test.py` and confirm all 6 layers pass.
   See `docs/bybit_connectivity_smoke_test.md`.

2. **Wire DecisionTraceLogger into runtime** — connect panel and final
   decision output to learning tables.

3. **Wire OutcomeAttributor on trade close** — connect
   `PerformanceJournalGroup._log_position_close()` to attribution pipeline.

4. **Implement ChartPatternGroup** — currently stubbed.

5. **Wire Panel into main runtime loop** — Layer B/C not yet active.

6. **Run 30+ paper trades** before relying on any calibration metrics.

7. **Conduct alignment audit** — review all ADRs, risk contracts, and
   learning policies before enabling live execution.

---

## Alignment Audit Checklist

- [ ] ADR-001 (BTC-only scope) still respected
- [ ] ADR-002 (deterministic pipelines first) still respected
- [ ] ADR-003 (LLM not in risk path) still respected
- [ ] Risk contract: all 9 rules implemented and tested
- [ ] OutcomeSource policy: no mixing in any query or metric
- [ ] Sample minimums enforced in all calibration code
- [ ] No automatic policy changes from recommendations
- [ ] Bybit connectivity verified from deployment machine
- [ ] ChartPatternGroup stubbed status documented
- [ ] Entry price wiring verified (startup_load lag documented)
