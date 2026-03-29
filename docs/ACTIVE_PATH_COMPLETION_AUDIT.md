# ACTIVE PATH COMPLETION AUDIT
**Date:** 2026-03-29
**Phase:** 6.4 (Chart Pattern Activation)

This document audits every stage of the active runtime decision path for correctness,
completeness, and honest wiring. All claims are verified by direct code inspection.

---

## STAGE 1: main_btc.py Routing

**File:** src/main_btc.py

| Mode | Routes to | Uses real pipeline | Bybit required | Status |
|------|-----------|-------------------|---------------|--------|
| --run | BtcBybitPaperRunner(simulation_mode=False) | YES | YES | CORRECT |
| --simulate N | BtcBybitPaperRunner(simulation_mode=True) | YES | NO | CORRECT |
| --backtest | BacktestEngine (EMA-crossover only) | NO | YES | CORRECT — separated |
| --analyze | BybitAdapter + FeatureComputer only | NO | YES | CORRECT — legacy |

Backtest mode logs an explicit warning: "Outcomes are tagged 'simplified_backtest' and
must NOT be mixed with event_driven_runtime calibration."

**Assessment: COMPLETE. No issues.**

---

## STAGE 2: Runner Setup and Group Wiring

**File:** src/runtime/runner.py

Active groups instantiated in _create_groups():
1. MarketDataGroup
2. ChartPatternGroup (Phase 6.4 activated)
3. IndicatorsGroup
4. CandlestickGroup
5. TechnicalStructureGroup
6. EntryGroup
7. PanelDecisionGroup
8. RiskLeverageGroup
9. ExitGroup
10. PerformanceJournalGroup

Cross-group caches wired in _wire_caches():
- PanelDecisionGroup ← MarketDataGroup._feature_cache (symbol, "1h")
- PanelDecisionGroup ← TechnicalStructureGroup._structural_cache
- PanelDecisionGroup ← CandlestickGroup._signals_cache (Phase 6.2.5 fix)
- PanelDecisionGroup ← ChartPatternGroup._signals_cache (Phase 6.4)
- PanelDecisionGroup ← ChartPatternGroup._active_cache (Phase 6.4)
- CandlestickGroup ← TechnicalStructureGroup (reference, for structural context)

Panel gate set: runner._risk_leverage.set_panel_wired(True)
Confirmed by test: test_panel_gate_blocks_candidate_trade_bypass PASS

Runner mode: ModeGate.SHADOW — proposals not blocked by Risk Rule 1.

**Known docstring bug:** runner.py lines 19-22 say ChartPatternGroup is "EXCLUDED:
_process_features raises NotImplementedError". This is stale from before Phase 6.4.
The code correctly instantiates and wires ChartPatternGroup. Code is correct.

**Assessment: COMPLETE. Docstring bug present but does not affect runtime.**

---

## STAGE 3: Layer A — Signal Generation

### MarketDataGroup
- Fetches BTC/Bybit OHLCV for 1h/4h/1d
- Maintains 250-bar rolling cache per timeframe
- Computes FeatureVector, updates state.last_close_by_symbol
- Publishes FeatureReadyEvent
- _feature_cache keyed by (symbol, timeframe)

### ChartPatternGroup
- Subscribes to FeatureReadyEvent
- Maintains per-symbol state machines: DoubleBottomMachine, H&SMachine, DescendingTriangleMachine, TripleBottomMachine
- CONFIRMED behavior: advances machines, emits ChartPatternSignal on CONFIRMED state
- DOES NOT publish GroupSignalEvent — feeds panel via _signals_cache only
- Updates _active_cache with in-progress pattern names
- RJ-007 (failure cooldown) and RJ-009 (ADX < 20 regime filter) active

### IndicatorsGroup
- Subscribes to FeatureReadyEvent
- Active hypotheses: H3-001 (RSI div), H3-002 (EMA cross), H3-004 (BB squeeze), H3-005 (trend continuation)
- Publishes GroupSignalEvent with GroupSignalBundle

