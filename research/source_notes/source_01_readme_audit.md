# Source Audit: learn-crypto-trading README.md
## URL: https://github.com/learn-crypto-trading/learn-crypto-trading.github.io/blob/master/README.md
## Audit Date: 2026-03-28
## Auditor: Phase 1 Research Agent

---

## 1. Source Classification

**Type:** Curated link library / educational index
**Authority Level:** LOW — This is a personal curation project (⧉ Infominer), not peer-reviewed research.
**Primary Value:** Taxonomy of topics; pointers to potentially useful secondary sources (Bulkowski, Murphy).
**Primary Risk:** Most claims are quoted from Twitter threads or blog posts — no statistical backing.

---

## 2. What It Claims

- Technical Analysis is a valid approach to forecasting price movement.
- Basic TA (triangles, patterns, Fibonacci) outperforms advanced patterns (Harmonics, Gartley).
- Risk management via the R-multiple and ATR-based stops is foundational.
- Position sizing is critical ("discipline is 90% of the game").
- Indicators like EMA, RSI, MACD, Bollinger Bands, Ichimoku are standard tools.
- Divergence (RSI vs price) is a leading signal when occurring within a trend.
- Wyckoff phases describe accumulation/distribution cycles.
- Elliott Wave describes multi-scale market structure.
- Fibonacci retracements (50%, 61.8%) and extensions (121%) are valid entry/target tools.
- Harmonic patterns (Gartley) are complex and less reliable than basics.
- Pump & dump groups are real and affect small-cap crypto.
- Stop-loss hunting by whales is real, especially on low-volume coins.
- BTC 4-year halving cycle is "programmed into the system."
- Alt season correlates with ETH bottoming.
- CME Futures contract dates may influence BTC price around expiry.

---

## 3. Market Behavior References

| Concept | Market Behavior |
|---|---|
| ATR trailing stop | Volatility-scaled exit trigger |
| EMA crossover | Trend-following momentum signal |
| RSI divergence | Momentum exhaustion leading price reversal |
| Wyckoff phases | Institutional accumulation/distribution cycles |
| Pump & dump | Coordinated price manipulation in thin markets |
| Stop-loss hunting | Engineered liquidity grabs at known stop clusters |
| BTC halving cycle | Supply-shock-driven macro price cycles (~4yr) |
| Alt season | Capital rotation from BTC to altcoins |
| CME expiry effect | Derivatives-driven price pressure near contract settlement |

---

## 4. Assumptions Embedded in Claims

- Price patterns repeat because human psychology repeats (behaviorist assumption).
- Volume confirms price moves (volume precedes price).
- Retail traders are consistently on the wrong side (contrarian framing).
- BTC halving mechanically reduces supply enough to cause bull runs (stock-to-flow assumption).
- ETH price leads altcoin performance (correlation assumption, may be regime-dependent).
- CME expiry influences spot price (weak, low sample size, likely discontinued or changed).
- Stop-loss hunting is universal in low-liquidity crypto (partially true, regime-dependent).

---

## 5. Failure Conditions

| Concept | Failure Conditions |
|---|---|
| ATR trailing stop | Does not work well in choppy/ranging markets; ATR multiplier choice is arbitrary |
| EMA crossover | Whipsaws in sideways markets; lagging in trending markets |
| RSI divergence | Works poorly after impulse candles; easily faked in manipulated markets |
| Wyckoff phases | Extremely subjective pattern fitting; no operational definition given |
| BTC halving cycle | Sample size = 3 events; adoption and macro context change each cycle |
| Alt season / ETH indicator | Correlation may break in regime changes; ETH itself may be manipulated |
| CME expiry effect | Low statistical power; market structure changed significantly post-2020 |
| Stop-loss hunting | Difficult to distinguish from genuine breakdowns |

---

## 6. Classification of Each Claim

| Claim | Type | Status |
|---|---|---|
| ATR-based stop loss | Heuristic → Operationalizable | Hold as hypothesis |
| R-multiple position sizing | Heuristic → Well-defined | Include in risk framework |
| EMA crossover baseline | Testable | Hypothesis for backtesting |
| RSI divergence in trend | Heuristic → Conditionally testable | Hold as conditional hypothesis |
| Wyckoff phases | Descriptive, subjective | Reject for automated use |
| Elliott Wave | Descriptive, highly subjective | Reject for automated use |
| Fibonacci 50%/61.8% retracements | Partially testable | Hold as hypothesis with strict operational definition |
| Harmonic patterns (Gartley) | Complex, low reliability | Reject |
| Pump & dump awareness | Regime knowledge, not tradable rule | Operational awareness only |
| Stop-loss hunting | Partially testable (liquidity cluster analysis) | Hold as structural hypothesis |
| BTC halving 4-year cycle | Descriptive, n=3 | Reject as trading rule; monitor as macro context |
| Alt season / ETH leading | Testable correlation claim | Hold as hypothesis |
| CME expiry effect | Low evidence | Reject pending stronger data |
| Trading plan structure | Process framework | Include in system design (not trading signal) |
| MACD criticism | Contextual critique | Valid — MACD alone is insufficient |
| "No magic indicator" | Meta-observation | Valid meta-principle |

---

## 7. Lookahead Bias Risk

- Several described patterns (e.g., "when the bottom forms" or "after the bounce") rely on knowing where price eventually went — no operational entry point specified.
- Fibonacci levels require labeling prior swings — if swings are defined post hoc this introduces bias.
- Wyckoff phase identification is entirely retrospective in most retail descriptions.

---

## 8. Redundancies Identified

- Sources 1 and 2 (README.md and general/) are nearly identical content — same curation, same links, same quotes.
- RSI and Stochastic RSI are explicitly noted as redundant (the source itself says "pick one").
- Multiple momentum indicators (RSI, MACD, Stochastic, CCI) are all variations of the same underlying question (momentum direction/divergence).

---

## 9. Overall Source Assessment

**Verdict:** Low direct alpha value. High taxonomic value.
This source functions as an index of trading concepts, not a trading system. Its value is in establishing the domain vocabulary and pointing toward more rigorous secondary sources (Bulkowski, Murphy). No claim from this source alone warrants inclusion as a live rule.

The source explicitly acknowledges its own limitations ("no magic indicator"). This intellectual honesty is noted and partially validates the meta-principles (position sizing, risk management, discipline) even though the specific technical claims lack quantitative backing.
