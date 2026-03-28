# Pattern Taxonomy
## Generated: 2026-03-28
## Source: Phase 1 Research Corpus

---

## Overview

This taxonomy organizes all patterns encountered in the source material into a structured hierarchy. Each pattern is classified by:
- **Type** (Candlestick / Chart Pattern / Indicator Signal)
- **Direction** (Bullish / Bearish / Bidirectional / Neutral)
- **Confirmation Required** (Yes/No)
- **Equity Performance** (Bulkowski statistics, where available)
- **Crypto Status** (Priority / Hold / Reject / Unknown)
- **Operationalizability** (Easy / Moderate / Hard)

---

## Tier 1: Candlestick Patterns

### 1.1 Single-Candle Patterns

| Pattern | Direction | Bulkowski Equity Performance | Crypto Status | Operationalizability |
|---|---|---|---|---|
| Doji | Neutral/Reversal | Indecision; requires confirmation | HOLD — conditional only | Easy |
| Shooting Star | Bearish reversal | 60% reversal rate (weak) | REJECT standalone | Easy |
| Hanging Man | Bearish reversal | 33% reversal rate | REJECT | Easy |
| Inverted Hammer | Bullish reversal (textbook) | ~60% bearish continuation (Bulkowski) | RE-TEST in crypto — direction is reversed | Easy |
| Long Black Day | Bearish | Continuation signal | HOLD | Easy |

### 1.2 Two-Candle Patterns

| Pattern | Direction | Bulkowski Equity Performance | Crypto Status | Operationalizability |
|---|---|---|---|---|
| Bearish Engulfing | Bearish reversal | "Reliable" | HOLD — HIGH PRIORITY | Easy |
| Bullish Engulfing | Bullish reversal | Standard pattern | HOLD | Easy |
| Dark Cloud Cover | Bearish | Listed, no stats given | HOLD | Easy |
| Piercing Line | Bullish | Listed, no stats given | HOLD | Easy |
| Matching Low | Bearish continuation (Bulkowski) | Contradicts textbook reversal | HOLD — test Bulkowski interpretation | Easy |
| Upside Tasuki Gap | Bullish continuation | Strong continuation | HOLD (crypto gap caveat) | Easy |
| Downside Tasuki Gap | Bearish continuation | Continuation | HOLD (crypto gap caveat) | Easy |
| Two Black Gapping | Bearish continuation | Listed | HOLD | Easy |
| Homing Pigeon | Bullish continuation/reversal | Listed | LOW PRIORITY | Easy |
| In Neck | Bearish continuation | Listed | HOLD | Easy |
| Thrusting | Bearish continuation | Listed | HOLD | Easy |
| Meeting Lines | Reversal | Listed | HOLD | Moderate |
| Stick Sandwich | Bullish reversal | Listed | HOLD | Easy |
| Window Falling | Bearish continuation | Gap | LOW PRIORITY (crypto) | Easy |

### 1.3 Three-Candle Patterns

| Pattern | Direction | Bulkowski Equity Performance | Crypto Status | Operationalizability |
|---|---|---|---|---|
| Morning Star | Bullish reversal | Classic, well-documented | HOLD — HIGH PRIORITY | Easy |
| Morning Doji Star | Bullish reversal | More precise | HOLD — HIGH PRIORITY | Easy |
| Evening Star | Bearish reversal | Classic | HOLD — HIGH PRIORITY | Easy |
| Evening Doji Star | Bearish reversal | More precise | HOLD | Easy |
| Three White Soldiers | Bullish reversal | "Rare bullish reversal" | HOLD | Easy |
| Three Black Crows | Bearish reversal | Well-documented | HOLD — HIGH PRIORITY | Easy |
| Identical Three Crows | Bearish reversal | "Reliable" | HOLD | Easy |
| Three Outside Up | Bullish reversal | Listed | HOLD | Easy |
| Three Inside Up | Bullish reversal | Listed | HOLD | Easy |
| Three Line Strike (Bearish) | Bulkowski: bullish reversal | Contradicts textbook | HOLD — test Bulkowski | Easy |
| Three Stars in the South | Bullish reversal | "Rare but potent" | HOLD — rare, small sample | Moderate |
| Abandoned Baby | Reversal | Gap-dependent | HOLD — crypto gap caveat | Moderate |
| Bearish Breakaway | Bearish reversal | "Rare bearish reversal" | HOLD | Moderate |

