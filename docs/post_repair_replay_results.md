# Post-Repair Replay Results

**Date:** 2026-03-28
**Phase:** 5.75
**Source tag:** `event_driven_runtime_replay`

---

## Summary

After applying the Phase 5.75 normalization repair to `EntryGroup._compute_composite_score()`, the three BTC replay fixtures were run against the full `BtcBybitPaperRunner` pipeline. Results were collected from real runtime event subscriptions.

---

## Fixture Results

### btc_bull_breakout_v1 (350 bars)

**Fixture description:** Bullish trend with EMA20/50 golden cross around bar 238, preceded by a death cross at bar 29.

| Metric | Value |
|--------|-------|
| Bars processed | 350 |
| EMA crossovers in fixture | 2 |
| CandidateTradeEvents fired | **2** |
| Positions opened | 0 |
| Positions closed | 0 |
| Errors | 0 |

**Candidate details:**

| # | Direction | raw_score | active_weight_sum | composite_score |
|---|-----------|-----------|-------------------|----------------|
| 1 | SHORT | 0.3975 | 0.55 | **0.7227** |
| 2 | SHORT | 0.3950 | 0.55 | **0.7182** |

Both candidates exceeded the 0.50 threshold. Panel evaluation occurred (Layer B). No position was opened — panel rejected both proposals.

---

### btc_bear_breakdown_v1 (350 bars)

**Fixture description:** Bearish breakdown with golden cross at bar 28 (early false bull signal), death cross at bar 244 confirming the bear trend.

| Metric | Value |
|--------|-------|
| Bars processed | 350 |
| EMA crossovers in fixture | 2 |
| CandidateTradeEvents fired | **2** |
| Positions opened | 0 |
| Positions closed | 0 |
| Errors | 0 |

**Candidate details:**

| # | Direction | raw_score | active_weight_sum | composite_score |
|---|-----------|-----------|-------------------|----------------|
| 1 | SHORT | 0.3950 | 0.55 | **0.7182** |
| 2 | LONG | 0.2975 | 0.55 | **0.5409** |

Both candidates exceeded the 0.50 threshold. Candidate #2 (LONG) is a marginal case with score 0.5409. Panel evaluation occurred. No positions opened.

---

### btc_ranging_v1 (200 bars)

**Fixture description:** Ranging/oscillating market with 9 EMA crossovers. Low ADX (15–39), frequent direction changes.

| Metric | Value |
|--------|-------|
| Bars processed | 200 |
| EMA crossovers in fixture | 9 |
| CandidateTradeEvents fired | **4** |
| Positions opened | 0 |
| Positions closed | 0 |
| Errors | 0 |

**Candidate details:**

| # | Direction | raw_score | active_weight_sum | composite_score |
|---|-----------|-----------|-------------------|----------------|
| 1 | SHORT | 0.3975 | 0.55 | **0.7227** |
| 2 | SHORT | 0.3950 | 0.55 | **0.7182** |
| 3 | SHORT | 0.2975 | 0.55 | **0.5409** |
| 4 | SHORT | 0.3950 | 0.55 | **0.7182** |

4 out of 9 EMA crossovers produced candidates. 5 crossovers did not produce candidates — their signal bundles did not satisfy the confirmation gate (insufficient supporting signals). This demonstrates the gate functions as a filter.

---

## Totals Across All Fixtures

| Metric | btc_bull | btc_bear | btc_ranging | **TOTAL** |
|--------|----------|----------|-------------|-----------|
| Bars | 350 | 350 | 200 | **900** |
| Crossovers | 2 | 2 | 9 | **13** |
| Candidates | 2 | 2 | 4 | **8** |
| Positions opened | 0 | 0 | 0 | **0** |
| Positions closed | 0 | 0 | 0 | **0** |
| Errors | 0 | 0 | 0 | **0** |

Source tag: `event_driven_runtime_replay`

---

## Comparison: Before vs After Repair

| Metric | Phase 5.5 (Before) | Phase 5.75 (After) |
|--------|-------------------|--------------------|
| composite_score ceiling | **0.4875** | **0.8864** |
| CandidateTradeEvents (900 bars) | **0** | **8** |
| Positions opened | 0 | 0 |
| Reason for zero positions | Ceiling blocked Layer A | Panel rejected (Layer B) |

The normalization repair successfully unblocked Layer A (EntryGroup). The structural barrier has shifted from Layer A (score ceiling) to Layer B (panel selectivity).

---

## Score Distribution

All 8 candidates:

```
0.5409  ████████████████████████████  (×2)
0.7182  ████████████████████████████████████████  (×4)
0.7227  ████████████████████████████████████████  (×2)
```

Range: [0.5409, 0.7227]
Threshold: 0.50

All 8 candidates cleared the threshold. The minimum margin above threshold: **0.0409** (0.5409 - 0.50).

---

## Why Positions Are Still Zero

After the normalization repair, CandidateTradeEvents fire and reach the TraderEvaluatorPanel (Layer B). The panel evaluates each proposal using its 20-trader voting system.

Phase 3 proposals are rejected because:

1. **Below avg_score floor.** Panel requires `avg_score ≥ 6.5`. Phase 3 proposals score approximately 5.9 average because `critic_report = None` and `historian_analog = None`. Several traders downgrade proposals with missing analyst context.

2. **Below approval count floor.** Panel requires `approvals ≥ 14/20`. Phase 3 proposals receive approximately 9/20 approvals. Traders in the 4.5–6.5 abstain zone (approximately 7/20) neither approve nor reject — and in a tied decision they implicitly deny by not approving.

**This is documented, not hidden.** The panel's selectivity is real. It cannot be bypassed without providing the missing Phase 4+ context (CriticAgent, HistorianAgent).

---

## What This Phase Does NOT Claim

- **Zero positions** is not a Phase 5.75 failure. The phase fixed Layer A. Layer B is a genuine second barrier.
- **8 candidates** are real events from a real pipeline run — not injected or forced.
- **Scores are not inflated.** The normalization repair reflects the correct scale for 3 active groups; it does not fabricate signal quality.
- **Panel constants were not lowered.** `APPROVE_THRESHOLD = 14` and `MIN_AVG_SCORE = 6.5` are unchanged.

---

## Source Separation

All results from this run carry tag `event_driven_runtime_replay`.
- This tag is in `EDGE_EVIDENCE_SOURCES`
- This tag is in `RUNTIME_SOURCES`
- No mixing with `simplified_backtest` or `synthetic_control_scenarios`

Phase 5.75 source audit: **PASS**
