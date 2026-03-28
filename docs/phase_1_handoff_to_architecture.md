# Phase 1 Handoff to Architecture
## Date: 2026-03-28
## From: Research Phase (Phase 1)
## To: Architecture Phase (Phase 2)
## System: Crypto Quantitative Trading System

---

## Handoff Purpose

This document provides a complete transfer of knowledge from Phase 1 (Research) to Phase 2 (Architecture and Implementation). It defines precisely:
1. What concepts survived scrutiny and should influence architecture
2. What the system needs to implement them
3. What data is required
4. What must be excluded from implementation until validated
5. Key architectural decisions that must be made before building

This document should be the first thing read by whoever architects the next phase.

---

## Part 1: What Survived Scrutiny

### 1.1 Risk Management Layer — HIGH CONFIDENCE, IMPLEMENT IMMEDIATELY

These are not trading signals. They are architectural requirements that apply regardless of which signals are used.

**R1: Position Sizing Module (R-Multiple)**
```
Fixed risk fraction per trade: 0.5% - 2% of portfolio
position_size = (portfolio_equity × risk_fraction) / stop_distance_price_units
This module is the single most important component of the system.
```

**R2: Stop Loss Module (ATR-Based)**
```
stop_distance = ATR(14) × multiplier
multiplier range: 1.5 to 3.0
Stop must be placed BEFORE position sizing is calculated.
```

**R3: Portfolio Exposure Limits**
```
max_total_open_risk = max_simultaneous_trades × R
max_correlated_risk = 2× R per correlation cluster (BTC, ETH ecosystem, etc.)
```

**R4: Drawdown Controls**
```
daily_loss_limit = portfolio × 5%
consecutive_loss_limit = 3 trades → halve position size for next 3
max_portfolio_drawdown = 20% → enter halt mode
```

**R5: Universe Filters (Pre-Trade Gate)**
```
min_24h_volume: $5M USD
max_fdmv_to_market_cap_ratio: 5.0
max_spread_at_entry: 0.5%
```

**R6: Execution Quality Gate**
```
All 5 trade components must be defined before entry:
  - Thesis (directional bias + reason)
  - Setup (conditions met)
  - Entry (specific price/condition)
  - Risk (stop loss level)
  - Reward (target level)
```

---

### 1.2 Signal Layer — CANDIDATE SIGNALS (need backtesting infrastructure, not live trading)

**Priority 1 — Build first, test first:**

| Signal | Type | Key Rule | Priority |
|---|---|---|---|
| H&S Top breakout | Pattern | Enter on neckline close below | CRITICAL |
| Inverse H&S breakout | Pattern | Enter on neckline close above | CRITICAL |
| Double Bottom (confirmed) | Pattern | Enter ONLY after close above mid-peak | CRITICAL |
| Triple Bottom | Pattern | Enter after close above highest intervening high | CRITICAL |
| Descending Triangle breakout | Pattern | Enter on confirmed close below support | CRITICAL |

**Priority 2 — Build second:**

| Signal | Type | Key Rule | Priority |
|---|---|---|---|
| Bull Flag breakout | Pattern | Use 50% measured move as target | HIGH |
| Falling Wedge breakout | Pattern | Enter on close above upper trendline | HIGH |
| Pipe Bottom | Pattern | Two adjacent spike lows in downtrend | HIGH |
| High & Tight Flag | Pattern | Prior rapid rise + tight consolidation | HIGH |
| Bearish Engulfing @ resistance | Candlestick | Structural level required | HIGH |
| Morning/Evening Star @ structure | Candlestick | Structural level required | HIGH |
| RSI Divergence (conditional) | Indicator | Context filters required | HIGH |

**Priority 3 — Build after Priority 1-2 validated:**

| Signal | Type | Notes |
|---|---|---|
| EMA Crossover | Trend | Baseline benchmark only |
| Inside Bar directional bias | Bar pattern | 70% directional edge claim |
| Dead-Cat Bounce short | Behavioral | Event-driven risk tool |
| BB Squeeze pre-breakout | Volatility | Filter, not signal |

---

### 1.3 Meta-Rules That Must Be Hard-Coded

These are not negotiable based on source analysis:

1. **Confirmation rule:** No pattern entry until candle CLOSES beyond breakout level. Never enter on intrabar wicks.
2. **Conservative targets:** Use 50% of measured move target. Full measured move targets are systematically optimistic.
3. **Volume check at breakout:** Volume should be above N-period average at breakout (increases signal quality).
4. **No trading after impulse candle for divergence:** RSI divergence signals are suppressed if recent candle > 2× ATR.
5. **No round-number stops:** All stops offset from obvious clustering levels.
6. **No low-volume assets:** Enforce universe filter at all times.

