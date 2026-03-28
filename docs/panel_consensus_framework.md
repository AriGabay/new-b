# Panel Consensus Framework

**Phase:** 4 Learning Layer
**Date:** 2026-03-28

---

## Panel Structure

20 trader evaluators vote on each setup. Panel result:

| Metric | Description |
|---|---|
| `approve_count` | Number of "approve" votes (max 20) |
| `reject_count` | Number of "reject" votes |
| `abstain_count` | Number of "abstain" votes |
| `avg_score` | Mean score across all 20 evaluators |
| `weighted_score` | Confidence-weighted mean score |
| `panel_recommendation` | "enter" or "hold" |

### Enter Threshold
```
panel_recommendation = "enter" IF:
  approve_count >= 14 (14/20)
  AND avg_score >= 6.5
```

Both conditions must be met. Any safety rail in FinalDecisionGroup
can still block a panel "enter".

---

## Panel Calibration Metrics

### Enter Win Rate
Of all setups where panel said "enter", what fraction became wins?

Requires: 30+ samples with outcome data.

### High Disagreement Signal
When `reject_count >= 8`, does the loss rate increase?

Expected behavior: High disagreement → worse outcomes.
If high-disagreement entries win at equal rate, the reject
signals are not informative.

### Score Discrimination
Does higher `avg_score` predict wins vs losses?

---

## Current Status

The panel is architecturally complete (traders/panel.py).
The 20 evaluator implementations are complete (traders/evaluators.py).
The panel is NOT yet wired into the main runtime loop (Phase 4 integration task).

Until wired, `panel_summaries` table will have zero rows.

---

## Disagreement Interpretation

High reject counts (8+/20) are a warning signal, not an automatic block.
The FinalDecisionGroup has an explicit safety rail for this:
  `reject_count > 12` → block (6-rail enforcement)

Disagreement in the 8–12 range is tracked for learning purposes.
