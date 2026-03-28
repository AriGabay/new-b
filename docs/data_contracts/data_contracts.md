# Data Contracts and Schemas
## Phase: 2 — Architecture
## Date: 2026-03-28

---

## Design Principle

All inter-module communication uses typed, validated schemas. No raw dicts.
Every schema is defined here as a Pydantic model specification.
Python implementations go in `/src/core/schemas.py`.

---

## 1. Market Data Schemas

### OHLCVBar
```python
class OHLCVBar:
    symbol: str                # e.g., "BTCUSDT"
    timeframe: str             # "1d" | "4h" | "1h"
    timestamp: datetime        # UTC, bar OPEN time
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal            # Base asset volume
    volume_usd: Decimal        # Quote volume (USD equivalent)
    is_closed: bool            # True only when bar is finalized

    # Invariants (enforced at parse time):
    # high >= max(open, close)
    # low  <= min(open, close)
    # high >= low
    # volume >= 0
```

### FeatureVector
```python
class FeatureVector:
    symbol: str
    timeframe: str
    timestamp: datetime        # Must match OHLCVBar.timestamp

    # Price / OHLCV
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    # ATR family
    true_range: Decimal
    atr14: Decimal             # Wilder's ATR, 14-period
    atr14_sma20: Decimal       # 20-bar SMA of ATR14 (for regime)

    # EMA family
    ema20: Decimal
    ema50: Decimal
    ema200: Decimal
    prev_ema20: Decimal        # Previous bar (for crossover detection)
    prev_ema50: Decimal

    # Momentum
    rsi14: float               # 0.0 - 100.0; Wilder's RSI
    prev_rsi14: float

    # Bollinger Bands
    bb_upper: Decimal
    bb_middle: Decimal
    bb_lower: Decimal
    bb_width: Decimal          # (upper - lower) / middle
    bb_width_pct: float        # Percentile rank of bb_width over 100 bars (0-100)

    # Trend
    adx14: float               # 0.0 - 100.0

    # Volume analysis
    volume_sma20: Decimal
    volume_ratio: float        # volume / volume_sma20

    # Candle anatomy
    candle_body: Decimal       # |close - open|
    candle_range: Decimal      # high - low
    body_ratio: float          # candle_body / candle_range; 0.0 = full doji
    upper_shadow: Decimal
    lower_shadow: Decimal

    # Derived flags (deterministic)
    impulse_flag: bool         # True if candle_range > 2.0 × atr14
    doji_flag: bool            # True if body_ratio < 0.1
```

---

## 2. Signal Schemas

### CandidateSignal (base class for all group signals)
```python
class CandidateSignal:
    signal_id: str             # UUID
    group_id: str              # Which group produced this
    symbol: str
    timeframe: str
    timestamp: datetime
    direction: str             # "long" | "short"
    signal_type: str           # e.g., "chart_pattern" | "candlestick" | "indicator"
    signal_subtype: str        # e.g., "hs_top" | "bearish_engulfing" | "ema_crossover"
    hypothesis_ref: str | None # e.g., "H1-001" (links to hypothesis registry)
    quality_score: float       # 0.0 - 1.0 (group-specific quality)
    requires_structural_level: bool
    context_confirmed: bool    # True after structural level check
    confirmation_required: bool  # Always True for chart patterns
    confirmed_on_bar_close: bool # True when breakout confirmed
    metadata: dict             # Group-specific additional data
```

### ChartPatternSignal (extends CandidateSignal)
```python
class ChartPatternSignal(CandidateSignal):
    signal_type: str = "chart_pattern"
    pattern_state: str         # "CONFIRMED" (only CONFIRMED signals are emitted)
    breakout_level: Decimal    # Price that was crossed
    measured_move: Decimal     # Full measured move distance
    conservative_target: Decimal  # measured_move × 0.50 (always)
    pattern_quality: float     # symmetry, depth, volume score
    bars_in_formation: int
    volume_at_breakout: Decimal
    volume_at_breakout_ok: bool  # volume_at_breakout > volume_sma20
    neckline_price: Decimal | None  # For H&S patterns
```