---

## Part 2: What the Architecture Must Include

### 2.1 Core Modules Required

```
Module 1: Data Ingestion
  - OHLCV data feed (Binance spot, primary; configurable)
  - Volume data (24h rolling)
  - On-chain data feed (optional Phase 2, required for MVRV)
  - Token supply/unlock schedule data (optional Phase 2)

Module 2: Preprocessing
  - ATR calculation (14-period, True Range)
  - EMA calculations (multiple periods)
  - Volume normalization (rolling N-period average)
  - Candle classification (body size, shadow ratio, doji threshold)

Module 3: Structural Level Detection
  - Prior swing high/low detection (N-bar lookback, minimum significance %)
  - Horizontal S/R identification
  - Moving average levels (20, 50, 200 EMA/SMA)

Module 4: Pattern Detection Engine
  - Pattern definitions as pure functions of OHLCV arrays
  - Each pattern: defined, parameterized, testable in isolation
  - Pattern output: {pattern_type, direction, breakout_level, confirmation_required}
  - CRITICAL: Zero lookahead — all signals generated on bar CLOSE

Module 5: Signal Confirmation Gate
  - Checks breakout confirmation conditions
  - Checks volume at breakout
  - Checks no-trade conditions (impulse candle, event risk, spread)
  - Outputs: {signal_id, confidence, direction, entry, stop, target}

Module 6: Risk Engine
  - R-multiple position sizing
  - ATR stop placement
  - Portfolio exposure tracking
  - Drawdown control state machine

Module 7: Backtesting Framework
  - In-sample / out-of-sample split (hard boundary, not crossvalidation)
  - Transaction cost model (0.1% per side baseline)
  - Slippage model (0.05% baseline)
  - Reporting: win rate, profit factor, Sharpe, Calmar, max drawdown
  - Parameter sensitivity analysis module (vary each parameter ± 20%)

Module 8: Validation Controller
  - Anti-p-hacking: Bonferroni or FDR correction for multiple hypotheses
  - Holdout set manager (final OOS set not touched during development)
  - Overfitting detection (OOS performance < 60% of IS → reject)

Module 9: Regime Classifier (Future Phase)
  - BTC above/below 200 SMA (bull/bear macro regime)
  - ADX level (trending/ranging classification)
  - Volatility regime (ATR relative to N-period mean)
  - Signal activation per regime
```

### 2.2 Architecture Principles

**Principle 1: Separate Signal Logic from Execution Logic**
- Signal generation → produces {direction, entry, stop, target}
- Execution → handles order placement, position management
- These must never be entangled

**Principle 2: All Patterns Are Hypotheses Until Validated**
- Pattern detection module is in "research mode" by default
- "Research mode" records signals to a database without executing trades
- Only signals from patterns with validated OOS performance can enter "live mode"
- Mode switch requires explicit human approval

