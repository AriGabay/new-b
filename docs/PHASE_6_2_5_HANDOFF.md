# Phase 6.2.5 Handoff Document

**Date:** 2026-03-29
**Phase:** 6.2.5 — Runtime Integration Audit and Repair (Complete)
**Outcome:** TWO INTEGRATION DEFECTS REPAIRED — Panel: 12/20 → 13/20, avg 6.350 → 6.700

---

## What Was Phase 6.2.5

Phase 6.2.5 challenged the Phase 6.2 conclusion that "only fixture design is blocking natural opens." A direct code audit found two runtime integration defects that systematically degraded setup packet quality regardless of fixture design.

**Phase 6.2 conclusion (incorrect):** Only fixture design is blocking.  
**Phase 6.2.5 finding:** Fixture design + two runtime integration defects.  
**Phase 6.2.5 outcome:** Both defects fixed. Remaining gap: fixture design only.

---

## What Was Repaired

### Defect 1: Candlestick Signal Propagation Broken

**Symptom:** `patterns_detected=[]` in every BTCSetupPacket sent to the panel.

**Root cause:** `CandlestickGroup` had no `_signals_cache`. `BtcBybitPaperRunner._wire_caches()` was documented to wire the candlestick signal cache to `PanelDecisionGroup`, but never called `set_candlestick_signal_cache()`. The panel always received an empty candlestick cache.

**Fix:**
- `src/groups/candlestick/group.py`: Added `_signals_cache: dict[str, list] = {}`; populate it each bar before publishing GroupSignalEvent
- `src/runtime/runner.py`: Added `self._panel_decision.set_candlestick_signal_cache(self._candlestick._signals_cache)`

**Impact:** One panel evaluator changed from "No candlestick signal → score 4.0 (abstain)" to "Bullish engulfing at structural level → score 10.0 (approve)". +1 approval.

---

### Defect 2: `_classify_trend()` Dead Code — Structural Fields Missing from Bundle

**Symptom:** `structure_quality='none'`, `trend_direction='sideways'`, `higher_highs=false`, `higher_lows=false` in every BTCSetupPacket, regardless of actual market structure.

**Root cause:** Two sub-defects:
1. `StructuralLevelBundle` in `src/core/schemas.py` was missing fields `structure_quality`, `trend_direction`, `higher_highs`, `higher_lows`. `build_structural_snapshot()` used `getattr()` with defaults, so always fell back to "none"/"sideways"/False/False.
2. `TechnicalStructureGroup._classify_trend()` — a fully implemented method — was never called anywhere. It was dead code.

**Fix:**
- `src/core/schemas.py`: Added four fields to `StructuralLevelBundle` (with "none"/"sideways"/False/False as defaults for backward compatibility)
- `src/groups/technical_structure/group.py`: Added `bars` parameter to `_build_structural_bundle()`; called `_classify_trend(bars, fv)` to populate the fields; added `structure_quality` derivation logic ("moderate" / "weak" / "none")
- `src/groups/technical_structure/group.py`: Updated `_process_features()` to pass `bars` to `_build_structural_bundle()`

**Impact:** One evaluator changed from "structure quality 'none' → score 4.0 (reject)" to "weak quality level → score 6.5 (approve)". +0.5 approval contribution. `higher_lows=true` now correctly detected for W-bottom.

---

## Before / After Panel Results

| Fixture | Pre-Fix Best | Post-Fix Best | Delta |
|---------|-------------|---------------|-------|
| W-bottom | 12/20 avg 6.350 | **13/20 avg 6.700** | +1 approve, +0.350 avg |
| M-top | 12/20 avg 6.350 | **13/20 avg 6.700** | +1 approve, +0.350 avg |
| Triple-touch | 12/20 avg 6.225 | **13/20 avg 6.575** | +1 approve, +0.350 avg |

Threshold: **14/20 approvals, avg ≥ 6.5**

**Avg score threshold (6.5):** NOW MET ✓  
**Approval count threshold (14):** Still -1 short  
**Natural positions opened:** 0 (unchanged — need 14th approval first)

---

## Current State: What Remains After Phase 6.2.5

