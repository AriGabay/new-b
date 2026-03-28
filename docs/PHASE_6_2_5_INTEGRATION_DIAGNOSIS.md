# Phase 6.2.5 — Integration Diagnosis Report

**Date:** 2026-03-29
**Phase:** 6.2.5 — Runtime Integration Audit and Repair
**Outcome:** TWO RUNTIME INTEGRATION DEFECTS IDENTIFIED AND REPAIRED

---

## Executive Summary

Phase 6.2.5 conducted a direct code audit of the runtime pipeline to determine whether the Phase 6.2 panel ceiling of 12/20 was caused by:
- (A) fixture design only
- (B) fixture design + runtime integration defects
- (C) mainly runtime integration defects

**Answer: (B) — fixture design plus two real runtime integration defects.**

The Phase 6.2 conclusion that "only fixture design is blocking" was **incorrect**. Two integration defects were present that caused the panel to receive systematically degraded setup packet data regardless of fixture quality:

| Defect | Location | Impact | Status |
|--------|----------|--------|--------|
| Candlestick signals never reaching setup packet | `runner.py` + `CandlestickGroup` | Panel saw `patterns_detected=[]` always | **FIXED** |
| `_classify_trend()` never called; structural fields missing from bundle | `TechnicalStructureGroup` + `schemas.py` | Panel always saw `structure_quality='none'` regardless of actual structure | **FIXED** |

**Before repair:** Best panel result: 12/20 approvals, avg 6.350 (threshold: 14/20, avg ≥6.5)  
**After repair:** Best panel result: 13/20 approvals, avg 6.700  
**Remaining gap:** −1 approval (avg score now exceeds minimum)

---

## Defect 1: Candlestick Signal Propagation Broken

### Root Cause

`PanelDecisionGroup._evaluate_proposal()` retrieves candlestick signals via:
```python
candlestick_signals = self._candlestick_signal_cache.get(symbol, [])
```

`_candlestick_signal_cache` is a `dict` that must be injected via:
```python
def set_candlestick_signal_cache(self, cache: dict) -> None:
    self._candlestick_signal_cache = cache
```

However:
1. `CandlestickGroup` had **no `_signals_cache`** attribute — it emitted signals only as `GroupSignalEvent` and never stored them.
2. `BtcBybitPaperRunner._wire_caches()` had a comment in the docstring saying it should wire the candlestick signal cache, but **never called** `set_candlestick_signal_cache()`.

Result: `self._candlestick_signal_cache` was always the default empty `{}`, so `candlestick_signals` was always `[]`. `build_candlestick_snapshot([])` returned:
```python
CandlestickSnapshot(patterns_detected=[], primary_pattern=None, ...)
```

The panel never knew that `bullish_engulfing` had fired.

### Evidence

From Phase 6.2 journal packet `f4700d62` (bar 246 — confirmed co-occurrence bar):
```json
"candlestick": {
    "patterns_detected": [],
    "primary_pattern": null,
    "pattern_direction": null,
    "pattern_at_structure": true,
    "raw_signals": []
}
```

Panel evaluator response to empty candlestick:
> "No candlestick signal to confirm or deny the trade. Absence of candlestick pattern means no bar-level confirmation." → score 4.0 (abstain)

### Fix Applied

**`src/groups/candlestick/group.py`:**
- Added `self._signals_cache: dict[str, list] = {}` to `__init__`
- In `_process_features`, before publishing the GroupSignalEvent: `self._signals_cache[symbol] = list(signals)`

**`src/runtime/runner.py` (`_wire_caches()`):**
- Added: `self._panel_decision.set_candlestick_signal_cache(self._candlestick._signals_cache)`

### Impact After Fix

Panel evaluator response to populated candlestick:
> "Candlestick 'bullish_engulfing' is at a structural level with matching direction" → score 10.0 (approve)

Approval count: 12 → **13** (+1). Avg: 6.350 → **6.700** (+0.350).

---

## Defect 2: Structural Snapshot Contract Mismatch

### Root Cause

`StructuralLevelBundle` (defined in `src/core/schemas.py`) did not contain the fields:
- `structure_quality`
- `trend_direction`
- `higher_highs`
- `higher_lows`

`build_structural_snapshot()` (in `src/runtime/setup_packet_builder.py`) used `getattr()` with defaults to read these fields:
```python
structure_quality=getattr(structural_bundle, "structure_quality", "none"),
trend_direction=getattr(structural_bundle, "trend_direction", "sideways"),
higher_highs=getattr(structural_bundle, "higher_highs", False),
higher_lows=getattr(structural_bundle, "higher_lows", False),
```

Since the fields didn't exist on the bundle, `getattr` always returned the defaults: `"none"`, `"sideways"`, `False`, `False`.

Additionally, `TechnicalStructureGroup._classify_trend()` was a fully implemented method that computed `higher_highs`, `higher_lows`, and `trend_direction` from the bar history — but it was **never called anywhere**. It computed results that were immediately discarded. The method had been implemented but never wired into `_build_structural_bundle()` or `_process_features()`.

### Evidence

