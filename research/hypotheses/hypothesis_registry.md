# Hypothesis Registry
## Generated: 2026-03-28
## Source: Phase 1 Research Corpus

---

## Overview

This document catalogs all testable hypotheses derived from the source corpus. Each hypothesis is:
- Stated in testable form (falsifiable)
- Assigned a priority tier
- Associated with required data and implementation notes
- Explicitly NOT treated as validated until backtested on crypto OHLCV data

**Important:** No hypothesis here has been validated. These are structured guesses that warrant investigation. A hypothesis is not alpha until tested.

---

## Hypothesis Format

Each hypothesis follows this structure:
- **HX-NNN:** Unique identifier
- **Claim:** Specific, falsifiable statement
- **Type:** Statistical (pattern hit rate) / Directional (bias test) / Conditional (requires context)
- **Data Required:** Minimum dataset
- **Success Metric:** What constitutes confirmation
- **Known Failure Modes:** Conditions under which hypothesis likely fails
- **Priority:** Critical / High / Medium / Low
- **Status:** Untested

---

## H1 Series: Chart Pattern Breakout Hypotheses

### H1-001: Head & Shoulders Top — Post-Neckline Short Entry
**Claim:** After a confirmed H&S Top pattern (price closes below neckline), a short entry yields positive expectancy over the following 5-20 bars on cryptocurrency OHLCV data.
**Type:** Statistical
**Data Required:** BTC, ETH, top-10 crypto daily/4h OHLCV, minimum 3 years
**Success Metric:** Win rate > 55% OR profit factor > 1.4 after realistic fees (0.1% per side) and slippage
**Known Failure Modes:** Strong macro bull markets (pattern fails to complete), manipulation invalidating necklines, low-volume false patterns
**Priority: CRITICAL**
**Status: UNTESTED**

---

### H1-002: Inverse Head & Shoulders — Post-Neckline Long Entry
**Claim:** After confirmed Inverse H&S (price closes above neckline), a long entry yields positive expectancy over the following 5-20 bars on cryptocurrency data.
**Type:** Statistical
**Data Required:** Same as H1-001
**Success Metric:** Same as H1-001
**Known Failure Modes:** Bear markets overwhelming reversal setups, fake breakouts
**Priority: CRITICAL**
**Status: UNTESTED**

---

