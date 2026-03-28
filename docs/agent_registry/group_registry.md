# Group Registry
## Phase: 2 — Architecture
## Date: 2026-03-28

---

## Registry Format

Each entry defines a Group as a first-class architectural module:
- `group_id`: canonical identifier
- `responsibility`: single sentence scope
- `trigger`: what activates this group
- `inputs`: typed data consumed
- `outputs`: typed data produced
- `always_on`: whether the group runs without signals
- `llm_permitted`: whether LLM reasoning is allowed in this group
- `deterministic_boundary`: what must remain deterministic
- `dependencies`: other groups this group reads from
- `implementation_priority`: Phase 2 build order

---

## GROUP-01: Market Data Group

```yaml
group_id: market_data
responsibility: >
  Ingest, normalize, validate, and distribute raw market data (OHLCV,
  volume, spread) for all symbols in the trading universe.
trigger: Continuous (always-on)
inputs:
  - Exchange WebSocket / REST feed (Binance spot, primary)
  - Historical Parquet files (backtest mode)
outputs:
  - BarCloseEvent per symbol per timeframe
  - FeatureReadyEvent per symbol (after feature computation)
  - UniverseUpdateEvent (hourly)
  - DataQualityAlert (on anomaly)
always_on: true
llm_permitted: false
deterministic_boundary: >
  All data ingestion, normalization, validation, and feature computation
  must be purely deterministic. No judgment involved.
dependencies: []
roles_active:
  - ParserAgent: normalizes raw exchange data
  - ValidatorAgent: checks OHLC constraints, gap detection
  - HistorianAgent: writes to Parquet store
  - SummarizerAgent: emits BarCloseEvent / FeatureReadyEvent
implementation_priority: 1
phase_2_deliverable: >
  Working data feed with Binance REST polling (daily bars), gap detection,
  and feature computation for ATR, EMA, RSI, BB, ADX.
```

---

## GROUP-02: News & Macro Group

```yaml
group_id: news_macro
responsibility: >
  Monitor and classify macro events, scheduled risk events, and market
  narrative shifts that may affect signal reliability or require position
  size reduction.
trigger: Scheduled (hourly) + webhook on breaking news
inputs:
  - News API feed (future phase)
  - Manually curated event calendar (CSV, Phase 2)
  - BTC MVRV / on-chain data (future phase)
outputs:
  - MacroContextEvent{event_type, risk_level, affected_symbols}
  - EventRiskFlag (pre-event risk reduction trigger)
always_on: false
llm_permitted: true
deterministic_boundary: >
  Event calendar lookups and threshold checks are deterministic.
  LLM may be used for news classification and narrative extraction
  (CriticAgent, SummarizerAgent only).
dependencies: []
roles_active:
  - ResearchAgent: fetches news, calendar events
  - ParserAgent: extracts event type, risk level
  - ValidatorAgent: confirms event is real and scheduled
  - ContextAgent: maps event to affected symbols
  - CriticAgent: [LLM-optional] assesses narrative risk
  - SummarizerAgent: emits MacroContextEvent
implementation_priority: 5
phase_2_deliverable: >
  Static event calendar (CSV) with known macro dates. No live news in Phase 2.
```

---

## GROUP-03: Indicators Group

