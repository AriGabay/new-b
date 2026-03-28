# Phase 6.2 Before/After Integration Fix — Phase 6.2.5

**Date:** 2026-03-29

---

## Summary

Two runtime integration defects were identified and repaired in Phase 6.2.5. This document shows the measurable impact on panel results before and after the repair.

---

## Defect Matrix

| Issue | Suspected Cause | Verified Root Cause | Code Fix Applied | Evidence After Fix | Still Limited? |
|-------|----------------|---------------------|------------------|--------------------|---------------|
| `patterns_detected=[]` in setup packet | Wiring missing | `CandlestickGroup` has no `_signals_cache`; runner never calls `set_candlestick_signal_cache()` | Added `_signals_cache` to CandlestickGroup; added wire in runner | `patterns_detected=['bullish_engulfing']` in journal packet ✓ | No — fixed |
| `structure_quality='none'` always | `_classify_trend()` not called | `_classify_trend()` exists but never called; `StructuralLevelBundle` missing fields | Added fields to `StructuralLevelBundle`; wired `_classify_trend()` into `_build_structural_bundle()` | `structure_quality='weak'`, `higher_lows=true` in journal packet ✓ | No — fixed |
| `trend_direction='sideways'` | Not a bug | W-bottom fixture genuinely lacks HH/HL → sideways is correct | Not applicable | `trend_direction='sideways'` (correct for W-bottom) | Yes — fixture design |
| `higher_lows=false` | Not a bug | Pre-fix: missing field → default. Post-fix: algorithm computes correctly | Fixed via field + _classify_trend() wiring | `higher_lows=true` (W-bottom second dip is higher) ✓ | No — fixed |
| Panel approval count 12/20 | Both code bugs + fixture | Code bugs: candlestick missing, structure_quality='none' wrong; Fixture: RSI neutral, volume weak | Code bugs fixed | 13/20 after fix | Yes — 1 more needed from fixture design |
| Panel avg score 6.350 | Both code bugs + fixture | Code bugs degraded scores: 4.0 abstain on candlestick, 4.0 reject on structure | Code bugs fixed | 6.700 after fix (exceeds 6.5 threshold) | No — avg now passes |
| Natural positions opened: 0 | Code bugs + fixture | Code bugs fixed; fixture still lacks wick/volume for 14th approval | Code bugs fixed | Still 0 — fixture design is the last blocker | Yes — 1 approval short |

---

## Quantitative Before/After

### W-Bottom Fixture (`btc_w_bottom_long_v1`)

| Metric | Pre-Fix (Phase 6.2) | Post-Fix (Phase 6.2.5) |
|--------|---------------------|------------------------|
| `patterns_detected` | `[]` | `['bullish_engulfing']` |
| `primary_pattern` | `null` | `'bullish_engulfing'` |
| `pattern_at_structure` | `false` | `true` |
| `structure_quality` | `'none'` | `'weak'` |
| `higher_lows` | `false` | `true` |
| `higher_highs` | `false` | `false` |
| `trend_direction` | `'sideways'` | `'sideways'` |
| Best panel approvals | **12/20** | **13/20** |
| Best panel avg score | **6.350** | **6.700** |
| Panel avg ≥ 6.5? | No | **Yes** |
| Panel approvals ≥ 14? | No | No |
| Natural opens | 0 | 0 |

### M-Top Fixture (`btc_m_top_short_v1`)

| Metric | Pre-Fix | Post-Fix |
|--------|---------|---------|
| `patterns_detected` | `[]` | `['bullish_engulfing']` |
| `structure_quality` | `'none'` | `'weak'` |
| Best panel approvals | **12/20** | **13/20** |
| Best panel avg score | **6.350** | **6.700** |
| Natural opens | 0 | 0 |

### Triple-Touch Fixture (`btc_triple_touch_long_v1`)

| Metric | Pre-Fix | Post-Fix |
|--------|---------|---------|
| `patterns_detected` | `[]` | `['bullish_engulfing']` |
| `structure_quality` | `'none'` | `'none'` (correctly stays 'none' — equal lows) |
| `higher_lows` | `false` | `false` (equal dips, not higher) |
| Best panel approvals | **12/20** | **13/20** |
| Best panel avg score | **6.225** | **6.575** |
| Natural opens | 0 | 0 |

### Combined Across All 3 Fixtures

| Metric | Phase 6.2 | Phase 6.2.5 | Delta |
|--------|-----------|-------------|-------|
| Max approval count | 12 | **13** | +1 |
| Max avg score | 6.350 | **6.700** | +0.350 |
| Avg score ≥ 6.5 anywhere | No | **Yes** | Fixed |
| Any natural opens | 0 | 0 | — |
| Pattern in every structural proposal | No | **Yes** | Fixed |

---

## Panel Score Driver Analysis (Post-Fix, Best Proposal)

### 13 Approvers (post-fix)

| Score | Changed from pre-fix? | Reason |
|-------|----------------------|--------|
| 10.0 | ✅ Was 4.0 abstain | Candlestick 'bullish_engulfing' at structural level |
| 10.0 | ✅ Was 9.0 approve | Confluence improved (now 5 signals) |
| 9.0  | — stable | BTC macro bull regime |
| 8.0  | — stable | EMA full_bull + ADX 35 |
| 8.0  | — stable | RSI 54.7 rising |
| 8.0  | — stable | Execution quality A-grade |
| 7.0  | — stable | R:R = 2.0 |
| 7.0  | — stable | Normal volatility |
| 7.0  | — stable | Chart target viable |
| 7.0  | — stable | Structural entry timing |
| 7.0  | — stable | Leverage 3x moderate |
| 7.0  | — stable | Pullback-to-support context |
| 6.5  | ✅ Was 4.0 reject | "weak quality level" (was "none") |

### 4 Abstainers (post-fix, previously 5)

| Score | Reason | Addressable? |
|-------|--------|-------------|
| 5.5 | No wick rejection present | Fixture: add lower wick on engulfing bar |
| 5.5 | Stop/R:R threshold evaluator | Not easily addressable |
| 5.0 | Volume 1.03 not high enough | Fixture: volume_ratio ≥ 1.5 on entry bar |
| 5.0 | Chart pattern not active | Architectural — ChartPatternGroup excluded |

### 3 Rejecters (unchanged from pre-fix)

| Score | Reason | Addressable? |
|-------|--------|-------------|
| 3.0 | RSI 54.7 not oversold | Fixture: RSI 40–45 on entry bar |
| 4.0 | Structural skepticism | Fixture: structure_quality='moderate' |
| 4.5 | BB squeeze + volume | Fixture: wider BB + higher volume |

---

## Conclusion

The Phase 6.2 conclusion that "only fixture design is blocking" was wrong. Two runtime integration defects were real, measurable, and together caused a 4.0 abstainer and a 4.0 rejecter to score low based on incorrect/absent data in the setup packet.

After repair:
- Both evaluators improved: one from 4.0 abstain → 10.0 approve, one from 4.0 reject → 6.5 approve
- Net gain: +1 approval, +0.350 avg score
- The avg score threshold (6.5) is now met
- The approval count threshold (14/20) requires 1 more approval from fixture improvements

**The correct Phase 6.2.5 answer:** Fixture design AND runtime integration defects were both blocking. Runtime defects are now fixed. Fixture design is the sole remaining blocker (-1 approval).
