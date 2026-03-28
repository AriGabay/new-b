# ADR-001: Logical Agent Groups, Not Always-On LLM Processes
## Status: ACCEPTED
## Date: 2026-03-28

---

## Context

The system is described as a "multi-agent" trading system. The naive interpretation is to run 100 always-on LLM agent processes — one per role per group. This interpretation is wrong and would produce a broken system.

## Decision

Agent Groups are implemented as **logical service modules** (Python classes/coroutines). Agent Roles are **behavioral specifications** implemented as methods or inner classes within each group module. LLM invocation occurs only for specific, bounded tasks in specific roles (CriticAgent and SummarizerAgent in limited groups), triggered on-demand.

## Reasoning

**Cost:** At $0.002 per LLM call, 100 calls per bar × 24 bars/day × 365 days = $1,752/year minimum for daily bars. For 4h bars: 6× more. This is just the API cost — not counting failure modes.

**Latency:** LLM calls take 200ms-5s. Bar close processing must complete in under 100ms to avoid cascading delays on higher-frequency timeframes. LLM calls cannot be on the critical path.

**Reliability:** If the LLM API is unavailable, trading must continue. Building critical path logic on LLM means the system cannot function during API outages.

**Traceability:** LLM output is stochastic. A trading system that makes decisions based on stochastic reasoning with no deterministic record is not auditable. When a trade loses money, "the LLM said so" is not a valid post-mortem.

**Signal quality:** The signals we are building (breakout confirmations, ATR stops, R-multiple sizing) are mathematical and deterministic. Using LLM reasoning for decisions that are expressible as formulas adds noise, not intelligence.

## Consequences

- All signal detection, feature computation, risk calculation, and journal writes are deterministic.
- LLM is permitted only in: CriticAgent (Entry Group, on-demand, advisory only), SummarizerAgent (Learning Group, periodic narrative reports), ParserAgent (News Group, unstructured text only).
- LLM failure always falls back gracefully — deterministic path proceeds.
- "100 agents" = 10 logical modules × 10 role specifications. Not 100 processes.

## Alternatives Rejected

- **Always-on LLM agents per role:** Rejected for cost, latency, reliability, traceability.
- **No LLM at all:** Rejected because CriticAgent (adversarial signal challenge) provides genuine value for ambiguous high-stakes signals that benefit from synthesis reasoning.
- **LLM for signal generation:** Rejected because signals must be deterministic and reproducible for backtesting to be meaningful.
