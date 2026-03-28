# PHASE 6 — Candidate Generator Repair

**Date:** 2026-03-29
**Status:** Complete
**Phase:** 6

---

## Executive Summary

Phase 6 identified and repaired the upstream candidate generation path as the primary barrier to natural position opening. The Phase 5.75 runtime generated 8 proposals, all at EMA crossover transition bars. These proposals were rejected by the panel not because the panel was broken (that was fixed in Phase 5.9), but because transition bars are genuinely poor entry conditions.

The repair adds H3-005 (trend continuation signal), enforces candlestick confirmation in the gate, and changes the EntryGroup trigger to wait for both indicator and candlestick bundles. Proposals now fire during established trend pullbacks, not at raw crossover moments.

---

## Problem Statement

After Phase 5.9:
- Panel can approve strong proposals (16/20, avg=7.78 for ideal synthetic)
- All 8 Phase 5.75 replay proposals still rejected (9/20, avg=6.05 → HOLD)
- The 8 proposals all came from EMA crossover bars where signal quality was poor

**Key finding**: The problem was not the panel. The problem was what the candidate generator was producing.

The 8 proposals were systematically weak:

| Signal | At crossover bars | Panel requirement |
|--------|------------------|-------------------|
| ema_alignment | "mixed" | "full_bear" or "full_bull" |
| candlestick | None | Pattern required for panel score |
| volume | 0.92x | ≥ 1.0x preferred |
| RSI | 75.14 rising | 35–65 for SHORT continuation |
| EMA separation | ~0% (just crossed) | >0.2% (committed) |

Every dimension was in the wrong state for a panel-compatible proposal.

---

## Root Cause Analysis

### Root Cause 1: Generator fires at transition bars (H3-002 only)

H3-002 (EMA crossover) detects the exact bar where EMA20 crosses EMA50. This is a lagging indicator of trend transition, not trend confirmation. At this bar:

- **EMA alignment**: EMA20 just crossed EMA50, so they're nearly equal. Price typically still above EMA200. Setup_packet_builder computes: above200=True, above50=False, above20=False → "mixed" (not full_bear).
- **Volume**: The momentum that caused the crossover is already in the past. Volume at the crossover bar is often declining.
- **Candlestick**: The crossover bar is an indicator event, not a price action reversal. No structural reason for a candlestick pattern to form at this specific bar.
- **RSI**: If the trend was bearish enough to produce a death cross, RSI may be elevated (prior bearish momentum reading).

All 8 Phase 5.75 proposals came from this signal. All were weak.

### Root Cause 2: EntryGroup evaluated before candlestick bundle arrived

EntryGroup previously triggered evaluation as soon as the IndicatorsGroup bundle arrived. The event bus processes FeatureReadyEvent subscribers in subscription order — IndicatorsGroup subscribed before CandlestickGroup. When EntryGroup received the indicators bundle, CandlestickGroup had not yet published its bundle for the same bar.

Result: `candlestick_quality = 0.0` in every proposal's composite score.

### Root Cause 3: Candlestick gate not enforced

The EntryGroup docstring stated "At least 1 must be a chart pattern or candlestick" but the code checked only `len(signals) >= 2`, not signal type. Two indicator signals (death_cross + rsi_overbought_fade) could pass the gate with zero candlestick signals.

This allowed proposals through that:
- Always had `candlestick_quality = 0.0` in composite
- Always had `patterns_detected=[]` in the setup packet
- The panel's Candlestick evaluator always scored 4.0 (abstain)
- Composite score was borderline (0.45–0.50) — barely above or below threshold

---

## Repairs Applied

### Repair 1: Add H3-005 (trend continuation signal) to IndicatorsGroup

**File**: `src/groups/indicators/group.py`

New method `_detect_trend_continuation()` (H3-005):

```
SHORT fires when:
  - EMA20 < EMA50 < EMA200 (full_bear alignment)
  - |EMA50 - EMA20| / EMA50 >= 0.2% (trend committed)
  - Price within 3% below EMA20 (pullback retest zone)
  - ADX >= 25 (trending)
  - volume_ratio >= 1.0 (average+ participation)
  - 35 < RSI < 65 (mid-zone, pulled back)

LONG fires when: (mirror conditions for full_bull)
```

This signal fires during the ESTABLISHED TREND PHASE (typically 3–15+ bars after the initial crossover), at the pullback-to-EMA retest. At these bars, EMA alignment is "full_bear"/"full_bull" — exactly what TrendFollowing needs to score 8.0+.

H3-005 also added to the `_score_signals` priority boost alongside H3-002 and H3-004.

### Repair 2: EntryGroup waits for candlestick bundle

**File**: `src/groups/entry/group.py`

Changed trigger in `_collect_bundle()`:

