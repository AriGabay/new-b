# Source Audit: learn-crypto-trading.github.io/chart-patterns/
## URL: https://learn-crypto-trading.github.io/chart-patterns/
## Audit Date: 2026-03-28
## Auditor: Phase 1 Research Agent

---

## 1. Source Classification

**Type:** Cheat sheet from Thomas Bulkowski's "Encyclopedia of Chart Patterns."
**Primary Authority:** Thomas Bulkowski — the most rigorously empirical chart pattern researcher available to retail traders.
**Critical Caveat:** Data from US equities, not crypto. Crypto transfer validity UNKNOWN. Statistics are historical and may be subject to non-stationarity.

---

## 2. Bulkowski Methodology Notes

Bulkowski's approach is more rigorous than most TA sources:
- Uses large sample sizes (hundreds of formations per pattern).
- Defines failure rate as formations that fail to move 5% in the expected direction.
- Measures "likely move" separately from "average move" (average is skewed by outliers).
- Studies both confirmation (waiting for breakout) vs. aggressive (before confirmation) entries.
- Defines specific "reliable" thresholds: failure rate < 20%, target hit rate > 80%.

**Key insight:** Bulkowski's most important contribution is showing that waiting for **breakout confirmation** dramatically lowers failure rates. This is consistently the strongest rule across all patterns.

---

## 3. Pattern-by-Pattern Analysis

### 3.1 Triangles

#### Ascending Triangle
- Visual: Horizontal resistance + rising support
- Rule: Wait for upside breakout
- Performance: Low failure rate ("one of my favorite formations")
- **Assessment:** Operationalizable. Criteria: 2+ touches of horizontal resistance, 2+ higher lows. Breakout: close above resistance. HOLD AS HYPOTHESIS.

#### Descending Triangle
- Visual: Horizontal support + falling resistance
- Failure rate after downside breakout: **4%** (outstanding)
- **Assessment:** High reliability with breakout confirmation. HOLD AS HYPOTHESIS.

#### Symmetrical Triangle
- Visual: Lower highs + higher lows converging
- Tends to break downward in downtrend
- **Assessment:** Direction prediction weaker than ascending/descending. More useful as continuation pattern. HOLD WITH LOWER PRIORITY.

### 3.2 Flags and Pennants

- Duration: Days to 3 weeks
- Theory: Marks halfway point in a price move
- Failure rates:
  - Pennants in downtrends: **34%** → ABOVE 20% threshold → UNRELIABLE
  - Flags: **12-13%** → below threshold → USABLE
  - Pennants in uptrends: **19%** → borderline
- Target hit rate: **52-63%** → Bulkowski says "disappointing, trade with caution"
- **Assessment:** Flags in uptrends have acceptable failure rates but poor target achievement. Can be used as entry triggers with REDUCED target expectations. Pennants in downtrends: REJECT.

#### High and Tight Flags
- Criteria: Short, quick prior rise + tight consolidation
- Failure rate with breakout: **17%** → reliable
- Volume: Receding volume outperforms; rising volume = lower but still positive performance
- **Assessment:** More selective; requires strong prior momentum. HOLD AS PRIORITY HYPOTHESIS. High-quality momentum entry pattern.

### 3.3 Wedges

#### Falling Wedge
- Failure rate: **10%** → very low
- Average rise: **43%** (but likely rise is 20-30%)
- Often signals bullish reversal despite bearish appearance
- **Assessment:** Strong pattern. Watch for crypto-specific: falling wedges in crypto often resolve sharply. HOLD AS HIGH PRIORITY HYPOTHESIS.

#### Rising Wedge
- Failure rate: **24%** → above threshold
- With downside breakout: drops to **6%** → very reliable
- Volume: Receding outperforms
- Bulkowski: "one of the poorer performing chart patterns"
- **Assessment:** Reject as standalone; viable as SHORT entry after confirmed downside breakout. HOLD AS CONDITIONAL HYPOTHESIS.

#### Broadening (Ascending/Descending) Wedges
- Descending Broadening Wedge: Average rise **46%** in bull market; 40% of formations gain 50%+
- **Assessment:** Strong in bull regime, regime-dependent. Mark as REGIME-CONDITIONAL HYPOTHESIS.

### 3.4 Rectangles
- Can act as continuation OR reversal → direction prediction is ambiguous
- Bulkowski: "a tug of war between buyers and sellers"
- **Assessment:** LOW VALUE as directional signal. Useful as ranging market identifier. Range trading system may be applicable within rectangles (buy support, sell resistance), but breakout direction is not predictable.

### 3.5 Double Bottoms
- WITHOUT confirmation: **64% failure rate** → disqualifying
- WITH confirmation (close above mid-peak): **3% failure rate** → outstanding
- Only 1/3 of "double bottom" formations are true double bottoms
- **Key rule:** Never enter a double bottom until price closes ABOVE the highest high between the two lows (confirmation point).
- **Assessment:** STRONG PATTERN IF AND ONLY IF confirmation rule is enforced. This is a critical implementation detail. HOLD AS HIGH PRIORITY HYPOTHESIS with mandatory confirmation filter.

