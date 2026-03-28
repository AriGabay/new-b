# Candidate Rule Families
## Generated: 2026-03-28
## Source: Phase 1 Research Corpus

---

## Overview

This document catalogs all candidate trading rule families extracted from the source corpus. Each family is defined by its logical structure, required inputs, known assumptions, failure modes, and implementation readiness.

Rules are classified as:
- **INCLUDE** — well-defined enough to implement and backtest
- **CONDITIONAL** — viable with additional specification
- **REJECT** — insufficient definition, high noise, or contradicted

---

## Family 1: Breakout Confirmation Rules

### 1.1 Chart Pattern Breakout
**Rule:** Enter when price closes beyond the breakout level of a confirmed chart pattern.
**Direction:** Long (above resistance) or Short (below support)
**Required Inputs:** OHLCV data, pattern detection algorithm, breakout level
**Key Principle (Bulkowski):** Waiting for breakout confirmation reduces failure rates dramatically across all patterns.

| Pattern | Breakout Level | Direction |
|---|---|---|
| Ascending Triangle | Horizontal resistance | Long |
| Descending Triangle | Horizontal support | Short |
| Double Bottom | Highest high between two lows | Long |
| Double Top | Lowest low between two highs | Short |
| H&S Top | Neckline | Short |
| Inverse H&S | Neckline | Long |
| Falling Wedge | Upper trendline | Long |
| Bull Flag | Prior swing high | Long |
| High & Tight Flag | Pattern high | Long |

**Implementation Notes:**
- Breakout = close of bar, not intrabar touch
- Volume confirmation (volume above N-period average) adds signal quality
- False breakout filter: price must close X% beyond level (e.g., 0.5% for crypto due to noise)
- Do NOT enter on wicks/shadows alone

**Status: INCLUDE**

---

### 1.2 Candlestick Reversal at Structural Level
**Rule:** Enter after a qualifying reversal candlestick forms at a significant support/resistance level.
**Direction:** Counter-trend or trend re-entry

**Qualifying Patterns (High Priority):**
- Bearish Engulfing at resistance
- Bullish Engulfing at support
- Morning Star at support
- Evening Star at resistance
- Three Black Crows after failed breakout attempt

**Required Inputs:** OHLCV, defined support/resistance levels
**Structural Level Definition:** Must be pre-defined via horizontal support/resistance, prior swing high/low, or moving average — NOT drawn retrospectively.

**Implementation Notes:**
- The candlestick pattern alone is NOT sufficient — must occur at a structural level
- Confirm with at least one of: RSI divergence, volume surge, prior support/resistance test
- Pattern must complete (final candle must close) before entry

**Status: INCLUDE (conditional on structural level requirement)**

---

### 1.3 Inside Bar Directional Bias
**Rule:** When an inside bar closes within the bottom 25% of the prior candle's range, expect a downside breakout.
**Source:** Bulkowski (equities)
**Direction:** Short bias
**Confidence:** 70% directional bias (equities data)

**Implementation:**
- `inside_bar = (High[0] <= High[1]) AND (Low[0] >= Low[1])`
- `close_position = (Close[0] - Low[1]) / (High[1] - Low[1])`
- `short_bias = close_position < 0.25` → 70% downside probability
- Entry: Short on next bar open or on break of inside bar low
- Stop: Above inside bar high

**Status: INCLUDE — backtest on crypto**

---

## Family 2: Trend-Following Rules

### 2.1 EMA Crossover System
**Rule:** Enter long when short EMA crosses above long EMA; short when crosses below.
**Source:** CryptoCred observation that "90% of Twitter traders would be better off trading EMA crossover than their current system"

**Standard Variants:**
- 9/21 EMA (short-term)
- 20/50 EMA (medium-term)
- 50/200 EMA (golden cross / death cross — lagging but reliable for trend direction)

**Critical Limitations:**
- Lagging indicator — enters after trend established
- Whipsaws heavily in sideways markets
- Optimal parameters change by asset and timeframe (optimization risk)

**Implementation Notes:**
- Do NOT use EMA crossover in isolation — combine with volume or ADX filter
- ADX > 25 suggests trending market (reduce whipsaws)
- Backtest multiple parameter combinations to check parameter sensitivity (avoid overfit)

**Status: INCLUDE — as baseline / benchmark, NOT as primary signal**

---

### 2.2 Moving Average as Dynamic Support/Resistance
**Rule:** Price pulling back to key MA in an established trend = potential re-entry.
**Direction:** With trend

**Common MAs used:**
- 20-period EMA (short-term trend)
- 50-period EMA/SMA (medium trend)
- 200-period SMA (long-term trend / bear/bull distinction)

