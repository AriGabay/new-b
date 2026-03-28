# Candlestick Packet Wiring Audit — Phase 6.2.5

**Date:** 2026-03-29

---

## Audit Question

Does the candlestick pattern detected by CandlestickGroup actually reach the `BTCSetupPacket` used by the panel evaluators?

**Answer: No — until Phase 6.2.5 repair.**

---

## Signal Flow (Pre-Fix)

```
Bar N arrives →
  CandlestickGroup._process_features(fv) →
    signals = [CandlestickSignal(signal_subtype='bullish_engulfing', ...)]
    GroupSignalBundle(signals=signals) published as GroupSignalEvent ←── EntryGroup listens ✓
    (No signals_cache populated)

  EntryGroup._collect_bundle(GroupSignalEvent) →
    candlestick_signals=[bullish_engulfing]
    composite_score = 0.8364 (includes candlestick weight 0.25) ✓
    CandidateTradeEvent published

  PanelDecisionGroup._on_candidate_trade(CandidateTradeEvent) →
    candlestick_signals = self._candlestick_signal_cache.get(symbol, [])
    # ↑ self._candlestick_signal_cache = {} (never populated) ← BUG
    # Result: candlestick_signals = []
    packet = build_btc_setup_packet(candlestick_signals=[]) →
      CandlestickSnapshot(patterns_detected=[], primary_pattern=None)
    Panel evaluates with empty candlestick context
```

The candlestick signal **correctly** reached EntryGroup (and influenced the composite score). It **failed** to reach PanelDecisionGroup.

---

## Root Cause Chain

### Step 1: CandlestickGroup has no signals cache

```python
# src/groups/candlestick/group.py (pre-fix)
def __init__(self, ...):
    self._feature_history:  dict[str, deque] = {}
    self._structural_cache: dict[str, StructuralLevelBundle] = {}
    self._tech_structure_group = None
    # NO _signals_cache
```

### Step 2: Runner._wire_caches() documented but not implemented

```python
# src/runtime/runner.py (pre-fix)
def _wire_caches(self) -> None:
    """
    ...
    PanelDecisionGroup needs:
    - FeatureVector cache (from MarketDataGroup)
    - StructuralLevelBundle cache (from TechnicalStructureGroup)
    - CandlestickSignal cache (from CandlestickGroup)  ← documented but not wired
    ...
    """
    self._panel_decision.set_feature_cache(...)      # ✓ wired
    self._panel_decision.set_structural_cache(...)   # ✓ wired
    # set_candlestick_signal_cache() ← NEVER CALLED  ✗
```

### Step 3: PanelDecisionGroup reads empty cache

```python
# src/groups/panel_decision/group.py
candlestick_signals = self._candlestick_signal_cache.get(symbol, [])
# = {}[symbol] = [] (always empty)
```

---

## Fix Applied

### `src/groups/candlestick/group.py`

Added `_signals_cache` attribute:
```python
def __init__(self, ...):
    ...
    self._signals_cache: dict[str, list] = {}  # populated each bar
```

Added cache write in `_process_features()`:
```python
# Store before publishing GroupSignalEvent
self._signals_cache[symbol] = list(signals)
```

### `src/runtime/runner.py`

Added the missing wire in `_wire_caches()`:
```python
self._panel_decision.set_candlestick_signal_cache(
    self._candlestick._signals_cache
)
```

---

## Verification

Post-fix journal packet (W-bottom bar 246):
```json
"candlestick": {
    "patterns_detected": ["bullish_engulfing"],
    "primary_pattern": "bullish_engulfing",
    "pattern_direction": "bullish",
    "pattern_at_structure": true,
    "raw_signals": [...]
}
```

Trader response (post-fix):
> "Candlestick 'bullish_engulfing' is at a structural level with matching direction" → **10.0 (approve)**

vs. pre-fix:
> "No candlestick signal to confirm or deny the trade" → 4.0 (abstain)

**Impact: +1 approval, +0.350 avg score**

---

## Is This the Only Candlestick Wiring Issue?

The `build_candlestick_snapshot()` function in `setup_packet_builder.py` extracts pattern names via:
```python
patterns = [getattr(s, "signal_subtype", "") for s in cs_signals if getattr(s, "signal_subtype", "")]
```

`CandlestickSignal` sets both `signal_subtype` and `pattern_name` to the same string (e.g., `"bullish_engulfing"`). The extraction is correct once `cs_signals` is non-empty.

The filter `isinstance(s, CandlestickSignal)` works correctly since the signals cache stores `CandlestickSignal` objects from `core.schemas`.

No other candlestick wiring issues were found.

---

## Confidence Level

**High.** The defect is unambiguous:
- `set_candlestick_signal_cache()` exists in PanelDecisionGroup (pre-fix)
- Runner docstring explicitly mentions this wire as needed
- CandlestickGroup had no cache to provide
- Journal packets always showed `patterns_detected=[]` in Phase 6.1 and Phase 6.2 (pre-fix)
- Post-fix packets correctly show `patterns_detected=['bullish_engulfing']`
