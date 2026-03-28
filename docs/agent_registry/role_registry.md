# Agent Role Registry
## Phase: 2 — Architecture
## Date: 2026-03-28

---

## Overview

This document defines the 10 standardized agent role types. Each role is a class template that groups instantiate to fulfill their function. Roles are NOT processes — they are behavioral specifications implemented as class methods or coroutines within each group's module.

---

## ROLE-01: ResearchAgent

```
Purpose:
  Queries the system's knowledge base (hypothesis registry, rejected ideas,
  validated edges, historical journal) to retrieve context relevant to
  current market conditions.

When Invoked:
  - Entry Group: before scoring a new signal
  - Learning Group: when indexing new trade outcomes
  - Any group: when a "novel" condition is detected

Inputs:
  - query: dict (symbol, pattern_type, conditions)
  - knowledge_base: HypothesisRegistry | ValidatedEdgeRegistry | JournalDB

Outputs:
  - ResearchResult{relevant_hypotheses, historical_analogs, warnings}

LLM Permitted: NO (queries are structured lookups against defined registries)
  Exception: If query cannot be resolved by structured lookup, may invoke
  LLM with strict context window (hypothesis file content only).

Implementation:
  - Phase 2: Direct lookup against /research/hypotheses/ files
  - Phase 3: Embedding-based semantic search over journal

Contract:
  - Must return within 100ms
  - Must not modify any registry
  - Must log every query and result
```

---

## ROLE-02: ParserAgent

```
Purpose:
  Converts raw, unstructured, or semi-structured input into the
  canonical typed data format expected by the group.

When Invoked:
  - Market Data Group: on every raw exchange message
  - News & Macro Group: on every news item or event calendar update

Inputs:
  - raw_data: bytes | dict | str (format depends on group)

Outputs:
  - Typed domain object (OHLCVBar, NewsEvent, EconomicEvent, etc.)
  - ParseResult{success: bool, object: domain_obj | None, errors: list}

LLM Permitted: YES (News & Macro Group only, for unstructured news parsing)
  Constraints: Only for News group; must include source URL; output must
  conform to EconomicEvent schema; no autonomous actions taken.

Implementation:
  - Market Data: deterministic JSON parser against Binance schema
  - News: rule-based first, LLM fallback for unstructured items

Contract:
  - Parse failures must be logged, not silently swallowed
  - Must not make network calls (input is pre-fetched)
  - Idempotent: same input always produces same output
```

---

## ROLE-03: SignalAgent

```
Purpose:
  Core computational role. Runs the group's primary signal detection
  logic and produces candidate signals in the group's domain.

When Invoked:
  - Every bar close (for data-driven groups)
  - On CandidateTradeEvent (for Exit Group)
  - On GroupSignalBundle arrival (for Entry Group)

Inputs:
  - FeatureVector (for indicator/candlestick/chart pattern groups)
  - GroupSignalBundles (for Entry Group)
  - PositionState (for Exit Group)

Outputs:
  - List[CandidateSignal] (may be empty)
  - Each CandidateSignal: {signal_id, direction, strength, metadata}

LLM Permitted: NO (ALL signal detection is deterministic)
  This is a hard boundary. Signal generation must be reproducible.

Key Constraints:
  - Must use ONLY data from current bar close or prior bars
  - Never use next bar data (enforced by FeatureStore API which only
    returns data up to and including the current bar)
  - For chart patterns: must be in CONFIRMED state (not FORMING)
  - For candlestick: complete pattern on bar close only

Implementation:
  - Pure functions of (features_array, config) → List[Signal]
  - Each pattern implemented as separate, independently testable function
  - Parameters from config file, never hardcoded
```

---

## ROLE-04: ValidatorAgent

```
Purpose:
  Applies the group's validation rules to each CandidateSignal.
  Rejects signals that fail quality or context requirements.

When Invoked:
  - After SignalAgent produces candidates
  - Entry Group: enforces confirmation gate (hard rule)
  - Risk Group: enforces all 9 Phase 1 risk rules

Inputs:
  - List[CandidateSignal]
  - ValidationContext (current features, system state, group context)

Outputs:
  - List[ValidatedSignal] (subset of input that passed all checks)
  - List[RejectedSignal] (with rejection reason for each)

LLM Permitted: NO (all validation rules are deterministic)

Key Validation Rules (varies by group):
  Market Data: OHLC constraint, gap detection
  Indicators: impulse_flag suppression for RSI divergence
  Candlestick: structural level requirement for context-dependent patterns
  Chart Pattern: bar close confirmation only; volume check; mode gate
  Entry: confirmation gate; conflict check; mode gate; score threshold
  Risk: ALL 9 Phase 1 risk rules (see risk_contract.md)

Contract:
  - Every rejection must include a rejection_code and reason string
  - Rejection rates are logged and monitored (high rejection rate = signal quality problem)
  - ValidatorAgent decisions are deterministic and auditable
```

