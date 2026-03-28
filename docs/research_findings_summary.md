# Research Findings Summary — Phase 1
## Date: 2026-03-28
## System: Crypto Quantitative Trading Research Layer

---

## Purpose

This document provides an executive-level summary of Phase 1 research findings. It is designed to be read by the system architect and implementation team. It distinguishes clearly between what is:
- **Promising** (worth building and testing)
- **Uncertain** (needs testing before implementation decision)
- **Rejected** (do not implement)
- **Untestable** (cannot be operationalized)

---

## Source Material Assessment

The five sources analyzed constitute a curated educational repository for retail crypto traders. The corpus is:
- **Not peer-reviewed**
- **Not statistically derived from crypto data**
- **Primarily US equity-based when statistical** (Bulkowski)
- **Largely anecdotal or from social media** for the non-Bulkowski content

The best material in the corpus — Bulkowski's chart pattern statistics — comes from US equity markets and must be re-validated on crypto before relying on it. Everything else is educational scaffolding.

---

## Section 1: PROMISING — Worth Building and Testing

### 1.1 Risk Management Framework

The most clearly valuable content is the risk management framework. These are not trading signals — they are architectural requirements:

| Rule | Source | Confidence | Status |
|---|---|---|---|
| R-multiple position sizing | Source 1/2 | HIGH — established quant practice | IMPLEMENT |
| ATR-scaled stop losses | Source 1/2 | HIGH — established quant practice | IMPLEMENT |
| Portfolio-level exposure limits | Implied | HIGH — portfolio theory | IMPLEMENT |
| Drawdown controls (daily and cumulative) | Implied | HIGH — essential for survival | IMPLEMENT |
| Liquidity universe filter | Implied | HIGH — avoids thin market manipulation | IMPLEMENT |
| Trading plan completeness gate | Source 2 | HIGH — process discipline | IMPLEMENT |

**Critical note:** These risk rules have value INDEPENDENT of whether any of the trading signals work. A system built on solid risk management with weak signals will survive; a system with strong signals and poor risk management will eventually blow up.

### 1.2 Chart Pattern Framework (High-Confidence Patterns)

These patterns have equity-market statistical backing (Bulkowski) AND logical structural grounding:

| Pattern | Equity Failure Rate | Hypothesis ID | Recommendation |
|---|---|---|---|
| Head & Shoulders Top | ~7% | H1-001 | BUILD AND TEST FIRST |
| Double Bottom (confirmed) | 3% | H1-003 | BUILD AND TEST |
| Triple Bottom | 4% | H1-005 | BUILD AND TEST |
| Descending Triangle (confirmed) | 4% | H1-004 | BUILD AND TEST |
| Complex H&S Bottom | 6% | H1-002 | BUILD AND TEST |
| Falling Wedge | 10% | H1-008 | BUILD AND TEST |
| BARR Bottom | 9% | (H1 group) | BUILD AND TEST |
| Pipe Bottom | 12% | H1-009 | BUILD AND TEST |

**Critical rule derived from Bulkowski:** Always wait for confirmed breakout. Without confirmation, most patterns fail at rates that eliminate any edge. This single rule must be hard-coded into all pattern detection.

### 1.3 Candlestick Reversal Signals (With Structural Context)

These candlestick patterns are operationalizable when occurring at pre-defined structural levels:

| Pattern | Direction | Hypothesis ID |
|---|---|---|
| Bearish Engulfing at resistance | Bearish | H2-001 |
| Bullish Engulfing at support | Bullish | H2-001 |
| Morning Star at support | Bullish | H2-002 |
| Evening Star at resistance | Bearish | H2-002 |
| Three Black Crows (in uptrend) | Bearish | H2-003 |

**Critical note:** These signals are CONTEXT-DEPENDENT. Without a structural level requirement, they are close to noise.

### 1.4 EMA Crossover as Baseline

A 20/50 EMA crossover is the minimum useful benchmark. It is likely to have positive expectancy on BTC daily data. Its primary value is as a COMPARISON BASELINE, not a strategy. Any pattern-based strategy that underperforms simple EMA crossover should be reconsidered.

### 1.5 Dead-Cat Bounce Awareness

