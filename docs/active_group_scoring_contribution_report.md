# Active Group Scoring Contribution Report

**Date:** 2026-03-28
**Phase:** 5.75

---

## Phase 3 Active Signal Groups

| Group | Weight | Status | Max Quality | Max Contribution to raw_score |
|-------|--------|--------|-------------|-------------------------------|
| ChartPatternGroup | 0.35 | **EXCLUDED** | 0.0 | 0.0 |
| CandlestickGroup | 0.25 | **Active** | 0.75 | 0.1875 |
| IndicatorsGroup | 0.20 | **Active** | 1.00 | 0.2000 |
| TechnicalStructureGroup | 0.10 | **Active** | 1.00 | 0.1000 |
| HistorianAgent | 0.10 | **EXCLUDED** | 0.0 | 0.0 |
| **TOTAL** | **1.00** | | | **0.4875** |

---

## Group Contributions in Phase 3

### CandlestickGroup (weight: 0.25)

**What it measures:** Quality of the most recent candlestick pattern. Each recognized pattern has a defined quality value.

| Pattern | Quality | Direction |
|---------|---------|-----------|
| Morning Star | 0.75 | LONG |
| Bullish Engulfing | 0.70 | LONG |
| Evening Star | 0.75 | SHORT |
| Bearish Engulfing | 0.70 | SHORT |
| Three Black Crows | 0.65 | SHORT |
| Inverted Hammer | 0.60 | LONG |
| Doji | 0.55 | Neutral |
| No pattern | 0.00 | None |

**Max contribution to raw_score:** `0.25 × 0.75 = 0.1875`

**Normalization contribution:** `0.1875 / 0.55 = 0.3409` (normalized ceiling from candlestick alone)

**Requirement for CandidateTradeEvent:** CandlestickGroup fires a `GroupSignalEvent` that is accumulated in EntryGroup's signal buffer. A minimum of 2 signals (confirmation gate) in the same direction is required before `_compute_composite_score` is called.

---

### IndicatorsGroup (weight: 0.20)

**What it measures:** Quality of technical indicator signals. Signal types include:

| Signal Type | Hypothesis | Trigger |
|------------|-----------|---------|
| EMA Crossover | H3-002 | ema20 crosses ema50 |
| RSI Signal | H3-001 | RSI out of extremes or confirming trend |
| MACD Signal | H3-003 | MACD crossover or divergence |
| BB Squeeze Breakout | H3-004 | Price breaks Bollinger Band squeeze |

**Max indicator_quality:** 1.0 (all signals aligned)

**Max contribution to raw_score:** `0.20 × 1.0 = 0.20`

**Normalization contribution:** `0.20 / 0.55 = 0.3636` (normalized ceiling from indicators alone)

---

### TechnicalStructureGroup (weight: 0.10)

**What it measures:** Quality of structural context — pivot levels, support/resistance zones, trend structure.

**What it outputs:** `structural_alignment` float in [0, 1].

- `1.0` — price at support (for LONG) or resistance (for SHORT) within 1×ATR14
- `0.5` — near but not at a structural level
- `0.0` — no relevant structural context

**Max contribution to raw_score:** `0.10 × 1.0 = 0.10`

**Normalization contribution:** `0.10 / 0.55 = 0.1818` (normalized ceiling from structure alone)

---

## Excluded Groups

### ChartPatternGroup (weight: 0.35, EXCLUDED in Phase 3)

**Would measure:** Multi-bar chart patterns — bull/bear flags, triangles, head-and-shoulders, wedges, cup-and-handle.

**Why excluded:** Not implemented. Phase 4 scope.

**Impact of exclusion (before repair):** `0.35` weight went to denominator but never to numerator → ceiling depressed by entire 0.35 weight.

**Impact of exclusion (after repair):** Normalization by active weight sum removes this penalty. The ceiling is now 0.8864 for the 3 active groups.

---

### HistorianAgent (weight: 0.10, EXCLUDED in Phase 3)

**Would measure:** Historical win rate of similar setups — extracted from past closed trades with matching structure/regime.

**Why excluded:** Requires closed trades to calibrate. Phase 3 has zero closed trades (no natural entries before this repair). Circular dependency: historian needs trades, but entries require historian for full composite_score.

**Impact of exclusion (before repair):** Same penalty as ChartPatternGroup — 0.10 weight to denominator but not numerator.

**Impact of exclusion (after repair):** Removed from active weight sum → no penalty.

---

## Normalized Weight Distribution (Phase 3)

After normalization, effective contribution ceiling per group:

| Group | Weight | Active Weight Sum | Normalized Weight |
|-------|--------|-------------------|------------------|
| CandlestickGroup | 0.25 | 0.55 | 0.25/0.55 = **45.5%** |
| IndicatorsGroup | 0.20 | 0.55 | 0.20/0.55 = **36.4%** |
| TechnicalStructureGroup | 0.10 | 0.55 | 0.10/0.55 = **18.2%** |
| **TOTAL** | 0.55 | — | **100.0%** |

This means in Phase 3, CandlestickGroup is the most influential single factor (45.5%), followed by IndicatorsGroup (36.4%) and structural context (18.2%).

---

## Observed Candidate Scores from Replay

8 CandidateTradeEvents fired across 900 bars after the repair.

Score breakdown for observed candidates:

| raw_score | active_weight_sum | normalized_score | Pattern implied |
|-----------|-------------------|-----------------|----------------|
| 0.3975 | 0.55 | 0.7227 | High candlestick + full indicator + structural |
| 0.3950 | 0.55 | 0.7182 | High candlestick + near-full indicator + structural |
| 0.2975 | 0.55 | 0.5409 | Low candlestick + near-full indicator + structural |

The 0.5409 score (raw 0.2975) represents a bar where:
- `candlestick_quality ≈ 0.55` (doji — weakest pattern)
- `indicator_quality ≈ 1.00` (indicators aligned)
- `structural_alignment = 1.00` (at support/resistance)

This is at the lower end of viable candidates but still above the 0.50 threshold.

---

## Phase 4+ Projection

When ChartPatternGroup (0.35) and HistorianAgent (0.10) are activated:
- `ACTIVE_COMPOSITE_WEIGHT_SUM = 1.00`
- Normalization becomes identity: `raw_score / 1.0 = raw_score`
- Full formula active, ceiling = 1.0
- Phase 3 and Phase 4+ thresholds are the same constant (0.50), preserving continuity
- Existing CandidateTradeEvent scoring logic is unchanged

The repair requires zero code changes when transitioning to Phase 4.
