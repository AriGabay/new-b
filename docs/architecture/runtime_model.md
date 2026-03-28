# Runtime Model
## Phase: 2 — Architecture
## Date: 2026-03-28

---

## 1. Execution Model Philosophy

This system is NOT a swarm of 100 always-on heavyweight LLM agents. That design fails in production for the following reasons:
1. Cost: 100 LLM calls per bar close × 24 bars/day × $0.01 per call = $8,760/year minimum, for noise
2. Latency: LLM calls are 500ms-5s; bar close processing must complete in <100ms
3. Reliability: LLM API unavailability cannot halt trading decisions
4. Traceability: LLM output is non-deterministic, making audit and debugging hard

**Architecture decision:** Agent Groups are logical modules. Agent Roles within groups are class instances. LLMs are invoked only for synthesis/critique tasks, and only when deterministic logic has already narrowed the decision space.

---

## 2. Process Topology

```
┌──────────────────────────────────────────────────────────────┐
│                     MAIN PROCESS                             │
│                                                              │
│  ┌─────────────────────────────────┐                        │
│  │  Orchestrator (asyncio event loop)                        │
│  │  - Schedules bar close callbacks                          │
│  │  - Routes events via EventBus                             │
│  │  - Maintains system state                                 │
│  └─────────────────────────────────┘                        │
│                                                              │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │  DataFeed     │  │  FeatureStore │  │  JournalWriter  │  │
│  │  (always-on)  │  │  (cache)      │  │  (always-on)    │  │
│  └───────────────┘  └───────────────┘  └─────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  GroupRunner (coroutines, one per active group)         │  │
│  │  - Each group runs as asyncio Task                      │  │
│  │  - Groups are started on BAR_CLOSE, complete before     │  │
│  │    RiskEngine runs                                       │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────┐  ┌───────────────┐                       │
│  │  RiskEngine   │  │  ModeGate     │                       │
│  │  (sync, final │  │  (global mode │                       │
│  │   authority)  │  │   enforcement)│                       │
│  └───────────────┘  └───────────────┘                       │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Event Types and Flow

### Event Hierarchy
```
SystemEvent (base)
├── BarCloseEvent          # New OHLCV bar finalized
├── FeatureReadyEvent      # Feature computation complete for symbol
├── GroupSignalEvent       # Group has produced its signal bundle
├── CandidateTradeEvent    # Entry Group proposes a trade
├── RiskDecisionEvent      # Risk Engine approves or rejects
├── OrderEvent             # Execution layer instruction
├── PositionUpdateEvent    # Position opened / modified / closed
├── JournalEntryEvent      # Anything journalable
└── SystemAlertEvent       # Drawdown breach, data gap, etc.
```

### Event Flow Timing (per bar close, daily timeframe)
```
T=0ms   BarCloseEvent fires for all symbols
T=1ms   DataFeed normalizes and stores new bar
T=2ms   FeatureComputer runs (ATR, EMA, RSI, BB, ADX) — sync, <5ms
T=7ms   Groups 1,3,4,5,6 run concurrently via asyncio.gather()
T=30ms  GroupSignalEvents arrive on EventBus
T=31ms  Entry Group collects all signals, runs conflict check
T=35ms  CandidateTradeEvent produced (or None)
T=36ms  Risk Engine runs (sync, deterministic, <5ms)
T=41ms  RiskDecisionEvent: APPROVED or REJECTED
T=42ms  ModeGate: RESEARCH → log only; LIVE → OrderEvent
T=43ms  JournalWriter logs everything
T=50ms  DONE (well within daily bar processing budget)
```

---

## 4. Group Activation Policy

Not all groups run on every bar close. Activation depends on available signals:

| Group | Trigger | Frequency |
|---|---|---|
| Market Data | Always-on, feeds bar close events | Continuous |
| News & Macro | Scheduled: hourly poll + event-driven | Hourly + on news |
| Indicators | Every bar close | Per bar |
| Candlestick | Every bar close | Per bar |
| Chart Pattern | Every bar close | Per bar |
| Technical Structure | Every bar close | Per bar |
| Entry | Only when ≥1 upstream group has signal | Per signal |
| Exit | Every bar close, for each open position | Per bar (positions) |
| Risk & Leverage | On every CandidateTradeEvent | Per candidate |
| Performance/Journal | Always-on async writer | Continuous |

---

## 5. Sub-Agent Spawning Policy

Groups may spawn lightweight sub-agents for specific tasks. Rules:

```python
class SubAgentSpawnPolicy:
    # Maximum concurrent sub-agents per group
    max_concurrent_per_group: int = 3

    # Sub-agents are only spawned when:
    # 1. Parent group's deterministic signal is ambiguous
    # 2. LLM synthesis is enabled in config
    # 3. System is not in high-load state (CPU < 80%)

    # Sub-agent types allowed:
    allowed_types: list = [
        "CriticSubAgent",      # Challenges a proposed signal
        "ContextSubAgent",     # Fetches additional context
        "HistorianSubAgent",   # Queries historical similar setups
    ]

    # Sub-agents are NEVER allowed to:
    # - Override risk decisions
    # - Fire orders directly
    # - Modify the FeatureStore
    # - Persist state between invocations

    # Sub-agent timeout: 2000ms hard limit
    timeout_ms: int = 2000
