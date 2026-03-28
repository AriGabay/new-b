# Learning Logic

**Phase:** 4 Learning Layer
**Date:** 2026-03-28

---

## 12 Learning Objectives

1. **Trader evaluation quality** — does each trader's votes predict winning trades?
2. **Trader calibration** — are confidence scores well-calibrated (Brier score)?
3. **Trader overconfidence** — do high-confidence traders fail disproportionately?
4. **Panel consensus quality** — does "enter" recommendation → win at acceptable rate?
5. **Panel disagreement signal** — does high reject_count predict failures?
6. **Setup-family performance** — which signal families have positive expectancy?
7. **Specialist-group contribution** — which groups' signals correlate with wins?
8. **Error taxonomy** — what categories of errors dominate?
9. **Regime sensitivity** — does performance vary by btc_macro regime?
10. **Exit quality** — which exit reasons produce best R-multiples?
11. **Score threshold calibration** — is composite_score >= 0.50 the right gate?
12. **Time in market** — what is the optimal hold period (bars_held) by setup family?

---

## How Learning Works

Learning in this system is **observational and advisory**. The system never
automatically changes parameters or thresholds. All learning outputs are
recommendations that require human review before application.

### Step 1: Decision Trace Logging
Every setup that reaches the panel is fully archived:
- `DecisionTraceLogger.log_setup_packet()` → `setup_packets` table
- `DecisionTraceLogger.log_trader_reviews()` → `trader_reviews` table
- `DecisionTraceLogger.log_panel_summary()` → `panel_summaries` table
- `DecisionTraceLogger.log_final_decision()` → `final_decisions` table

### Step 2: Outcome Attribution
When a trade closes, `OutcomeAttributor.process_closed_trade()`:
1. Writes `outcome_attributions` record linking trade → decision trace
2. Updates `trader_calibration` for all traders who reviewed this setup
3. Updates `setup_family_records` for the trade's setup family
4. Updates `specialist_group_records` for all contributing groups
5. Classifies the error type (losses only) via `ErrorTaxonomy`

### Step 3: Report Generation
`LearningReportGenerator.generate_full_report()` queries all tables and
produces a `LearningReport` with all 8 sections. Reports are observations;
they do not trigger actions.

### Step 4: Recommendation Generation
`RecommendationEngine.generate_all_recommendations()` scans calibration
records and emits advisory `LearningRecommendation` objects. Minimum 30
samples required for any recommendation.

---

## What the System Does NOT Do

- Does NOT automatically adjust trader weights.
- Does NOT automatically disable setup families.
- Does NOT automatically change risk parameters.
- Does NOT draw conclusions from < 30 samples.
- Does NOT mix outcomes from different `OutcomeSource` values.
- Does NOT use LLM output for risk decisions (ADR-003).

---

## Error Taxonomy Categories

| Code | Category | Description |
|---|---|---|
| A | entry_timing | Entered too early/late; slow bleed to stop |
| B | stop_placement | Stop hit within 3 bars (noise) |
| C | target_too_far | Time stop after 18+ bars; target never reached |
| D | regime_mismatch | LONG in confirmed bear regime |
| E | signal_quality | Low composite_score (< 0.55) on entry |
| F | execution | Slippage or order placement errors |
| G | unknown | Insufficient data to classify |

Category classification is heuristic. Manual review is required before
drawing conclusions from error taxonomy data.
