# Panel Behavior Report

**Source:** `event_driven_runtime_simulation`
**Date:** 2026-03-28
**Scenarios:** 10 labelled BTCSetupPackets (synthetic)
**Evaluators:** 20 real TraderEvaluatorPanel traders (no forced approvals)

---

## ⚠️ Sample Size Warning

**10/30 minimum.** Panel behavior analysis is indicative only, not statistically reliable.
These results describe threshold behaviour on 10 constructed scenarios, not real market performance.

---

## Overall Results

| Metric | Value |
|--------|-------|
| Total evaluations | 10 |
| Enter rate | **30.0%** (3/10) |
| Hold rate | **70.0%** (7/10) |
| Production threshold | 14/20 approve + avg_score ≥ 6.5 |

The 30% enter rate on this scenario set is consistent with a selective threshold.
It is NOT a market-edge win rate — it is a filtering rate on constructed scenarios.

---

## Per-Scenario Results

| # | Scenario | approve/20 | avg_score | Decision | Safety Rails Triggered |
|---|----------|-----------|-----------|----------|------------------------|
| s01 | Ideal Bull LONG | 14/20 | 7.2 | **enter** | none |
| s02 | Ideal Bear SHORT | 14/20 | 7.2 | **enter** | none |
| s03 | Bear Macro LONG | 14/20 | 6.5 | hold | `long trade in bear regime blocked` |
| s04 | Poor R:R LONG (1.2) | 11/20 | 6.5 | hold | `R:R 1.20 < 1.5` |
| s05 | High Vol Moderate | 13/20 | 7.0 | hold | `high volatility requires 16 approves (got 13)` |
| s06 | Ranging / Weak | 4/20 | 4.5 | hold | `avg_score 4.5 < 5.0` |
| s07 | Mean Reversion | 12/20 | 6.6 | hold | none (below approve threshold) |
| s08 | Overbought RSI82 | 7/20 | 5.4 | hold | `high volatility requires 16 approves (got 7)` |
| s09 | Excellent R:R (3.2) | 15/20 | 7.6 | **enter** | none |
| s10 | Invalid Setup Quality | 2/20 | 3.8 | hold | `avg_score 3.8 < 5.0`, `setup_quality=invalid` |

---

## Approval Distribution

| approve_count | Scenarios |
|--------------|-----------|
| 2/20 | 1 (invalid quality) |
| 4/20 | 1 (ranging/weak) |
| 7/20 | 1 (overbought) |
| 11/20 | 1 (poor R:R) |
| 12/20 | 1 (mean reversion) |
| 13/20 | 1 (high vol) |
| **14/20** | **3** (bull LONG, bear SHORT, bear macro LONG) |
| **15/20** | **1** (excellent R:R) |

---

## Score Distribution

| Stat | Value |
|------|-------|
| count | 10 |
| mean | 6.213 |
| min | 3.775 |
| max | 7.565 |
| median | 6.545 |
| std | 1.195 |
| p25 | 5.36 |
| p75 | 7.213 |

---

## Safety Rail Frequencies

| Rail | Triggers | Scenario(s) |
|------|---------|-------------|
| Rail1: avg_score < 5.0 | 2 | s06 (Ranging), s10 (Invalid Quality) |
| Rail3: R:R < 1.5 | 1 | s04 (Poor R:R) |
| Rail4: invalid setup quality | 1 | s10 (Invalid Quality) |
| Rail5: bear regime + LONG | 1 | s03 (Bear Macro LONG) |
| Rail6: high vol + insufficient consensus | 2 | s05 (High Vol), s08 (Overbought) |
| **No rails triggered** | **4** | s01, s02, s07, s09 |

All 6 safety rails are present and fire on appropriate scenarios.

---

## Key Observations

### Panel consensus is genuinely selective
- Scenarios with approve_count=14 represent the minimum-pass threshold
- Three scenarios hit exactly 14: two ideal setups and one that passes panel but is blocked by Rail5
- One scenario (s07: Mean Reversion) passes individual score threshold (avg=6.6) but fails approval count (12/20)

### Safety rails catch what panel threshold misses
- s03 (Bear Macro LONG): Panel says enter (14/20, avg=6.5) but Rail5 correctly holds — demonstrating the independent safety rail layer adds value
- s05 (High Vol): Panel says 13/20 (close to threshold) but Rail6 escalates requirement to 16/20 in high-vol regimes

### Bottom of the distribution is clean
- s10 (Invalid Quality): 2/20 approvals — the lowest realistic scenario. Panel correctly identifies this as poor
- s06 (Ranging): 4/20 — no trader consensus on a directionless market

---

## Limitations

- 10 scenarios is below the 30-sample minimum for statistical conclusions
- Scenarios are constructed, not drawn from real market history
- Enter rate (30%) reflects scenario diversity, not live market performance
- Per-evaluator breakdown not shown here — see `per_evaluator_votes` in full report

---

## Production Threshold Assessment

The production threshold (14/20, avg≥6.5) sits at the **moderate-to-strict** boundary:
- Lenient alternatives (10-11/20) would accept 70% of these scenarios
- Production correctly filters out borderline setups (s07: 12 approves with OK score)
- The threshold is appropriately tight for a selective paper-trading system

No threshold changes are recommended from this data alone. Minimum 30 real closed trades required before any calibration decision.