After large declines (>15-20% in 1-3 bars), bounces should be treated as temporary, not reversal signals. This has both risk management value (don't buy the bounce as a reversal) and potential short entry value (short the continuation after the bounce fades).

---

## Section 2: UNCERTAIN — Test Before Deciding

### 2.1 RSI Divergence

RSI divergence has some theoretical and empirical basis, but its usefulness depends critically on context filtering. Specifically:
- RSI divergence after impulse candles is nearly meaningless (very common false signals)
- RSI divergence during established trends with no recent spike has more promise
- The hypothesis is testable (H3-001) and should be tested with strict context filters

**Verdict: Test with filters. Do not implement without filtering.**

### 2.2 Bull Flags and High & Tight Flags

Flags work in equities (12-13% failure rate). In crypto, three concerns:
1. Crypto "flags" may not complete as cleanly due to manipulation
2. Target achievement rates are already weak in equities (52-63%)
3. Crypto volatility may mean targets are even less reliable

**Verdict: Test, but use 50% discounted targets. May still produce positive expectancy.**

### 2.3 Fibonacci Retracements (50%, 61.8%)

Fibonacci levels are widely watched, making them partially self-fulfilling. However:
- Multiple levels exist simultaneously — cherry-picking the "right" one is retrospective
- Must be implemented with strict prior-swing definition (automated, pre-defined)
- No Bulkowski-style statistics on Fibonacci in the corpus

**Verdict: Test with strict algorithmic implementation. Skeptical prior, but self-fulfilling dynamics may produce usable zones.**

### 2.4 Bollinger Band Squeeze

BB squeeze as breakout precursor has logical basis (compression → expansion). However:
- It does not predict direction — needs directional filter
- False squeezes (compression without subsequent expansion) are common

**Verdict: Use as secondary filter only. Test whether it improves breakout performance.**

### 2.5 Inside Bar Directional Bias

Bulkowski finding (70% downside probability when close is in bottom 25% of prior bar) is specific and testable. However:
- Sample size concerns in crypto
- May only work on specific timeframes

**Verdict: Test directly. Easy to implement. Valuable if finding transfers.**

### 2.6 ETH as Alt Season Leading Indicator

An anecdotal observation that ETH bottoming precedes broader altcoin recovery.
- Has some structural logic (capital rotation)
- But "bottom" is undefined; lag is undefined; correlation may be spurious

**Verdict: Test as conditional macro filter. Define operational ETH "bottom" criteria before testing.**

---

## Section 3: REJECTED — Do Not Implement

These are rejected with explicit reasoning. Do not revisit without new, substantial empirical evidence:

| Idea | Reason for Rejection |
|---|---|
| Hanging Man as bearish reversal | Only 33% reverse — worse than trend continuation |
| Shooting Star as standalone signal | 60% reversal — too close to random |
| Island Reversals | "Mediocre performance" per Bulkowski |
| Pennant in downtrend | 34% failure rate — above threshold |
| Rounding Top | Contradicted interpretations; source recommends ignoring |
| Elliott Wave for automation | Not falsifiable, highly subjective, no consistent wave count |
| Wyckoff phases for automation | Too subjective, no operational definition |
| Gartley/Butterfly harmonics | Complex, no statistical backing, source says basic > complex |
| CNBC reverse indicator | n=3, anecdotal |
| CME expiry effect | Low evidence, changed market structure |
| BTC halving cycle as signal | n=4, cannot infer rule |
| DOGE cycles as altseason indicator | n=2, absurd sample size |
| Fibonacci mysticism | Pseudoscience — only the self-fulfilling market mechanism is valid |
| Bitcoin moonshot pattern charts | Survivorship and lookahead bias |
| Generic 4-stage market cycle | Retroactive fitting, no predictive power |

---

## Section 4: UNTESTABLE — Cannot Be Operationalized

These ideas were encountered in the corpus but cannot be converted into testable algorithmic hypotheses without fundamental redefinition:

| Idea | Why Untestable |
|---|---|
| "Buy the dip" | No definition of "dip" |
| "Patience is key" | Not a signal |
| "Markets are manipulated" | Observation, not prediction |
| "Conviction investing" | No operational definition |
| "Strong hands vs. weak hands" | Metaphor, not a signal |
| Austrian economics → BTC value | Ideological claim with no timing signal |
| "Narrative drives crypto" | True but requires NLP infrastructure; not directly testable from price data alone |
| Wyckoff Springs/Upthrusts | Requires contextual judgment that cannot be algorithmically codified |
| "Stare at the minute chart for 2 weeks" | Non-algorithmic skill development advice |

---

## Section 5: Meta-Findings and Architectural Implications

### 5.1 The Single Most Important Rule

**Wait for breakout confirmation before entering any chart pattern trade.**

This is the most statistically supported, most consistently stated, and most actionable finding in the entire corpus. Bulkowski demonstrates it across every pattern. It reduces failure rates from unacceptable to reliable. This must be a hard architectural requirement, not optional.

### 5.2 The Second Most Important Rule

**Manage risk with position sizing, not with signal confidence.**

No signal in this corpus is confident enough to justify oversizing. Signal confidence should influence whether to trade (yes/no), not how much to trade. Position sizing should be mechanical (R-multiple), not intuitive.

### 5.3 The Biggest Gap in Source Material

The corpus completely ignores:
- Market microstructure (order book, spread, impact)
- Regime detection (when to use which signal type)
- Portfolio construction and correlation management
- Backtesting methodology and bias prevention

These gaps are critical and must be filled in the architecture phase.

### 5.4 Crypto-Specific Risks Not Addressed

The source material is largely equity-trained with superficial crypto adaptation:
1. 24/7 trading eliminates gaps (invalidates gap-dependent patterns)
2. Manipulation is more prevalent (inflates false signal rates)
3. Survivorship bias is severe (altcoin datasets exclude failed projects)
4. Regime changes are faster and more extreme in crypto
5. Correlation clustering (most alts move with BTC) limits portfolio diversification

---

## Quantitative Summary

| Category | Count |
|---|---|
| Patterns inventoried | 50+ |
| Patterns classified as CRITICAL/HIGH priority | 14 |
| Patterns classified as MEDIUM priority | 10 |
| Patterns REJECTED | 18 |
| Risk rules defined | 9 |
| Candidate rule families | 8 |
| Testable hypotheses generated | 25 |
| Validated edges | **0** |
| Open questions requiring resolution | 20 |

**Bottom line:** Phase 1 has produced a well-structured research corpus with 25 prioritized hypotheses and a rigorous risk framework. Zero validated edges exist at this point. This is the correct and expected state after a Phase 1 literature review. Phase 2 must begin with data acquisition, backtesting infrastructure, and systematic hypothesis testing — starting with the EMA baseline and the five critical chart patterns.
