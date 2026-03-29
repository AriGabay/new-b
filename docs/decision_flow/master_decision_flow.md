# Master Decision Flow
## Phase: 2 — Architecture
## Date: 2026-03-28
## Grounded in: Phase 1 hypothesis registry + risk rules

---

## Overview

This document defines the authoritative decision flow for whether to take a trade, which side, when to enter, how much size, what leverage, and when to exit. Every decision branch is explicit. No step is a black box.

---

## Stage 0: Pre-Cycle Checks (Before Any Bar Processing)

```
CHECK: system.risk_state.halted == True?
  YES → ABORT all processing; no signals generated this cycle
  NO  → Continue

CHECK: system.portfolio.daily_pnl <= -daily_loss_limit (5% portfolio)?
  YES → Set halted=True, halt_reason="daily_loss_limit"; ABORT
  NO  → Continue

CHECK: system.portfolio.drawdown_pct >= 20%?
  YES → Set halted=True, halt_reason="max_drawdown"; ABORT
  NO  → Continue
```

---

## Stage 1: Data Ingestion and Feature Computation

```
INPUT: BarCloseEvent{symbol, timeframe, timestamp, open, high, low, close, volume}

VALIDATE:
  - timestamp is new (not duplicate)
  - OHLC constraints: high >= max(open,close), low <= min(open,close)
  - volume > 0
  - No gap > 2 bars (flag data quality issue if gap)
  FAIL → log DataQualityWarning; skip symbol this cycle

COMPUTE FEATURES (deterministic, in order):
  1. true_range = max(high-low, |high-prev_close|, |low-prev_close|)
  2. ATR14 = EMA(true_range, 14)  [Wilder's smoothing]
  3. EMA20, EMA50, EMA200
  4. RSI14 (Wilder's RSI, NOT simple momentum RSI)
  5. BB(20, 2.0): upper, middle, lower, width, width_percentile_100
  6. ADX14
  7. volume_sma20 = SMA(volume, 20)
  8. volume_ratio = volume / volume_sma20
  9. candle_body = |close - open|
  10. candle_range = high - low
  11. body_ratio = candle_body / candle_range  [doji threshold: < 0.1]
  12. upper_shadow = high - max(open, close)
  13. lower_shadow = min(open, close) - low
  14. impulse_flag = ATR14 > 0 AND candle_range > (2.0 × ATR14)

PUSH to FeatureStore[symbol][timestamp]
EMIT FeatureReadyEvent{symbol, timestamp, features}
```

---

## Stage 2: Universe Filter (Group 1 Output)

```
INPUT: Hourly universe update

FOR EACH symbol in watchlist:
  CHECK volume_24h_usd >= 5_000_000?
    NO → EXCLUDE; do not process signals for this symbol
  CHECK market_cap_usd >= 50_000_000?
    NO → EXCLUDE
  CHECK fdmv_ratio <= 5.0?
    NO → EXCLUDE
  CHECK pump_signal (see Risk Rule 8)?
    YES → EXCLUDE for 24h; log pump_exclusion

universe.eligible_symbols = {symbols passing all checks}
```

---

## Stage 3: Group Signal Generation (Parallel)

All groups run concurrently on the same FeatureReadyEvent. Each produces a GroupSignalBundle.

### Group 3: Indicators Group Signal

```
INPUT: features for symbol

COMPUTE regime signals:
  btc_macro = "bull" if close > EMA200 else "bear"
    [applies only when symbol == BTC; others inherit BTC regime]
  trending = ADX14 > 25
  volatility_regime = "high" if ATR14 > (2.0 × ATR14_sma20) else
                      "low"  if ATR14 < (0.5 × ATR14_sma20) else "normal"

COMPUTE indicator signals:
  ema_crossover_signal:
    if EMA20 crosses above EMA50 (prev EMA20 < prev EMA50): "bullish"
    if EMA20 crosses below EMA50 (prev EMA20 > prev EMA50): "bearish"
    else: None

  rsi_divergence_signal (CONDITIONAL — only if NOT impulse_flag):
    [see full divergence detection logic in Group 3 spec]
    if valid divergence found: {type, direction, bars_formed}
    else: None

  bb_squeeze_signal:
    if BB.width_percentile_100 < 10 (10th percentile): "squeeze_active"
    else: None

EMIT GroupSignalBundle{
  group="indicators",
  symbol=symbol,
  timestamp=timestamp,
  regime={btc_macro, trending, volatility_regime},
  signals=[...],
  metadata={atr14, ema20, ema50, rsi14}
}
```

