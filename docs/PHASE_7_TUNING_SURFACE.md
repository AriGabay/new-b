# PHASE 7 TUNING SURFACE
**Date:** 2026-03-29

---

## PARAMETER MATRIX

| Parameter | Current Value | Safe to Tune Now? | Evidence Source | Overfitting Risk | Guardrail | Owner Layer | Notes |
|-----------|--------------|-------------------|----------------|-----------------|-----------|-------------|-------|
| **Panel: APPROVE_THRESHOLD** | 14/20 | NO — insufficient outcome data | fixture replay + outcome attribution | HIGH | Must keep V1 at hold, V3 at enter | TraderEvaluatorPanel | 34 trades all losses; lowering would increase losses |
| **Panel: AVG_SCORE_THRESHOLD** | 6.5 | NO — insufficient outcome data | fixture replay + outcome attribution | HIGH | V2 at 6.850, V3 at 7.325 — small margin | TraderEvaluatorPanel | 13/20 fixtures have avg 6.5-6.7; change would flip many |
| **Entry: candlestick_weight** | 0.25 | YES with care | fixture replay | MEDIUM | Must update ACTIVE_COMPOSITE_WEIGHT_SUM | EntryGroup | |
| **Entry: indicator_weight** | 0.20 | YES with care | fixture replay | MEDIUM | Must update ACTIVE_COMPOSITE_WEIGHT_SUM | EntryGroup | |
| **Entry: structural_weight** | 0.10 | YES with care | fixture replay | MEDIUM | Must update ACTIVE_COMPOSITE_WEIGHT_SUM | EntryGroup | |
| **Entry: ACTIVE_COMPOSITE_WEIGHT_SUM** | 0.55 | MUST match weight sum | N/A | N/A | Must equal sum of active weights | EntryGroup | |
| **Entry: COMPOSITE_SCORE_THRESHOLD** | 0.50 | YES with care | fixture replay | MEDIUM | Must re-run all fixtures | EntryGroup | Lowering increases candidate rate; raising decreases |
| **Entry: chart_pattern_weight** | 0.35 (inactive) | NOT YET | — | — | ChartPatternGroup must emit GroupSignalEvent first | EntryGroup | Currently 0.0 always because no GroupSignalEvent |
| **Entry: historian_weight** | 0.10 (inactive) | NOT YET | — | — | HistorianAgent not wired | EntryGroup | |
| **Safety: min_avg_score** | 5.0 | YES | fixture replay | LOW | Never remove entirely | FinalDecisionGroup | |
| **Safety: max_reject_count** | 12 | YES | fixture replay | LOW | Never remove entirely | FinalDecisionGroup | |
| **Safety: min_r_r_ratio** | 1.5 | YES | fixture replay | MEDIUM | Never below 1.0 | FinalDecisionGroup | |
| **Safety: high_vol_approve_count** | 16 | YES | fixture replay | LOW | Only matters in high_vol regime | FinalDecisionGroup | |
| **Risk: DEFAULT_RISK_FRACTION** | 0.01 (1%) | YES | paper simulation | LOW | Range 0.005-0.02 | RiskLeverageGroup | |
| **Risk: MAX_SINGLE_POSITION** | 0.10 (10%) | YES | paper simulation | LOW | Range 0.05-0.15 | RiskLeverageGroup | |
| **Risk: DAILY_LOSS_LIMIT** | -0.02 (-2%) | TIGHTEN ONLY | paper simulation | LOW | Never loosen without justification | RiskLeverageGroup | |
| **Risk: MAX_DRAWDOWN_HALT** | 0.10 (10%) | TIGHTEN ONLY | paper simulation | LOW | Never loosen without justification | RiskLeverageGroup | |
| **Risk: PUMP_VOLUME_RATIO** | 5.0 | YES | fixture replay | LOW | Range 3.0-7.0 | RiskLeverageGroup | |
| **Exit: time_stop_bars** | 20 bars (20 hours on 1h) | YES | fixture replay + outcomes | LOW | Range 15-30 bars (15-30 hours on 1h) | ExitGroup | |
| **Exit: trailing_ATR_mult** | 2.0 | YES | fixture replay + outcomes | MEDIUM | Range 1.5-3.0 | ExitGroup | |
| **Exit: trailing_activation** | +1R | YES | fixture replay + outcomes | MEDIUM | Range +0.5R to +2R | ExitGroup | |
| **Evaluator scoring logic** | varies per evaluator | NOT YET — need calibration data | outcome attribution with trader_calibration | HIGH | Min 50 outcomes per evaluator before changes | evaluators.py | trader_calibration now working but empty |
| **Evaluator vote thresholds** | 7.0=approve, 5.0=abstain | NOT YET | outcome attribution | HIGH | Would change approval ceiling | evaluators.py | |
| **Fixture regime balance** | 11 fixtures, LONG-biased | YES | fixture design | LOW | Must represent realistic market conditions | fixtures | Need SHORT, ranging, bear fixtures |

---

## WHAT IS NOT SAFE TO TUNE YET

1. **APPROVE_THRESHOLD and AVG_SCORE_THRESHOLD**: All 34 existing outcomes are losses.
   Loosening thresholds would increase the number of losing trades without evidence that
   the currently-rejected fixtures represent better setups.

2. **Per-evaluator scoring logic**: trader_calibration was broken until this session.
   No per-evaluator outcome data exists yet. Must accumulate 50+ trades with the fixed
   calibration pipeline before making data-driven evaluator changes.

3. **Evaluator vote thresholds** (7.0 approve / 5.0 abstain): Changing these would
   alter the approval ceiling for every fixture simultaneously. Not safe without
   comprehensive outcome data.

4. **chart_pattern_weight and historian_weight in EntryGroup**: These are inactive
   because the underlying data sources don't emit GroupSignalEvent. Activating them
   requires architecture changes, not just weight tuning.

---

## RECOMMENDED FIRST TUNING TARGETS (Future Sessions)

1. **Exit parameters** — highest impact with lowest regression risk:
   - trailing_ATR_mult (currently 2.0): all 34 trades are stop_loss exits at avg -0.184R.
     A tighter trailing stop or earlier activation might reduce loss magnitude.
   - time_stop_bars (currently 20): may be too long, allowing positions to drift to stop.

2. **Entry weights** — moderate impact:
   - The current 0.25/0.20/0.10 split is Phase 3 vintage. With structural/candlestick
     data quality now verified, a rebalance may be warranted.
   - Must update ACTIVE_COMPOSITE_WEIGHT_SUM after any change.

3. **Fixture expansion** — no regression risk:
   - Add SHORT setup fixtures
   - Add ranging-market fixtures where entry SHOULD be blocked
   - Add bear-market fixtures
