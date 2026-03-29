# Final Runtime Path: BTC/Bybit

**Phase:** 4.75 Runtime Wiring
**Date:** 2026-03-28

---

## End-to-End Event Path

This is the actual executable path as wired in `BtcBybitPaperRunner`.

### Step 1: Bar Ingestion (MarketDataGroup)
```
runner.run_one_bar("60")
  → MarketDataGroup.fetch_and_process("BTCUSDT", "60")
  → BybitAdapter.fetch_bars() [LIVE: requires Bybit; SIM: skipped]
  → FeatureComputer.compute(bars)
  → state.update_last_close("BTCUSDT", fv.close)
  → EventBus.publish(BarCloseEvent)
  → EventBus.publish(FeatureReadyEvent)
```

In simulation mode:
```
runner.simulate_bar(fv)
  → state.update_last_close("BTCUSDT", fv.close)
  → EventBus.publish(FeatureReadyEvent)
```

### Step 2: Layer A Signal Generation
```
FeatureReadyEvent received by:
  → IndicatorsGroup._process_features(fv)
     → EMA crossover, RSI, BB, ADX signal detection
     → EventBus.publish(GroupSignalEvent[indicators])

  → CandlestickGroup._process_features(fv)
     → Engulfing, morning star, hammer, doji detection
     → EventBus.publish(GroupSignalEvent[candlestick])

  → TechnicalStructureGroup._process_features(fv)
     → Swing detection, S/R clustering, proximity flags
     → EventBus.publish(GroupSignalEvent[structure])

  → ExitGroup._check_exits(fv)
     → evaluates all open positions
     → may publish PositionCloseEvent
```

### Step 3: Layer A Aggregation (EntryGroup)
```
GroupSignalEvent(s) received by EntryGroup._collect_bundle()
  → accumulates bundles by group_id
  → when indicators bundle arrives: triggers _evaluate_trade_opportunity()
  → confirmation gate: >=2 signals same direction
  → composite score formula:
      0.35 × chart_pattern_quality  [0.0 — group stubbed]
    + 0.25 × candlestick_quality
    + 0.20 × indicator_quality
    + 0.10 × structural_alignment
    + 0.10 × historian_win_rate     [0.0 — agent not wired]
    = composite_score
  → if composite_score >= 0.50:
    → EventBus.publish(CandidateTradeEvent)
```

### Step 4: Layer B — 20-Trader Panel (PanelDecisionGroup)
```
CandidateTradeEvent received by PanelDecisionGroup._evaluate_proposal()
  → build_btc_setup_packet(proposal, fv, structural_bundle, candlestick_signals)
  → TraderEvaluatorPanel.evaluate(packet)
     → 20 traders: score(1-10), vote(approve/reject/abstain), confidence
     → PanelResult: approve_count, avg_score, panel_recommendation
  → DecisionTraceLogger.log_setup_packet(packet)     [if wired]
  → DecisionTraceLogger.log_trader_reviews(...)       [if wired]
  → DecisionTraceLogger.log_panel_summary(...)        [if wired]
```

### Step 5: Layer C — Final Decision (FinalDecisionGroup)
```
  → FinalDecisionGroup.decide(packet, panel_result)
     → Safety Rail 1: avg_score < 5.0 → hold
     → Safety Rail 2: reject_count > 12 → hold
     → Safety Rail 3: r_r_ratio < 1.5 → hold
     → Safety Rail 4: setup_quality == "invalid" → hold
     → Safety Rail 5: bear regime + LONG → hold
     → Safety Rail 6: high volatility + approve_count < 16 → hold
     → FinalDecision(decision="enter" or "hold")
  → DecisionTraceLogger.log_final_decision(...)       [if wired]

  If decision == "enter":
    → EventBus.publish(PanelApprovedProposalEvent)
  If decision == "hold":
    → event swallowed (logged, not forwarded)
```

### Step 6: Risk Gate (RiskLeverageGroup)
```
PanelApprovedProposalEvent received by RiskLeverageGroup._evaluate_proposal()
  → Rule 1: Mode gate (RESEARCH blocks)
  → Rule 2: Daily loss limit (< −2%)
  → Rule 3: Max drawdown halt (> 10%)
  → Rule 4: Portfolio exposure (≤ 25%)
  → Rule 5: Correlated cluster (≤ 15%)
  → Rule 6: Liquidity / universe filter
  → Rule 7: Pump signal (volume_ratio > 5.0)
  → Rule 8: Event risk (always 1.0 — news not wired)
  → Rule 9: Plan completeness (entry, stop, target, hypothesis, score)

  If all pass:
    → ATRStopPlacer.compute()
    → RMultipleSizer.compute()
    → state.open_position(position)
    → EventBus.publish(PositionOpenEvent)
    → EventBus.publish(RiskDecisionEvent[approved])

  If any fail:
    → EventBus.publish(RiskDecisionEvent[rejected])
```

**NOTE:** In current RESEARCH mode, Rule 1 blocks all orders. Proposals flow
through the full pipeline to Layer C but are stopped at Risk Rule 1.
Mode must be changed to PAPER or LIVE for positions to open.

### Step 7: Exit Monitoring (ExitGroup)
```
FeatureReadyEvent received by ExitGroup._check_exits(fv)
  → for each open position:
    → _check_stop_loss(position, fv)
    → _check_target(position, fv)
    → _check_trailing_stop(position, fv)
    → bars_held >= 20 (20 hours on 1h) → time stop
  → if exit triggered:
    → _compute_pnl(position, exit_price)
    → state.close_position(position_id, pnl_usd)
    → EventBus.publish(PositionCloseEvent)
```

### Step 8: Journal + Learning
```
All events received by PerformanceJournalGroup:
  → GroupSignalEvent     → insert_signal()
  → CandidateTradeEvent  → insert_journal_event("candidate_trade")
  → RiskDecisionEvent    → insert_journal_event("risk_decision")
  → PositionOpenEvent    → insert_trade_open()
  → PositionCloseEvent   → update_trade_close()
  → SystemAlertEvent     → insert_journal_event("system_alert")

Decision traces (via PanelDecisionGroup → DecisionTraceLogger):
  → setup_packets table
  → trader_reviews table (20 rows per decision)
  → panel_summaries table
  → final_decisions table
```

---

## Mode Gate Note

`CandidateTradeProposal.mode_gate` is hardcoded to `ModeGate.RESEARCH` in
`EntryGroup._build_proposal()`. Risk Rule 1 blocks all orders in RESEARCH mode.

To allow positions to open, either:
(a) Change the mode in EntryGroup._build_proposal() to ModeGate.PAPER, OR
(b) Update SystemState.mode to ModeGate.PAPER in the runner config

This is intentional. RESEARCH mode is the default safe state.

---

## Bybit Connectivity Note

- Live mode (`--run`): requires Bybit API access
- Simulation mode (`--simulate N`): fully functional without Bybit
- Dev environment: HTTP 404 from Bybit CDN (IP restriction, not code defect)
- To verify: run smoke test from clean deployment machine