---

## ROLE-05: ScoringAgent

```
Purpose:
  Assigns a numerical score to validated signals, reflecting their
  quality, confluence, and context alignment.

When Invoked:
  - After ValidatorAgent approves a signal
  - Entry Group: computes composite score across all group signals

Inputs:
  - ValidatedSignal
  - ScoringContext (regime, volume, structural confirmation, etc.)

Outputs:
  - ScoredSignal{...signal, score: float, score_breakdown: dict}

Score Range: 0.0 - 1.0
Score Interpretation:
  0.00 - 0.39: DISCARD (below minimum threshold)
  0.40 - 0.59: WEAK (log only, no trade in Phase 2 unless high-conviction context)
  0.60 - 0.79: ACCEPTABLE (tradeable with standard size)
  0.80 - 1.00: STRONG (tradeable; may run CriticAgent to challenge)

LLM Permitted: NO (scoring formulas are deterministic)
  This is critical: score must not be influenced by LLM output.
  LLM may CHALLENGE the score but not compute it.

Scoring Weights (Entry Group composite):
  chart_pattern_quality   × 0.40
  candle_signal_quality   × 0.20
  structure_confirmation  × 0.20
  volume_at_breakout      × 0.10
  regime_alignment        × 0.10

  These weights are configuration parameters, validated against backtest results.

Contract:
  - Same inputs always produce same score (deterministic)
  - Score breakdown must be logged for every signal
  - Weights must match configuration file (not hardcoded)
```

---

## ROLE-06: ConflictAgent

```
Purpose:
  Detects conflicts between signals within or across groups.
  Conflicts reduce confidence or block trade proposals.

When Invoked:
  - Entry Group: before building CandidateTradeProposal
  - Candlestick Group: when multiple patterns detected on same bar

Inputs:
  - List[ValidatedSignal or GroupSignalBundle]

Outputs:
  - ConflictReport{conflicts: list, resolution: str, net_direction: str | None}

Conflict Types:
  DIRECTION: signals disagree on long/short (most serious)
  TIMEFRAME: higher vs. lower timeframe signals disagree
  STRENGTH: primary signal contradicted by secondary signal
  REGIME: signal direction opposes macro regime

Resolution Logic:
  DIRECTION conflict: if score gap < 0.20 → BLOCK trade (too ambiguous)
  DIRECTION conflict: if score gap >= 0.20 → proceed with higher-scored direction
  TIMEFRAME conflict: higher timeframe always wins
  REGIME conflict: reduce position size by 50%

LLM Permitted: YES (only for ConflictAgent in Entry Group, when conflict type
  is REGIME and resolution is ambiguous. Strict: 1 LLM call, 500ms timeout,
  result is advisory only — does not override deterministic score gap rule.)

Contract:
  - All conflicts must be logged
  - ConflictAgent cannot cancel a trade that Risk Engine would approve
    (it can reduce score, not veto — Risk Engine has final veto)
  - LLM advice is logged alongside deterministic resolution, for audit
```

---

## ROLE-07: ContextAgent

```
Purpose:
  Enriches validated signals with contextual information from the
  current market environment: regime, macro risk, correlation cluster,
  sector narrative.

When Invoked:
  - After ValidatorAgent, before ScoringAgent
  - Entry Group: adds regime and macro context to CandidateTradeProposal

Inputs:
  - ValidatedSignal
  - SystemState.regime
  - MacroContextEvent (from News & Macro Group)
  - CorrelationCluster (from static cluster map + dynamic BTC correlation)

Outputs:
  - ContextEnrichedSignal{...signal, regime_context, macro_context,
      correlation_cluster, event_risk_flag}

LLM Permitted: NO (context enrichment is structured lookups)

Contract:
  - regime_context must be one of: {bull, bear, ranging}
  - correlation_cluster must be assigned from predefined taxonomy
  - event_risk_flag reduces position size (handled by Risk Engine)
  - Staleness: if regime data > 1 hour old, flag as stale
```

---

## ROLE-08: HistorianAgent