### CandlestickSignal (extends CandidateSignal)
```python
class CandlestickSignal(CandidateSignal):
    signal_type: str = "candlestick"
    pattern_name: str          # e.g., "bearish_engulfing"
    bars_consumed: int         # How many bars the pattern spans
    nearest_structural_level: Decimal | None
    structural_level_distance_pct: float | None
```

### IndicatorSignal (extends CandidateSignal)
```python
class IndicatorSignal(CandidateSignal):
    signal_type: str = "indicator"
    indicator_name: str        # e.g., "ema_crossover" | "rsi_divergence" | "bb_squeeze"
    indicator_values: dict     # e.g., {"ema20": 45123.5, "ema50": 44800.0}
    context_filter_passed: bool  # For RSI divergence: no impulse flag, trend confirmed
```

### StructuralLevelSignal
```python
class StructuralLevelSignal:
    symbol: str
    timeframe: str
    timestamp: datetime
    resistance_levels: list[StructuralLevel]
    support_levels: list[StructuralLevel]
    at_resistance: bool
    at_support: bool
    nearest_resistance: StructuralLevel | None
    nearest_support: StructuralLevel | None

class StructuralLevel:
    price: Decimal
    touches: int
    strength: float            # touches × recency_weight × volume_weight
    first_tested: datetime
    last_tested: datetime
    level_type: str            # "swing_high" | "swing_low" | "ma"
```

---

## 3. Group Communication Schema

### GroupSignalBundle
```python
class GroupSignalBundle:
    group_id: str
    symbol: str
    timeframe: str
    timestamp: datetime
    signals: list[CandidateSignal]   # may be empty
    regime: RegimeContext | None     # Only indicators group
    structural: StructuralLevelSignal | None  # Only structure group
    processing_latency_ms: float
    metadata: dict
```

### RegimeContext
```python
class RegimeContext:
    btc_macro: str             # "bull" | "bear" | "ranging"
    trending: bool             # ADX14 > 25
    volatility_regime: str     # "low" | "normal" | "high"
    adx14: float
    atr14: Decimal
    atr14_vs_sma20: float      # ratio: current ATR / SMA of ATR
```

---

## 4. Trade Proposal and Decision Schemas

### CandidateTradeProposal
```python
class CandidateTradeProposal:
    proposal_id: str           # UUID
    symbol: str
    timeframe: str
    timestamp: datetime
    direction: str             # "long" | "short"
    entry_price: Decimal       # Close price of confirmation bar
    thesis: str                # Human-readable: "H&S Top confirmed at 45200"
    setup_refs: list[str]      # signal_ids that contributed
    hypothesis_refs: list[str] # e.g., ["H1-001"]
    raw_target: Decimal        # Conservative target (50% measured move)
    composite_score: float     # 0.0 - 1.0
    score_breakdown: dict      # Component scores
    conflict_report: ConflictReport | None
    historian_analog: HistoricalAnalog | None
    critic_report: CriticReport | None  # Only if LLM critic was run
    regime_context: RegimeContext
    mode_gate: str             # "research" | "shadow" | "live"
```

### RiskApprovedOrder
```python
class RiskApprovedOrder:
    order_id: str              # UUID
    proposal_id: str           # Links to CandidateTradeProposal
    symbol: str
    direction: str
    entry_price: Decimal
    stop_price: Decimal        # ATR-based, anti-gamed
    target_price: Decimal      # = proposal.raw_target
    position_size_usd: Decimal
    position_size_base: Decimal  # In asset units
    leverage: float            # 1.0 for spot
    r_amount: Decimal          # Actual $ risk = position × (entry-stop)/entry
    risk_fraction: float       # r_amount / portfolio_equity
    risk_checks_passed: list[str]  # Names of all checks that passed
    max_bars_to_hold: int      # Default 20
    timestamp: datetime
```

### RiskRejectedEvent
```python
class RiskRejectedEvent:
    proposal_id: str
    rejection_reason: str      # From enum: "daily_loss_limit" | "max_drawdown" |
                               #  "portfolio_exposure" | "correlated_exposure" |
                               #  "spread_too_wide" | "pump_signal" |
                               #  "incomplete_trade_plan" | "mode_gate" | etc.
    rejection_detail: str      # Specific values that triggered rejection
    timestamp: datetime
```

---

## 5. Position and Exit Schemas