**Principle 3: Zero Lookahead Tolerance**
- Every signal must be computable using only data available at bar close time T
- Data at T+1 (next bar's open, etc.) must never be used in signal generation
- This must be enforced at the architecture level, not just by convention

**Principle 4: Parameterization Over Hardcoding**
- Every threshold, period, multiplier must be a configurable parameter
- This enables sensitivity analysis without code changes
- Single configuration file drives all parameters

**Principle 5: Logging Everything**
- Every signal generated (even those not executed) must be logged
- Every trade must have: timestamp, signal source, expected metrics, actual outcome
- This enables ongoing signal quality monitoring and edge decay detection

---

## Part 3: Data Requirements

### 3.1 Minimum Data for Phase 2

| Data Type | Source | Frequency | Priority |
|---|---|---|---|
| BTC/USD OHLCV | Binance spot (or Coinbase) | Daily | CRITICAL |
| ETH/USD OHLCV | Binance spot | Daily | CRITICAL |
| Top-10 altcoin OHLCV | Binance spot | Daily | HIGH |
| Volume (24h USD) | Binance | Daily | HIGH |
| BTC/USD OHLCV | 4h timeframe | 4h | HIGH |
| Order book (bid/ask spread) | Binance real-time | Tick | MEDIUM |
| Token supply schedules | Coingecko / tokenomics.net | Static + updates | MEDIUM |

### 3.2 Data for Future Phases

| Data Type | Source | Notes |
|---|---|---|
| BTC MVRV Ratio | Glassnode / CryptoQuant | Requires API access |
| Hash Rate | Blockchain.com / Glassnode | For hash ribbon indicator |
| Social sentiment | LunarCrush / Santiment | NLP layer |
| News/events calendar | Manually curated / API | Event risk management |
| Perpetual funding rates | Binance / FTX alternatives | For futures strategies |
| Orderbook depth | Binance WebSocket | For microstructure analysis |

### 3.3 Data Quality Requirements

- **No survivorship bias:** Include delisted coins OR acknowledge and quantify survivorship bias impact
- **Adjusted for splits/forks:** Handle chain splits (BCH from BTC, ETC from ETH)
- **Consistent timestamps:** All data normalized to UTC
- **Gap handling:** 24/7 markets have no "overnight" gaps; handle exchange downtime explicitly
- **Historical depth:** Minimum 5 years for BTC/ETH; minimum 3 years for altcoins
- **Training/Test split:** Reserve 2024-2025 as final holdout period; do not touch until last validation step

---

## Part 4: What Must Be Excluded Until Validated

These concepts must NOT be implemented in the signal layer until they have passed validation testing:

### Hard Exclusions (Rejected)
- Elliott Wave counting
- Wyckoff phase identification
- Gartley/Butterfly harmonic patterns
- Hanging Man signals
- Island Reversal signals
- Rounding Top signals
- Pennant in downtrend

### Soft Exclusions (Conditional — test first, implement after validation)
- RSI divergence without context filter
- Fibonacci retracements (require strict swing definition)
- Double Top without mandatory confirmation
- ETH as alt season indicator
- MVRV macro filter (requires on-chain data infrastructure)
- Dead-cat bounce short entries (test first on clean historical events)

### Process Exclusions (Never in automation)
- Discretionary overrides to risk limits
- "High conviction" as justification for larger position
- Trading during account drawdown > 10% without half-size rule
- Entering trades without all five trade plan components defined

---

## Part 5: Decision Points Requiring Architectural Resolution

Before implementation begins, the following decisions must be made explicitly:

| Decision | Options | Recommendation |
|---|---|---|
| Primary data source | Binance, Coinbase, Kraken, aggregated | **Binance spot; cross-check on Coinbase** |
| Training/Test split | 70/30, 80/20, rolling window | **Fixed: train 2017-2022, OOS 2023-2025** |
| P-value correction method | Bonferroni, FDR, holdout only | **Bonferroni (conservative) + strict holdout** |
| Spot vs. derivatives first | Spot only, perps only, both | **Spot first; perps layer added after signal validation** |
| Pattern detection scope | BTC/ETH only, top-10, top-50 | **BTC/ETH only for Phase 2; expand after** |
| Regime conditioning | On from day 1, added later | **Add regime filter after baseline patterns tested** |
| On-chain data | Phase 2, Phase 3 | **Phase 3 (requires separate infrastructure)** |
| Execution connectivity | Manual review, semi-auto, full auto | **Manual review only until OOS validated** |

---

## Part 6: What Phase 2 Should Deliver

Phase 2 (Architecture) must produce:

1. **Data pipeline** — clean, bias-free OHLCV with volume, from Binance spot
2. **Backtesting engine** — with correct in-sample/OOS split, transaction costs, no lookahead
3. **Pattern detection library** — each of the 5 CRITICAL patterns implemented as a pure function
4. **Risk engine** — R-multiple sizing + ATR stop + drawdown controls
5. **Baseline benchmark result** — EMA crossover on BTC daily with exact performance metrics
6. **First pattern backtest result** — H&S Top performance in crypto vs. equity baseline
7. **Sensitivity analysis framework** — parameter sweep infrastructure

Phase 2 is NOT complete until:
- A clean OOS test can be run without touching the holdout set
- At least one pattern has been tested in-sample with sensitivity analysis
- The EMA crossover baseline is documented with performance metrics
- The risk engine has been stress-tested against historical drawdown scenarios (2018, 2020 March, 2022)

---

## Closing Statement

Phase 1 has successfully converted 5 educational sources into a structured, critically analyzed research corpus. The corpus contains:
- **25 testable hypotheses** (0 validated)
- **9 risk rules** (implementation-ready)
- **8 candidate rule families** (implementation-ready, test first)
- **18 rejected concepts** (with explicit reasoning)
- **20 open questions** (must be resolved systematically)

The next phase should not add more concepts. It should build the infrastructure to test the concepts that already exist. The primary risk in Phase 2 is building too much complexity before validating the fundamentals. Start simple. Test the biggest patterns first. Add sophistication only where validated edge exists.

**No concept from Phase 1 should be treated as live alpha. Everything is a hypothesis until the data says otherwise.**
