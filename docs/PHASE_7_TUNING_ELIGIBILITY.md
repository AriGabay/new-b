# PHASE 7 TUNING ELIGIBILITY
**Date:** 2026-03-29
**Status:** GO confirmed — this surface is now eligible for calibration work

This document defines the exact parameters eligible for tuning in Phase 7.
It also defines the guardrails that must not be violated during tuning.

DO NOT begin tuning without reading the guardrails section.

---

## WHAT PHASE 7 IS

Phase 7 = learning, calibration, and parameter optimization.

The goal is to improve the system's ability to identify high-quality setups,
reduce false approvals, and calibrate evaluator influence — without breaking the
structural integrity of the runtime path.

Phase 7 is NOT:
- Architectural rewiring
- Adding new groups
- Rewriting evaluators from scratch
- Enabling live trading
- Multi-symbol expansion

---

## ELIGIBLE TUNING SURFACE

### 1. Panel Thresholds (TraderEvaluatorPanel)

| Parameter | Current Value | Location | Notes |
|-----------|--------------|----------|-------|
| APPROVE_THRESHOLD | 14/20 | src/traders/panel.py | Min approvals to enter |
| AVG_SCORE_THRESHOLD | 6.5 | src/traders/panel.py | Min avg score to enter |

**Safe tuning range:**
- APPROVE_THRESHOLD: 12–18 (below 12 = too permissive; above 18 = near-impossible)
- AVG_SCORE_THRESHOLD: 6.0–7.5

**Guardrail:** Any threshold change must be validated by running ALL fixture variants
(V1, V2, V3) and confirming behavior is consistent with observed evidence. V1 must
continue to reject (or regression is undetectable).

---

### 2. FinalDecisionGroup Safety Rails (FinalDecisionGroup)

| Rail | Current Value | Location | Notes |
|------|--------------|----------|-------|
| Minimum avg_score | 5.0 | src/decision/final_group.py | Below this → hold regardless |
| Maximum reject_count | 12 | src/decision/final_group.py | Above this → hold |
| Minimum R:R ratio | 1.5 | src/decision/final_group.py | Below this → hold |
| High volatility threshold | 16 approvals required | src/decision/final_group.py | During high vol |

**Safe tuning range:**
- These are safety rails, not performance parameters. Change only if evidence shows
  they are incorrectly blocking valid setups.
- Minimum avg_score: 4.0–6.0
- R:R minimum: 1.2–2.0

**Guardrail:** These rails exist for a reason. Do not remove any of them. Only tighten
or loosen within the safe range above.

---

### 3. EntryGroup Composite Score Weights

| Component | Weight | Location |
|-----------|--------|----------|
| chart_pattern_quality | 0.35 | src/groups/entry/group.py _compute_composite_score |
| candlestick_quality | 0.25 | src/groups/entry/group.py |
| indicator_quality | 0.20 | src/groups/entry/group.py |
| structural_alignment | 0.10 | src/groups/entry/group.py |
| historian_win_rate | 0.10 | src/groups/entry/group.py |

**Current state:**
- chart_pattern_quality weight is in the formula but always evaluates to 0.0
  (ChartPatternGroup does not emit GroupSignalEvent to EntryGroup)
- historian_win_rate is always 0.0 (HistorianAgent not wired)
- Effective active sum: 0.55 (candlestick + indicator + structural)

**Tuning eligibility:**
- Candlestick weight (0.25): eligible, range 0.20–0.40
- Indicator weight (0.20): eligible, range 0.15–0.30
- Structural weight (0.10): eligible, range 0.05–0.20
- chart_pattern_quality: only becomes tunable if ChartPatternGroup is wired to emit
  GroupSignalEvent (currently not — intentional design)

**CRITICAL GUARDRAIL:**
If you change weights, you MUST also update ACTIVE_COMPOSITE_WEIGHT_SUM to match
the sum of weights for ACTIVE groups only. Failure to do this will cause composite_score
to be incorrectly normalized and proposals will either all fire or none fire.

**CRITICAL GUARDRAIL:**
After any weight change, re-run all fixture replay tests and confirm:
- V1 still holds (< 14/20 or score < 6.5)
- V2 still enters (14/20+, score >= 6.5)
- V3 still enters with chart pattern boost

---

### 4. EntryGroup Composite Score Threshold

| Parameter | Current Value | Location |
|-----------|--------------|----------|
| COMPOSITE_SCORE_THRESHOLD | 0.50 | src/groups/entry/group.py |
| CRITIC_SCORE_THRESHOLD | 0.60 | src/groups/entry/group.py |

**Safe tuning range:**
- COMPOSITE_SCORE_THRESHOLD: 0.45–0.65
- CRITIC_SCORE_THRESHOLD: 0.55–0.75