```yaml
group_id: indicators
responsibility: >
  Compute and classify all technical indicator signals (EMA crossovers,
  RSI divergence, BB squeeze, ADX regime) per symbol per bar close.
trigger: FeatureReadyEvent (per bar close, per symbol)
inputs:
  - FeatureReadyEvent (features from Market Data Group)
  - Previous N bars of features (from FeatureStore)
outputs:
  - GroupSignalBundle{group="indicators", symbol, regime, indicator_signals}
always_on: false
llm_permitted: false
deterministic_boundary: >
  All indicator computation and signal classification is deterministic.
  No LLM permitted in this group.
dependencies:
  - market_data
roles_active:
  - SignalAgent: computes EMA crossover, RSI divergence, BB squeeze
  - ValidatorAgent: applies context filters (no impulse candle for divergence)
  - ScoringAgent: scores each indicator signal
  - ContextAgent: classifies regime (btc_macro, trending, volatility)
  - SummarizerAgent: emits GroupSignalBundle
implementation_priority: 2
phase_2_deliverable: >
  EMA crossover signal (20/50), RSI divergence with impulse filter,
  BB squeeze detector, ADX-based regime classifier.
notes:
  - RSI must use Wilder's smoothing, not simple RSI
  - Divergence suppressed when impulse_flag=True (candle > 2×ATR)
  - EMA crossover is baseline benchmark signal (hypothesis H3-002)
```

---

## GROUP-04: Candlestick Group

```yaml
group_id: candlestick
responsibility: >
  Detect and classify candlestick patterns on current and recent bars,
  respecting hypothesis registry status (no rejected patterns).
trigger: FeatureReadyEvent (per bar close, per symbol)
inputs:
  - FeatureReadyEvent (last 5 bars OHLCV + computed features)
  - Technical Structure GroupSignalBundle (for context-dependent patterns)
outputs:
  - GroupSignalBundle{group="candlestick", symbol, candle_signals}
always_on: false
llm_permitted: false
deterministic_boundary: >
  All pattern matching is based on exact OHLCV relationships.
  No LLM involved.
dependencies:
  - market_data
  - technical_structure  # For structural level context
roles_active:
  - SignalAgent: runs pattern detection for each active hypothesis
  - ValidatorAgent: applies structural level requirement
  - ScoringAgent: scores pattern quality (body size, shadow ratios)
  - ConflictAgent: detects conflicting patterns (bullish+bearish same bar)
  - SummarizerAgent: emits GroupSignalBundle
implementation_priority: 3
phase_2_deliverable: >
  Detection of: Bearish/Bullish Engulfing, Morning Star, Evening Star,
  Three Black Crows, Doji. All requiring structural level confirmation.
blocked_patterns:
  - Hanging Man (RJ-001)
  - Shooting Star standalone (RJ-002)
  - All harmonics (RJ-009, RJ-010)
notes:
  - Context-dependent patterns deferred to Entry Group if structural level unclear
  - Pattern must be complete on bar CLOSE (no intrabar detection)
```

---

## GROUP-05: Chart Pattern Group

```yaml
group_id: chart_pattern
responsibility: >
  Track multi-bar chart pattern state machines, detect confirmed
  breakouts, and produce ChartPatternSignals grounded in the
  Phase 1 hypothesis registry.
trigger: FeatureReadyEvent (per bar close, per symbol)
inputs:
  - FeatureReadyEvent (last 200 bars OHLCV + features)
  - PatternStateStore (persisted state per symbol per pattern)
outputs:
  - GroupSignalBundle{group="chart_pattern", symbol, chart_signals, pattern_states}
always_on: false
llm_permitted: false
deterministic_boundary: >
  Pattern state machines are deterministic finite automata.
  All transitions based on OHLCV conditions.
dependencies:
  - market_data
roles_active:
  - SignalAgent: manages state machines for each active pattern type
  - ValidatorAgent: confirms breakout on bar close
  - ScoringAgent: scores pattern quality (depth, symmetry, volume confirmation)
  - HistorianAgent: checks if similar pattern performed in past (from journal)
  - SummarizerAgent: emits GroupSignalBundle with confirmed signals only
implementation_priority: 2
phase_2_deliverable: >
  State machine implementations for the 5 CRITICAL hypothesis patterns:
  H1-001 (H&S Top), H1-002 (Inverse H&S), H1-003 (Double Bottom confirmed),
  H1-004 (Descending Triangle), H1-005 (Triple Bottom).
  Conservative target: 50% of measured move (Phase 1 hard rule).
blocked_patterns:
  - Elliott Wave (RJ-008)
  - Wyckoff phases (RJ-007)
  - Gartley/Butterfly (RJ-009)
  - All other Phase 1 rejected patterns
active_hypotheses:
  critical: [H1-001, H1-002, H1-003, H1-004, H1-005]
  high: [H1-006, H1-007, H1-008, H1-009]
  medium: []  # Defer until critical/high validated
```