### 3.6 Double Tops
- After confirmation: **83% correct** in predicting continued decline
- BUT: **Only 39% reach the predicted target** (measuring height of pattern projected down from neckline)
- Almost half decline less than 15%
- **Assessment:** Reliable for direction prediction, but measured move targets are overly optimistic. Enter on confirmation, use conservative targets (half of measured move). HOLD AS HYPOTHESIS with downgraded target expectations.

### 3.7 Triple Bottoms
- Failure rate: **4%** (surprisingly low per Bulkowski)
- Average rise: **38%**, likely gain: **20%**
- Extra finding: Third bottom above second bottom → 48% gain; third bottom below second → 31% gain
- **Assessment:** Very strong pattern. The sub-finding (relative position of third bottom) is actionable: prefer triple bottoms where each successive bottom is slightly higher. HOLD AS HIGH PRIORITY HYPOTHESIS.

### 3.8 Triple Tops
- Failure rate: **15%** (approaching but under 20% threshold)
- Counter-intuitive: Third top higher than second top → larger average decline (22% vs 17%)
- **Assessment:** HOLD AS HYPOTHESIS. Triple tops with progressive highs may be stronger setups.

### 3.9 Cup with Handle
- Strict criteria: Must be U-shaped (not V), must have handle, 30%+ prior rise
- Bulkowski removed V-shapes and no-handles from study (better performance on stricter criteria)
- **Assessment:** The strictness of criteria is important — this is NOT a common pattern. Operationalize with: prior rise threshold, U-shape detection (smooth curve vs sharp reversal), handle detection (slight downward drift, lower volume). HOLD AS HYPOTHESIS.

### 3.10 Head and Shoulders (Tops)
- **93% of formations break downward and continue** — statistically strongest pattern in the source
- Bulkowski: "no need to wait for breakout before trading" (rare exception to the breakout rule)
- **Assessment:** This is the most statistically validated pattern in the entire source. HEAD AND SHOULDERS TOPS deserve PRIORITY attention. HOLD AS HIGH PRIORITY HYPOTHESIS.

### 3.11 Complex Head and Shoulders (Tops & Bottoms)
- Complex HS Bottoms: **6% failure rate, 82% hit price targets** — outstanding
- Left shoulder volume > right shoulder volume (confirmation criterion)
- Downward-sloping neckline → better performance
- **Assessment:** Even better than standard H&S. Operationalizing complex HS requires defining "multiple heads/shoulders" — non-trivial algorithmically. HOLD AS HYPOTHESIS with complexity flag.

### 3.12 Inverted Head and Shoulders (Bottoms)
- Entry: Long when price breaks above neckline resistance
- Standard bullish reversal
- **Assessment:** HOLD AS HYPOTHESIS. Pairs naturally with HS Top for short entries.

### 3.13 Dead-Cat Bounce
- NOT a traditional formation — a behavioral pattern
- Triggering event: Average **25% decline**
- Bounce followed by continued decline: Another **~15% from event low**
- Larger initial decline → larger bounce
- **Assessment:** This is useful for risk management and SHORT continuation setups after large drops. After a confirmed large drop (>15-20%), be skeptical of bounces as trend reversals. HOLD AS HYPOTHESIS for shorting bounce continuations.

### 3.14 Gaps
- Definition provided but no specific statistics on reliability
- Causes: exuberance, earnings, news
- **Assessment:** Gap-fill hypothesis (gaps tend to get filled) is NOT validated here. Do not include without separate validation.

### 3.15 Island Reversals
- "Mediocre performance"
- **Assessment:** REJECT. Source says mediocre performance.

### 3.16 Rounding Bottoms
- With upside breakout: **5% failure rate**
- **Assessment:** Very low failure rate. Identifying rounding bottoms algorithmically is challenging (smooth curve detection). HOLD AS HYPOTHESIS with implementation complexity flag.

### 3.17 Rounding Tops
- Controversy: Bulkowski says upside breakout likely; most traders expect downside
- Source recommends ignoring due to conflicting interpretations
- **Assessment:** REJECT per source recommendation. Move to other indicators when this appears.

### 3.18 Bump-and-Run Reversal Bottoms (BARR)
- Failure rate: **9%** with breakout
- Average gain: **37%**, likely rise: **20%**
- Discovered by Bulkowski 1999
- Related to Cup with Handle
- **Assessment:** Very strong performance stats. HOLD AS HIGH PRIORITY HYPOTHESIS.

### 3.19 Bump-and-Run Reversal Tops
- Describes momentum peaking and declining
- "The visual representation of momentum"
- **Assessment:** HOLD AS HYPOTHESIS for identifying momentum exhaustion at tops.

### 3.20 Diamond Tops and Bottoms
- "Rare, but reliable"
- Diamond bottom breaks upward **69%** of time
- "Diamond bottom with downward breakout is one of best performing patterns" (Bulkowski)
- Stop placement: Above last top inside diamond (bearish) / below last low inside diamond (bullish)
- **Assessment:** Rare pattern with complex visual detection. Hold as low-priority hypothesis.