```

---

## 6. State Model

```
SystemState (singleton, shared across all groups):
├── mode: ModeGate           # RESEARCH | SHADOW | LIVE
├── portfolio:
│   ├── equity: Decimal      # Current total portfolio value
│   ├── available: Decimal   # Available capital for new trades
│   ├── open_positions: dict # symbol → Position
│   ├── daily_pnl: Decimal   # Resets at UTC 00:00
│   ├── consecutive_losses: int
│   └── drawdown_pct: float  # From high-water mark
├── regime:
│   ├── btc_macro: str       # "bull" | "bear" | "ranging"
│   ├── volatility: str      # "low" | "normal" | "high"
│   └── trending: bool       # ADX > 25
├── universe:
│   └── eligible_symbols: set[str]  # Updated hourly
└── risk_state:
    ├── halted: bool         # True if max_drawdown exceeded
    ├── size_reduction: float  # 1.0 = normal, 0.5 = half size
    └── halt_reason: str | None
```

---

## 7. Caching Strategy

```
Layer 1 — In-process cache (Redis or dict):
  - Feature vectors per symbol: TTL = 1 bar close
  - S/R levels per symbol: TTL = 4 bars (recompute periodically)
  - Universe filter results: TTL = 1 hour
  - Pattern state per symbol: TTL = 1 bar

Layer 2 — Feature store (Parquet files):
  - Historical features for backtesting
  - Immutable once written
  - Keyed by symbol + timeframe + bar_timestamp

Layer 3 — Journal (TimescaleDB or SQLite):
  - Append-only
  - Never deleted
  - Used by HistorianAgent and Learning Group
```

---

## 8. Failure Modes and Recovery

| Failure | Detection | Response |
|---|---|---|
| Data feed gap | Missing bar timestamp | Flag symbol as "data_gap"; skip signals for that symbol |
| Feature computation error | Exception in compute | Log error; use last-known features with staleness flag |
| Group processing timeout | asyncio timeout | Log timeout; group contributes no signal this bar |
| Risk Engine error | Exception in risk calc | REJECT all trades for this bar; alert |
| Journal write failure | Exception in journal | Retry 3×; if persistent: halt system |
| LLM API failure | HTTP error | Skip LLM step; proceed with deterministic result only |
| Drawdown limit breach | Portfolio state | Halt immediately; no new trades; alert |

**Safety principle:** Any failure in analysis layers defaults to NO TRADE. Failure in risk layers defaults to HALT. Only journal write failures can halt the system — no other failure does.

---

## 9. Backtesting Runtime (Separate Mode)

Backtesting uses the identical pipeline with these overrides:
- `DataFeed` replaced by `HistoricalDataFeed` (replays from Parquet store)
- `ModeGate` forced to `RESEARCH` (no execution)
- `JournalWriter` writes to isolated backtest journal
- Sub-agent spawning disabled (deterministic only)
- LLM calls disabled (deterministic only)
- Timing constraints relaxed (no real-time requirement)

This ensures backtesting uses EXACTLY the same logic as live, preventing implementation divergence.