### Group 4: Candlestick Group Signal

```
INPUT: last 5 bars OHLCV for symbol

EVALUATE each pattern in PRIORITY order:
  [Only patterns in hypothesis registry with status != REJECTED]

  Pattern check order (CRITICAL first):
    1. Bearish Engulfing (at resistance — requires Group 6 context)
    2. Bullish Engulfing (at support — requires Group 6 context)
    3. Morning Star (3-bar)
    4. Evening Star (3-bar)
    5. Three Black Crows (in uptrend — requires regime context)
    6. Doji (conditional — requires prior trend context)
    [Lower priority patterns checked only if none of above match]

  For each pattern check:
    MATCH criteria (deterministic):
      return PatternMatch{
        pattern_id, direction, bars_consumed,
        requires_structural_level: bool,
        quality_score: float  # 0.0-1.0, deterministic formula
      }

  FILTER: only emit patterns where all criteria met
  FILTER: if requires_structural_level=True, defer to Entry Group

EMIT GroupSignalBundle{
  group="candlestick",
  symbol=symbol,
  timestamp=timestamp,
  signals=[PatternMatch, ...],
  metadata={body_ratio, impulse_flag}
}
```

### Group 5: Chart Pattern Group Signal

```
INPUT: last N bars OHLCV for symbol (N = max lookback = 200 bars)

EVALUATE each chart pattern in PRIORITY order:
  Priority 1 (CRITICAL — from hypothesis registry):
    1. Head & Shoulders Top        [H1-001]
    2. Inverse H&S / Complex H&S   [H1-002]
    3. Double Bottom (track state) [H1-003]
    4. Triple Bottom               [H1-005]
    5. Descending Triangle         [H1-004]

  Priority 2 (HIGH):
    6. Bull Flag / High & Tight Flag [H1-006, H1-007]
    7. Falling Wedge               [H1-008]
    8. Pipe Bottom                 [H1-009]
    [others per hypothesis registry]

  Each pattern is a STATE MACHINE:
    States: INACTIVE → FORMING → CANDIDATE → BREAKOUT_PENDING → CONFIRMED
    State transitions are deterministic.
    Signal emitted ONLY on CONFIRMED state (bar close beyond breakout level).
    Confirmation required = True always (from Phase 1 hard rule).

  For confirmed pattern:
    return ChartPatternSignal{
      pattern_id,
      hypothesis_ref,       # Links to /research/hypotheses/
      direction,            # "long" | "short"
      breakout_level,       # Price that was confirmed
      measured_move,        # Full measured move distance
      conservative_target,  # measured_move × 0.50 (Phase 1 rule)
      pattern_quality,      # based on depth, symmetry, volume
      bars_in_formation,
      volume_at_breakout    # Must be > volume_sma20 for full quality
    }

EMIT GroupSignalBundle{
  group="chart_pattern",
  symbol=symbol,
  timestamp=timestamp,
  signals=[ChartPatternSignal, ...],
  pattern_states=[...]  # All active formation states (for journal)
}
```

### Group 6: Technical Structure Group Signal

```
INPUT: last 200 bars OHLCV for symbol

COMPUTE:
  swing_highs = detect_swing_highs(lookback=20, min_prominence=0.02)
  swing_lows  = detect_swing_lows(lookback=20, min_prominence=0.02)

  resistance_levels = [
    StructuralLevel{price, touches, strength, last_tested_bar}
    for price in swing_highs where touches >= 2
  ]
  support_levels = [
    StructuralLevel{price, touches, strength, last_tested_bar}
    for price in swing_lows where touches >= 2
  ]

  key_mas = {
    "ema20": EMA20[-1],
    "ema50": EMA50[-1],
    "ema200": EMA200[-1]
  }

  # Price proximity to levels (for candlestick group context)
  nearest_resistance = min(resistance_levels, key=lambda l: l.price - close) if close < closest_resistance else None
  nearest_support    = max(support_levels, key=lambda l: close - l.price) if close > closest_support else None
  at_resistance = nearest_resistance is not None AND |close - nearest_resistance.price| / close < 0.005
  at_support    = nearest_support is not None AND |close - nearest_support.price| / close < 0.005

EMIT GroupSignalBundle{
  group="technical_structure",
  symbol=symbol,
  timestamp=timestamp,
  resistance_levels=[...],
  support_levels=[...],
  at_resistance=at_resistance,
  at_support=at_support,
  nearest_resistance=nearest_resistance,
  nearest_support=nearest_support,
  key_mas=key_mas
}
```

