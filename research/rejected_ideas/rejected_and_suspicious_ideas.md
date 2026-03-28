# Rejected and Suspicious Ideas
## Generated: 2026-03-28
## Source: Phase 1 Research Corpus

---

## Overview

This document catalogs all ideas from the source corpus that have been rejected or flagged as suspicious. An idea is rejected if it meets any of the following criteria:
- Has explicit empirical evidence against it (from Bulkowski or other sources)
- Cannot be operationalized without lookahead bias
- Relies on underdefined concepts that cannot be made precise
- Has contradicted itself within the source material
- Has a failure rate above 20% (Bulkowski threshold) without compensating factors
- Is purely narrative/ideological without testable predictions
- Relies on information not available at trade entry time

---

## REJECTED — Class 1: Explicitly Contradicted by Empirical Data

### RJ-001: Hanging Man as Bearish Reversal
**Source:** Chart patterns page, Bulkowski data
**Claimed:** Hanging Man signals trend reversal at tops
**Bulkowski Finding:** Only 1/3 of formations reverse; 2/3 continue higher
**Rejection Reason:** 33% reversal rate is worse than random in a trending market. Explicitly rejected by Bulkowski.
**Verdict: REJECTED**

### RJ-002: Shooting Star as Reliable Bearish Reversal
**Source:** Candlesticks page
**Claimed:** Shooting Star in uptrend signals bearish reversal
**Finding:** 60% reversal rate per Bulkowski
**Rejection Reason:** 60% is too close to 50% (random) to be a reliable standalone signal. The extra 10% is likely consumed by spread and slippage.
**Verdict: REJECTED as standalone signal**

### RJ-003: Island Reversals as Reliable Patterns
**Source:** Chart patterns page
**Claimed:** Island reversals signal trend reversals
**Source Assessment:** "Performance of island reversals is perhaps surprising only for its mediocrity."
**Rejection Reason:** Source explicitly describes performance as mediocre. No statistical backup given.
**Verdict: REJECTED**

### RJ-004: Rounding Top as Bearish Pattern
**Source:** Chart patterns page
**Claimed:** Rounding tops are bearish patterns breaking downward
**Contradiction:** Bulkowski says upside breakout is more likely; mainstream traders say downside. Conflicting interpretations with no resolution.
**Rejection Reason:** Source itself recommends: "ignore this pattern and move to some other indicator."
**Verdict: REJECTED per source recommendation**

### RJ-005: Pennants in Downtrends
**Source:** Chart patterns page, Bulkowski
**Claimed:** Pennants mark halfway points in moves (continuation)
**Finding:** 34% failure rate in downtrends (threshold is 20%)
**Rejection Reason:** Failure rate exceeds Bulkowski's reliability threshold by 14 percentage points.
**Verdict: REJECTED**

### RJ-006: Inverted Hammer as Bullish Reversal (Standard Textbook)
**Source:** Candlesticks page, Bulkowski
**Claimed:** Inverted Hammer in downtrend = bullish reversal
**Bulkowski Finding:** ~60% bearish continuation (NOT bullish reversal)
**Rejection Reason:** The conventional interpretation is WRONG according to Bulkowski's data. The textbook interpretation should be used inversely or not at all.
**Important Note:** This is not "reject the pattern" — it's "reject the conventional interpretation." The inverted hammer may be a BEARISH continuation signal. Requires dedicated crypto backtest.
**Verdict: REJECT CONVENTIONAL INTERPRETATION. Test inverse interpretation.**

---

## REJECTED — Class 2: Too Vague / Not Operationalizable

### RJ-007: Wyckoff Phases for Automation
**Source:** README, general page
**Claimed:** Wyckoff phases (Accumulation, Markup, Distribution, Markdown) describe institutional market cycles
**Problem:** No operational definition is given or exists in the source. Wyckoff phase identification requires:
- Subjective identification of "trading ranges"
- Volume interpretation that is context-dependent
- Identification of specific events (Spring, Upthrust, Sign of Strength) that are defined in hindsight
**Reality:** Professional Wyckoff analysis is a skill requiring years of practice and remains controversial among empirical researchers. No published study demonstrates consistent out-of-sample alpha from automated Wyckoff classification.
**Verdict: REJECTED FOR AUTOMATION. Educational background only.**

### RJ-008: Elliott Wave for Automation
**Source:** README, general page
**Claimed:** Elliott Wave describes 5-wave impulse and 3-wave corrective structures
**Problem:**
- Wavecount is subjective; professional practitioners regularly disagree on current wave count
- The theory is inherently self-referential (any pattern can be fit to a wavecount)
- Extremely high false positive rate
- Predictions are retrospectively adjusted
- Not falsifiable in practice
**Published Evidence:** Academic studies on EW have generally failed to find significant predictive value.
**Verdict: REJECTED FOR ALL AUTOMATION PURPOSES.**