### Position
```python
class Position:
    position_id: str           # UUID
    order_id: str
    symbol: str
    direction: str
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    position_size_usd: Decimal
    leverage: float
    r_amount: Decimal
    opened_at: datetime
    bars_held: int
    peak_favorable_price: Decimal  # For trailing stop
    trailing_stop_price: Decimal | None
    current_pnl_usd: Decimal
    current_pnl_r: float       # P&L in R multiples
    status: str                # "open" | "closed"
    correlation_cluster: str   # "btc" | "eth_defi" | "l1" | "meme" | etc.
    setup_refs: list[str]
    hypothesis_refs: list[str]
```

### ExitSignal
```python
class ExitSignal:
    position_id: str
    exit_reason: str           # "stop_loss" | "target_reached" | "trailing_stop" |
                               #  "time_stop" | "signal_reversal" | "manual"
    exit_price: Decimal
    bars_held: int
    pnl_usd: Decimal
    pnl_r: float               # P&L as multiple of R
    timestamp: datetime
```

---

## 6. Journal Schema

### TradeJournalEntry
```python
class TradeJournalEntry:
    # Identity
    journal_id: str            # UUID, append-only
    trade_id: str              # position_id
    logged_at: datetime

    # Trade facts
    symbol: str
    timeframe: str
    direction: str
    entry_price: Decimal
    exit_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    position_size_usd: Decimal
    leverage: float

    # Outcome
    pnl_usd: Decimal
    pnl_r: float
    bars_held: int
    exit_reason: str
    outcome: str               # "win" | "loss" | "breakeven"

    # Signal context
    setup_refs: list[str]      # signal_ids
    hypothesis_refs: list[str] # e.g., ["H1-001"]
    composite_score: float
    score_breakdown: dict

    # Market context at entry
    regime_at_entry: RegimeContext
    features_at_entry: FeatureVector  # Snapshot

    # Market context at exit
    regime_at_exit: RegimeContext
    features_at_exit: FeatureVector   # Snapshot

    # Decision artifacts
    critic_report: CriticReport | None
    conflict_report: ConflictReport | None
    risk_checks_at_entry: list[str]

    # Backtest flags
    is_backtest: bool
    backtest_run_id: str | None
```

### SignalJournalEntry (for all generated signals, traded or not)
```python
class SignalJournalEntry:
    journal_id: str
    signal_id: str
    symbol: str
    timeframe: str
    timestamp: datetime
    group_id: str
    signal_type: str
    signal_subtype: str
    hypothesis_ref: str | None
    direction: str
    quality_score: float
    was_traded: bool           # Did this signal result in a trade?
    rejection_reason: str | None  # If not traded
    features_snapshot: dict    # Key features at signal time
```

---

## 7. Feature Store Contract

```
The FeatureStore is an append-only time-series store.

API:
  get_features(symbol, timeframe, timestamp) → FeatureVector | None
  get_features_range(symbol, timeframe, start, end) → list[FeatureVector]
  get_last_n(symbol, timeframe, n) → list[FeatureVector]
  append(feature_vector: FeatureVector) → None

Constraints:
  - get_* methods NEVER return data with timestamp > query timestamp
    (enforces no-lookahead at the API level)
  - append() is idempotent (same timestamp = overwrite with same data)
  - No delete operations
  - Thread-safe reads

Storage:
  - Phase 2: Parquet files partitioned by symbol/timeframe/date
  - Phase 3: TimescaleDB hypertable
```

---

## 8. Event Bus Contract

```
EventBus is an asyncio-based publish-subscribe system.

Events: All events are typed objects (no raw dicts)
Channels: One channel per event type
Subscribers: Groups subscribe to specific event types

API:
  publish(event: SystemEvent) → None        # async
  subscribe(event_type, callback) → token   # async callback
  unsubscribe(token) → None

Ordering guarantee:
  - Events are delivered in publication order within a channel
  - No ordering guarantee across channels

Failure handling:
  - If subscriber raises exception: exception logged; other subscribers unaffected
  - EventBus itself must never raise (catch-all in publish loop)

Phase 2 implementation: asyncio.Queue per event type
Phase 3+ implementation: Redis Streams for multi-process support
```
