# Source Audit: learn-crypto-trading.github.io/general/
## URL: https://learn-crypto-trading.github.io/general/
## Audit Date: 2026-03-28
## Auditor: Phase 1 Research Agent

---

## 1. Source Classification

**Type:** Rendered website version of README.md — substantially identical content.
**Overlap with Source 1:** ~95% identical. Treated as a single source for analytical purposes.
**Marginal New Content:** Slightly expanded descriptions of some concepts.
**Authority Level:** LOW (same as Source 1).

---

## 2. Unique / Incremental Content vs. Source 1

### 2a. Trading Plan Framework (CryptoCred)
Five components explicitly laid out:
1. **Thesis** — directional bias, what price is reaching for
2. **Setup** — conditions required for entry signal
3. **Entry** — specific price levels/conditions
4. **Risk** — stop loss definition, where the setup fails
5. **Reward** — price target

**Assessment:** This is a PROCESS framework, not a trading signal. It is valuable as a template for system design — defining that every trade requires all five components before execution. This is operationalizable and should influence architecture.

### 2b. RSI Nuance
Source explicitly states RSI is NOT an overbought/oversold indicator per its original definition. Correct interpretation: RSI measures momentum strength, not price level extremes.
**Assessment:** Critical nuance. If RSI is used in system, it must be used as momentum/divergence tool, not as static OB/OS threshold trigger.

### 2c. Leverage Mechanics Clarification
BitMEX quiz reveals: leverage level does not change P&L if position size in contracts is the same. Higher leverage = less margin required, not more profit per price move.
**Assessment:** Operationally important. System must track position size in base units, not leverage ratio.

### 2d. ATR Stop Loss (Turtle Traders Reference)
ATR × multiplier (e.g., ATR × 2) for stop loss placement.
**Assessment:** Well-defined, operationalizable. Requires: choosing lookback period for ATR (typically 14), choosing multiplier (system parameter to optimize), and defining whether ATR is measured on close-to-close or true range basis.

### 2e. Divergence Context Rules (CryptoCred)
- "After a big move/candle there will almost always be a regular divergence."
- "Don't use divergence to snipe bottom/top after an impulse candle."
- "Divergences work better when they form during a discernible trend."

**Assessment:** This is a CONDITIONAL rule that could be operationalized:
- Measure the size of the most recent candle as a multiple of ATR.
- If recent candle > N × ATR: suppress divergence signal.
- Only look for divergence signals within established trends (defined by e.g., MA slope).

### 2f. CNBC Reverse Indicator
Claimed: when CNBC covers a crypto asset bullishly, it marks a top.
**Assessment:** Anecdotal, media coverage timing is not systematically tradable. REJECTED.

### 2g. Fear and Greed Index Reference
Mentioned as a tool.
**Assessment:** Sentiment indices have some utility as secondary filters (extreme fear may indicate accumulation zones) but are lagging and noisy. Not sufficient as primary signal. Hold as secondary indicator.

### 2h. Stop-Loss Hunting Mechanics
"Stop-loss hunting is intentionally pushing price through support to trigger stops, creating a flash-crash which can then be used to buy coins cheap. Easiest on anything with low volume outside top 15."
**Assessment:** This is real and documented. Operationally relevant:
- Avoid setting stops at obvious round numbers or just below obvious support.
- Filter out thin-volume pairs from trading universe.
- Consider using mental stops or conditional orders rather than limit stops.

### 2i. Market Manipulation Framing
"Markets do not reflect collective wisdom — prices are manipulated."
**Assessment:** Partially true in crypto (higher than equity markets). This is a regime characteristic, not a tradable rule per se. Relevant for: signal reliability degradation in thin markets, avoiding patterns that depend on "rational" price discovery.

---

## 3. Indicators Inventory (from this source)

| Indicator | Category | Assessment |
|---|---|---|
| EMA (Exponential Moving Average) | Trend / momentum | Operationalizable; requires parameter definition |
| SMA (Simple Moving Average) | Trend | Operationalizable; baseline benchmark |
| MACD | Momentum / trend | Derivative of EMAs; redundant with raw EMA analysis; weak as standalone |
| RSI | Momentum / divergence | Operationalizable in divergence mode; not OB/OS mode |
| Stochastic RSI | Momentum | Redundant with RSI per source; use one |
| Bollinger Bands | Volatility / mean-reversion | Operationalizable; BB squeeze has some predictive value |
| Ichimoku Cloud | Multi-component trend | Complex but operationalizable; requires defining which components to use |
| ATR | Volatility | Operationalizable for stop sizing; well-established |
| Fear & Greed Index | Sentiment | Secondary filter; not primary signal |

---

## 4. Overall Source Assessment

**Verdict:** Near-identical to Source 1. The incremental value is in:
- CryptoCred's trading plan framework (valuable for system architecture)
- ATR stop loss (valuable for risk framework)
- Divergence context rules (valuable conditional hypothesis)
- RSI clarification (important for correct implementation)
- Manipulation awareness (important regime characteristic)

No additional trading alpha is extracted from this source vs. Source 1.
