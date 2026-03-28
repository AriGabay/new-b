# Source Audit: learn-crypto-trading.github.io/fundamentals/economics/
## URL: https://learn-crypto-trading.github.io/fundamentals/economics/
## Audit Date: 2026-03-28
## Auditor: Phase 1 Research Agent

---

## 1. Source Classification

**Type:** Curated link library — "cryptoeconomics" resources.
**Primary Value:** Macro/fundamental context for crypto markets; valuation frameworks; market narrative theory.
**Authority Level:** LOW-MEDIUM for trading signals; MEDIUM for macro context.

**Important Note:** This source contains ZERO operational trading rules. It is a collection of links and quotes about cryptocurrency economics, token design, and monetary theory. It does not provide price action signals, pattern statistics, or backtested edge. Its value is in providing macro context that may help define regime filters.

---

## 2. Concepts Extracted and Analyzed

### 2a. Bitcoin MVRV Ratio (Market Value to Realized Value)
**Claim:** MVRV measures whether BTC price is above or below the average price at which all coins were last moved.
- MVRV > 1: Current price > average cost basis → holders in profit
- MVRV < 1: Current price < average cost basis → holders at a loss

**Assessment:** MVRV is a real, widely-tracked on-chain metric. It has shown some correlation with market cycle extremes (MVRV > 3.5 tends to be historically near cycle tops; MVRV < 1 near cycle bottoms). However:
- It's a slow-moving indicator
- It requires on-chain data infrastructure
- It has degraded in predictive accuracy as derivatives markets grew
- NOT a short-term signal; potentially useful as MACRO REGIME FILTER

**Status:** HOLD AS MACRO CONTEXT INDICATOR. Requires on-chain data source.

### 2b. BTC Halving 4-Year Cycle
**Claim:** Bitcoin's supply issuance halves every ~4 years, mechanically reducing selling pressure from miners, historically preceding bull markets.

**Evidence:** n=4 events (2012, 2016, 2020, 2024). Each preceded a significant bull run 6-18 months later.

**Assessment:**
- Sample size of n=4 is statistically trivial.
- Correlation observed, causation debated.
- Each cycle has been different in character (adoption curve effects, derivatives market maturation, institutional participation).
- The 2024 halving occurred with ETF inflows coinciding, making it unclear what drove the 2024-2025 bull run.
- CANNOT be treated as a reliable trading rule.
- Value: As a coarse macro regime indicator (are we in pre-halving accumulation, post-halving euphoria, post-peak bear?).

**Status:** HOLD AS COARSE MACRO CONTEXT. Do NOT use as a trading signal.

### 2c. Alt Season / ETH as Leading Indicator
**Claim:** ETH bottoming is a signal for broader altcoin season.
Source quote: "Use ETH as your leading indicator for 'when alt season?', and wait for it to bottom out before buying alts."

**Assessment:**
- This is an anecdotal observation with no statistical backing provided.
- There is some structural logic: capital flows from BTC → ETH → large caps → small caps in risk-on phases.
- However, this correlation breaks down in bear markets, regulatory events, and sector-specific narratives.
- Defining "bottom" for ETH is itself a difficult problem.
- Not operationalizable without defining: how to detect ETH bottom, what "alt season" means quantitatively, what lag to expect.

**Status:** HOLD AS MACRO CONTEXT HYPOTHESIS. Requires quantitative definition before testing.

### 2d. Token Valuation Models
Three approaches mentioned:
1. **Cost of production** — mining cost as price floor
2. **Equation of exchange** (MV = PQ) — velocity-based value
3. **Network value** — Metcalfe's law (value ∝ n²)

**Assessment:**
- These are all **fundamentals-based valuation models**, not trading signals.
- Cost of production for PoW coins (BTC, ETH pre-merge) has some empirical basis as a floor estimate, but miners have varied cost structures.
- MV = PQ has been widely criticized as inapplicable to cryptocurrencies (velocity assumption is broken by HODLing behavior).
- Metcalfe's law has shown empirical fit in studies but is circular (price drives adoption which drives network effect).
- None of these produces a timing signal.

