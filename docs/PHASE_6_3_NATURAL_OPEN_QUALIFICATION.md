# Phase 6.3 — Natural Open Qualification

Source: phase_6_3_natural_open

## Objective

Phase 6.3 converts the W-bottom LONG fixture from a panel hold (13/20, rec=hold) to a panel approval (14/20, rec=enter) that triggers a real `PanelApprovedProposalEvent` through the unmodified runtime. No system policy, panel threshold, evaluator weighting, or risk rule was changed.

## Target Evaluator: VolumeProfileEvaluator

The Phase 6.2 W-bottom fixture (`btc_w_bottom_long_v1`) achieved 13/20 panel approvals. The gap to threshold (14/20) was exactly one vote. Of the four abstaining evaluators (VolumeProfile, PatternCompletion, DrawdownRisk, WickAnalysis), `VolumeProfileEvaluator` was the only one whose score could be raised by adjusting fixture price structure without requiring capabilities that are architecturally excluded (ChartPatternGroup) or impossible to satisfy without contradictory conditions.

### VolumeProfileEvaluator Scoring Logic

```
score = 5.0
if vol_ratio > 1.5:  score += 2.0
elif vol_ratio > 1.2: score += 1.0   # triggers at 1.227
elif vol_ratio < 0.8: score -= 2.0

if volume_character == "surge":     score += 3.0
elif volume_character == "above_avg": score += 1.0  # triggers at 1.227
elif volume_character == "below_avg": score -= 2.0
```

`IndicatorsGroup` sets `volume_character = "above_avg"` when `vol_ratio > 1.2`. A `vol_ratio` of 1.227 crosses both thresholds simultaneously:

- `vol_ratio > 1.2` → `+1.0`
- `volume_character = "above_avg"` → `+1.0`
- total: `5.0 + 1.0 + 1.0 = 7.0` → approve

## Method: Increasing Entry Bar Body to 800 BTC

Volume in the fixture is generated deterministically from price movement via:

```
move_pct = body / open
vol_mult  = 1.0 + move_pct * 20 + noise(seed=621)
vol       = max(volume_base * vol_mult, volume_base * 0.5)
```

With `volume_base = 1200.0` and `seed=621`, the noise term at bar+19 is approximately `+0.027`. For `vol_ratio` to exceed 1.2, the `vol_mult` at bar+19 must exceed the 20-bar rolling average volume multiplier by more than 20%.

The v1 entry bar had `body = 300` (open=70300, close=70400) → `move_pct ≈ 0.00428` → `vol_mult ≈ 1.086`. With 3 extra consolidation bars replacing the flat continuation, the rolling SMA-20 volume drops toward baseline, and the entry bar body was raised to `800` (open=69700, close=70500):

```
move_pct = 800 / 69700 = 0.01148
vol_mult  ≈ 1.0 + 0.01148 × 20 + 0.027 = 1.257
vol_ratio = vol_mult / (SMA20 of vol_mult) ≈ 1.227 > 1.2 ✓
```

## Three Consolidation Bars

Three flat consolidation bars (closes: 70500, 70300, 70100) were inserted after DIP2 confirmation (bar+14) and before the bearish setup bar. Their purpose:

1. Keep SMA-20 volume denominator near `volume_base × 1.0` (low-body bars produce `vol_mult ≈ 1.0`).
2. Allow EMA20 to drift toward the 70,000–70,200 range without rising too fast.
3. Provide separation between the DIP2 confirmation and the engulfing entry to avoid triggering the 1-bar lag issue at the wrong structural bundle.

Without these bars, the entry bar body increase alone produces `vol_ratio ≈ 1.18` — just below threshold. The consolidation bars lower the rolling baseline enough to push the ratio above 1.2.

## 1-Bar Structural Cache Lag

`PanelDecisionGroup` reads the structural bundle from a cache populated by `TechnicalStructureGroup`. `CandlestickGroup`'s subscription fires first (subscription order), so when the panel evaluates a proposal at bar N, the structural cache still holds bar N-1's bundle.

This means:

- **bar+18** (bearish setup, close=69700): structural bundle written to cache.
- **bar+19** (entry, close=70500): panel reads bar+18's bundle → `at_support=True`.

Bar+18's close (69700) is just 29.8 above the merged support level (69670.2), well within ATR, so `at_support=True` is confirmed in that bundle. Without this design, the panel would read bar+17's bundle (close=70100, distance=430 from support — still within ATR, so `at_support` would also be True in v2, but the precise close=69700 ensures there is no ambiguity).

## V2 Fixture Bar Layout (bars +15 to +19)

| Bar  | Close  | Open   | Body | Role                              |
|------|--------|--------|------|-----------------------------------|
| +15  | 70500  | 70300  | 200  | Consolidation 1                   |
| +16  | 70300  | 70500  | 200  | Consolidation 2                   |
| +17  | 70100  | 70300  | 200  | Consolidation 3                   |
| +18  | 69700  | 70100  | 400  | Bearish setup; at_support=True    |
| +19  | 70500  | 69700  | 800  | Entry: engulfing, vol_ratio=1.227 |

## Result

- Fixture: `btc_w_bottom_long_v2` (260 bars: 200 warmup + 30 bull + 20 W-bottom + 10 continuation)
- Panel result: 14/20 approve, avg=6.850, rec=enter
- `PanelApprovedProposalEvent` fires: 1 event
- Entry price: 70500.0 LONG BTCUSDT
- Composite score: 0.8545
- No system policy, threshold, or evaluator code was modified