---

## Stage 4: Entry Group — Signal Aggregation and Candidate Trade Formation

```
INPUT: all GroupSignalBundles from Stage 3

STEP 4.1: Collect all signals this cycle for this symbol
  chart_signals    = GroupSignalBundle[chart_pattern].signals
  candle_signals   = GroupSignalBundle[candlestick].signals
  indicator_sigs   = GroupSignalBundle[indicators].signals
  structure        = GroupSignalBundle[technical_structure]
  regime           = GroupSignalBundle[indicators].regime

STEP 4.2: Apply structural context to candlestick signals
  For each candle_signal where requires_structural_level=True:
    if candle_signal.direction == "bearish" AND structure.at_resistance:
      candle_signal.context_confirmed = True
    elif candle_signal.direction == "bullish" AND structure.at_support:
      candle_signal.context_confirmed = True
    else:
      candle_signal.context_confirmed = False
      → DISCARD this candle signal (no structural level = no trade)

STEP 4.3: Check confirmation gate (HARD RULE — no exceptions)
  For each signal:
    if signal.confirmation_required AND NOT signal.confirmed_on_bar_close:
      DISCARD → log ConfirmationGateReject

STEP 4.4: Check mode gate
  For each signal:
    if signal.hypothesis_ref NOT in validated_hypotheses
      AND system.mode != ModeGate.RESEARCH:
      BLOCK → this pattern cannot live-trade; research only

STEP 4.5: Check conflict
  if chart_signal.direction == "long" AND candle_signal.direction == "short":
    → CONFLICT: log ConflictEvent; do not generate trade for conflicting signals
    [non-conflicting signals may still proceed]

STEP 4.6: Compute composite signal score
  score = weighted sum:
    chart_pattern_quality   × 0.40
    candle_signal_quality   × 0.20
    structure_confirmation  × 0.20
    volume_at_breakout_ok   × 0.10
    regime_alignment        × 0.10

  if score < MIN_SCORE_THRESHOLD (0.40): DISCARD

STEP 4.7: Build CandidateTradeProposal
  proposal = CandidateTradeProposal{
    symbol,
    direction,           # "long" | "short"
    entry_price,         # current close (bar close entry)
    thesis,              # string: dominant signal description
    setup_refs,          # [signal_ids that contributed]
    raw_target,          # conservative_target from primary pattern
    composite_score,
    timestamp,
    hypothesis_refs      # links to /research/hypotheses/
  }

EMIT CandidateTradeEvent{proposal}
```

---

## Stage 5: Risk & Leverage Group — Final Gate

```
INPUT: CandidateTradeProposal

STEP 5.1: Compute ATR-based stop
  stop_distance = ATR14[symbol] × config.atr_stop_multiplier  [default: 2.0]
  if direction == "long":
    stop_price = entry_price - stop_distance
    # Anti-gaming: shift stop if within 0.5% of round number
    stop_price = anti_round_number_shift(stop_price)
  else:
    stop_price = entry_price + stop_distance
    stop_price = anti_round_number_shift(stop_price)

  # Ensure stop is not beyond an obvious cluster
  # (Check if stop_price coincides with swing_low±0.3% for longs)

STEP 5.2: Compute position size (R-multiple)
  R = portfolio.equity × config.risk_fraction  [default: 0.01 = 1%]
  stop_distance_price = |entry_price - stop_price|
  position_size_usd = R / (stop_distance_price / entry_price)
  position_size_usd = min(position_size_usd, portfolio.available × 0.25)
    # Never risk more than 25% of available capital in single position

STEP 5.3: Compute leverage
  # Leverage is a consequence of position sizing, not an input
  notional_exposure = position_size_usd
  required_margin = notional_exposure / config.max_leverage  [default: 3.0]
  leverage_used = min(config.max_leverage, position_size_usd / required_margin)
  # For Phase 2 spot trading: leverage = 1.0 always

STEP 5.4: Portfolio exposure check
  total_open_risk = sum(position.risk_amount for position in open_positions)
  new_total_risk = total_open_risk + R

  if new_total_risk > portfolio.equity × config.max_portfolio_risk  [default: 0.10]:
    → REJECT: "portfolio_exposure_limit"

  correlated_risk = sum(
    position.risk_amount
    for position in open_positions
    if position.correlation_cluster == proposal.correlation_cluster
  )
  if correlated_risk + R > portfolio.equity × config.max_correlated_risk  [default: 0.02]:
    → REJECT: "correlated_exposure_limit"

STEP 5.5: Drawdown state check
  if portfolio.consecutive_losses >= 3:
    position_size_usd × 0.5  # Half-size rule

  if portfolio.drawdown_pct >= config.max_drawdown  [default: 0.20]:
    → REJECT: "max_drawdown_halt"

STEP 5.6: Spread check
  current_spread_pct = (ask - bid) / mid_price
  if current_spread_pct > config.max_spread  [default: 0.005]:
    → REJECT: "spread_too_wide"

STEP 5.7: Pump signal check
  if pump_signal_active(symbol):
    → REJECT: "pump_signal_active"

STEP 5.8: Trading plan completeness gate
  verify all 5 components defined:
    - thesis: proposal.thesis is not None
    - setup: len(proposal.setup_refs) > 0
    - entry: proposal.entry_price is not None
    - risk: stop_price is not None
    - reward: proposal.raw_target is not None
  if any missing → REJECT: "incomplete_trade_plan"

STEP 5.9: Emit risk decision
  if all checks pass:
    EMIT RiskApprovedOrder{
      ...proposal,
      stop_price,
      target_price,
      position_size_usd,
      leverage_used,
      R_amount,
      risk_checks_passed=[...],
      timestamp
    }
  else:
    EMIT RiskRejectedEvent{proposal, rejection_reason, timestamp}
    [ALWAYS journal rejections — not just approvals]
```

