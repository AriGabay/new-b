# System Overview — Autonomous Crypto Trading Decision System
## Phase: 2 — Architecture
## Date: 2026-03-28
## Grounded in: /docs/phase_1_handoff_to_architecture.md

---

## 1. What This System Is

An autonomous multi-agent crypto trading decision system that:
- Ingests live and historical market data
- Detects technically-defined setups from Phase 1's hypothesis registry
- Computes entry, stop, target, and position size for each candidate trade
- Governs all risk at trade and portfolio level before any order reaches execution
- Journals every signal and outcome for continuous learning
- Never executes trades it cannot explain

**What this system is NOT:**
- Not a black box
- Not an always-on LLM swarm
- Not a prediction machine (no price forecasting)
- Not a validated system yet (Phase 1 produced 0 validated edges; Phase 2 validates them)

---

## 2. Core Design Constraints (from Phase 1 handoff)

These constraints drive every architecture decision:

| Constraint | Source | Enforcement |
|---|---|---|
| Zero lookahead — signals only on bar CLOSE | P1 Principle 3 | Data layer: bar close event only |
| Breakout confirmation required | Bulkowski (P1 S1.2 hard rule) | Signal Gate: confirmation_required=True enforced |
| 50% target discount on measured moves | Bulkowski (P1 S1.3) | Target calculator: built-in discount |
| R-multiple position sizing | P1 R1 | Risk Engine: mandatory pre-entry |
| ATR(14)×2 stop loss default | P1 R2 | Risk Engine: mandatory pre-entry |
| 5% daily loss limit | P1 R4 | Risk Governor: hard halt |
| 20% portfolio drawdown halt | P1 R4 | Risk Governor: hard halt |
| Universe: min $5M 24h volume | P1 R5 | Universe Filter: pre-signal gate |
| No Elliott Wave, Wyckoff, harmonics | P1 Part 4 hard exclusions | Pattern Registry: explicitly blocked |
| All patterns in research mode until OOS validated | P1 Principle 2 | Mode gate: enforced in signal router |

---

## 3. The 10 Agent Groups

Agent groups are **logical service boundaries**, not 100 always-on heavyweight processes. Each group is a module with defined inputs, outputs, and internal roles. Groups are instantiated on demand and communicate via message bus.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION ENGINE                             │
│                    (DecisionOrchestrator)                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  Coordinates via AsyncEventBus
          ┌────────────────────┼────────────────────────┐
          ▼                    ▼                        ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐
│  GROUP 1        │  │  GROUP 2        │  │  GROUP 3                │
│  MARKET DATA    │  │  NEWS & MACRO   │  │  INDICATORS             │
│  (always-on)    │  │  (scheduled)    │  │  (per bar close)        │
└─────────────────┘  └─────────────────┘  └─────────────────────────┘
          ▼                    ▼                        ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐
│  GROUP 4        │  │  GROUP 5        │  │  GROUP 6                │
│  CANDLESTICK    │  │  CHART PATTERN  │  │  TECHNICAL STRUCTURE    │
│  (per bar)      │  │  (per bar)      │  │  (per bar)              │
└─────────────────┘  └─────────────────┘  └─────────────────────────┘
          ▼                    ▼                        ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐
│  GROUP 7        │  │  GROUP 8        │  │  GROUP 9                │
│  ENTRY          │  │  EXIT           │  │  RISK & LEVERAGE        │
│  (on signal)    │  │  (on position)  │  │  (always-on gate)       │
└─────────────────┘  └─────────────────┘  └─────────────────────────┘
                               ▼
              ┌────────────────────────────────┐
              │  GROUP 10                      │
              │  PERFORMANCE, JOURNAL          │
              │  & LEARNING                    │
              │  (async, always logging)       │
              └────────────────────────────────┘
```

---

## 4. Agent Role Types (Standardized Across All Groups)

Each group has up to 10 agent roles. These are class types, not always-on processes:

| Role | Function | When Invoked |
|---|---|---|
| **ResearchAgent** | Queries knowledge base; retrieves relevant hypotheses/rules | On-demand |
| **ParserAgent** | Parses raw data into structured format for group consumption | Per data event |
| **SignalAgent** | Generates candidate signals in group's domain | Per bar close |
| **ValidatorAgent** | Validates signal against group's quality rules | Per candidate signal |
| **ScoringAgent** | Assigns numerical score to validated signal | Per validated signal |
| **ConflictAgent** | Detects conflicts between this group's signals and others | Pre-decision |
| **ContextAgent** | Enriches signal with regime, sector, correlation context | Per signal |
| **HistorianAgent** | Queries trade journal for similar historical setups | Per signal |
| **CriticAgent** | Challenges the signal; lists reasons it may fail | Per signal |
| **SummarizerAgent** | Produces the group's contribution to DecisionPacket | Per cycle |

**Key principle:** Most roles use deterministic algorithms. Only the CriticAgent and SummarizerAgent for high-stakes decisions may invoke LLM reasoning. Details in ADR-003.

---

## 5. Decision Lifecycle

```
BAR CLOSE EVENT
     │
     ▼