```
Purpose:
  Queries the trade journal for historical analogs to the current signal.
  Returns relevant past performance statistics and any known failure modes.

When Invoked:
  - Entry Group: before building proposal (optional, max 50ms budget)
  - Learning Group: when indexing new outcomes

Inputs:
  - SignalQuery{pattern_type, direction, regime, score_range, recency_days}

Outputs:
  - HistoricalAnalog{
      similar_trades_count,
      win_rate,
      avg_r_multiple,
      common_failure_modes,
      last_10_outcomes
    }

LLM Permitted: NO (journal queries are structured database lookups)

Implementation:
  - Phase 2: SQLite query against trade journal
  - Phase 3: Vector similarity search for analog finding

Contract:
  - Returns empty HistoricalAnalog if journal has < 10 analogous trades
  - Never blocks the main pipeline (budget: 50ms, else skip)
  - Must not return journal data from OOS holdout period
```

---

## ROLE-09: CriticAgent

```
Purpose:
  Challenges a proposed trade by generating a structured list of reasons
  it may fail. Provides adversarial perspective before final entry decision.

When Invoked:
  - Entry Group: when composite_score >= 0.60 AND system.mode != RESEARCH
  - Learning Group: post-trade for high-r-multiple losses
  - Optional: high composite score in RESEARCH mode (for journal quality)

Inputs:
  - CandidateTradeProposal (full context: signal, regime, history, conflicts)
  - CriticPromptContext (relevant hypothesis from /research/hypotheses/)

Outputs:
  - CriticReport{
      trade_id,
      bullish_case: list[str],
      bearish_case: list[str],  # The critique
      failure_modes: list[str],
      confidence_in_critique: float,  # 0.0-1.0
      recommendation: str  # "proceed" | "reduce_size" | "skip"
    }

LLM Permitted: YES — this is one of only two primary LLM roles.
  Constraints:
  - Invoked only when composite_score >= 0.60 (don't waste LLM on weak signals)
  - Must complete within 2000ms (hard timeout)
  - Output must conform to CriticReport schema (JSON with validation)
  - recommendation is ADVISORY ONLY; Risk Engine has final authority
  - LLM context window: current signal + hypothesis file + last 5 journal analogs
    (No internet access; no hallucination of external events)
  - recommendation == "skip" reduces composite_score by 0.10 (not to 0)

Contract:
  - CriticAgent output always logged alongside trade, even if ignored
  - If LLM call fails: CriticAgent returns None; pipeline proceeds normally
  - No cascading failure from LLM unavailability
```

---

## ROLE-10: SummarizerAgent

```
Purpose:
  Produces the group's final output: a typed, structured bundle that
  the orchestrator or downstream groups consume.

When Invoked:
  - End of each group's processing cycle
  - Learning Group: periodic performance reports

Inputs:
  - All role outputs from the current processing cycle
  - GroupConfig (defines what to include in bundle)

Outputs:
  - GroupSignalBundle (for analysis groups 3-6)
  - CandidateTradeProposal (Entry Group)
  - RiskApprovedOrder or RiskRejectedEvent (Risk Group)
  - PerformanceReport (Learning Group)

LLM Permitted: YES — for Learning Group's narrative report ONLY.
  Constraints:
  - LLM produces natural language summary for human review
  - Summary accompanies (not replaces) structured metrics
  - Learning Group only; all other groups produce structured output only

Contract:
  - Output must always be a valid typed object (schema validated)
  - Empty bundle is valid output (means no signal this cycle)
  - Must include: group_id, symbol, timestamp, processing_latency_ms
  - Must not include any future data (lookahead audit checkpoint)
```

---

## Role Activation Matrix

| Group | Research | Parser | Signal | Validator | Scoring | Conflict | Context | Historian | Critic | Summarizer |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| market_data | - | ✓ | - | ✓ | - | - | - | ✓ | - | ✓ |
| news_macro | ✓ | ✓ | - | ✓ | - | - | ✓ | - | ✓* | ✓ |
| indicators | - | - | ✓ | ✓ | ✓ | - | ✓ | - | - | ✓ |
| candlestick | - | - | ✓ | ✓ | ✓ | ✓ | - | - | - | ✓ |
| chart_pattern | - | - | ✓ | ✓ | ✓ | - | - | ✓ | - | ✓ |
| technical_structure | - | - | ✓ | ✓ | ✓ | - | - | - | - | ✓ |
| entry | ✓ | - | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓* | ✓ |
| exit | - | - | ✓ | ✓ | - | - | - | - | - | ✓ |
| risk_leverage | - | - | - | ✓ | - | - | - | - | - | ✓ |
| performance_journal | ✓ | - | - | - | ✓ | - | - | ✓ | ✓* | ✓* |

✓* = LLM permitted in this role for this group