`TechnicalStructureGroup._classify_trend()` exists at line 315 and correctly computes:
```python
higher_highs = second_half_high > first_half_high
higher_lows  = second_half_low  > first_half_low
```

But the only caller chain: `_process_features() → _build_structural_bundle()`. Neither called `_classify_trend()`. The method was dead code.

From Phase 6.2 journal packet (structural section):
```json
"structure_quality": "none",
"trend_direction": "sideways",
"higher_highs": false,
"higher_lows": false
```

Despite the W-bottom fixture having:
- `higher_lows=True` (second dip at bar 240–243 is higher than first dip at bar 230–234)
- This would have produced `structure_quality='weak'` if the algorithm had been called

Panel evaluator response to `structure_quality='none'`:
> "structure quality 'none' — the market rarely moves cleanly in this context" → score 4.0 (reject)

### Fix Applied

**`src/core/schemas.py`:**
Added four fields to `StructuralLevelBundle`:
```python
structure_quality:  str  = "none"     # "none" | "weak" | "moderate"
trend_direction:    str  = "sideways" # "uptrend" | "downtrend" | "sideways"
higher_highs:       bool = False
higher_lows:        bool = False
```

**`src/groups/technical_structure/group.py` (`_build_structural_bundle()`):**
- Added `bars: list` parameter
- Added call: `higher_highs, higher_lows, trend_direction = self._classify_trend(bars, fv)`
- Added structure_quality derivation:
  - `"moderate"` if `higher_highs and higher_lows and trend_direction != "sideways"`
  - `"weak"` if `higher_highs or higher_lows`
  - `"none"` otherwise

Updated `_process_features()` to pass `bars` to `_build_structural_bundle()`.

### Impact After Fix

For W-bottom fixture (bar 246):
- `higher_lows=True` ← correctly computed (second dip is higher than first)
- `higher_highs=False` ← correctly computed (pullback bar, not making new highs)
- `structure_quality='weak'` ← correctly elevated from 'none'
- `trend_direction='sideways'` ← still sideways (HH absent, so not "uptrend")

Panel evaluator response to `structure_quality='weak'`:
> "Trade is at key support with **weak** quality level providing solid reference point" → score 6.5 (approve, was 4.0 reject)

This converted one reject to approve.

---

## Before / After Comparison

### Phase 6.2 (pre-fix) vs Phase 6.2.5 (post-fix)

| Metric | Phase 6.2 | Phase 6.2.5 | Delta |
|--------|-----------|-------------|-------|
| `patterns_detected` in packet | `[]` | `['bullish_engulfing']` | **Fixed** |
| `primary_pattern` in packet | `null` | `'bullish_engulfing'` | **Fixed** |
| `structure_quality` in packet | `'none'` | `'weak'` (W-bottom) | **Fixed** |
| `higher_lows` in packet | `false` | `true` (W-bottom) | **Fixed** |
| `trend_direction` in packet | `'sideways'` | `'sideways'` (unchanged, correct) | — |
| Best approve count | 12/20 | **13/20** | +1 |
| Best avg score | 6.350 | **6.700** | +0.350 |
| Avg score ≥ threshold (6.5) | No | **Yes** | Fixed |
| Approval count ≥ threshold (14) | No | No | Still -1 |
| Natural positions opened | 0 | 0 | Still 0 |

---

## Current State After Repair

The pipeline now delivers correct setup packets. The remaining panel gap is:

- **Approval count:** 13/20 (need 14)
- **Avg score:** 6.700 (threshold 6.5 ✓ — now passing)
- **Gap:** -1 approval

The 4 abstainers in the post-fix best proposal score 5.0–5.5:
1. `5.5` — "No wick rejection present — structure is the primary reference" → fixture design issue
2. `5.5` — Risk profile concerns → threshold-bounded evaluator
3. `5.0` — "Volume character 'normal' with ratio 1.03" → fixture volume design
4. `5.0` — "Chart pattern capability not active" → architectural (ChartPatternGroup excluded)

The 3 rejecters score 3.0–4.5:
1. `3.0` — RSI 54.7 not oversold → evaluator wants RSI 35–45 for mean-reversion entry
2. `4.0` — Structural skepticism (persistent)
3. `4.5` — BB squeeze / volume below breakout threshold

**The remaining gap is genuinely fixture design, not code defects.** One more approval requires either:
- Lower wick on the engulfing bar (demonstrating rejection of support by bears)
- Volume ratio ≥ 1.5 on the entry bar (showing institutional participation / breakout conviction)
- RSI near 40–45 on entry (showing pullback to neutral zone from overbought, not already neutral)

---

## Integrity Statement

Phase 6.2.5 does NOT claim:
- The runtime bugs caused all failures ← Two specific defects are identified and fixed
- Fixing the bugs would have produced natural opens ← False; structural fixture improvements are also needed
- The panel threshold should change ← It should not; 13/20 correctly holds a setup with no wick confirmation and weak volume

Phase 6.2.5 DOES establish:
- Two runtime integration defects were real and measurably impacted panel scores
- Both defects are now fixed
- The remaining -1 approval gap is attributable to fixture design (wick/volume)
- After code repair, the Phase 6.2 conclusion must be revised: it was "fixture design + runtime defects," not "fixture design only"