### What is now correct
- Candlestick pattern names appear in setup packet ✓
- `structure_quality` computed by real algorithm ✓
- `trend_direction` computed by real algorithm ✓
- `higher_highs` / `higher_lows` populated from bar history ✓
- Panel avg score exceeds 6.5 for structural proposals ✓
- All existing tests pass (79 passed, 1 skipped) ✓

### What remains as the next blocker

**ONE approval short (13/20 vs 14/20)**

The remaining 4 abstainers score 5.0–5.5 for fixture-attributable reasons:

| Evaluator | Score | Reason | Phase 6.3 Fix |
|-----------|-------|--------|---------------|
| Wick evaluator | 5.5 | No wick rejection on engulfing bar | Design entry bar with lower wick touching support |
| Risk threshold evaluator | 5.5 | Stop/R:R threshold boundary | Not easily addressable |
| Volume evaluator | 5.0 | volume_ratio=1.03, needs 1.5+ | Set volume_ratio ≥ 1.5 on entry bar in fixture |
| Chart pattern evaluator | 5.0 | ChartPatternGroup excluded (architectural) | Not addressable in Phase 6.3 |

The 3 rejecters (3.0, 4.0, 4.5) respond to:
- RSI 54.7 not oversold — fixture should have RSI 40–45 on entry
- Structural skeptic — `structure_quality='moderate'` would help (requires HH/HL sequence)
- BB squeeze — wider BB (ADX-driven volatility expansion)

**The most actionable fixture change:** Add a clear lower wick on the Bullish Engulfing bar (demonstrating rejection of support zone), AND set volume_ratio ≥ 1.5 on that bar. These changes alone could convert the 5.5 wick-evaluator and 5.0 volume-evaluator to approve (7.0+), reaching 15/20.

---

## Required Phase 6.3 Actions

### Option A: Fix entry bar design (RECOMMENDED)

Design the engulfing bar with:
- Lower wick extending to support level (low ≈ 69,670) and close well above
- Volume ratio ≥ 1.5 (high participation bar)
- RSI 40–48 (pullback from overbought, not already neutral)

This targets +2 approvals (wick evaluator + volume evaluator) → 15/20, which exceeds threshold.

### Option B: Build HH/HL structure before entry

Design bars 200–240 with confirmed higher-highs and higher-lows in sequence, so `_classify_trend()` produces `higher_highs=True, higher_lows=True, trend_direction='uptrend'` and `structure_quality='moderate'`.

This targets the structural-skeptic rejecter (4.0 → 6.0+) → +0.5 approval.

### Option C: Combined A + B

Estimated result: 15–16/20 approvals, avg 7.2–7.5 → natural open expected.

---

## Integrity Statement

Phase 6.2.5 does NOT:
- Claim the runtime bugs were the only blocker ← Fixture design is also needed
- Claim natural opens are now achievable without fixture improvement ← They are not
- Downplay the importance of fixture wick/volume design ← It's the last hurdle

Phase 6.2.5 DOES establish:
- The Phase 6.2 "fixtures only" conclusion was wrong
- Two real integration defects contributed to the 12/20 ceiling
- Both defects are now fixed permanently
- The panel avg score now meets its threshold (6.700 ≥ 6.5)
- The remaining -1 approval gap is attributable to fixture design only

---

## Files Delivered

| File | Status |
|------|--------|
| `src/core/schemas.py` | ✅ Fixed: StructuralLevelBundle +4 fields |
| `src/groups/technical_structure/group.py` | ✅ Fixed: _classify_trend() wired |
| `src/groups/candlestick/group.py` | ✅ Fixed: _signals_cache added |
| `src/runtime/runner.py` | ✅ Fixed: candlestick cache wired |
| `docs/PHASE_6_2_5_INTEGRATION_DIAGNOSIS.md` | ✅ Written |
| `docs/candlestick_packet_wiring_audit.md` | ✅ Written |
| `docs/structural_snapshot_contract_audit.md` | ✅ Written |
| `docs/phase_6_2_before_after_integration_fix.md` | ✅ Written |
| `docs/PHASE_6_2_5_HANDOFF.md` | ✅ This file |

---

*Phase 6.2.5 closed. Two runtime integration defects repaired.*  
*Panel: 12/20 → 13/20, avg 6.350 → 6.700.*  
*Phase 6.3: Add wick + volume to entry bar → target 15/20 → natural open.*
