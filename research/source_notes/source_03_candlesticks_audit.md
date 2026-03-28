# Source Audit: learn-crypto-trading.github.io/candlesticks/
## URL: https://learn-crypto-trading.github.io/candlesticks/
## Audit Date: 2026-03-28
## Auditor: Phase 1 Research Agent

---

## 1. Source Classification

**Type:** Curated list of candlestick patterns with Bulkowski statistical references.
**Primary Authority:** Thomas Bulkowski (Encyclopedia of Candlestick Patterns) — legitimate empirical research on equities.
**Critical Caveat:** All Bulkowski statistics are from equity markets (US stocks), not cryptocurrency. Crypto has different volatility regimes, 24/7 trading, no earnings-driven gaps, different liquidity structures. Transfer validity is UNKNOWN.

---

## 2. Core Educational Claims

### 2a. Candlestick Anatomy
- Body: difference between open and close
- Shadow (wick): high/low extending beyond body
- **Claim:** "Long shadows indicate comparative strength between buyers and sellers. Longer shadow → more likely prices move in opposite direction."
- **Assessment:** This is a logical deduction (long lower shadow = buyers rejected lower prices), but "more likely" is vague. Needs operational definition: how long? Relative to what? Not testable as stated.

### 2b. Doji
- Open ≈ Close; all gains/losses returned intrabar
- Signals indecision; appears at potential turning points
- **Assessment:** Doji as a standalone signal is **WEAK**. Indecision does not predict direction. However, doji at key support/resistance or after extended moves may carry more weight as a CONDITIONAL signal. The claim "look for confirmation" is the correct approach but is vague.

---

## 3. Reversal Candlestick Patterns (Bulkowski-Ranked)

### High-Confidence Patterns (Retain as Hypotheses)

| Pattern | Claimed Direction | Bulkowski Notes | Assessment |
|---|---|---|---|
| Three Stars in the South | Bullish reversal | Rare, potent | Rare = small sample size = less reliable statistically in crypto |
| Bearish Engulfing | Bearish reversal | "Reliable" per Bulkowski | Second body larger than first in both directions. Operationalizable. Hold. |
| Morning Star | Bullish reversal | Classic pattern | 3-candle, middle candle is doji/small — operationalizable. Hold. |
| Morning Doji Star | Bullish reversal | More precise morning star | Operationalizable. Hold. |
| Evening Star | Bearish reversal | Classic | Operationalizable. Hold. |
| Three White Soldiers | Bullish reversal (in downtrend) | "Rare bullish reversal" | Definition: 3 consecutive long bullish candles, each opening within prior body. Operationalizable. Hold. |
| Three Black Crows | Bearish reversal (in uptrend) | Well-documented | Operationalizable. Hold. |
| Identical Three Crows | Bearish reversal | "Not common, but reliable" | Each opens near prior close. Hold. |
| Three Outside Up | Bullish reversal | Listed | Operationalizable. Hold. |
| Abandoned Baby | Reversal | Listed with image | Gap-dependent — gaps less common in 24/7 crypto (but do occur). Conditional hold. |

### Weak/Contradicted Patterns (Hold with Skepticism or Reject)

| Pattern | Claimed Direction | Issue | Assessment |
|---|---|---|---|
| Shooting Star | Bearish reversal | Only 60% reversal rate per Bulkowski | **Too close to random (coin flip). Reject as standalone signal.** |
| Three Line Strike (Bearish) | Supposed bearish continuation | Bulkowski: actually bullish reversal | Contradicts conventional teaching. Flag as confusing/unreliable. |
| Inverted Hammer | Supposed bullish reversal | Bulkowski: bearish continuation ~60% | Contradicts textbook — **useful reversal: standard interpretation is wrong. Mark for re-validation.** |
| Matching Low | Supposed reversal | Bulkowski says bearish continuation | Another contradiction. **Reject conventional interpretation.** |

### Continuation Patterns (Less Detail in Source)

| Pattern | Direction | Notes |
|---|---|---|
| Upside Tasuki Gap | Bullish continuation | Gap-dependent |
| Downside Tasuki Gap | Bearish continuation | Gap-dependent |
| Window Falling | Bearish continuation | Gap concept |
| Two Black Gapping | Bearish continuation | Gap-dependent |
| Stick Sandwich | Listed | No detail given |
| Thrusting | Listed | No detail given |
| In Neck | Listed | No detail given |
| Long Black Day | Listed | No detail given |
| Three Inside Up | Listed | No detail given |
| Homing Pigeon | Listed | No detail given |
| Dark Cloud Cover | Listed | No detail given |

**Assessment of unlisted continuation patterns:** Insufficient detail provided to evaluate. All require cross-reference with Bulkowski's actual statistics before use.

---

## 4. Critical Gaps in This Source

1. **No performance statistics provided** beyond narrative claims ("reliable," "rare but potent," "60% of the time"). The source points to Bulkowski but doesn't reproduce his actual numbers.
2. **No timeframe guidance** — do these patterns perform differently on daily vs. 4h vs. 1h candles?
3. **No volume confirmation guidance** stated.
4. **No context filters** — most patterns are claimed to work "in a downtrend" or "in an uptrend" but no operational definition of trend is given.
5. **No crypto-specific adaptation** — all references are to equities.

---

## 5. What Is Operationalizable

A candlestick pattern is operationalizable if:
- The exact open/close/high/low relationships are mathematically defined.
- The context (prior trend direction) can be algorithmically determined.
- The expected outcome (direction of next N candles) is specified.

The following pass this test:
- Bearish Engulfing: `C[1] > O[1]` (prior bull) AND `C[0] < O[0]` (current bear) AND `O[0] >= C[1]` AND `C[0] <= O[1]`
- Morning Star: 3-bar pattern with definable body size thresholds
- Evening Star: inverse of morning star
- Three White Soldiers: 3 consecutive bullish bars each closing within upper portion of prior bar's range
- Three Black Crows: inverse
- Engulfing patterns: body size comparison
- Doji: `|Open - Close| / (High - Low) < 0.1` (small body relative to range)

The following are NOT operationalizable without additional specification:
- "Rare but potent" patterns without statistics
- Any pattern requiring subjective trend identification
- Gap-dependent patterns (gaps are less meaningful in 24/7 crypto)

---

## 6. Lookahead Bias Risk

- All pattern descriptions describe what the pattern looks like AFTER the fact.
- The 3rd candle of a 3-candle pattern is not confirmed until the candle CLOSES.
- System must trigger signals only on bar CLOSE, never on bar open or intrabar.
- This is a standard implementation requirement.

---

## 7. Transfer Risk (Equities → Crypto)

Bulkowski's data is from US equities. Key differences that may affect pattern performance in crypto:
1. **24/7 trading** — no overnight gaps, which changes gap-dependent patterns significantly.
2. **Higher volatility** — patterns may complete and reverse faster; holding periods need recalibration.
3. **Manipulation** — stop-loss hunting can create engineered candlestick patterns (e.g., fake wicks).
4. **Lower liquidity on altcoins** — noise-to-signal ratio higher.
5. **Correlated moves** — BTC dominance means all crypto often moves together, reducing pattern independence.

---

## 8. Overall Source Assessment

**Verdict:** Moderate taxonomic value. Low direct alpha value without crypto-specific backtesting.
The candlestick patterns listed are standard and well-known. Bulkowski's work is the best empirical reference available for pattern statistics. However, these statistics must be re-derived on crypto OHLCV data before use. The source correctly flags contradictions (Inverted Hammer, Matching Low, Three Line Strike) — these are genuinely important and non-obvious. Mark all patterns as **HYPOTHESES** pending crypto backtesting.