---

## Tier 2: Multi-Bar / Chart Patterns

### 2.1 Continuation Patterns

| Pattern | Direction | Equity Failure Rate | Target Hit Rate | Crypto Status | Priority |
|---|---|---|---|---|---|
| Bull Flag | Bullish continuation | 12-13% | 52-63% | HOLD | HIGH |
| Bear Flag | Bearish continuation | 12-13% | 52-63% | HOLD | HIGH |
| High & Tight Flag | Bullish continuation | 17% (w/ breakout) | N/A | HOLD | HIGH |
| Pennant (uptrend) | Bullish continuation | 19% | 52-63% | HOLD | MEDIUM |
| Pennant (downtrend) | Bearish continuation | 34% | <80% | REJECT | — |
| Ascending Triangle | Bullish continuation/reversal | Low | N/A | HOLD | HIGH |
| Rectangle (continuation) | Bidirectional | Ambiguous | N/A | LOW VALUE | LOW |
| BARR Bottom | Bullish reversal/continuation | 9% | N/A | HOLD | HIGH |
| BARR Top | Bearish reversal | Not given | N/A | HOLD | MEDIUM |

### 2.2 Reversal Patterns (Multi-Bar)

| Pattern | Direction | Equity Failure Rate | Target Hit Rate | Crypto Status | Priority |
|---|---|---|---|---|---|
| Head & Shoulders Top | Bearish reversal | ~7% | 93% break down | HOLD | CRITICAL |
| Inverse H&S (Bottom) | Bullish reversal | N/A | High | HOLD | CRITICAL |
| Complex H&S Bottom | Bullish reversal | 6% | 82% | HOLD | CRITICAL |
| Complex H&S Top | Bearish reversal | Low | High | HOLD | HIGH |
| Double Bottom (confirmed) | Bullish reversal | 3% | N/A | HOLD | CRITICAL |
| Double Top (confirmed) | Bearish reversal | ~17% | 39% | HOLD | HIGH (reduced target) |
| Triple Bottom | Bullish reversal | 4% | N/A | HOLD | CRITICAL |
| Triple Top | Bearish reversal | 15% | N/A | HOLD | HIGH |
| Falling Wedge | Bullish reversal/continuation | 10% | N/A | HOLD | HIGH |
| Rising Wedge (w/breakout) | Bearish reversal | 6% | N/A | HOLD | HIGH |
| Cup with Handle | Bullish continuation | Low | N/A | HOLD | HIGH |
| Rounding Bottom (confirmed) | Bullish reversal | 5% | N/A | HOLD | MEDIUM (complex detection) |
| Pipe Bottom | Bullish reversal | 12% | N/A | HOLD | HIGH |
| Pipe Top | Bearish reversal | N/A | N/A | HOLD | MEDIUM |
| Descending Triangle | Bearish continuation | 4% | N/A | HOLD | CRITICAL |
| Symmetrical Triangle | Ambiguous | N/A | N/A | HOLD | MEDIUM |
| Diamond Top | Bearish reversal | Rare but reliable | N/A | LOW PRIORITY | LOW |
| Diamond Bottom | Bullish reversal | 69% upside break | N/A | LOW PRIORITY | LOW |
| Broadening Top | Bearish reversal | Bearish, 5-reversal | N/A | HOLD | MEDIUM |
| Broadening Bottom | Bullish reversal | Bullish, 5-reversal | N/A | HOLD | MEDIUM |
| Descending Broadening Wedge | Bullish continuation | 46% avg rise | N/A | HOLD (bull regime) | MEDIUM |
| Dead-Cat Bounce | Bearish continuation | ~15% further drop | N/A | HOLD | HIGH (risk tool) |

### 2.3 Pattern Clusters / Event Patterns

| Pattern | Direction | Notes | Status |
|---|---|---|---|
| Inside Bar (close near prior low) | Bearish | 70% downside | HOLD |
| Inside Bar (close near prior high) | Bullish | Implied inverse | HOLD |
| Outside Bar (continuation context) | With trend | Context-dependent | HOLD |
| Gap (any type) | N/A | Mediocre overall | LOW PRIORITY |
| Island Reversal | Bidirectional | "Mediocre performance" | REJECT |