**Guardrail:** Lowering COMPOSITE_SCORE_THRESHOLD increases proposal rate.
More proposals = more panel evaluations but also more panel rejects.
Raising it reduces proposal rate — risk is no proposals reaching panel at all.
Validate with replay after any change.

---

### 5. Per-Evaluator Scoring Logic (20 TraderEvaluators)

**File:** src/traders/evaluators.py

Each evaluator has:
- A base score (starting point)
- Condition-based adjustments (+/- score)
- Vote threshold: score >= 7.0 → approve, score >= 5.0 → abstain, else reject

**Eligible tuning:**
- Individual evaluator score adjustments (the +/- condition rules)
- Vote thresholds per evaluator
- Evaluator confidence weights

**Guardrail:** Changes to any evaluator must be justified by outcome attribution data
showing that evaluator's predictions were systematically miscalibrated. Do not tune
evaluators based on intuition alone. The calibration DB should accumulate data first.

**Current state:** Calibration DB is empty (no live trades yet). Phase 7 should first
accumulate ≥50 outcomes before making data-driven evaluator tuning decisions.

---

### 6. Risk Sizing Parameters (RiskLeverageGroup)

| Parameter | Current Value | Location |
|-----------|--------------|----------|
| DEFAULT_RISK_FRACTION | 0.01 (1%) | src/groups/risk_leverage/group.py |
| MAX_SINGLE_POSITION | 0.10 (10%) | src/groups/risk_leverage/group.py |
| DAILY_LOSS_LIMIT | -0.02 (-2%) | src/groups/risk_leverage/group.py |
| MAX_DRAWDOWN_HALT | 0.10 (10%) | src/groups/risk_leverage/group.py |
| MAX_PORTFOLIO_EXPOSURE | 0.25 (25%) | src/groups/risk_leverage/group.py |

**Safe tuning range:**
- DEFAULT_RISK_FRACTION: 0.005–0.02 (0.5%–2%)
- MAX_SINGLE_POSITION: 0.05–0.15 (5%–15%)
- Risk limits (DAILY_LOSS_LIMIT, MAX_DRAWDOWN_HALT): only tighten, never loosen,
  without extensive justification

**Guardrail:** This is paper mode. Risk parameters exist to simulate realistic
constraints. Do not make risk limits so loose that they fail to enforce any discipline,
even in paper mode.

---

### 7. Replay Fixture Regime Balance

**Current fixtures:**
- btc_w_bottom_long_v1 (257 bars, holds at 13/20)
- btc_w_bottom_long_v2 (260 bars, approves at 14/20)
- btc_double_bottom_long_v1 (260 bars, approves at 16/20)

**Eligible for Phase 7:**
- Add SHORT setup fixtures
- Add sideways/ranging regime fixtures
- Add bearish trend + rejection fixtures
- Add multi-signal confluence fixtures

**Guardrail:** New fixtures must NOT be constructed to force a specific outcome.
They must represent realistic market conditions that the system should learn from.
All new fixtures must undergo the same integrity checks as existing ones
(no at_support pre-injection, no force_approve fields, etc.).

---

### 8. ExitGroup Trailing Stop Parameters

| Parameter | Current Value | Location |
|-----------|--------------|----------|
| Trailing activation | +1R favorable | src/groups/exit/group.py |
| Trailing ATR multiplier | 2.0 | src/groups/exit/group.py |
| Time stop bars | 20 | src/groups/exit/group.py |

**Safe tuning range:**
- Trailing activation: +0.5R–+2R
- ATR multiplier: 1.5–3.0
- Time stop: 15–30 bars

---

## PHASE 7 TUNING GUARDRAILS SUMMARY

1. **Never change two parameter categories simultaneously.** Change one, run all fixture
   tests, verify regression baseline holds, then move to the next.

2. **Always re-run the V1/V2/V3 regression suite after any parameter change.** The test
   suite is the truth. If tests fail, the change is not valid.

3. **Never tune based on a single fixture run.** Require at least 3 regime variants
   before drawing conclusions.

4. **Never tune evaluator weights before accumulating calibration data.** The calibration
   tables require real outcome data. Empty calibration tables mean random tuning.

5. **Document every tuning decision with before/after evidence.** One-line explanation +
   fixture results = minimum acceptable documentation.

6. **Do not remove any safety rail.** FinalDecisionGroup rails can be adjusted but not
   removed.

7. **Source separation must not be violated.** Never mix simplified_backtest outcomes
   with event_driven_runtime calibration. The source_separation tests must always pass.

8. **Do not start live trading during Phase 7.** Phase 7 is paper/simulation only.