```python
# Old: fire on indicators alone
if has_indicators and symbol not in self._evaluating:

# New: wait for both indicators AND candlestick
if has_indicators and has_candlestick and symbol not in self._evaluating:
```

CandlestickGroup always publishes a bundle every bar (even with 0 signals). This change is safe — no proposals are lost. It ensures `candlestick_quality` is computed from the actual bar's pattern data.

### Repair 3: Enforce candlestick/chart_pattern in confirmation gate

**File**: `src/groups/entry/group.py`

Added gate enforcement in `_evaluate_trade_opportunity()`:

```python
has_bar_level_confirmation = any(
    getattr(s, "signal_type", "") in ("candlestick", "chart_pattern")
    for s in primary_signals
)
if not has_bar_level_confirmation:
    return  # indicator-only proposals suppressed
```

This enforces what the docstring promised. Pure indicator-only proposals (which the panel cannot approve due to missing candlestick context) are blocked before composite score computation or panel evaluation.

---

## What Was NOT Changed

- `APPROVE_THRESHOLD = 14` — unchanged
- `MIN_AVG_SCORE = 6.5` — unchanged
- FinalDecisionGroup safety rails — unchanged
- H3-002 (EMA crossover) still fires — unchanged (it's a valid signal when accompanied by a candlestick signal)
- Phase 5.9 evaluator repairs (PatternCompletion, RiskParity, DrawdownRisk) — unchanged

---

## Expected Impact

### Old proposals (indicator-only at crossover bars): Blocked

These proposals never reach the panel. The candlestick gate suppresses them. This reduces noise in the proposal pipeline.

### New proposals (H3-005 + candlestick at pullback bars): Expected

H3-005 fires in established trend phases during pullback-to-EMA bars. When CandlestickGroup also detects a pattern at the same bar (Evening Star, Bearish Engulfing, Three Black Crows), the two signals combine:

- Composite score: ~0.83 (well above 0.50)
- EMA alignment for panel: "full_bear" → TrendFollowing 8.0+
- Candlestick present → Candlestick 7.0–10.0
- At resistance (required for most CS patterns) → Structure 7.5+
- Volume ≥ 1.0x → VolumeProfile 6.5+
- ADX ≥ 25 → Momentum and Confluence benefit

Projected panel score for strong H3-005 + CS proposal: 14–16/20, avg 6.8–7.5 → ENTER

---

## Test Coverage

**File**: `src/tests/test_candidate_generator_repair.py` — 20 tests

| Section | Tests | Coverage |
|---------|-------|---------|
| H3-005 fires correctly | 2 | SHORT and LONG established trend |
| H3-005 suppression | 6 | ADX, volume, EMA separation, RSI range, price distance, mixed alignment |
| H3-002 not broken | 1 | Regression: still fires at death cross |
| H3-005 quality score | 1 | Quality ≥ 0.85 in ideal conditions |
| EntryGroup gate | 4 | Bundle wait, indicator-only rejection, H3-005+CS acceptance |
| Composite score | 2 | H3-005+CS well above threshold, indicator-only below |
| Panel regression | 2 | Ideal still ENTER, weak still HOLD |
| No hardcoded approvals | 1 | Signal scored by panel, not pre-approved |

Total: **244 tests passing** (20 new + 224 prior)

---

## Repair Summary Matrix

| Component | Previous behavior | Weakness | Repair | New behavior | Evidence | Still limited? |
|-----------|------------------|---------|--------|-------------|---------|----------------|
| Indicator trigger timing (H3-002) | Fires at exact crossover bar | EMA alignment="mixed", RSI high, no candlestick | Add H3-005 for established trend | Fires at pullback-to-EMA in full alignment | 8 unit tests | H3-002 still fires at transitions (but gate blocks proposals) |
| Candlestick confirmation timing | Not required (evaluated before CS bundle) | candlestick_quality=0.0 always | Wait for CS bundle before evaluating | CS quality included in every proposal | Gate test | None |
| Confirmation gate behavior | ≥2 signals any type | Pure indicator proposals passed | Enforce candlestick/CS requirement | indicator-only suppressed | Gate test | Chart_pattern still excluded (Phase 4) |
| Composite score | 0.45–0.50 (borderline) | No candlestick, poor indicator quality | All 3 above repairs | 0.79–0.83 (strong) | Score test | Structural and candlestick quality still variable |
| Proposal publication timing | At first indicators arrival | Missing CS data | Wait for both bundles | After both bundles collected | Bundle wait test | None |
| Replay proposal quality | "mixed" EMA, no CS, 0.92x vol | All 8 rejected by panel | H3-005 + gate | "full_bear" EMA, CS present, vol ≥ 1.0x | Analysis (unit tests verify signal logic) | Exact replay count TBD |
| Panel compatibility | 0/8 compatible | Signal profile mismatch | Changes above | H3-005+CS proposals projected to pass | Panel regression tests | Contrary requires R:R>3 + strong structure |