---

## GROUP-06: Technical Structure Group

```yaml
group_id: technical_structure
responsibility: >
  Identify and maintain key support/resistance levels, trend direction,
  and structural context that other groups use for signal validation.
trigger: FeatureReadyEvent (per bar close, per symbol)
inputs:
  - FeatureReadyEvent (last 200 bars OHLCV + EMAs)
outputs:
  - GroupSignalBundle{group="technical_structure", symbol,
      resistance_levels, support_levels, at_resistance, at_support,
      nearest_levels, key_mas}
always_on: false
llm_permitted: false
deterministic_boundary: >
  All S/R detection is algorithmic (swing high/low detection with
  defined lookback and prominence parameters).
dependencies:
  - market_data
roles_active:
  - SignalAgent: detects swing highs/lows; identifies S/R levels
  - ValidatorAgent: verifies minimum touches and significance
  - ScoringAgent: scores level strength (touches × recency × volume)
  - SummarizerAgent: emits GroupSignalBundle
implementation_priority: 2
phase_2_deliverable: >
  Swing high/low detector (N-bar lookback, min 2% prominence).
  Horizontal S/R identification (min 2 touches).
  at_resistance / at_support flags (within 0.5% of level).
notes:
  - Uses OQ-012 resolution: swing high/low with lookback=20, prominence=2%
  - MA levels (EMA20, EMA50, EMA200) provided as dynamic levels
```

---

## GROUP-07: Entry Group

```yaml
group_id: entry
responsibility: >
  Aggregate signals from all upstream groups, apply the confirmation gate,
  resolve conflicts, compute composite score, and produce CandidateTradeProposal.
trigger: When ≥1 upstream group emits a non-empty GroupSignalBundle
inputs:
  - All GroupSignalBundles from Groups 3-6
  - SystemState (mode, regime, portfolio state)
outputs:
  - CandidateTradeEvent (if proposal passes all gates)
  - SignalDiscardEvent (if proposal rejected by confirmation/conflict/score gate)
always_on: false
llm_permitted: true  # CriticAgent may invoke LLM for ambiguous confluence
deterministic_boundary: >
  Confirmation gate, conflict detection, score computation are deterministic.
  LLM only permitted for CriticAgent when composite_score is in
  ambiguous range (0.40 - 0.55).
dependencies:
  - indicators
  - candlestick
  - chart_pattern
  - technical_structure
  - news_macro
roles_active:
  - SignalAgent: collects and aligns signals by direction
  - ValidatorAgent: enforces confirmation gate (bar close rule)
  - ScoringAgent: computes composite_score from group weights
  - ConflictAgent: detects and resolves direction conflicts
  - ContextAgent: adds regime and macro context to proposal
  - CriticAgent: [LLM-optional] challenges the trade thesis
  - HistorianAgent: checks similar setups in journal
  - SummarizerAgent: builds CandidateTradeProposal
implementation_priority: 4
phase_2_deliverable: >
  Signal aggregation, confirmation gate, conflict detection,
  composite scoring. CriticAgent is a stub initially.
```

---

## GROUP-08: Exit Group