### CandlestickGroup
- Subscribes to FeatureReadyEvent
- Active patterns: Bullish/Bearish Engulfing, Morning/Evening Star, Three Black Crows, Inverted Hammer, Doji
- Requires structural context (at_resistance or at_support) for pattern confirmation
- Publishes GroupSignalEvent AND updates _signals_cache for PanelDecisionGroup
- Always publishes a bundle even with 0 signals (enables EntryGroup timing gate)

### TechnicalStructureGroup
- Subscribes to FeatureReadyEvent
- Detects S/R levels, computes at_resistance/at_support proximity flags
- Publishes GroupSignalEvent with structural bundle

**Assessment: ALL ACTIVE. Signal generation path complete.**

---

## STAGE 4: EntryGroup — Signal Aggregation and Proposal

**File:** src/groups/entry/group.py

Confirmation gate triggers when BOTH indicators AND candlestick bundles received.
Gate logic:
1. Minimum 2 signals agreeing on direction
2. At least 1 must be candlestick or chart_pattern type (bar-level confirmation)
3. Regime filter: LONG blocked in bear macro
4. Composite score >= 0.50 threshold

Composite score formula:
```
raw_score = 0.35 * chart_pattern_quality   # always 0.0 (ChartPatternGroup no GroupSignalEvent)
          + 0.25 * candlestick_quality
          + 0.20 * indicator_quality
          + 0.10 * structural_alignment
          + 0.10 * historian_win_rate       # always 0.0 (HistorianAgent not wired)

composite_score = raw_score / ACTIVE_COMPOSITE_WEIGHT_SUM  # = 0.55
```

ACTIVE_COMPOSITE_WEIGHT_SUM = 0.55 is correct:
- ChartPatternGroup does not emit GroupSignalEvent → chart_pattern_quality always 0.0
- HistorianAgent not wired → historian_win_rate always 0.0
- Effective formula: (0.25*ck + 0.20*iq + 0.10*sa) / 0.55
- Maximum achievable: (0.25 + 0.20 + 0.10) / 0.55 = 1.00 ✓

Verified composite_score in V3 fixture: 0.8545 (confirms formula works correctly)

Entry price: from state.last_close_by_symbol (set by MarketDataGroup each bar)
Proposal fields: direction, entry_price, composite_score, hypothesis_refs, setup_refs
raw_target: defaults to Decimal("0") — enriched by PanelDecisionGroup before forwarding

Publishes CandidateTradeEvent.

**Assessment: COMPLETE. Composite score normalization is correct by design.**

---

## STAGE 5: PanelDecisionGroup — Layer B+C

**File:** src/groups/panel_decision/group.py

Subscribes to CandidateTradeEvent.

Step 1: Build BTCSetupPacket via build_btc_setup_packet()
  - FeatureVector from _feature_cache
  - StructuralLevelBundle from _structural_cache
  - CandlestickSignals from _candlestick_signal_cache
  - ChartPatternSignals from _chart_pattern_signal_cache
  - ActiveChartPatterns from _active_chart_pattern_cache

Step 2: TraderEvaluatorPanel.evaluate(packet) — 20 deterministic evaluators
  - Each evaluator: score (1-10), vote (approve/reject/abstain), confidence
  - PanelResult: approve_count, reject_count, abstain_count, avg_score

Step 3: FinalDecisionGroup.decide(packet, panel_result) — 6 safety rails
  - avg_score < 5.0 → hold
  - reject_count > 12 → hold
  - r_r_ratio < 1.5 → hold
  - setup_quality == "invalid" → hold
  - bear regime + LONG → hold
  - high_volatility + approve_count < 16 → hold

Step 4: If decision == "enter":
  - raw_target enrichment: if proposal.raw_target == 0, set to packet.proposal.target_price
  - Publish PanelApprovedProposalEvent with packet_id, panel_id, decision_id

Step 5: DecisionTraceLogger writes setup_packet, trader_reviews, panel_summary, final_decision to DB

