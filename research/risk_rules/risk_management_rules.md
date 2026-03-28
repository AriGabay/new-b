# Risk Management Rules
## Generated: 2026-03-28
## Source: Phase 1 Research Corpus

---

## Overview

This document catalogs all risk management concepts extracted from the source corpus and converts them into formal, operationalizable rules. Risk rules are separated from signal rules because they apply universally, regardless of which pattern or strategy triggers the entry.

**Fundamental principle (from source):** "The success that a trader achieves in the markets is directly correlated to one's trading discipline or lack thereof. Trading discipline is 90 percent of the game."

---

## Risk Rule 1: Capital Allocation per Trade (R-Multiple)

### Definition
Risk a fixed fraction R of total portfolio equity on every trade.

### Formula
```
R = portfolio_value × risk_fraction_per_trade
position_size = R / stop_distance_in_price_units
```

### Recommended Parameters
- `risk_fraction_per_trade`: 0.5% to 2% of portfolio per trade
  - Conservative: 0.5%
  - Standard: 1%
  - Aggressive: 2% (only for high-confidence setups)
- This parameter should be FIXED, not variable per trade (prevents unconscious risk escalation)

### Why This Matters
- If R = 1% and portfolio = $100,000, max loss per trade = $1,000
- You can lose 50 consecutive trades before portfolio drops to ~60% (survival through drawdown)
- Position sizing via R-multiple decouples position size from "conviction" (conviction is untrustworthy)

### Implementation Requirements
- Portfolio equity tracked in real-time
- Stop distance calculated BEFORE position sizing
- Position size = R / stop_distance (in asset price units per contract)
- Maximum position size cap to prevent concentration risk

### Status: INCLUDE — CORE MODULE

---

## Risk Rule 2: ATR-Based Stop Loss Placement

### Definition
Place stop loss at a distance proportional to the asset's Average True Range.

### Formula
```
ATR_period = 14 (default; test 7, 21)
stop_distance = ATR(ATR_period) × multiplier
long_stop = entry_price - stop_distance
short_stop = entry_price + stop_distance
```

### Recommended Parameters
- Multiplier range: 1.5× to 3×
  - Tight: 1.5× (more stops hit, smaller per-trade loss)
  - Standard: 2.0×
  - Wide: 3.0× (fewer stops hit, larger per-trade loss if hit)
- Do NOT use the same multiplier for all timeframes/assets — volatility scales differently

### Why This Matters (vs. Fixed Percentage Stops)
- Fixed % stops (e.g., "always stop out at -3%") ignore volatility
- A 3% stop on a 5% daily ATR asset = extremely tight, will whipsaw constantly
- A 3% stop on a 0.5% daily ATR asset = extremely wide, wastes capital
- ATR-scaled stops are regime-adaptive

### Failure Modes
- ATR can spike after large moves, making stops very wide temporarily (acceptable — means market is explosive)
- In extremely low-volatility environments, ATR may suggest very tight stops that don't account for spread/slippage
- Parameter optimization risk: avoid overfitting multiplier to historical data

### Status: INCLUDE — CORE MODULE

---

## Risk Rule 3: Portfolio-Level Exposure Limits

### Definition
Cap total open risk at portfolio level, not just per-trade.

### Rules
```
max_simultaneous_trades = N (e.g., 5-10)
max_total_open_risk = max_simultaneous_trades × R
max_correlated_exposure = 2× R in any single correlated cluster
```

### Rationale
- In crypto, most assets are highly correlated with BTC
- Opening 10 trades that all short altcoins in a BTC bear market creates ~10× concentration risk
- Portfolio-level risk must be managed, not just per-trade risk

### Correlation Clusters to Monitor
- BTC-correlated (most altcoins): treat as one cluster
- ETH ecosystem (DeFi tokens)
- Layer 1 competitors
- Meme/speculation coins
- Stablecoins (near-zero volatility)

### Status: INCLUDE — CORE MODULE

---

## Risk Rule 4: Stop Loss Placement Anti-Gaming

### Definition
Do not place stop losses at obvious, round-number, or textbook levels.

### Source
Stop-loss hunting: "intentionally pushing the price down through a major support level to trigger stop-loss orders." Easier on thin-volume assets.

### Rules
- Never place stop exactly AT a round number (e.g., $1.00, $50,000)
- Add/subtract 0.3-0.5% randomization or shift stop by ATR × 0.1 beyond the obvious level
- Never cluster stop at the same price as a textbook double-bottom confirmation level
- Consider the "liquidity map" — where obvious stops would cluster

### Implementation
- If pattern-defined stop would be at an obviously clustered level, push stop 1-2% beyond
- For low-volume altcoins: use mental stops or conditional orders, not hard limit stops on exchange

