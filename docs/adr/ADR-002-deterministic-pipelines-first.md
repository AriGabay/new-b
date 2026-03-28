# ADR-002: Deterministic Pipelines Come Before LLM Reasoning
## Status: ACCEPTED
## Date: 2026-03-28

---

## Context

It is tempting to delegate complex trading decisions to LLM reasoning immediately, especially when pattern recognition seems "subjective" (e.g., identifying H&S patterns, assessing trend quality). The question is: when should deterministic code be used, and when should LLM reasoning be invoked?

## Decision

Deterministic code is always implemented first. LLM reasoning is only added where:
1. The task is genuinely ambiguous (cannot be reduced to an algorithm)
2. The output is advisory (not gate-controlling)
3. The cost/latency is acceptable
4. Fallback to deterministic result is safe

## Reasoning

**Backtesting requires determinism.** If signal generation uses LLM calls, backtesting on historical data would require replaying LLM interactions — making backtests stochastic, irreproducible, and potentially expensive. The hypothesis validation pipeline (central to Phase 1's entire framework) cannot work with non-deterministic signals.

**Debugging requires determinism.** When a pattern fires and results in a loss, the investigation must be able to reproduce exactly what the system saw and decided. LLM-based decisions cannot be exactly reproduced.

**Phase 1 produced deterministic hypotheses.** All 25 hypotheses in the registry are defined as mathematical conditions on OHLCV data. There is no ambiguity that requires LLM reasoning for their detection. The ambiguity lies in interpretation and confluence — which CriticAgent handles at the end of the pipeline, not the beginning.

**The cost of wrong LLM calls is asymmetric.** A deterministic algorithm that is wrong can be fixed in code. An LLM that produces a confident-sounding wrong signal for a trade is harder to detect and fix, and may cause real losses.

## Decision Boundary

| Decision | Type |
|---|---|
| Is this an engulfing candle? | Deterministic (exact OHLCV comparison) |
| What is the ATR? | Deterministic (formula) |
| Is this breakout confirmed? | Deterministic (binary: close beyond level) |
| What is the position size? | Deterministic (formula from R-multiple) |
| Should I veto this trade? | Deterministic (risk rules) |
| Is this pattern forming? | Deterministic (state machine) |
| Does this signal conflict with macro context? | Deterministic (structured lookup) |
| Should I challenge this trade idea? | LLM-optional (CriticAgent) |
| Write a narrative about this week's performance | LLM-optional (Summarizer) |
| Classify this unstructured news headline | LLM-permitted (News Parser) |

## Consequences

- The backtesting engine works on historical data without any LLM calls.
- All pattern detection is reproducible across runs.
- LLM integration is additive (can be disabled without breaking core functionality).
- CriticAgent's LLM output is logged and measured for accuracy over time.

## Alternatives Rejected

- **LLM-first approach:** Rejected. Makes backtesting impossible and adds stochasticity to deterministic math.
- **No LLM at all:** Partially rejected — CriticAgent's adversarial synthesis provides genuine value for complex confluence situations that are hard to encode as rules.
