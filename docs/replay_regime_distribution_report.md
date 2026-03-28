# Replay Regime Distribution Report — Phase 6.1

**Date:** 2026-03-29
**Phase:** 6.1 Observational Replay

---

## Summary

This report documents the EMA-alignment regime distribution observed across Phase 6.1 fixtures. Regime distribution is important for understanding when H3-005 can and cannot fire, and how the panel scores proposals in each regime.

---

## EMA Alignment Classification

The system classifies each bar into one of five regimes based on EMA ordering:

| Regime | Condition | H3-005 eligible? | Panel scoring |
|--------|-----------|-----------------|---------------|
| `full_bull` | EMA20 > EMA50 > EMA200 | LONG ✓ | High (trend-following scores ~8.5) |
| `full_bear` | EMA20 < EMA50 < EMA200 | SHORT ✓ | High (trend-following scores ~8.5) |
| `partial_bull` | EMA20 > EMA50, but EMA50 ≤ EMA200 | No | Medium (scores ~6.0–6.5) |
| `partial_bear` | EMA20 < EMA50, but EMA50 ≥ EMA200 | No | Medium (scores ~6.0–6.5) |
| `mixed` | EMA20 ≈ EMA50, or crossing | No | Low (scores ~4.0–5.0) |

---

## Per-Fixture Regime Distribution

### Fixture 1: btc_bull_continuation_pullback_v1 (320 bars)

| Regime | Bars | % of Total | Proposal-eligible | H3-005 fired |
|--------|------|-----------|-------------------|-------------|
| `mixed` | ~85 | 26.6% | via H3-002 (crossover) | 0 |
| `partial_bull` | ~95 | 29.7% | limited | 0 |
| `full_bull` | ~140 | 43.7% | LONG H3-005 | 8 |
| `partial_bear` | ~0 | 0% | — | 0 |
| `full_bear` | ~0 | 0% | — | 0 |

H3-005 fires only in `full_bull` regime. Warmup bars are pre-full_bull. Crossover bars (mixed/partial) produce proposals but score poorly.

**Key finding:** The pullback zone (bars 280–295) is entirely in `full_bull` regime. H3-005 fires there. But candlestick co-occurrence is absent due to S/R non-detection.

---

### Fixture 2: btc_bear_continuation_pullback_v1 (~370 bars)

| Regime | Bars | % of Total | H3-005 fired |
|--------|------|-----------|-------------|
| `mixed` | ~50 | 13.5% | 0 |
| `partial_bull` | ~60 | 16.2% | 0 |
| `full_bull` | ~30 | 8.1% | 6 (LONG) |
| `partial_bear` | ~80 | 21.6% | 0 |
| `full_bear` | ~150 | 40.5% | 5 (SHORT) |

`full_bull` bars appear early (warmup transition). `full_bear` dominates the bear-continuation phase.

**Key finding for SHORT path:** The 5 H3-005 SHORT bars occur in `full_bear` regime. No candlestick pattern fires simultaneously because H2-003 Three Black Crows requires `ema20 > ema50` — exactly the opposite regime.

---

### Fixture 3: btc_long_established_trend_v1 (300 bars)

| Regime | Bars | % of Total | H3-005 fired |
|--------|------|-----------|-------------|
| `mixed` | ~60 | 20.0% | 0 |
| `partial_bull` | ~80 | 26.7% | 0 |
| `full_bull` | ~160 | 53.3% | 11 (LONG) |
| `partial_bear` | ~0 | 0% | 0 |
| `full_bear` | ~0 | 0% | 0 |

Dominant `full_bull` regime. H3-005 fires 11 times — highest single-fixture count.
1 co-occurrence with candlestick. Panel evaluated; held at 12/20 approvals.

---

## H3-005 Firing Conditions Analysis

H3-005 fires when all 6 conditions are simultaneously met. Breakdown of which conditions are typically limiting:

### Limiting Factor 1: EMA Alignment (30% of bars are full_bull/full_bear)
Warmup phase is all `mixed` or `partial`. H3-005 can only fire post-crossover in established trend.
- full_bull/full_bear coverage: ~30–44% of bars across fixtures
- H3-005 fires on: 8–11 of those bars (~6–9%)

### Limiting Factor 2: Price Within 3% of EMA20
In the established trend phase, price often runs away from EMA20 (momentum phase). H3-005 requires a pullback.
- Typical post-trend: price is 5–15% above EMA20
- H3-005 zone: price within ±3% of EMA20
- Only pullback or oscillation bars qualify

### Limiting Factor 3: RSI Between 35–65
After a strong trend, RSI stays above 65 for extended periods (overbought).
After a strong decline, RSI stays below 35 (oversold).
H3-005 requires a RSI pullback into neutral zone.

### Limiting Factor 4: ADX >= 25
Usually met once a trend is established. ADX < 25 indicates ranging/choppy market.
In fixtures: ADX is above 25 for most of the established-trend phase.

### Limiting Factor 5: Volume Ratio >= 1.0
Volume spikes accompany pullback reversals. Synthetic fixtures maintain volume_ratio ≈ 0.9–1.3.
Not the primary limiter in observed fixtures.

---

## Regime Transition Events

### Crossover Timing

| Fixture | Crossover bar (approx) | Type |
|---------|----------------------|------|
| bull_continuation_pullback | bar ~80 (warmup zone) | partial_bull emerges |
| bull_continuation_pullback | bar ~120 | full_bull achieved |
| bear_continuation_pullback | bar ~90 | partial_bear emerges after peak |
| bear_continuation_pullback | bar ~150 | full_bear achieved |
| long_established_trend | bar ~100 | partial_bull |
| long_established_trend | bar ~145 | full_bull achieved |

Proposals from crossover bars cluster around bars 80–155 across fixtures. These are `mixed` or `partial_bull` regime bars → panel scores low.

---

## Regime-to-Signal-to-Panel Pathway

```
Regime         →  H3-005 eligible  →  Candlestick eligible  →  Co-occur?  →  Panel score
------         -  ----------------  -  --------------------  -  ---------  -  -----------
mixed          →  No               →  Yes (crossover cndle)  →  N/A        →  Low (4.5)
partial_bull   →  No               →  Sometimes             →  N/A        →  Medium (6.0)
full_bull      →  LONG ✓           →  Only if at_support     →  3.3%       →  High (8.5 if H3-005)
full_bear      →  SHORT ✓          →  Impossible (conflict)  →  0%         →  High (8.5 if H3-005)
```

---

## Conclusion

The regime distribution confirms:
1. **Establishing `full_bull` regime takes ~100–150 warmup bars** — this is expected and correct behavior
2. **H3-005 fires correctly within `full_bull`/`full_bear` — ~3% of total bars**
3. **Candlestick patterns in `full_bull` require `at_support=True` — never achieved in current fixtures**
4. **The SHORT path via `full_bear` has a fundamental candlestick conflict** — no SHORT pattern works without S/R
5. **Proposals from non-H3-005 bars are correctly rejected by the panel** — the panel discriminates well

The regime distribution is healthy. The system correctly distinguishes trend regimes. The problem is not regime classification — it is downstream structural level detection.