### Status: INCLUDE — RISK QUALITY RULE

---

## Risk Rule 5: Liquidity and Universe Filters

### 5a. Minimum Volume Filter
```
min_24h_volume_usd = $5,000,000 (conservative)
min_24h_volume_usd = $1,000,000 (minimum acceptable)
```
Assets below minimum volume threshold: EXCLUDE from trading universe.

### 5b. Minimum Market Cap Filter
```
min_market_cap_usd = $50,000,000 (conservative)
```

### 5c. Fully Diluted Market Cap Ratio
```
max_fdmv_to_market_cap_ratio = 5.0
```
If FDMV > 5× current market cap → EXCLUDE (severe future dilution risk).

### 5d. Spread Filter (at execution time)
```
max_spread_pct = 0.5%
```
If bid/ask spread > 0.5%: DO NOT ENTER, wait for liquidity improvement.

### Status: INCLUDE — UNIVERSE FILTER MODULE

---

## Risk Rule 6: Drawdown Controls

### 6a. Daily Loss Limit
```
daily_loss_limit = portfolio_value × 0.05 (5%)
```
If daily P&L reaches -5%: STOP TRADING for the day. No new entries.

### 6b. Consecutive Loss Pause
```
consecutive_loss_limit = 3 trades
```
After 3 consecutive losing trades: Pause, review setups, reduce position size by 50% for next N trades.

### 6c. Portfolio Drawdown Limit
```
max_portfolio_drawdown = 20%
```
If portfolio drawdown from high-water mark exceeds 20%: HALT all new entries, enter review mode.

### Rationale
- Losing streaks are normal but can escalate via "revenge trading"
- Hard limits prevent catastrophic loss
- Source explicitly warns against "sloppy, rushed, arrogant" trading after losses

### Status: INCLUDE — RISK GOVERNANCE MODULE

---

## Risk Rule 7: Leverage Governance

### Source
CryptoCred BitMEX analysis: "Higher leverage simply means less collateral, not more profit per price move."

### Rules
```
max_leverage = 3× for standard trades
max_leverage = 1× (spot) for uncertain setups
max_leverage = 5× only for highest-confidence setups with tight stops
```

### Critical Points
- Leverage amplifies LOSSES just as much as gains
- Using 10×+ leverage with 5-10% stops = near-certain account blow-up on any losing streak
- Position size in base units must be the controlled variable, not leverage ratio
- Liquidation price must be checked: `liquidation_price = entry - (1/leverage) × entry` approximately

### Status: INCLUDE — LEVERAGE GOVERNANCE MODULE

---

## Risk Rule 8: Manipulation and Pump & Dump Detection

### Source
Pump & dump anatomy: "Core layer gets info 5-6 seconds before others. Outer rim finds out 10-30 seconds later."

### Detection Signals
```
pump_signal_1: price_change_1min > 5% AND volume_spike_1min > 10× average_volume
pump_signal_2: price_change_5min > 10% AND order_book_thin
pump_signal_3: asset is low-cap (<$5M market cap) AND volume_24h suddenly > 5× 7-day average
```

### Rules
- If any pump signal triggers: DO NOT BUY (you are buying from those exiting)
- If already holding and pump signal triggers: consider partial exit
- Blacklist assets where pump patterns are detected frequently

### Status: INCLUDE — SIGNAL QUALITY FILTER

---

## Risk Rule 9: News/Event Risk Management

### Source
AriDavidPaul: "People mistakenly assume the current trend will continue until some exogenous event."

### Rules
- Flag upcoming scheduled events: major protocol upgrades, ETF decisions, regulatory hearings, major earnings (for BTC-correlated stocks like MicroStrategy, Coinbase)
- Reduce position size by 50% going into known high-risk events
- Do NOT hold leveraged positions over major macro risk events (e.g., CPI prints, Fed decisions)

### Status: INCLUDE — EVENT RISK MODULE

---

## Risk Rules Priority Summary

| Priority | Rule | Type |
|---|---|---|
| 1 | R-Multiple position sizing | Core |
| 1 | ATR-based stop loss | Core |
| 1 | Drawdown controls (daily, cumulative) | Core |
| 2 | Portfolio-level exposure limits | Core |
| 2 | Liquidity universe filters | Core |
| 3 | Leverage governance | Core |
| 3 | Stop placement anti-gaming | Quality |
| 4 | Manipulation detection | Quality |
| 4 | News/event risk reduction | Quality |

---

## Critical Warning

All risk rules above are MINIMUM standards. A system that follows these rules will not guarantee profitability, but it will:
1. Survive through losing streaks
2. Prevent catastrophic single-event losses
3. Create conditions where edge (if it exists) can compound over time

A system that ignores these rules will blow up, even if the underlying signals have genuine edge.
