# End-to-End Position Flow Proof

**Date:** 2026-03-28
**Verification method:** Automated integration tests with state inspection

---

## What "End-to-End" Means Here

Full wired path from CandidateTradeEvent to PositionCloseEvent, with:
- All real components (no mocked pipeline stages)
- Panel forced-approve via patched `panel.evaluate` (returns real `PanelResult` + `TraderVerdict` objects)
- Real `FinalDecisionGroup.decide()` runs on the real `PanelResult`
- Real risk rules all execute in sequence
- Real `state.open_position()` updates `SystemState.portfolio.open_positions`
- Real `ExitGroup._check_exits()` scans open positions on each bar
- Real `PerformanceJournalGroup._log_position_close()` updates DB and runs `OutcomeAttributor`

---

## Position Open Flow

### Step 1: Panel forces approval
```python
runner._panel_decision._panel.evaluate = _make_force_approve_panel()
# → PanelResult(approve_count=14, reject_count=3, abstain_count=3, avg_score=7.0)
```

### Step 2: PanelDecisionGroup enriches proposal and publishes
```
PanelDecisionGroup._evaluate_proposal(proposal):
  1. build_btc_setup_packet(proposal, fv) → packet
     └─ build_setup_proposal(proposal, fv):
           entry_price = 65000
           stop_price = 65000 - 2×800 = 63400          [2×ATR14]
           stop_dist = 1600
           target_price = 65000 + 2×1600 = 68200        [2R target]
           → SetupProposal(target_price=68200)
  2. TraderEvaluatorPanel.evaluate(packet) → PanelResult(14/20 approve)
  3. FinalDecisionGroup.decide(packet, panel_result) → FinalDecision("enter")
  4. DecisionTraceLogger writes: 1 packet + 20 reviews + 1 summary + 1 decision = 23 rows
  5. enriched_proposal = dataclass_replace(proposal, raw_target=68200)
  6. bus.publish(PanelApprovedProposalEvent(
         proposal=enriched_proposal,    ← raw_target=68200, not 0
         packet_id="uuid-xxx",
         panel_id="uuid-yyy",
         decision_id="uuid-zzz",
     ))
```

### Step 3: RiskLeverageGroup evaluates
```
RiskLeverageGroup._handle_event(PanelApprovedProposalEvent):
  → _evaluate_proposal(proposal, packet_id, panel_id, decision_id)
  Rule 1: state.mode == SHADOW (not RESEARCH) → PASS
  Rule 2: daily_pnl_pct = 0.0 > -0.02 → PASS
  Rule 3: drawdown_pct = 0.0 < 0.10 → PASS
  Rule 4: open exposure = 0 → PASS
  Rule 5: BTC cluster = 0 → PASS
  Rule 6: BTCUSDT in eligible_symbols → PASS
  Rule 7: volume_ratio = 1.25 < 5.0 → PASS
  Rule 8: no news event → size_reduction = 1.0
  Rule 9: raw_target = 68200 > 0 ✓
          hypothesis_refs = ["H3-001","H3-002"] ✓
          composite_score = 0.65 >= 0.50 ✓
          → PASS

  → _compute_order() → RiskApprovedOrder(
        stop_price=63400, target_price=68200,
        position_size_usd=~1000, leverage=~0.02x
    )
  → _approve(proposal, order, packet_id, panel_id, decision_id):
      bus.publish(RiskDecisionEvent(approved=True))
      position = Position(
          symbol="BTCUSDT", direction=LONG,
          entry_price=65000, stop_price=63400, target_price=68200,
          composite_score=0.65,
          packet_id="uuid-xxx",    ← threaded from PanelApprovedProposalEvent
          panel_id="uuid-yyy",
          decision_id="uuid-zzz",
      )
      await state.open_position(position)    ← adds to portfolio.open_positions
      bus.publish(PositionOpenEvent(position=position))
```