---

## Tier 3: Indicator Signals

### 3.1 Trend Indicators

| Indicator | Use Case | Assessment |
|---|---|---|
| EMA crossover | Trend direction, momentum | HOLD — basic hypothesis |
| SMA | Baseline trend | HOLD — benchmark comparison |
| Ichimoku Cloud | Multi-component trend | HOLD — complex but operationalizable |
| Bollinger Bands | Volatility / mean-reversion | HOLD — squeeze as breakout precursor |
| ATR | Volatility measurement | CORE — stop sizing and volatility regime |

### 3.2 Momentum/Oscillator Indicators

| Indicator | Correct Use | Incorrect Use | Assessment |
|---|---|---|---|
| RSI | Divergence in trend; momentum strength | OB/OS thresholds as standalone signals | HOLD — divergence mode only |
| Stochastic RSI | Redundant with RSI | — | REJECT (use RSI) |
| MACD | Trend confirmation, divergence | Standalone trigger | HOLD — confirmation filter only |
| CCI | Divergence | Standalone OB/OS | LOW PRIORITY |

### 3.3 Macro/Sentiment Indicators

| Indicator | Use Case | Assessment |
|---|---|---|
| MVRV Ratio | BTC cycle extreme detection | HOLD — macro regime filter; on-chain data needed |
| Fear & Greed Index | Sentiment extremes | HOLD — secondary filter only |
| BTC Dominance | Alt season proxy | HOLD — macro context |
| Hash Ribbon | BTC miner capitulation | HOLD — future research |
| Fully Diluted Market Cap | Universe filter for altcoins | INCLUDE — fundamental universe filter |

---

## Tier 4: Structural / Behavioral Patterns

| Concept | Description | Tradability |
|---|---|---|
| Wyckoff Accumulation | Institutional buying in sideways range | NOT operationalizable as written — too subjective |
| Wyckoff Distribution | Institutional selling at top | NOT operationalizable as written |
| Elliott Wave | 5-wave impulse + 3-wave correction | REJECT for automation — too subjective |
| Fibonacci Retracements | 50%, 61.8% as support/resistance | HOLD as entry zone hypothesis |
| Fibonacci Extensions | 121%, 161.8% as targets | HOLD as target projection |
| ABCD Pattern | Harmonic measured move | HOLD — strict definition exists |
| Gartley Pattern | Complex harmonic | REJECT — too complex, low reliability |
| Butterfly Pattern | Complex harmonic | REJECT — same as Gartley |
| Pump & Dump Detection | Abnormal volume spikes + coordinated buying | HOLD — structural risk filter |
| Stop-Loss Hunting | Engineered liquidity sweeps | HOLD — structural risk awareness |
| Dead-Cat Bounce | Post-crash bounce before continuation | HOLD — short opportunity |

---

## Pattern Priority Matrix

### CRITICAL Priority (implement first for backtesting)
1. Head & Shoulders Top
2. Inverse Head & Shoulders
3. Complex H&S Bottom
4. Double Bottom (confirmed)
5. Triple Bottom
6. Descending Triangle (confirmed breakout)

### HIGH Priority (implement second)
7. Falling Wedge
8. Bull Flag / Bear Flag
9. BARR Bottom
10. Pipe Bottom / Pipe Top
11. High & Tight Flag
12. Morning Star / Evening Star
13. Bearish Engulfing (in downtrend) / Bullish Engulfing (in uptrend)
14. Dead-Cat Bounce (as risk/short tool)
15. Inside Bar with directional close bias

### MEDIUM Priority (after validation of critical/high)
16. Triple Top
17. Double Top (with reduced targets)
18. Rising Wedge (confirmed)
19. Cup with Handle
20. Three White Soldiers / Three Black Crows
21. Symmetrical Triangle

### LOW Priority / Future Research
22. Diamond patterns
23. Broadening formations
24. Rounding patterns (detection complexity)
25. Complex harmonic patterns

### REJECTED
- Hanging Man
- Shooting Star (standalone)
- Island Reversal
- Pennant (downtrend)
- Gartley/Butterfly harmonics
- Elliott Wave (for automation)
- Wyckoff (for automation without redefinition)
- Rounding Top (contradicted)
