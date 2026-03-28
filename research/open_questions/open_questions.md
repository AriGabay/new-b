# Open Research Questions
## Generated: 2026-03-28
## Source: Phase 1 Research Corpus

---

## Overview

These are unresolved questions that emerged during source corpus analysis. They must be answered before implementation or validation can be completed correctly. Some require additional research, some require data, and some require architectural decisions.

---

## Category 1: Statistical Questions (Require Backtesting)

### OQ-001: Do Bulkowski's Equity Statistics Transfer to Crypto?
**Question:** Do the failure rates and average move statistics from Bulkowski's equity pattern research (US stocks, 1990s-2000s) apply to cryptocurrency markets?
**Why It Matters:** Our entire hypothesis set is built on Bulkowski priors. If crypto failure rates are 2× higher, many hypotheses collapse.
**Resolution:** Replicate Bulkowski's study methodology on crypto OHLCV data. Compute failure rates, average moves, and target achievement rates for the 10 critical patterns identified.
**Priority: CRITICAL**

---

### OQ-002: What Is the Appropriate Lookback for Pattern Detection in Crypto?
**Question:** How many bars back should pattern detection look? The "right" lookback will differ between daily, 4h, and 1h timeframes, and may differ between bull and bear markets.
**Why It Matters:** A double bottom formed over 3 bars is different from one formed over 30 bars. Short lookbacks produce noisy patterns; long lookbacks produce stale patterns.
**Resolution:** Empirically test lookback lengths on crypto data for each pattern type.
**Priority: HIGH**

---

### OQ-003: How Do Crypto Patterns Perform Across Regimes?
**Question:** Do patterns that work in bull markets work equally well in bear markets? The source material gives equity statistics (which may be biased toward bull market conditions).
**Sub-questions:**
- H&S tops likely work better in bear markets (macro alignment)
- Inverse H&S bottoms likely work better in early bull markets
- Does regime conditioning improve all pattern performance?
**Resolution:** Segment backtests by BTC macro regime (bull/bear/ranging, defined by 200-SMA) and compare pattern performance per regime.
**Priority: HIGH**

---

### OQ-004: Does Volume Confirmation Materially Improve Pattern Performance?
**Question:** The source references volume confirmation multiple times but provides no statistics on the improvement.
**Specific Tests Needed:**
- High-volume breakout vs. low-volume breakout for ascending/descending triangles
- Volume at support tests for double bottoms
**Resolution:** Backtest patterns with and without volume filter; measure improvement in failure rates.
**Priority: HIGH**

---

### OQ-005: What is the Optimal ATR Multiplier for Crypto Stop Losses?
**Question:** The source recommends ATR × 2 (Turtle Traders). Is this optimal for crypto, which has higher volatility than equities?
**Sub-question:** Should the multiplier vary by timeframe? (Shorter timeframes = higher noise = may need wider multiplier)
**Resolution:** Parameter sweep on multiplier (1.0 to 4.0) for several strategies; analyze Sharpe ratio sensitivity curve. Accept a range where Sharpe is flat (robust), not the single optimal point.
**Priority: HIGH**

---

### OQ-006: Is RSI Divergence Better on Specific Timeframes in Crypto?
**Question:** Source says divergence is better in "discernible trends" — but which timeframe is best for detecting usable divergences in crypto?
**Hypothesis:** Daily > 4h > 1h for reliability; 1h divergence may be noise.
**Resolution:** Backtest conditional RSI divergence (H3-001) across 1h, 4h, and daily on BTC/ETH.
**Priority: MEDIUM**

---

### OQ-007: What Fraction of Crypto "Double Bottoms" Confirm?
**Question:** Bulkowski found only 1/3 of equity double bottoms confirm (close above the mid-peak). Is this fraction similar in crypto?
**Why It Matters:** If 1/3 confirm in crypto too, it validates the confirmation rule. If more confirm, the unconfirmed rate may still be too high.
**Resolution:** Count all "visual" double bottoms vs. confirmed double bottoms in crypto data.
**Priority: MEDIUM**

---

## Category 2: Data / Infrastructure Questions

### OQ-008: Which OHLCV Data Source Should Be Used for Backtesting?
**Question:** Different exchanges have different data quality. Binance, Coinbase, Kraken, and aggregated data sources all differ. Which is appropriate?
**Considerations:**
- Exchange-specific data may include manipulation specific to that exchange
- Aggregated data removes exchange-specific noise but may not reflect actual tradable prices
- Spot vs. perpetual futures data for signals
**Resolution:** Establish data source decision matrix:
  - Use Binance spot data as primary (highest liquidity)
  - Cross-check signal performance on Coinbase/Kraken data
  - Separate signal generation from execution exchange considerations
**Priority: CRITICAL (must decide before backtesting)**

---

### OQ-009: What Is the Minimum History Required for Meaningful Pattern Statistics?
**Question:** BTC has history to 2013; most altcoins have 4-6 years of meaningful data; many altcoins have 2-3 years. Is 3 years of daily data sufficient to generate statistically meaningful pattern statistics?
**Statistical Reality:** Many patterns occur infrequently (e.g., H&S top maybe 5-10 per year on daily data). 3 years = 15-30 samples. This is marginally significant at best.
**Resolution:**
- For BTC/ETH: use full history (8+ years)
- For altcoins: pool across multiple assets to increase sample count
- Set minimum sample size threshold: reject any pattern with < 30 occurrences in backtest
**Priority: CRITICAL**

---