```yaml
group_id: exit
responsibility: >
  Monitor all open positions each bar and determine when to exit based
  on stops, targets, trailing stops, time stops, or signal reversal.
trigger: BarCloseEvent (for each open position)
inputs:
  - Open positions from SystemState
  - FeatureReadyEvent (for trailing stop computation)
  - GroupSignalBundles (for signal reversal detection)
outputs:
  - ExitSignal{position_id, exit_reason, exit_price}
always_on: false  # Only active when positions are open
llm_permitted: false
deterministic_boundary: >
  All exit logic is deterministic. No judgment involved.
dependencies:
  - market_data
  - indicators
  - chart_pattern
roles_active:
  - SignalAgent: detects stop hits, target hits, trailing stop triggers
  - ValidatorAgent: confirms exit condition on bar close
  - SummarizerAgent: emits ExitSignal
implementation_priority: 3
phase_2_deliverable: >
  Stop loss exit, target exit, time stop exit. Trailing stop and
  signal reversal exit as Phase 3.
```

---

## GROUP-09: Risk & Leverage Group

```yaml
group_id: risk_leverage
responsibility: >
  Final, non-overridable gate for every trade. Applies all 9 Phase 1
  risk rules. Computes position size, stop placement, leverage.
  Cannot be bypassed by any other group.
trigger: CandidateTradeEvent
inputs:
  - CandidateTradeProposal
  - SystemState (portfolio, drawdown, consecutive_losses)
  - FeatureReadyEvent (for ATR stop computation)
  - Universe filter (for spread check)
outputs:
  - RiskApprovedOrder (if all checks pass)
  - RiskRejectedEvent (if any check fails, with reason)
always_on: false
llm_permitted: false
deterministic_boundary: >
  ALL risk computations are deterministic. This is non-negotiable.
  LLM reasoning must never influence risk decisions.
dependencies:
  - market_data
  - entry
roles_active:
  - ValidatorAgent: runs all risk rule checks in sequence
  - ScoringAgent: not applicable (pass/fail only)
  - SummarizerAgent: emits RiskApprovedOrder or RiskRejectedEvent
implementation_priority: 1  # Must be implemented before any live signal
phase_2_deliverable: >
  All 9 Phase 1 risk rules implemented as deterministic checks:
  R-multiple sizing, ATR stop, portfolio exposure, drawdown control,
  leverage cap, spread check, pump filter, anti-round-number stop,
  trading plan completeness.
```

---

## GROUP-10: Performance, Journal & Learning Group

```yaml
group_id: performance_journal_learning
responsibility: >
  Log every event in the system; compute signal performance metrics;
  detect edge decay; update the HistorianAgent knowledge base;
  produce periodic performance reports.
trigger: Every event (async listener); scheduled batch at end of day
inputs:
  - All system events (subscribed to full EventBus)
outputs:
  - JournalEntry (persistent, append-only)
  - PerformanceReport (periodic)
  - EdgeDecayAlert (if signal performance degrades)
  - KnowledgeBaseUpdate (to HistorianAgent)
always_on: true  # Always listening
llm_permitted: true  # SummarizerAgent may produce narrative reports
deterministic_boundary: >
  All P&L computation, win rate, profit factor, Sharpe ratio calculations
  are deterministic. LLM only for narrative summary reports.
dependencies: all groups (event subscriber)
roles_active:
  - HistorianAgent: indexes trades by pattern type, regime, outcome
  - ScoringAgent: computes signal performance metrics per hypothesis
  - CriticAgent: [LLM-optional] produces post-trade analysis
  - SummarizerAgent: [LLM-optional] generates periodic performance narrative
implementation_priority: 3
phase_2_deliverable: >
  Append-only SQLite journal, trade outcome logging, basic
  performance metrics (win rate, profit factor, Sharpe).
  Edge decay detection as Phase 3.
```

---

## Group Dependency Graph

```
market_data ──────────────────────────────────┐
     │                                         │
     ├──► indicators ──────────────┐           │
     ├──► technical_structure ─────┤           │
     ├──► candlestick ─────────────┤           │
     └──► chart_pattern ───────────┤           │
                                   ▼           ▼
                              entry_group ─► risk_leverage ─► execution
                                   │
                              news_macro (enriches context)
                                   │
                    performance_journal_learning (async, all events)
```