### 3.21 Hanging Man
- "Only 1/3 reverse; others continue higher"
- Source conclusion: "Cannot recommend trading this formation"
- **Assessment:** REJECT. Source explicitly rejects it based on Bulkowski's data.

### 3.22 Inside Days / Inside Bars
- Key finding: When inside day closes within 25% of prior day's LOW → downside breakout 70% of time
- **Assessment:** THIS IS ACTIONABLE. An inside bar closing near the bottom of prior range has a specific directional bias. Operationalizable. HOLD AS HYPOTHESIS.

### 3.23 Outside Days / Outside Bars
- Can be continuation or reversal
- Bullish outside day in uptrend = continuation
- Outside reversal = opposite direction from trend
- **Assessment:** Context-dependent. As continuation signal: HOLD. As reversal signal: requires additional confirmation.

### 3.24 Measured Move Up/Down
- Measured Move Down: Failure rate **22%** (above threshold), average decline **36%**
- Measured Move Up: Failure rate **23%** (above threshold), average gain **68%** (misleading due to outliers)
- **Assessment:** Both have failure rates above 20% threshold. Useful as TARGET PROJECTION tool after first leg is identified, not as entry signal. Use measured move targets with 50% discount.

### 3.25 Pipe Bottoms
- Failure rate: **12%** (low)
- Average rise: **47%** (high)
- Two spike (V-shaped) formations in downtrend
- **Assessment:** Strong performance stats. Operationalizable as two adjacent spike candles in a downtrend. HOLD AS HYPOTHESIS.

### 3.26 Pipe Tops
- Inverse of pipe bottoms
- **Assessment:** HOLD AS HYPOTHESIS.

### 3.27 Scallops
- Ascending: **33% average rise** (respectable but mediocre)
- Target achievement rate: **52%** (weak)
- **Assessment:** Mediocre performance. Low priority. HOLD AS LOW PRIORITY HYPOTHESIS.

### 3.28 Broadening Formations
- Bearish patterns with increased volatility
- "Useful for low timeframe traders"
- Broadening Top: 5 reversals + significant drop
- Broadening Bottom: 5 reversals + advance
- **Assessment:** Complex to identify algorithmically. Regime-dependent (increased volatility regime). HOLD AS LOW PRIORITY HYPOTHESIS.

---

## 4. Summary Statistics Table

| Pattern | Failure Rate | Target Hit Rate | Assessment |
|---|---|---|---|
| Descending Triangle (breakout confirmed) | 4% | N/A | HIGH PRIORITY |
| Triple Bottom | 4% | N/A | HIGH PRIORITY |
| Double Bottom (confirmed) | 3% | N/A | HIGH PRIORITY |
| HS Bottom Complex | 6% | 82% | HIGH PRIORITY |
| Falling Wedge | 10% | N/A | HIGH PRIORITY |
| HS Top | 7% (implied) | 93% break down | HIGH PRIORITY |
| BARR Bottom | 9% (breakout) | N/A | HIGH PRIORITY |
| Pipe Bottom | 12% | N/A | HIGH PRIORITY |
| High and Tight Flag | 17% (breakout) | N/A | MEDIUM PRIORITY |
| Flag (uptrend) | 12-13% | 52-63% | MEDIUM (low target) |
| Triple Top | 15% | N/A | MEDIUM PRIORITY |
| Ascending Triangle | Low (not specified) | N/A | MEDIUM PRIORITY |
| Rounding Bottom (breakout) | 5% | N/A | MEDIUM (detection complex) |
| Rising Wedge (breakout) | 6% (w/ breakout) | N/A | MEDIUM PRIORITY |
| Double Top (confirmed) | 17% implied | 39% | LOW (poor targets) |
| Hanging Man | N/A | 33% reverse | REJECTED |
| Island Reversal | Mediocre | Mediocre | REJECTED |
| Rounding Top | Contradicted | Contradicted | REJECTED |
| Pennant (downtrend) | 34% | <80% | REJECTED |

---

## 5. Critical Implementation Rules Derived from This Source

1. **Always wait for breakout confirmation** before entering any chart pattern trade.
2. **Use conservative targets** — measured move targets are systematically optimistic; discount by 40-50%.
3. **Double Bottom confirmation** = close above the highest high between the two lows. Without this, 64% fail.
4. **Head and Shoulders Top** is the statistically strongest single pattern — prioritize in system.
5. **Inside bar closing near prior day's low** → 70% downside breakout probability.
6. **Don't trade Hanging Man** — only 33% reversal rate.
7. **Rising Wedge alone** is unreliable (24% failure); only trade after confirmed downside breakout.

---

## 6. Overall Source Assessment

**Verdict:** HIGH VALUE. This source provides the most concrete statistical grounding in the entire corpus.
Bulkowski's empirical work on chart patterns is the closest thing to genuine quantitative research available from retail-accessible sources. The failure rates and performance statistics are the key actionable outputs. The critical finding — that breakout confirmation dramatically improves all patterns — is the single most important rule to implement.

However: All statistics must be re-derived on crypto OHLCV data. Equity-based statistics are informative priors, not ground truth for crypto.
