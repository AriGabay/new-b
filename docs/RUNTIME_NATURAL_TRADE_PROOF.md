# RUNTIME NATURAL TRADE PROOF
**Date:** 2026-03-29
**Standard:** A natural trade is one achieved without forcing, overriding, or bypassing any
system component. No panel threshold changes. No evaluator weight changes. No risk rule bypass.

---

## PROOF 1: Natural Panel Approval (Phase 6.3, btc_w_bottom_long_v2)

**Fixture:** btc_w_bottom_long_v2 (260 bars)
**Fixture type:** runtime replay through real BtcBybitPaperRunner
**No forcing:** panel.evaluate() not patched; thresholds not changed

**Result:**
- PanelApprovedProposalEvent: **exactly 1** (test asserts == 1)
- approve_count: **14/20** (threshold: 14)
- avg_score: **6.850** (threshold: 6.5)
- decision: enter
- entry_price: 70500.0
- composite_score: 0.8545

**Mechanism:**
- VolumeProfileEvaluator: abstain(5.0) → approve(7.0) via vol_ratio=1.227 > 1.2
  - Entry bar: open=69700, close=70500, body=800
  - 3 consolidation bars before (small bodies → low rolling volume SMA → high vol_ratio)
  - vol_ratio=1.227 triggers: +1.0 (ratio > 1.2) + 1.0 (character=above_avg) = 7.0 → approve
- BreakoutEvaluator: reject(4.5) → abstain(5.5) (no W-bottom confirmation yet)
- Net change: 13 → 14 approvals (VolumeProfile abstain→approve)

**Tests that prove this:**
- `test_v2_fixture_fires_exactly_one_panel_approved_event` — PASS
- `test_v2_approved_event_has_correct_panel_counts` — PASS
- `test_v2_approved_event_avg_score` — PASS
- `test_v2_approved_event_entry_price` — PASS
- `test_v2_approved_event_direction_long` — PASS
- `test_panel_gate_is_active` — PASS
- `test_v1_still_fires_zero_approved_events` (regression) — PASS
- `test_no_direct_approval_injection` — PASS

---

## PROOF 2: Enhanced Panel Approval with Chart Pattern (Phase 6.4, btc_double_bottom_long_v1)

**Fixture:** btc_double_bottom_long_v1 (260 bars)
**Fixture type:** runtime replay through real BtcBybitPaperRunner
**No forcing:** panel.evaluate() not patched; thresholds not changed; ChartPatternGroup active

**Result:**
- PanelApprovedProposalEvent: **exactly 1** (test asserts == 1)
- approve_count: **16/20** (threshold: 14; +2 vs V2 baseline)
- avg_score: **7.325** (threshold: 6.5)
- decision: enter
- entry_price: 70600.0
- composite_score: 0.8545

**Mechanism (additional approvals over V2 baseline):**
- DoubleBottomMachine reaches CONFIRMED state at bar 249
  - neckline_price: ~70300
  - measured_move: ~500
  - close at bar 249 (70600) > neckline (70300) → CONFIRMED
- ChartPatternGroup populates _signals_cache with ChartPatternSignal (H1-003, double_bottom)
- PanelDecisionGroup reads cache → BTCSetupPacket includes chart pattern data
- PatternCompletionEvaluator: approve (10.0) — confirmed double bottom with conservative target
- BreakoutEvaluator: abstain(5.5) → approve (7.5) — proximity to confirmed neckline breakout
- Net change: 14 → 16 approvals (+2 from chart pattern evaluators)

**V2 regression confirms no regression:**
- V2 fixture after ChartPatternGroup wiring: still 14/20 approvals (machine not confirmed) ✓

**Tests that prove this:**
- `test_v3_fixture_fires_exactly_one_approved_event` — PASS
- `test_v3_panel_approve_count_is_16` — PASS
- `test_v3_panel_avg_score_exceeds_7` — PASS
- `test_v3_entry_price_is_70600` — PASS
- `test_v2_still_fires_14_approvals` — PASS
- `test_v1_still_fires_zero_approved_events` — PASS
- `test_panel_threshold_unchanged` (14/20, 6.5 confirmed) — PASS
- `test_chart_pattern_group_is_wired_in_runner` — PASS
- `test_no_direct_approval_injection` — PASS

---

## PROOF 3: Natural Position Open (full risk path)

**Method:** V3 fixture through real pipeline (bus.publish patched for capture only, not
panel logic).

**Direct runtime verification (executed 2026-03-29):**
```
PanelApprovedProposalEvents: 1
PositionOpenEvents: 1
  approve_count=16, avg=7.325
  entry=70600.0, raw_target=73197.52, score=0.8545
  Position:
    entry_price=70600.0
    stop_price=69301.240
    target_price=73197.520
    position_size_usd=10000.00
    leverage=0.1
    r_amount=1000.0
    correlation_cluster='btc'
    setup_refs=['indicator', 'candlestick']
    hypothesis_refs=['H3-005', 'H2-001']
    composite_score=0.8545
    packet_id='42fc0b7a-...' (non-empty)
    panel_id='593fcfb5-...' (non-empty)
    decision_id='aa94a1af-...' (non-empty)
```

All 9 risk rules passed:
1. Mode = SHADOW (not RESEARCH) ✓
2. daily_pnl_pct = 0% > -2% ✓
3. drawdown_pct = 0% < 10% ✓
4. portfolio_exposure = 0% < 25% ✓
5. btc_cluster = 0% < 15% ✓
6. BTCUSDT in eligible_symbols ✓
7. vol_ratio = 1.24 < 5.0 ✓
8. no event risk → no size reduction ✓
9. entry/stop/target present, hypothesis_refs set, score=0.8545 >= 0.50 ✓

R:R ratio: (73197.52 - 70600) / (70600 - 69301.24) = 2597.52 / 1298.76 ≈ 2.0

---

## PROOF 4: Natural Position Close

**Method:** V3 fixture run through full pipeline.

**Result:**
- PositionOpenEvents: 1
- PositionCloseEvents: 1
- total_trades: 1

The position opened at bar 249 (entry=70600) and closed naturally within the 10
continuation bars (bars 250-259) of the fixture. ExitGroup processed each bar and
triggered exit based on stop/target/trailing stop/time conditions without any
override or forcing.

**Confirms:** The full trade lifecycle (open → hold → close) works through the intended
runtime path.

---

## DISTINCTION FROM FORCED TESTS

Proof tests (Proofs 1-4) use the real pipeline with no component overriding.
The following forced tests exist separately and are clearly labeled:
- `test_end_to_end_position_opens`: uses `_make_force_approve_panel()` to patch panel.evaluate()
- `test_end_to_end_position_closes_on_stop`: also uses forced panel + crash bar

These forced tests verify the risk/open/close mechanics in isolation.
They are NOT the natural trade proof. They are labeled as such in the test code.

The natural trade proof is Proofs 1-4 above.