---

## Stage 6: Execution

```
INPUT: RiskApprovedOrder

MODE GATE:
  RESEARCH → JOURNAL ONLY (no order sent)
  SHADOW   → PAPER TRADE (simulate fill at entry_price)
  LIVE     → SEND ORDER to exchange API

[Phase 2: always RESEARCH mode]
```

---

## Stage 7: Exit Management

```
RUNS independently per open position on each bar close.

INPUT: open position, new bar OHLCV

EXIT TRIGGERS (checked in priority order):
  1. STOP HIT: close <= stop_price (long) or close >= stop_price (short)
     → EXIT immediately at next bar open
     Type: "stop_loss"

  2. TARGET HIT: close >= target_price (long) or close <= target_price (short)
     → EXIT at market (or limit near target)
     Type: "target_reached"

  3. TRAILING STOP (if enabled):
     trailing_stop = peak_favorable_price - (ATR14 × config.trail_multiplier)
     if close <= trailing_stop (long) → EXIT
     Type: "trailing_stop"

  4. TIME STOP:
     if bars_held > config.max_bars_in_trade  [default: 20 bars = 20 hours on 1h timeframe]
     → EXIT at close
     Type: "time_stop"

  5. SIGNAL REVERSAL:
     if primary signal reverses direction with score > 0.6
     → EXIT at close
     Type: "signal_reversal"

EMIT ExitSignal{position_id, exit_reason, exit_price, pnl, bars_held}
```

---

## Stage 8: Journal and Learning

```
EVERY CYCLE, regardless of trade outcome:
  JournalWriter.log(BarJournalEntry{
    timestamp, symbol, features, group_signals,
    candidate_proposals, risk_decisions,
    active_positions, system_state
  })

ON TRADE CLOSE:
  JournalWriter.log(TradeJournalEntry{
    trade_id, symbol, direction, entry, exit, pnl,
    setup_refs, hypothesis_refs, exit_reason,
    bars_held, r_multiple_achieved,
    signals_at_entry, market_conditions_at_entry,
    market_conditions_at_exit
  })

ASYNC LEARNING (scheduled, not blocking):
  Every 100 trades:
    LearningGroup.compute_signal_performance()
    LearningGroup.detect_decay(recent_window=50, full_window=100)
    LearningGroup.update_historian_knowledge_base()
```

---

## Decision Matrix Summary

| Question | Answer Source | Logic Type |
|---|---|---|
| Should I trade? | Stage 0 + Stage 5 | Deterministic |
| Which side? | Stage 4 (signal direction) | Deterministic |
| When to enter? | Stage 3 (bar close confirmation) | Deterministic |
| How much size? | Stage 5.2 (R-multiple) | Deterministic |
| What leverage? | Stage 5.3 (derived, not chosen) | Deterministic |
| When to exit? | Stage 7 (stop/target/time) | Deterministic |
| What to learn? | Stage 8 (async) | Mixed: stats deterministic, synthesis LLM-optional |