Panel thresholds (confirmed unchanged):
  APPROVE_THRESHOLD = 14
  AVG_SCORE_THRESHOLD = 6.5

**Assessment: COMPLETE. All paths verified by direct test execution.**

---

## STAGE 6: RiskLeverageGroup — 9 Risk Rules

**File:** src/groups/risk_leverage/group.py

Subscribes to PanelApprovedProposalEvent (primary) and CandidateTradeEvent (gated).
When panel_wired=True: CandidateTradeEvent ignored, only PanelApprovedProposalEvent processed.

9 rules in sequence:
1. Mode gate: SHADOW passes ✓
2. Daily loss limit: 0% > -2% → passes ✓
3. Max drawdown: 0% < 10% → passes ✓
4. Portfolio exposure: 0% < 25% → passes ✓
5. Correlated exposure: 0% < 15% → passes ✓
6. Liquidity: BTCUSDT in eligible_symbols → passes ✓
7. Pump detection: vol_ratio < 5.0 → passes ✓
8. Event risk: no events → no size reduction ✓
9. Plan completeness: entry, stop, target present, hypothesis_refs, score >= 0.50 ✓

Rule 9 passes because:
- stop_price: computed from ATR by setup_packet_builder
- target_price: enriched by PanelDecisionGroup before forwarding as raw_target
- composite_score: 0.8545 >= 0.50

Position sizing:
  R = equity * 0.01 = $100 (default $10K equity)
  stop_dist = |entry - stop| = ~1300
  size_base = R / stop_dist ≈ 0.077 BTC
  size_usd = size_base * entry ≈ $5,400
  cap: min($5,400, equity * 0.10 = $1,000) → $1,000
  Note: In test environment equity=$10K so cap=$1,000; realistic position sizing

Publishes: RiskDecisionEvent + PositionOpenEvent
Updates: SystemState.portfolio.open_positions

Verified by test: test_panel_approved_reaches_risk PASS
End-to-end position open test: PASS

**Assessment: COMPLETE. Risk path verified by direct test execution.**

---

## STAGE 7: ExitGroup — Position Monitoring

**File:** src/groups/exit/group.py

Subscribes to FeatureReadyEvent (checks open positions each bar).
Subscribes to PositionOpenEvent (registers position for monitoring).

Exit conditions (priority order):
1. Hard stop loss: low <= stop_price (or high >= stop_price for SHORT)
2. Target reached: high >= target_price (or low <= target_price for SHORT)
3. Trailing stop: ATR-based ratchet after +1R favorable move
4. Time stop: bars_held >= 20
5. Signal reversal (advisory only)

Verified by test: test_end_to_end_position_closes_on_stop PASS
Natural close: V3 fixture full lifecycle — 1 open, 1 close, total_trades=1

**Assessment: COMPLETE. Exit path verified.**

---

## STAGE 8: PerformanceJournalGroup and Learning

**File:** src/groups/performance_journal/group.py
**Supporting:** src/learning/attribution.py, src/learning/decision_logger.py

Journal writes on:
- BarCloseEvent
- GroupSignalEvent
- CandidateTradeEvent
- PanelApprovedProposalEvent
- PositionOpenEvent
- PositionCloseEvent

On PositionCloseEvent: calls OutcomeAttributor if wired.

OutcomeAttributor pipeline:
1. Validate outcome_source (always EVENT_DRIVEN_RUNTIME)
2. Write OutcomeAttribution to DB
3. Update TraderCalibration for all 20 participating traders
4. Update SetupFamilyRecord
5. Update SpecialistGroupRecord

DecisionTraceLogger: writes setup_packets, trader_reviews, panel_summaries, decisions.

Learning IDs (packet_id, panel_id, decision_id) threaded from PanelDecisionGroup
→ PanelApprovedProposalEvent → RiskLeverageGroup → Position object.
Verified by test: test_position_carries_learning_ids PASS
Verified by test: test_outcome_attributor_wired_after_setup PASS

**Assessment: COMPLETE. Learning hooks wired and verified.**