### State after open
```python
assert len(runner.state.portfolio.open_positions) == 1   # ✅ VERIFIED
assert runner.state.portfolio.available < Decimal("100000")   # reduced by position_size_usd
```

---

## Position Close Flow

### Step 4: Simulate crash bar (price crosses stop)
```python
fv_crash = make_fv(price=crash_price)
# Override low to guarantee stop hit: low = stop_price - 1000 (well below stop)
fv_crash = dc_replace(fv_crash, low=stop_price - 1000, close=crash_price)
await bus.publish(FeatureReadyEvent(features=fv_crash))
```

### Step 5: ExitGroup fires
```
ExitGroup._check_exits(fv_crash):
  for position_id, position in state.portfolio.open_positions.items():
    if position.symbol != fv_crash.symbol: continue
    exit_signal = _evaluate_position(position, fv_crash):
      _check_stop_loss():
        direction == LONG → fv_crash.low <= stop_price → True ✓
        return ExitSignal(exit_reason=STOP_LOSS, exit_price=stop_price, ...)
  → _execute_exit(position, exit_signal):
      await state.close_position(position.position_id, pnl_usd)
      bus.publish(PositionCloseEvent(exit_signal, position))
```

### Step 6: PerformanceJournalGroup logs close
```
PerformanceJournalGroup._log_position_close(PositionCloseEvent):
  1. journal_db.update_trade_close(exit_signal, final_position)
  2. outcome_attributor.process_closed_trade(
         trade_id=position.position_id,
         outcome="loss",    ← pnl_r < -0.05 (stop loss)
         pnl_r=...,
         exit_reason="stop_loss",
         bars_held=0,
         setup_family="ema_crossover",   ← from position.setup_refs[0]
         packet_id="uuid-xxx",
         panel_id="uuid-yyy",
         decision_id="uuid-zzz",
         composite_score=0.65,
     )
     → log_outcome_attribution() → outcome_attributions DB row
     → TraderCalibrator.process_trade_outcome() × 20 traders
     → SetupFamilyTracker.process_trade_outcome("ema_crossover", "loss", ...)
```

### State after close
```python
assert len(runner.state.portfolio.open_positions) == 0   # ✅ VERIFIED
```

---

## DB Writes Per Full Cycle

| Table | Rows | Written by |
|-------|------|-----------|
| `setup_packets` | 1 | DecisionTraceLogger |
| `trader_reviews` | 20 | DecisionTraceLogger |
| `panel_summaries` | 1 | DecisionTraceLogger |
| `final_decisions` | 1 | DecisionTraceLogger |
| `trades` (open) | 1 | PerformanceJournalGroup |
| `journal_events` (risk_decision) | 1 | PerformanceJournalGroup |
| `trades` (close update) | 1 | PerformanceJournalGroup |
| `outcome_attributions` | 1 | OutcomeAttributor |
| `setup_family_records` | 1 | SetupFamilyTracker |
| `trader_calibrations` | up to 20 | TraderCalibrator |
| **Total** | **27-47** | |

---

## Test Mapping

| Claim | Test | Status |
|-------|------|--------|
| Position opens in SystemState | `test_end_to_end_position_opens` | ✅ PASS |
| PositionOpenEvent published | `test_end_to_end_position_opens` | ✅ PASS |
| Position.composite_score carries proposal score | `test_end_to_end_position_opens` | ✅ PASS |
| Position carries packet_id/panel_id/decision_id | `test_position_carries_learning_ids` | ✅ PASS |
| Stop loss closes position | `test_end_to_end_position_closes_on_stop` | ✅ PASS |
| PositionCloseEvent published | `test_end_to_end_position_closes_on_stop` | ✅ PASS |
| open_positions empty after close | `test_end_to_end_position_closes_on_stop` | ✅ PASS |
| OutcomeAttributor wired | `test_outcome_attributor_wired_after_setup` | ✅ PASS |
| 23 learning DB rows on evaluation | `test_decision_trace_logger_writes_to_db` | ✅ PASS |

Total test suite: **54/54 PASS**