### OQ-010: What Transaction Costs Should Be Modeled?
**Question:** How should fees and slippage be modeled in backtests?
**Source Mention:** None (significant gap in the source material)
**Market Reality for Crypto:**
- Maker fees: 0.02-0.10% per side (Binance maker = 0.02% with BNB)
- Taker fees: 0.05-0.10% per side
- Slippage: Depends on order size vs. market depth
- Funding rates on perpetuals: variable but significant (~0.01% per 8 hours)
**Resolution:** Model 0.1% per side (round trip 0.2%) as conservative baseline; test sensitivity.
**Priority: HIGH**

---

### OQ-011: How to Handle Altcoin Survivorship Bias?
**Question:** Any altcoin dataset will exclude dead/delisted coins. This creates survivorship bias — patterns measured on surviving coins will look better than they would in a live system.
**Solution:** Include data from delisted coins in backtests. Not always possible.
**Resolution:** Acknowledge survivorship bias in all altcoin backtests; apply survival probability penalty to altcoin strategies.
**Priority: HIGH**

---

## Category 3: Implementation / Architecture Questions

### OQ-012: How to Operationalize Support and Resistance Detection?
**Question:** Support/resistance is conceptually clear but algorithmically difficult. How should levels be detected?
**Candidate Methods:**
1. Prior swing highs/lows (look-back N bars, local max/min)
2. Volume profile (VWAP, POC, value area from volume distribution)
3. Psychological round numbers
4. Moving averages as dynamic levels
**Resolution:** Need to select and test at least one method. Recommended: swing high/low detection with minimum N-bar lookback AND N% price significance filter.
**Priority: HIGH**

---

### OQ-013: How to Define "Prior Trend" for Pattern Context?
**Question:** Many patterns are only valid in specific trend contexts (e.g., evening star in uptrend, not during sideways chop). How should "prior trend" be algorithmically defined?
**Options:**
1. Price vs. N-bar EMA (price above 20-EMA = uptrend)
2. EMA slope (EMA rising = uptrend)
3. ADX threshold (ADX > 25 = trending)
4. Higher highs and higher lows
**Resolution:** Test each method; likely use combination of MA slope + ADX.
**Priority: HIGH**

---

### OQ-014: How to Handle Pattern Conflicts?
**Question:** Multiple patterns may trigger simultaneously or contradict each other on the same asset at the same time (e.g., bullish candlestick pattern at bearish chart pattern resistance).
**Resolution:** Need a pattern scoring/priority system. A confluence of aligned signals should score higher. Conflicting signals should cancel or reduce confidence.
**Priority: HIGH (architecture decision)**

---

### OQ-015: Should the System Trade Spot or Derivatives?
**Question:** The source material mentions both spot trading and leveraged derivatives (BitMEX/Binance Futures). These have very different risk profiles and pattern behaviors.
**Key Difference:** Perpetual futures have funding rates that affect hold cost; forced liquidations create artificial price moves; higher leverage amplifies both profits and losses.
**Resolution:** Phase 1 recommendation: develop on spot first to validate signals; derivatives layer added only after signal validation on spot.
**Priority: HIGH (architecture decision)**

---

### OQ-016: How to Prevent P-Hacking in Pattern Validation?
**Question:** With 25 hypotheses, if we test all of them and publish only the "winning" ones, we will encounter false positives by chance (~5% chance per hypothesis at p=0.05 = ~1.25 expected false positives).
**Resolution:**
- Apply Bonferroni correction: significance threshold = 0.05 / 25 = 0.002
- Or use FDR (False Discovery Rate) control
- Reserve a final OOS holdout set untouched until final validation of pre-selected hypotheses
- Penalize for number of parameters in each strategy
**Priority: CRITICAL (research integrity)**

---

### OQ-017: Is This System Designed for Mean-Reversion or Trend-Following?
**Question:** The source material covers BOTH trend-following patterns (flags, triangles, breakouts) AND reversal patterns (H&S, double tops/bottoms, candlestick reversals). These require different execution approaches and position management styles.
**Resolution:** Define system architecture to support both types; use regime filter to prefer trend-following in trending regime and reversion in ranging regime.
**Priority: HIGH (fundamental architecture question)**

---

## Category 4: Market Structure Questions

### OQ-018: How Does Crypto Market Microstructure Affect Pattern Performance?
**Question:** Unlike equities, crypto trades 24/7, has no central exchange, and has significant cross-exchange arbitrage. How does this affect:
- Gap patterns (less meaningful in crypto)
- Daily open/close significance
- Pattern detection on hourly vs. daily candles
**Resolution:** Start with daily candles to minimize microstructure noise. Build hypotheses on microstructure effects separately.
**Priority: MEDIUM**

---

### OQ-019: How Prevalent Is Stop-Loss Hunting in Crypto?
**Question:** The source asserts stop-loss hunting is common. Is this quantitatively measurable? Do certain assets / market cap tiers have higher rates?
**Sub-question:** Can stop-loss hunting be detected and traded profitably (fading the sweep)?
**Resolution:** This is a separate research workstream — requires tick/orderbook data and specialized analysis.
**Priority: MEDIUM**

---

### OQ-020: Do Patterns Degrade Over Time (Edge Decay)?
**Question:** If patterns like H&S top worked well in 2017-2019 crypto, do they still work in 2024-2026 when crypto markets are more sophisticated?
**Why It Matters:** As more algorithmic traders use the same patterns, the edge may get competed away.
**Resolution:** Test pattern performance by year-cohort; check if performance trends downward over time. Apply rolling-window backtest.
**Priority: HIGH**

---

## Summary: Open Questions by Priority

| Priority | Count | Key Questions |
|---|---|---|
| CRITICAL | 4 | OQ-001, OQ-008, OQ-009, OQ-016 |
| HIGH | 12 | OQ-002 to OQ-007, OQ-010 to OQ-015, OQ-017, OQ-020 |
| MEDIUM | 4 | OQ-006, OQ-018, OQ-019 |
| **TOTAL** | **20** | All unresolved |