### H1-003: Double Bottom Confirmation Rule
**Claim:** Among all price structures that look like double bottoms, those that confirm (close above the highest high between the two lows) have a failure rate below 10% in crypto, consistent with Bulkowski's equity finding of 3%.
**Type:** Statistical
**Data Required:** Daily/4h OHLCV, minimum 3 years
**Sub-hypothesis:** Without confirmation, failure rate exceeds 50% in crypto (consistent with Bulkowski's 64%)
**Success Metric:** Confirmed double bottoms: failure rate < 15%. Unconfirmed: failure rate > 40%.
**Known Failure Modes:** False confirmations in manipulated thin markets
**Priority: CRITICAL**
**Status: UNTESTED**

---

### H1-004: Descending Triangle Breakout Short
**Claim:** After a confirmed downside breakout from a descending triangle (price closes below horizontal support), a short entry yields positive expectancy.
**Type:** Statistical
**Equity Baseline:** Bulkowski 4% failure rate
**Crypto Hypothesis:** Failure rate remains below 15% in crypto
**Data Required:** Daily/4h OHLCV
**Success Metric:** Failure rate < 15% on crypto
**Known Failure Modes:** Crypto "fakeouts" below support followed by V-reversal (more common than in equities)
**Priority: CRITICAL**
**Status: UNTESTED**

---

### H1-005: Triple Bottom Long Entry
**Claim:** A confirmed triple bottom (price closes above the highest intervening high after three tests of support) yields positive expectancy with average gain approximating Bulkowski's equity finding of 38%.
**Type:** Statistical
**Data Required:** Daily OHLCV
**Success Metric:** Average gain > 15% after fees; failure rate < 15%
**Known Failure Modes:** Requires 3 valid tests of support — identification may produce spurious patterns
**Priority: CRITICAL**
**Status: UNTESTED**

---

### H1-006: Bull Flag / Bear Flag Pattern Performance in Crypto
**Claim:** Bull flags (brief consolidation after a sharp up-move) in cryptocurrency produce positive expectancy entries on upside breakout, but targets are significantly lower than measured move predictions.
**Type:** Statistical
**Data Required:** Daily/4h OHLCV
**Equity Baseline:** 12-13% failure rate, 52-63% target achievement
**Success Metric:** Failure rate < 20%; use 50% of measured move as target; check that this still yields positive expectancy after fees
**Known Failure Modes:** Crypto "extended bull flags" that consolidate for months and fail; bear market context kills bull flag performance
**Priority: HIGH**
**Status: UNTESTED**

---

### H1-007: High & Tight Flag Performance
**Claim:** High & Tight Flags (short, rapid prior rise + tight consolidation) produce superior breakout performance compared to standard flags in crypto.
**Type:** Statistical / Comparative
**Data Required:** Daily/4h OHLCV; requires defining "short, rapid rise" (e.g., >20% in 10 bars)
**Equity Baseline:** 17% failure rate with breakout
**Success Metric:** Failure rate < 20%; meaningfully better than standard flag performance
**Known Failure Modes:** Rare pattern — small sample size in crypto; prior rise threshold definition is arbitrary
**Priority: HIGH**
**Status: UNTESTED**

---

### H1-008: Falling Wedge Reversal
**Claim:** Confirmed upside breakouts from falling wedge patterns in crypto produce positive expectancy long entries.
**Type:** Statistical
**Data Required:** Daily/4h OHLCV
**Equity Baseline:** 10% failure rate, 43% average rise
**Crypto Hypothesis:** Likely rise 15-25% (lower than equity due to higher noise)
**Success Metric:** Failure rate < 20%; average gain > 10%
**Known Failure Modes:** Falling wedges in macro bear markets (ETH 2022 had multiple failed falling wedge breakouts)
**Priority: HIGH**
**Status: UNTESTED**

---

### H1-009: Pipe Bottom Long Entry
**Claim:** Pipe bottom formations (two adjacent spike-low candles) in cryptocurrency produce positive expectancy long entries in downtrend context.
**Type:** Statistical
**Data Required:** Daily OHLCV
**Equity Baseline:** 12% failure rate, 47% average rise
**Success Metric:** Failure rate < 20%; average gain > 15%
**Known Failure Modes:** Manipulation-driven wicks creating artificial pipe bottoms; hard to algorithmically distinguish from random double-wick noise
**Priority: HIGH**
**Status: UNTESTED**

---

## H2 Series: Candlestick Pattern Hypotheses

### H2-001: Bearish Engulfing at Resistance as Short Signal
**Claim:** A bearish engulfing candle forming at a pre-defined resistance level (prior swing high, or horizontal resistance with 2+ prior touches) produces a negative next-N-bar return with positive expectancy.
**Type:** Conditional Statistical
**Data Required:** Daily/4h OHLCV; requires structural level detection
**Context Requirement:** Bearish engulfing ONLY valid at identified resistance level, not random location
**Success Metric:** Average next-5-bar return < -2% (meaningful directional edge) after fees
**Known Failure Modes:** Trending markets where resistance breaks cleanly; manipulation creating false engulfing patterns
**Priority: HIGH**
**Status: UNTESTED**

---

### H2-002: Morning Star / Evening Star at Structural Levels
**Claim:** Morning Star (bullish 3-candle reversal) at structural support and Evening Star (bearish) at structural resistance produce directional edge in crypto.
**Type:** Conditional Statistical
**Data Required:** Daily OHLCV
**Structural Level Definition:** Pre-defined in code, not retrospective
**Success Metric:** Same as H2-001
**Priority: HIGH**
**Status: UNTESTED**

---

### H2-003: Three Black Crows in Uptrend as Short Entry
**Claim:** Three consecutive large bearish candles following an uptrend in crypto produce reliable downside continuation.
**Type:** Statistical
**Data Required:** Daily OHLCV
**Context:** Must occur in an established uptrend (defined by MA slope)
**Success Metric:** Next 5-bar return < -3% with frequency > 60%
**Priority: HIGH**
**Status: UNTESTED**

---

### H2-004: Inverted Hammer Directional Hypothesis
**Claim:** In crypto, inverted hammer candles function as BEARISH continuation signals (per Bulkowski's equity finding of 60% bearish continuation), NOT bullish reversals as textbooks claim.
**Type:** Directional (tests whether Bulkowski's contrary finding transfers to crypto)
**Data Required:** Daily/4h OHLCV
**Success Metric:** Next 3-bar return < 0 with frequency > 55% after inverted hammer in various contexts
**Note:** This is a HYPOTHESIS AGAINST the conventional interpretation — needs direct testing
**Priority: MEDIUM (important to test before using either interpretation)**
**Status: UNTESTED**

---

### H2-005: Doji as Context-Dependent Signal
**Claim:** A doji candle alone has no directional predictive value, but a doji following 2+ consecutive trend candles has statistically higher reversal probability than random.
**Type:** Conditional Statistical
**Data Required:** Daily/4h OHLCV
**Success Metric:** After 3+ trend candles + doji: next 3-bar return probability of reversal > 55%
**Priority: MEDIUM**
**Status: UNTESTED**

---

## H3 Series: Indicator Hypotheses

### H3-001: RSI Divergence in Trend — Conditional Edge
**Claim:** RSI regular divergence forming during an established trend, when the most recent candle is within 1.5× ATR in size (no impulse candle), produces positive expectancy reversals in crypto.
**Type:** Conditional Statistical
**Data Required:** Daily/4h OHLCV
**Conditions:**
1. Trend established (price above/below 50-EMA for last 10 bars)
2. RSI divergence confirmed over last 2-3 swings
3. Most recent candle size < 1.5× ATR(14)
**Success Metric:** Win rate > 55% with R:R ≥ 1.5:1
**Priority: HIGH**
**Status: UNTESTED**

---

### H3-002: EMA Crossover as Baseline Performance Benchmark
**Claim:** A simple 20/50 EMA crossover applied to daily crypto data produces positive expectancy (profit factor > 1.0) after fees, serving as a minimal useful benchmark.
**Type:** Statistical
**Data Required:** BTC daily OHLCV minimum 5 years
**Purpose:** Establishes minimum bar that any more complex strategy must exceed
**Success Metric:** Profit factor > 1.2; max drawdown < 40%
**Note:** This is a BENCHMARK, not a strategy goal
**Priority: HIGH**
**Status: UNTESTED**

---

### H3-003: ATR-Scaled Position Sizing Improves Risk-Adjusted Returns
**Claim:** ATR-scaled stop losses (2× ATR) combined with R-multiple position sizing produce superior Sharpe ratio vs. fixed percentage stops on the same entry signals.
**Type:** Comparative
**Data Required:** Backtest result sets comparing two risk approaches on same signals
**Success Metric:** Sharpe improvement > 0.1; max drawdown reduction > 5%
**Priority: MEDIUM (implementation-level test)**
**Status: UNTESTED**

---

### H3-004: BB Squeeze as Breakout Precursor
**Claim:** Bollinger Band squeeze (BB width in bottom 10% of 100-bar lookback) followed by breakout produces higher magnitude moves than average breakouts.
**Type:** Statistical
**Data Required:** Daily/4h OHLCV
**Success Metric:** Post-squeeze breakout returns > 2× baseline breakout returns; probability of >10% move in 10 bars > 60%
**Priority: MEDIUM**
**Status: UNTESTED**

---

## H4 Series: Macro / Fundamental Hypotheses

### H4-001: Volume Filter Improves Pattern Performance
**Claim:** Chart patterns and candlestick signals from assets with >$10M daily 24h volume have lower failure rates than the same patterns from low-volume assets in crypto.
**Type:** Comparative Statistical
**Data Required:** Multi-asset OHLCV + volume data
**Success Metric:** Failure rate difference > 10 percentage points between high-volume and low-volume asset patterns
**Priority: HIGH (important universe filter decision)**
**Status: UNTESTED**

---

### H4-002: MVRV > 3 as Macro Risk Filter
**Claim:** When BTC MVRV Ratio exceeds 3.0, long positions in any cryptocurrency have significantly lower average forward returns over 30/90/180 days.
**Type:** Statistical
**Data Required:** BTC MVRV history (Glassnode/CryptoQuant) + BTC price data
**Success Metric:** Average 90-day forward return when MVRV > 3 is statistically significantly lower (p < 0.05) than baseline
**Priority: MEDIUM (requires on-chain data infrastructure)**
**Status: UNTESTED**

---

### H4-003: Dead-Cat Bounce Short Continuation
**Claim:** After a large initial drop (>15% in 3 bars), a subsequent bounce of 5-15% followed by bearish candlestick signals produces profitable short continuation entries.
**Type:** Conditional Statistical
**Data Required:** Daily OHLCV for BTC, ETH
**Success Metric:** Average forward 5-day return after short entry: < -5%; win rate > 55%
**Priority: HIGH**
**Status: UNTESTED**

---

### H4-004: Inside Bar Directional Bias
**Claim:** Inside bars closing in the bottom 25% of the prior candle's range produce downside breakouts more than 60% of the time in crypto (replicating Bulkowski's equity finding of 70%).
**Type:** Statistical
**Data Required:** Daily OHLCV
**Success Metric:** Downside breakout frequency > 55% (slightly lower than equity baseline expected)
**Priority: MEDIUM**
**Status: UNTESTED**

---

## H5 Series: Risk/Market Structure Hypotheses

### H5-001: Round-Number Stop Clustering = Elevated False Breakout Risk
**Claim:** Price spikes beyond round numbers ($1000, $10000, etc.) that immediately reverse represent stop-hunting events, and entering a counter-direction trade after such events has positive expectancy.
**Type:** Statistical
**Data Required:** Tick/minute OHLCV for BTC/ETH
**Success Metric:** Win rate > 55% with R:R ≥ 1.5:1 for fading stop hunts
**Priority: MEDIUM**
**Status: UNTESTED**

---

### H5-002: Volume Anomaly as Pump & Dump Filter
**Claim:** Trades filtered to exclude assets where 1-minute volume spike exceeds 10× the 60-period average have lower portfolio volatility and higher Sharpe ratio than unfiltered trades on same signals.
**Type:** Comparative
**Data Required:** Minute OHLCV + volume data
**Success Metric:** Sharpe improvement; removal of blowup events in portfolio history
**Priority: HIGH**
**Status: UNTESTED**

---

## Hypothesis Priority Summary

| Priority | Count | Key Hypotheses |
|---|---|---|
| CRITICAL | 5 | H1-001 through H1-005 (major chart patterns) |
| HIGH | 11 | H1-006 to H1-009, H2-001 to H2-003, H3-001, H3-002, H4-001, H4-003, H5-002 |
| MEDIUM | 9 | H2-004, H2-005, H3-003, H3-004, H4-002, H4-004, H5-001 |
| LOW | 0 | (none in this phase) |
| **TOTAL** | **25** | All untested; none validated |
