# GO / NO-GO DECISION
**Audit Date:** 2026-03-29
**System:** BTC/Bybit Paper Trading — Phase 6.4
**Question:** Is the system ready to begin Phase 7 (learning, calibration, parameter tuning)?

---

## VERDICT

**GO — the system is sufficiently developed to move into Phase 7 learning/tuning.**

---

## HARD REASON

The active runtime path is built end-to-end, honest, and no longer blocked by any
structural defect. The system can naturally generate proposals, achieve panel approval,
pass risk evaluation, open a position, and close that position — all through the intended
runtime pipeline without forcing, overriding, or bypassing any component.

Future progress should come from calibrating parameters and weights, not from rewiring
foundational plumbing.

---

## EVIDENCE

### Natural runtime proof (fixture btc_double_bottom_long_v1):
- Panel result: **16/20 approvals, avg_score=7.325** → decision=enter
- Panel approval achieved without forcing or modifying any threshold or evaluator
- `PanelApprovedProposalEvent` fires exactly once (verified by test)
- Risk path passes all 9 rules → `PositionOpenEvent` published
- Position opened: entry=70600.0, stop=69301.240, target=73197.520, R:R≈2.0
- Learning IDs threaded: packet_id, panel_id, decision_id all populated in Position
- Full lifecycle: position opens AND closes within fixture run, total_trades=1

### Panel proof (fixture btc_w_bottom_long_v2):
- Baseline result: **14/20 approvals, avg_score=6.850** → decision=enter
- Not regressed by Phase 6.4 changes (confirmed by test)
- V1 fixture still correctly holds at 13/20 (regression locked)

### Test suite:
- **383 tests pass, 1 skipped, 0 failures** as of 2026-03-29
- All 27 runtime_wiring and runtime_verification tests pass
- test_end_to_end_position_opens: PASS
- test_end_to_end_position_closes_on_stop: PASS
- test_position_carries_learning_ids: PASS
- test_outcome_attributor_wired_after_setup: PASS
- Source separation tests: all PASS

---

## WHAT IS COMPLETE

1. **Core runtime path** — all 10 active groups instantiated, wired, and receiving events
2. **main_btc.py routing** — 4 modes correctly separated; --simulate uses real pipeline
3. **Setup packet assembly** — FeatureVector + structural + candlestick + chart_pattern data
4. **Panel path** — 20 deterministic evaluators + FinalDecisionGroup (6 safety rails) active
5. **Risk path** — 9 rules executed in sequence, position sized and opened on approval
6. **Open/close lifecycle** — PositionOpenEvent, PositionCloseEvent, SystemState updated
7. **Learning hooks** — DecisionTraceLogger, JournalExtension, OutcomeAttributor all wired
8. **Journal DB** — SQLite with all required tables; writes on open, close, and attribution
9. **Source separation** — outcome_source tagged; backtest results explicitly excluded from calibration
10. **Management console** — FastAPI + WebSocket + HTML frontend; reads real state and DB
11. **Replay harness** — RuntimeReplayHarness runs real pipeline with real panel + risk logic
12. **Validation fixtures** — 3 fixture variants covering different scenarios

---

## WHAT IS STILL INCOMPLETE (non-blocking)

1. **runner.py docstring** incorrectly says ChartPatternGroup is EXCLUDED — stale, code is correct
2. **ACTIVE_COMPOSITE_WEIGHT_SUM = 0.55** in EntryGroup does not include chart_pattern weight —
   intentional by design; ChartPatternGroup feeds panel via cache, not EntryGroup via events
3. **Bybit connectivity** blocked from dev IP (HTTP 404) — environment constraint, not code defect
4. **NewsMarcoGroup** not implemented — not required for Phase 7
5. **HistorianAgent** not wired (Phase 3 comment still present) — not required for Phase 7
6. **CriticAgent** not wired (composite_score >= 0.60 gate) — not required for Phase 7
7. **Live trading** not tested — by design, out of scope until Phase 7+ completes

---

## WHAT PHASE 7 MAY NOT BEGIN UNTIL FIXED

Nothing. There are no structural blockers.

Phase 7 may begin immediately.

---

## WHAT PHASE 7 IS (defined scope)

Phase 7 = learning, weighting, calibration, and parameter optimization.

Eligible work includes:
- Adjusting per-group weights in EntryGroup's composite_score formula
- Adjusting per-evaluator weights in TraderEvaluatorPanel
- Adjusting approval count threshold (currently 14/20)
- Adjusting minimum average score threshold (currently 6.5)
- Adjusting composite_score entry threshold (currently 0.50)
- Adjusting setup quality classification thresholds (A/B/C/invalid)
- Tuning confluence rules and regime filters
- Calibrating evaluator influence from outcome attribution data
- Optimizing replay fixture regime balance
- Tuning risk sizing parameters

See PHASE_7_TUNING_ELIGIBILITY.md for the full safe optimization surface and guardrails.

---

## WHAT PHASE 7 IS NOT

- NOT: live trading
- NOT: LLM agent rewrite
- NOT: multi-symbol expansion
- NOT: Binance or altcoin support
- NOT: changing the core runtime architecture
- NOT: adding new groups without validation
