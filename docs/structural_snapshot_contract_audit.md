# Structural Snapshot Contract Audit — Phase 6.2.5

**Date:** 2026-03-29

---

## Audit Question

Does `TechnicalStructureGroup` correctly populate all fields that `build_structural_snapshot()` expects in `StructuralLevelBundle`? Specifically: `structure_quality`, `trend_direction`, `higher_highs`, `higher_lows`.

**Answer: No — until Phase 6.2.5 repair.**

---

## Contract Mismatch

### What `build_structural_snapshot()` expected

```python
# src/runtime/setup_packet_builder.py
structure_quality=getattr(structural_bundle, "structure_quality", "none"),
trend_direction=getattr(structural_bundle, "trend_direction", "sideways"),
higher_highs=getattr(structural_bundle, "higher_highs", False),
higher_lows=getattr(structural_bundle, "higher_lows", False),
```

### What `StructuralLevelBundle` provided (pre-fix)

```python
# src/core/schemas.py (pre-fix)
@dataclass
class StructuralLevelBundle:
    symbol:             str
    timeframe:          str
    timestamp:          datetime
    resistance_levels:  list[StructuralLevel] = field(default_factory=list)
    support_levels:     list[StructuralLevel] = field(default_factory=list)
    at_resistance:      bool = False
    at_support:         bool = False
    nearest_resistance: Optional[StructuralLevel] = None
    nearest_support:    Optional[StructuralLevel] = None
    # ← MISSING: structure_quality, trend_direction, higher_highs, higher_lows
```

`getattr(bundle, "structure_quality", "none")` returned `"none"` because the field didn't exist.  
Similarly for `trend_direction`, `higher_highs`, `higher_lows`.

---

## Dead Code: `_classify_trend()`

`TechnicalStructureGroup._classify_trend()` correctly computes the missing fields:

```python
def _classify_trend(self, bars, fv):
    """Determine higher_highs, higher_lows, trend_direction from recent bars."""
    recent = bars[-10:]
    mid = len(recent) // 2
    higher_highs = max(highs[mid:]) > max(highs[:mid])
    higher_lows  = min(lows[mid:]) > min(lows[:mid])

    ema_bull = fv.ema20 > fv.ema50
    ema_bear = fv.ema20 < fv.ema50

    if higher_highs and higher_lows and ema_bull:
        trend_direction = "uptrend"
    elif not higher_highs and not higher_lows and ema_bear:
        trend_direction = "downtrend"
    else:
        trend_direction = "sideways"

    return higher_highs, higher_lows, trend_direction
```

This method was fully implemented. However, it was **never called**. A `grep` confirms:

```
$ grep -n "_classify_trend" src/groups/technical_structure/group.py
12:  6.  _classify_trend        — determine HH/HL and trend direction  (docstring only)
315:    def _classify_trend(                                             (definition only)
```

No call site exists pre-fix. The method was dead code.

---

## Fix Applied

### `src/core/schemas.py`

Added missing fields to `StructuralLevelBundle`:
```python
# Trend structure fields — populated by TechnicalStructureGroup._classify_trend()
structure_quality:  str  = "none"     # "none" | "weak" | "moderate"
trend_direction:    str  = "sideways" # "uptrend" | "downtrend" | "sideways"
higher_highs:       bool = False
higher_lows:        bool = False
```

### `src/groups/technical_structure/group.py`

Updated `_build_structural_bundle()`:
- Added `bars: list` parameter
- Added call to `_classify_trend(bars, fv)`
- Added `structure_quality` derivation:
  - `"moderate"`: HH and HL both True, trend_direction established
  - `"weak"`: HH or HL True
  - `"none"`: neither HH nor HL

Updated `_process_features()` to pass `bars`:
```python
bundle = self._build_structural_bundle(
    symbol=symbol,
    timeframe=fv.timeframe,
    fv=fv,
    resistance=self._resistance_levels[symbol],
    support=self._support_levels[symbol],
    bars=bars,   # ← added
)
```

---

## Verification

Post-fix journal packet (W-bottom, bar 246):
```json
"structure": {
    "at_support": true,
    "structure_quality": "weak",
    "trend_direction": "sideways",
    "higher_highs": false,
    "higher_lows": true
}
```

**`higher_lows=true`** is correct for the W-bottom fixture:
- First W-bottom dip (bars ~230–233): close minimum ≈ 69,800
- Second W-bottom dip (bars ~237–240): close minimum ≈ 70,100 (higher than first dip)
- Last 10 bars before bar 246: second half low > first half low ✓

**`structure_quality='weak'`** is correct: `higher_lows=True but higher_highs=False` → one direction confirmed → "weak".

Pre-fix vs. post-fix for same bar 246 packet:

| Field | Pre-fix (default) | Post-fix (computed) | Correct? |
|-------|-------------------|---------------------|---------|
| `structure_quality` | `"none"` | `"weak"` | ✓ |
| `trend_direction` | `"sideways"` | `"sideways"` | ✓ (same, correctly so) |
| `higher_highs` | `false` | `false` | ✓ |
| `higher_lows` | `false` | `true` | ✓ (Fixed) |

Panel impact:
- Pre-fix: "structure quality 'none'" → reject 4.0
- Post-fix: "weak quality level providing solid reference point" → approve 6.5

---

## Structure Quality for Triple-Touch Fixture

The triple-touch fixture shows `structure_quality='none'` post-fix. This is **correct**:
- Triple touch creates equal lows (not higher lows)
- All three touches are at approximately the same price
- `higher_lows=False` → `structure_quality='none'`

This demonstrates the algorithm works correctly: W-bottom (two dips with second higher) → "weak"; triple-touch (three equal dips) → "none".

---

## What `trend_direction='sideways'` Means in This Context

Even after the fix, W-bottom shows `trend_direction='sideways'`. This is algorithmically correct:
- The W-bottom is a consolidation/reversal pattern, not an established uptrend
- `higher_highs=False` (the pullback at bar 246 doesn't make new highs vs bar 234–239 zone)
- Without higher_highs, the condition `higher_highs AND higher_lows AND ema_bull` is not met
- Therefore `trend_direction='sideways'`, not "uptrend"

The EMA alignment (full_bull) and the structural trend_direction (sideways) measure different things. The panel correctly sees both — and the tension between them causes some evaluators to score lower. This is accurate, not a bug.

A fixture with a clear HH/HL sequence before the entry bar would produce `trend_direction='uptrend'` and `structure_quality='moderate'`, potentially earning 1–2 more approvals.
