# Phase 6.3 Handoff

Source: phase_6_3_natural_open

## What Was Done in Phase 6.3

Phase 6.3 achieved the first natural panel approval (14/20, rec=enter) and corresponding `PanelApprovedProposalEvent` for a W-bottom LONG trade in the BTC/Bybit paper trading system. The approach was fixture engineering only — no system code was modified.

### Root Cause Resolved

Phase 6.2 identified that the W-bottom fixture produced 13/20 panel approvals — one short of threshold. Phase 6.3 diagnosed the root cause as insufficient volume on the entry bar (`vol_ratio ≈ 1.05`), preventing `VolumeProfileEvaluator` from scoring above the abstain threshold.

The entry bar body was raised from 300 to 800 (open=69700, close=70500) and three consolidation bars were inserted to keep the rolling volume baseline at the minimum level. This pushed `vol_ratio` to 1.227, triggering both the `> 1.2` score bonus and the `above_avg` character bonus in `VolumeProfileEvaluator`.

### Key Insight: 1-Bar Structural Cache Lag

`PanelDecisionGroup` reads the structural bundle from bar N-1 when evaluating bar N's proposal, due to subscription ordering in `BtcBybitPaperRunner`. The v2 fixture was designed so that bar+18 (bearish setup, close=69700) writes `at_support=True` to the structural cache, which bar+19's panel evaluation reads. This preserved `at_support=True` for the panel while using bar+19 as the high-volume engulfing entry.

## Files Created

### Documentation

| File                                                        | Purpose                                              |
|-------------------------------------------------------------|------------------------------------------------------|
| `docs/PHASE_6_3_NATURAL_OPEN_QUALIFICATION.md`             | Design rationale and method overview                 |
| `docs/final_approval_gap_analysis.md`                      | Why v1 was stuck at 13/20; evaluator-by-evaluator    |
| `docs/improved_fixture_design_report.md`                   | Exact OHLCV values, vol_ratio derivation, lag design |
| `docs/panel_vote_shift_report.md`                          | V1 vs V2 full 20-evaluator comparison table          |
| `docs/natural_open_proof_or_failure_report.md`             | Event proof, proposal details, policy confirmation   |
| `docs/PHASE_6_3_HANDOFF.md`                                | This document                                        |

### Fixture

The `btc_w_bottom_long_v2` fixture was added to:

- `/Users/arigabay/Code/new-b/src/validation/fixtures/btc_structure_fixture.py`
  - `_generate_w_bottom_long_v2_prices()`
  - `get_w_bottom_long_v2_fixture()`
  - `get_all_phase63_fixtures()`

### Tests

- `/Users/arigabay/Code/new-b/src/tests/test_phase_6_3_natural_open.py`

## Files Modified

No production system files were modified. Only the fixture file was extended with a new fixture function.

## Phase 6.3 Results

| Metric                           | V1                | V2                |
|----------------------------------|-------------------|-------------------|
| Fixture name                     | btc_w_bottom_long_v1 | btc_w_bottom_long_v2 |
| Bar count                        | 257               | 260               |
| Entry bar index                  | 246               | 249               |
| Panel approve count              | 13                | 14                |
| Panel avg score                  | 6.700             | 6.850             |
| Panel recommendation             | hold              | enter             |
| PanelApprovedProposalEvent count | 0                 | 1                 |
| Entry price                      | —                 | 70500.0 LONG      |
| Composite score                  | 0.8364            | 0.8545            |

## What the Remaining Abstainers Need

### PatternCompletion (score 5.0)

Requires `ChartPatternGroup` to be re-enabled and producing completed chart pattern signals (e.g., cup-and-handle completion, inverse head-and-shoulders). `ChartPatternGroup` is currently excluded from the active runtime (`NotImplementedError` stub). Re-enabling it is a multi-phase effort:

1. Implement pattern recognition algorithms in `ChartPatternGroup`.
2. Wire `ChartPatternGroup` into `BtcBybitPaperRunner._create_groups()`.
3. Verify that `PatternCompletionEvaluator` receives and correctly interprets the pattern signals.
4. Engineer fixture bars that complete a recognizable chart pattern at the entry point.

Addressing this would move `PatternCompletion` from 5.0 to potentially 7.0–9.0, raising the potential panel ceiling from 14/20 to 15/20.

### WickAnalysis (score 5.5)

Requires the entry bar to exhibit a hammer-type candlestick pattern: bullish close with lower shadow comprising at least 60% of the total candle range. The v2 entry bar is a bullish engulfing (body=800, minimal wicks) — this is the opposite of a hammer shape.

To satisfy `WickAnalysisEvaluator`:
- The entry bar should have close near the top of its range.
- Lower shadow / candle_range > 0.6.
- This means `low[i] << open[i]` before a strong close — a dip-and-recover pattern within one bar.

This is achievable through fixture design, but it conflicts with the body=800 engulfing requirement (a hammer has a small body, not a large engulfing body). These two conditions cannot be simultaneously optimized without a redesign of the entry structure. One approach: place the hammer at the bar before the engulfing bar, then let `WickAnalysis` score the structural context rather than the entry bar itself.

### DrawdownRisk (score 5.5)

Requires either:
1. A tighter stop loss (smaller risk distance per unit). The current stop is below 69,670 (support level), giving a risk distance of ~830 points from the 70,500 entry.
2. A different account configuration that changes the risk-to-account-balance ratio.

Option 1 would require placing a stop inside the support zone, which conflicts with the structural trading rationale. Option 2 is a runtime configuration change, which is out of scope for fixture-only engineering.

The most viable path: accept DrawdownRisk as a structural abstainer for W-bottom entries (tight stops at support naturally produce this score profile) and focus on other evaluators for reaching 15/20 or higher.

## Next Steps

Recommended Phase 6.4 actions, in priority order:

1. **Re-enable ChartPatternGroup** — implement the minimum viable pattern recognizer (at least cup-and-handle and inverse H&S) and engineer a fixture that produces a completed pattern at the W-bottom recovery. This addresses `PatternCompletion` (5.0 → 7.0+) and potentially `Breakout` (5.5 → 7.0+) for a total gain of +2 approvals → 16/20.

2. **WickAnalysis hammer fixture** — design a v3 fixture that inserts a hammer bar at bar+18 (close near high, long lower shadow) and uses bar+19 as the entry with moderate body. This requires verifying that `WickAnalysis` evaluates structural context (prior bars) rather than only the entry bar. If so, the hammer at bar+18 suffices.

3. **Document MeanReversion ceiling** — `MeanReversionEvaluator` will always reject W-bottom recovery entries by design. Add a note to the evaluator's documentation that this is expected behavior and does not represent a fixable gap.

4. **Contrary evaluator behavior** — as approve_count rises above 14, `ContraryEvaluator`'s score may continue to decrease. Monitor whether increasing consensus from 14 to 16 causes Contrary to drop below 4.0 (into a stronger reject), which would partially offset gains.

## Policy Confirmation

Phase 6.3 did not change:
- Panel approval thresholds (14/20, avg ≥ 6.5)
- Any evaluator scoring logic or weights
- `BtcBybitPaperRunner` configuration
- Risk gate rules
- Entry group composite score threshold (0.50)
- Any event bus wiring

The natural open was earned entirely through fixture market data design.
