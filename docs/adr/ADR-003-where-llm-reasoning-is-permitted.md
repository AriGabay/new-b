# ADR-003: Where LLM Reasoning Is Permitted
## Status: ACCEPTED
## Date: 2026-03-28

---

## Context

Having decided in ADR-001 and ADR-002 that LLM is not the primary mechanism, this ADR defines precisely where LLM reasoning IS permitted and the constraints that apply.

## Decision

LLM reasoning is permitted in exactly 3 contexts:

### Context 1: CriticAgent in Entry Group (On-Demand, Advisory)

**When:** When composite_score >= 0.60 AND system.mode is SHADOW or LIVE.
**Purpose:** Generate structured adversarial critique of a trade proposal.
**Inputs:** Current proposal, hypothesis file from /research/hypotheses/, last 5 historical analogs.
**Output schema:** CriticReport (typed JSON, validated against schema).
**Authority:** ADVISORY ONLY. Cannot block trade — can reduce composite_score by at most 0.10.
**Timeout:** 2000ms hard limit. If exceeded: CriticAgent returns None, pipeline continues.
**Cost:** One LLM call per qualifying trade proposal. In Research mode: disabled.
**Fallback:** None (pipeline proceeds without critic report, trade proceeds at full score).

### Context 2: SummarizerAgent in Learning Group (Scheduled, Narrative)

**When:** Weekly performance report generation.
**Purpose:** Produce human-readable narrative summary of system performance for operator review.
**Inputs:** Structured LearningReport (JSON). No free-form market data.
**Output:** Markdown narrative (advisory, for human consumption only).
**Authority:** Zero. Narrative is read by human. No automated action taken from it.
**Timeout:** 10000ms (not on critical path).
**Fallback:** If LLM unavailable, structured report delivered without narrative.

### Context 3: ParserAgent in News & Macro Group (On-Demand, Parsing)

**When:** When a news item or event cannot be classified by rule-based parser.
**Purpose:** Extract event type, risk level, and affected symbols from unstructured text.
**Inputs:** News headline + body (truncated to 500 chars). No OHLCV data.
**Output:** EconomicEvent (typed JSON, validated).
**Authority:** Classification only. No trading decisions made from raw LLM output.
**Timeout:** 1000ms.
**Fallback:** If LLM unavailable or output fails schema validation: event classified as "unknown"; event_risk_flag set to "low".

## LLM Usage Rules (Apply to All 3 Contexts)

1. **Structured output only.** Every LLM call must request JSON output conforming to a defined schema. Free-text responses are not accepted.

2. **Schema validation mandatory.** Every LLM response is parsed and validated against its Pydantic schema before use. Validation failure = treat as no response.

3. **Context window is bounded.** No LLM call receives more than 2000 tokens of context. No internet access from LLM. No current price data injected into LLM (prevents hallucination of specific price levels).

4. **Every LLM call is logged.** Input context, output, latency, model used, and token count are logged to the journal. This enables audit and cost tracking.

5. **LLM cannot modify system state.** LLM output is always read by deterministic code that applies it according to defined rules (e.g., "if critic recommends skip → reduce score by 0.10"). The LLM does not directly set any system variable.

6. **LLM is disabled in backtest mode.** Backtests are deterministic only.

7. **LLM is disabled in Research mode** (Context 1 only, by design).

8. **Model selection:** Anthropic Claude claude-haiku-4-5 for CriticAgent (cost efficiency, speed). Claude claude-sonnet-4-5 for SummarizerAgent (quality narrative). Both configurable.

## What LLM Is Explicitly Forbidden From Doing

- Generating pattern detection signals
- Modifying risk parameters
- Approving or rejecting trades (veto power)
- Writing to the FeatureStore
- Calling exchange APIs
- Overriding drawdown controls
- Producing price predictions or level estimates
- Influencing position sizing