**Status:** EDUCATIONAL/CONTEXTUAL. Not tradable rules. Could be used to define "fundamentally cheap/expensive" zones for macro regime classification.

### 2e. Fully Diluted Market Value (FDMV)
**Claim:** Current market cap excludes future dilution from unvested tokens, options, etc. True value should be assessed at fully diluted level.

**Assessment:** Correct and important for altcoin evaluation. High FDMV relative to current market cap signals major future selling pressure from vesting unlocks. This is operationalizable:
- If FDMV >> current market cap, beware large supply unlocks.
- Token unlock schedules are publicly available (tokenomics.net, coingecko, etc.).

**Status:** HOLD AS FUNDAMENTAL FILTER for altcoin selection. Not a price timing tool but a UNIVERSE FILTER to avoid structurally toxic supply situations.

### 2f. Market Narratives
**Claim:** "Crypto is a battleground for competing narratives. Narratives explain what's happening and inform actions."

**Assessment:** This is empirically true and important. Market narratives drive crypto much more strongly than in equity markets because:
- No underlying cash flows for most coins
- Price is heavily driven by story and sentiment
- Narrative shifts drive sector rotation

However, measuring and trading narratives systematically is difficult. It requires:
- NLP/sentiment analysis of news and social media
- Narrative taxonomy (DeFi, AI, RWA, meme, etc.)
- Historical mapping of narrative cycles

**Status:** IMPORTANT STRUCTURAL INSIGHT. Hold as hypothesis for sentiment/narrative layer of system. Not immediately actionable without data infrastructure.

### 2g. Game Theory / Miner Incentives
**Claim:** Blockchain incentive structures create game-theoretic dynamics (e.g., FOMO3D as "entrapment" game theory).

**Assessment:** Academically interesting, not directly tradable. Mining economics matter for PoW chains (miner capitulation as bottoming signal, hash ribbon indicator), but this is specialized.

**Status:** LOW PRIORITY. Hold as future research topic for miner behavior signals.

### 2h. Austrian Economics References
The source includes references to Austrian economics (Bitcoin Standard, Saifedean Ammous framing).

**Assessment:** This is ideological framing, not trading research. The Austrian economics lens may inform some market participants' long-term conviction, but it produces no operational trading rule.

**Status:** EDUCATIONAL BACKGROUND. No trading value.

### 2i. Byzantine Political Economy / Ecosystem Splits
References to hard forks, network splits, and Metcalfe's law effects on ecosystem splits.

**Assessment:** Fork events create short-term volatility and sometimes create temporary arbitrage opportunities. Fork arbitrage requires sophisticated position management and is a specialized strategy.

**Status:** LOW PRIORITY for now. Flag for future research.

---

## 3. What This Source Is Missing

1. **No price action research** — no patterns, no statistical backing for any trading entry.
2. **No risk metrics** — no discussion of drawdown, position sizing, volatility.
3. **No market microstructure** — no bid/ask spread, order flow, liquidity analysis.
4. **Valuation models are theoretical** — none have demonstrated live trading edge.
5. **Macro claims are narrative, not empirical** — halving cycle n=4, alt season anecdotal.

---

## 4. Extracted Items for Future Use

| Concept | Status | Data Required |
|---|---|---|
| MVRV Ratio as cycle indicator | Macro context indicator | On-chain data (Glassnode, CryptoQuant) |
| BTC halving cycle phase | Coarse regime filter | Halving dates are fixed/calculable |
| ETH as alt season indicator | Correlation hypothesis | ETH/USDT price data + altcoin basket |
| Fully diluted market cap filter | Universe filter | Token supply schedule data |
| Token unlock schedules | Risk filter | Tokenomics data feeds |
| Market narrative sentiment | Secondary signal | NLP infrastructure + social data |
| Hash ribbons / miner capitulation | BTC-specific signal | Hash rate data (blockchain.info) |

---

## 5. Overall Source Assessment

**Verdict:** LOW DIRECT TRADING VALUE. HIGH CONTEXTUAL VALUE.
This source is useful for understanding the macro environment in which trades will occur, not for generating trade signals. The most actionable item is fully diluted market cap as a universe filter. The rest belongs to a "macro regime classification" layer that would contextualize trade signals from other sources.