**Implementation Notes:**
- Trend must be established (price above MA for X bars, MA sloping upward)
- Entry trigger needed on MA touch (candlestick reversal or small-range bar)
- Stop: Below MA support level + ATR buffer

**Status: INCLUDE**

---

## Family 3: Momentum / Divergence Rules

### 3.1 RSI Divergence (Trend-Aligned)
**Rule:** Enter when RSI shows divergence DURING an established trend, with additional confirmation.
**NOT FOR:** Post-impulse candle scenarios; after massive single-bar moves.

**Types:**
- **Regular Bullish Divergence:** Price makes lower low, RSI makes higher low → potential trend reversal up
- **Regular Bearish Divergence:** Price makes higher high, RSI makes lower high → potential trend reversal down
- **Hidden Bullish Divergence:** Price makes higher low, RSI makes lower low → trend continuation up
- **Hidden Bearish Divergence:** Price makes lower high, RSI makes higher high → trend continuation down

**Critical Filter (from source):**
- Suppress divergence signals when most recent candle size > 2× ATR (impulse candle)
- Divergence must form over multiple bars, not on a single spike

**Implementation Notes:**
- RSI period: 14 (standard); test 7 and 21 for crypto timeframes
- Require price confirmation (e.g., close above prior swing high for bullish divergence)
- Works better on higher timeframes (daily > 4h > 1h)

**Status: INCLUDE — conditional on trend filter and impulse candle filter**

---

### 3.2 Bollinger Band Squeeze / Expansion
**Rule:** When BB width compresses to a multi-period low (squeeze), expect an imminent volatility expansion / breakout.
**Direction:** Ambiguous until breakout direction is confirmed.

**Implementation:**
- `BB_width = (Upper_Band - Lower_Band) / Middle_Band`
- `squeeze = BB_width < N-period minimum of BB_width`
- Entry: Only after breakout direction established (NOT on squeeze alone)
- Combine with: Volume surge, candlestick pattern, or price pattern breakout

**Status: CONDITIONAL — use as breakout filter, not directional signal**

---

## Family 4: Measured Move / Target Projection Rules

### 4.1 Measured Move Targets
**Rule:** After completing the first leg of a two-leg move, project a target equal to the first leg's length.
**Application:** Flags/pennants, measured move up/down patterns, ABCD pattern.

**Critical Caveat (Bulkowski):**
- Target achievement rates are disappointing: 52-63% for flags/pennants
- Measured move targets should be DISCOUNTED by 30-50%
- Use measured move as upper bound, not expected outcome

**Implementation:**
- Conservative target: 50% of measured move
- Full target: 100% of measured move (less reliable)
- Do not hold for full target in high-volatility crypto environments

**Status: INCLUDE — with discounted targets**

---

### 4.2 Fibonacci Retracement Zones
**Rule:** After a significant move, price often retraces to Fibonacci levels (38.2%, 50%, 61.8%) before resuming.
**Source:** Widely cited in source material (50% and 61.8% specifically mentioned).

**Critical Assessment:**
- Fibonacci levels have some empirical support in forex and equities due to widespread trader use (self-fulfilling prophecy dynamic)
- In crypto, multiple Fibonacci levels exist simultaneously — cherry-picking the "relevant" level after the fact is a form of lookahead bias
- To operationalize correctly: define the prior swing clearly, compute levels before price reaches them, do not "find" the relevant level after it already held

**Implementation:**
- Define prior swing: most recent significant high-to-low or low-to-high move
- Pre-compute levels at 38.2%, 50%, 61.8%
- Wait for price to enter zone AND show reversal candlestick OR divergence
- Treat ALL three levels as potential support/resistance zones, not just the one that "worked"

**Status: CONDITIONAL — operationalizable with strict swing definition rules**

---

## Family 5: Volatility / Regime Rules

### 5.1 ATR-Based Stop Loss
**Rule:** Place stop loss at entry price ± (ATR × multiplier).
**Source:** Turtle Traders system (referenced in source material)
**Standard:** ATR(14) × 2 for stop distance.

**Why This Works:**
- Stop is proportional to current market volatility
- Prevents stops that are "too tight" (whipsawed by noise) or "too wide" (excessive risk)
- Regime-adaptive: wider stops in high-volatility environments

**Implementation:**
- ATR period: 14 (standard); consider 7 or 21 for crypto
- Multiplier: 1.5 to 3.0 (system parameter — optimize but check for overfit)
- True Range = max(High - Low, |High - PrevClose|, |Low - PrevClose|)
- Stop distance = ATR(14) × multiplier
- Long stop: Entry - stop_distance
- Short stop: Entry + stop_distance

**Status: INCLUDE — core risk module**

---

### 5.2 Volatility Regime Filter
**Rule:** Classify market into "trending," "ranging," or "explosive" regime before applying pattern signals.
**Rationale:** Most patterns only work in specific regimes. Trend-following fails in ranges; mean-reversion fails in trends.