[Market Data Group] → normalized OHLCV + features pushed to FeatureStore
     │
     ├──► [Indicators Group] → computes ATR, EMAs, RSI, BB, ADX per symbol
     ├──► [Candlestick Group] → detects candlestick patterns per symbol
     ├──► [Chart Pattern Group] → evaluates pattern states per symbol
     └──► [Technical Structure Group] → S/R levels, trend, regime

Each group produces → GroupSignalBundle (typed message on EventBus)
     │
     ▼
[Entry Group] ← receives all GroupSignalBundles
     │  Checks: universe filter, confirmation gate, conflict check
     │  Produces: CandidateTradeProposal (or None)
     │
     ▼
[Risk & Leverage Group] ← receives CandidateTradeProposal
     │  Applies: R-multiple sizing, ATR stop, leverage cap,
     │            portfolio exposure check, drawdown state,
     │            spread check, pump signal check
     │  Produces: RiskApprovedOrder (or Rejected)
     │
     ▼
[Exit Group] ← runs independently on open positions
     │  Monitors: stop hit, target hit, time stop, trailing stop
     │  Produces: ExitSignal
     │
     ▼
[EXECUTION LAYER] ← receives RiskApprovedOrder or ExitSignal
     │  Phase 2: logs to journal (research mode)
     │  Phase 3+: sends to exchange API
     │
     ▼
[Performance, Journal & Learning Group]
     │  Logs every event: signal, decision, execution, outcome
     │  Runs async analysis: win rate, failure mode patterns
     └──► Updates HistorianAgent's knowledge base
```

---

## 6. Mode Gates

Every signal path passes through a Mode Gate before execution:

```python
class ModeGate(Enum):
    RESEARCH = "research"     # Log signals, never execute
    SHADOW   = "shadow"       # Paper trade with real-time data
    LIVE     = "live"         # Execute real orders

# Promotion requires explicit sign-off:
# RESEARCH → SHADOW: OOS backtest passes acceptance criteria
# SHADOW   → LIVE:   Shadow P&L positive for 90+ days
```

**Phase 2 default: ALL signals in RESEARCH mode.**

---

## 7. What Is Deterministic vs. LLM-Governed

| Layer | Logic Type | Justification |
|---|---|---|
| Data ingestion, normalization | Deterministic | No ambiguity |
| Feature computation (ATR, EMA, RSI) | Deterministic | Mathematical definitions |
| Pattern detection (all patterns) | Deterministic | Defined as pure functions |
| Risk calculations (sizing, stops) | Deterministic | Formulas from P1 risk rules |
| Universe filter | Deterministic | Threshold rules |
| Breakout confirmation gate | Deterministic | Binary rule: close beyond level |
| Signal conflict detection | Deterministic | Rule-based |
| Journal writes | Deterministic | Append-only log |
| CriticAgent synthesis (optional) | LLM | Synthesizes conflicting signals |
| SummarizerAgent (high-stakes) | LLM | Produces natural language rationale |
| ResearchAgent (novel situations) | LLM | Queries knowledge base with fuzzy context |
| Backtesting, reporting | Deterministic | Must be reproducible |
| OOS validation pass/fail | Deterministic | Statistical rules from P1 OQ-016 |

**LLM invocation is the exception, not the default.** See ADR-003.

---

## 8. Technology Stack (Recommended)

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Ecosystem for quant/data |
| Data store | TimescaleDB or DuckDB | Time-series optimized |
| Feature store | Parquet files (local) + Redis cache | Fast feature retrieval |
| Message bus | asyncio queues (Phase 2); Redis Streams (Phase 3+) | Start simple |
| Config | YAML + Pydantic validation | Type-safe, parameterized |
| Testing | pytest + hypothesis (property testing) | Correctness verification |
| Backtesting | Custom (no vectorbt/backtrader initially) | Enforce no-lookahead at architecture level |
| LLM integration | Anthropic Claude API | For CriticAgent and SummarizerAgent only |
| Monitoring | Structured JSON logs → any log aggregator | Traceability |

---

## 9. Key Non-Negotiables

1. **No signal fires before bar CLOSE.** This is enforced at the data layer, not by convention.
2. **Risk engine veto cannot be overridden.** If drawdown limit is hit, no trade fires.
3. **Patterns stay in RESEARCH mode until OOS validation passes.** This is enforced by ModeGate.
4. **Every signal, every decision, every exit is logged.** Logging failures are system failures.
5. **Rejected signals are logged identically to accepted signals.** The false negative rate matters.