### RJ-009: Gartley and Butterfly Harmonic Patterns
**Source:** README, general page
**Claimed:** Harmonic patterns (Gartley 222, Butterfly) provide high-precision reversal levels
**Problem:**
- The Fibonacci ratios used are flexible (0.618, 0.786, 0.886, etc.) — creates high fitting degrees of freedom
- Multiple valid interpretations of the same price structure
- Source itself says basic TA "is almost always more powerful than Harmonics"
**Verdict: REJECTED. Simpler patterns with better statistical backing exist.**

### RJ-010: ABCD Pattern (Standard Form)
**Source:** README
**Claimed:** AB = CD pattern shows "perfect harmony between price and time"
**Problem:** The "perfect harmony" claim is pseudoscientific. While measured moves (equal legs) have some empirical basis, the ABCD labeling system is a retrofitted narrative.
**What IS valid:** The measured move concept (first leg ≈ second leg) has more direct statistical support (from Bulkowski's measured move patterns).
**Verdict: REJECT HARMONIC FRAMING. The underlying measured move concept is absorbed into Family 4 (Measured Move rules).**

### RJ-011: "Fibonacci is a Universal Language Found in Nature"
**Source:** General page (direct quote)
**Claimed:** "Fibonacci is a sequence found in us and our genes, our mentality, nature and our universe. Its is a universal, multidimensional language, that in my belief is used far beyond our personal human lifetimes and this world."
**Assessment:** This is mysticism, not finance. Fibonacci ratios appear in price charts primarily because:
1. Many traders watch them, creating self-fulfilling dynamics
2. They are round fractions (50% = 1/2, 61.8% ≈ 2/3) that humans naturally gravitate to
3. Cherry-picking which level "worked" retrospectively inflates apparent accuracy
**Verdict: REJECT THE MYSTICAL FRAMING ENTIRELY. The empirical self-fulfilling aspect of Fibonacci levels is what should be tested and used, stripped of all mysticism.**

---

## REJECTED — Class 3: Unverifiable or Anecdotal Claims

### RJ-012: CNBC as Reverse Indicator
**Source:** General page
**Claimed:** When CNBC covers Bitcoin bullishly, it marks tops
**Assessment:** Anecdotal pattern with sample size ~3-5 events. Media coverage does correlate roughly with public attention cycles (which do correlate with tops), but:
- Cannot be systematically detected in real-time
- CNBC sentiment cannot be automated without NLP infrastructure
- The correlation, even if real, is not actionable at sufficient precision
**Verdict: REJECTED AS TRADING RULE. Amusing anecdote.**

### RJ-013: CME Futures Expiry Effect
**Source:** README (CarpeNoctom tweet)
**Claimed:** CME Bitcoin futures contract expiry dates influence BTC price
**Assessment:**
- Very low sample size
- CME market structure changed significantly after 2020
- Mechanism is not well-defined
- Even if there was an effect, it may have been arbitraged away as awareness spread
**Verdict: REJECTED pending peer-reviewed evidence.**

### RJ-014: Bitcoin 4-Year Halving Cycle as Trading Signal
**Source:** README, economics pages
**Claimed:** BTC 4-year cycle is "programmed into the system" and reliably precedes bull runs
**Assessment:** n=4 events; each bull run has been driven by overlapping factors (institutional adoption, derivatives launch, macro liquidity, ETF approvals) not just halving. Cannot attribute causality. Extrapolating from n=4 is statistically invalid.
**Verdict: REJECT AS TRADING SIGNAL. Use as COARSE MACRO CONTEXT ONLY.**

### RJ-015: ETH as Alt Season Leading Indicator
**Source:** General page (AltcoinPsycho tweet)
**Claimed:** Wait for ETH to bottom before buying alts
**Assessment:** An anecdotal Twitter observation with no statistical backing. ETH may sometimes lead alts and sometimes lag. The correlation likely varies by cycle and regime.
**Verdict: REJECT AS RULE. Test as hypothesis before relying on it.**

### RJ-016: DOGE Cycles as Altseason Signal
**Source:** README (tweet reference)
**Claimed:** DOGE has historical cycle symmetry and signals altseason
**Assessment:** n=2-3 observations at best. Absurd to treat DOGE price cycles as a systematic leading indicator.
**Verdict: REJECTED.**

---

## REJECTED — Class 4: Lookahead Bias / Retroactive Pattern Fitting

### RJ-017: BTC "Moonshot" Growth Pattern Charts
**Source:** README (various tweets)
**Claimed:** Historical BTC price charts show identifiable growth patterns implying future continuation
**Assessment:** Fitting exponential growth curves or pattern overlays to any historical asset that has grown 1000×+ is trivial and provides no predictive value. Survivorship bias: assets that failed are not shown.
**Verdict: REJECTED.**

### RJ-018: Market Cycle Diagrams (Generic "4 Stages")
**Source:** General (image reference)
**Claimed:** Markets reliably cycle through accumulation → markup → distribution → markdown
**Assessment:** This is a post-hoc narrative framework that is always "correct" because the labels can be applied to any completed cycle. Identifying the CURRENT stage in real-time is the actual challenge, and no systematic approach is provided.
**Verdict: REJECTED AS PREDICTIVE TOOL. Useful as conceptual vocabulary only.**

---

## SUSPICIOUS — Class 5: Requires Validation Before Use

### SUS-001: RSI Divergence Without Context Filter
**Source:** General page
**Claimed:** RSI divergence predicts reversals
**Why Suspicious:** Source itself (CryptoCred) warns: "After a big move/candle there will almost always be a regular divergence — don't use it to snipe top/bottom." The base divergence claim is not wrong, but unfiltered divergence is nearly meaningless.
**Status: HOLD — test only with context filter (no impulse candle, established trend)**

### SUS-002: Double Top as Reliable Setup
**Source:** Chart patterns page
**Claimed:** Double top with confirmation = reliable bearish reversal
**Why Suspicious:** Only 39% of formations reach their measured move target. The pattern direction is correct (83% of the time), but the size of the move is unpredictable. Positions sized for the measured move target will frequently stop out after partial moves.
**Status: HOLD — use for entry direction only; use conservative targets**

### SUS-003: Ascending Triangle as Reliable Pattern
**Source:** Chart patterns page
**Claimed:** Ascending triangle with upside breakout is reliable
**Why Suspicious:** No specific failure rate given in source (Bulkowski quote is enthusiastic but not quantified here). Crypto ascending triangles frequently have false breakouts due to manipulation.
**Status: HOLD — require additional confirmation (volume, candle close)**

### SUS-004: Scallops
**Source:** Chart patterns page
**Stats:** 33% average rise, 52% target achievement
**Why Suspicious:** Both metrics are mediocre. 52% target achievement barely beats random. Complex to detect algorithmically.
**Status: LOW PRIORITY — only if nothing else applies**

### SUS-005: Fear & Greed Index as Trading Signal
**Source:** README (tools section)
**Claimed:** Extreme fear → buy; extreme greed → sell
**Why Suspicious:** Sentiment extremes are necessary but not sufficient for reversals. Extreme fear can persist for months in bear markets. Extreme greed in crypto is the normal state of bull markets.
**Status: SECONDARY FILTER ONLY — never primary signal**

---

## Summary Table

| ID | Pattern/Idea | Rejection Class | Verdict |
|---|---|---|---|
| RJ-001 | Hanging Man reversal | Empirical data | REJECTED |
| RJ-002 | Shooting Star standalone | Low statistical edge | REJECTED |
| RJ-003 | Island Reversals | Mediocre performance | REJECTED |
| RJ-004 | Rounding Top | Contradicted | REJECTED |
| RJ-005 | Pennant in downtrend | 34% failure rate | REJECTED |
| RJ-006 | Inverted Hammer bullish | Wrong direction | REJECT CONVENTIONAL |
| RJ-007 | Wyckoff for automation | Too subjective | REJECTED |
| RJ-008 | Elliott Wave for automation | Not falsifiable | REJECTED |
| RJ-009 | Gartley/Butterfly harmonics | Too complex, weak | REJECTED |
| RJ-010 | ABCD harmonic framing | Absorbed as measured move | REJECTED |
| RJ-011 | Fibonacci mysticism | Pseudoscience | REJECTED |
| RJ-012 | CNBC reverse indicator | Anecdotal n=3 | REJECTED |
| RJ-013 | CME expiry effect | Low evidence | REJECTED |
| RJ-014 | Halving cycle as signal | n=4 sample | REJECTED as signal |
| RJ-015 | ETH as alt season indicator | Unvalidated | REJECTED until tested |
| RJ-016 | DOGE cycles | n=2, absurd | REJECTED |
| RJ-017 | BTC moonshot pattern | Lookahead/survivorship | REJECTED |
| RJ-018 | 4-stage market cycle | Retroactive fitting | REJECTED as predictor |
| SUS-001 | RSI divergence (no filter) | Context-dependent | HOLD with filter |
| SUS-002 | Double Top measured targets | 39% hit rate | HOLD with discount |
| SUS-003 | Ascending Triangle | No crypto stats | HOLD with confirmation |
| SUS-004 | Scallops | Mediocre stats | LOW PRIORITY |
| SUS-005 | Fear & Greed as signal | Lagging sentiment | SECONDARY only |