**Implementation Options:**
- ADX > 25 = trending regime
- ATR relative to N-period mean: high ATR = explosive/volatile, low ATR = compressed/ranging
- BB width relative to N-period mean: same as ATR relative
- Price vs. key MAs: above 200 SMA = bull regime, below = bear regime

**Status: INCLUDE — as regime classification layer**

---

## Family 6: Market Structure Rules

### 6.1 Support and Resistance Levels
**Rule:** Price levels where price historically reversed or consolidated are relevant for future price action.
**Assessment:** This is one of the most empirically supported concepts in TA across all markets.

**Implementation:**
- Identify via: prior swing highs/lows, round numbers, high-volume nodes (VPOC), prior pattern levels
- Level strength: number of touches, time spent at level, volume at level
- Do NOT draw support/resistance retrospectively to fit a trade

**Status: INCLUDE — as structural context layer**

---

### 6.2 Dead-Cat Bounce Recognition
**Rule:** After a large drop (>15-20%), be skeptical of immediate recoveries. Expect continuation lower.
**Source:** Bulkowski: event decline averages 25%, subsequent decline another ~15% from event low.
**Application:** After a large event-driven drop, do NOT buy the initial bounce as a reversal.

**Implementation:**
- Identify "event decline": drop > 15% in single or few bars
- Tag as "dead-cat bounce candidate"
- If price bounces and shows bearish pattern, short the continuation
- Measured move target: ~15% below event low

**Status: INCLUDE — as risk and short entry rule**

---

## Family 7: Fundamental Universe Filters

### 7.1 Fully Diluted Market Cap Filter
**Rule:** Exclude assets where fully diluted market cap is > 5× current market cap (severe future dilution risk).
**Source:** Source 5 (economics)
**Implementation:** Requires token supply schedule data; apply as pre-trade filter.

**Status: INCLUDE — as universe filter**

---

### 7.2 Volume/Liquidity Filter
**Rule:** Only trade assets meeting minimum 24h volume threshold (e.g., $5M minimum USD volume).
**Rationale:** Low-volume assets are prone to manipulation, stop-loss hunting, and slippage.
**Source:** Implied by source discussion of manipulation and stop-loss hunting.

**Status: INCLUDE — core universe filter**

---

## Family 8: Meta-Rules (Process / Risk Management)

### 8.1 R-Multiple Position Sizing
**Rule:** Size every position so that the maximum loss is a fixed fraction R of portfolio (e.g., R = 1%).
**Source:** Source 1/2 explicitly describe R-multiple system.
**Formula:** `position_size = (portfolio_value × R) / stop_distance_in_currency`

**Status: INCLUDE — core risk module**

---

### 8.2 Trading Plan Completeness Check
**Rule:** Do not enter any trade without all five components defined:
1. Thesis (directional bias and reason)
2. Setup (specific conditions that must be met)
3. Entry (specific price/condition)
4. Risk (stop loss level)
5. Reward (price target)

**Status: INCLUDE — as system validation layer**

---

### 8.3 No-Trade Filters
**Rule:** Do not enter trades under any of these conditions:
- Volume spike anomaly (possible pump & dump)
- Spread > 0.5% (insufficient liquidity)
- Asset in "dead-cat bounce" window
- Market regime = "explosive volatility" without breakout confirmation
- News event pending (scheduled major announcements)

**Status: INCLUDE — as pre-trade gate**

---

## Summary: Rule Families by Implementation Priority

| Priority | Family | Status |
|---|---|---|
| 1 | ATR-based stop loss | INCLUDE |
| 1 | R-multiple position sizing | INCLUDE |
| 2 | Chart pattern breakout (confirmed) | INCLUDE |
| 2 | Candlestick reversal at structural level | INCLUDE |
| 3 | Volatility regime filter | INCLUDE |
| 3 | Support/resistance level detection | INCLUDE |
| 4 | EMA crossover (baseline/benchmark) | INCLUDE |
| 4 | RSI divergence (conditional) | INCLUDE |
| 5 | Inside bar directional bias | INCLUDE — backtest |
| 5 | Dead-cat bounce recognition | INCLUDE |
| 6 | Measured move targets (discounted) | INCLUDE |
| 6 | Fibonacci retracements (strict definition) | CONDITIONAL |
| 7 | Volume/liquidity filter | INCLUDE |
| 7 | Fully diluted market cap filter | INCLUDE |
| 8 | BB squeeze as breakout precursor | CONDITIONAL |
| 8 | MA as dynamic support/resistance | INCLUDE |
| 9 | Trading plan completeness check | INCLUDE (process) |
| 9 | No-trade filters | INCLUDE (process) |
