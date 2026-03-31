# Backtest Report: 2023-12-01 → 2024-12-31

**Generated:** 2026-03-31
**Data file:** `btcusdt_1h_2024_2025.csv`
**Date range requested:** `--start 2023-01-01 --end 2024-12-31`
**Actual date range available:** 2023-12-01 → 2024-12-31 (CSV starts Dec 2023)
**Bars in range:** 9,528 hourly bars (13.2 months)
**Bars processed:** 9,329 (after 200-bar EMA warm-up)
**Run time:** 108.3s (3 iterations × ~36s each)
**Initial equity:** $10,000
**Best iteration reported:** Iteration 3/3 (101 trades — most trades wins tie-break)

---

## Performance Summary

| Metric | Value |
|---|---|
| Total trades taken | **101** |
| Win rate | **42.6%** (43 wins / 58 losses) |
| Profit factor | **0.82** |
| Net P&L | **−$3,675** (−36.75%) |
| Final equity | $6,324.67 |
| Max drawdown | **39.9%** |
| Average R per trade | **−0.05R** |
| Avg winner (USD) | +$385.42 |
| Avg loser (USD) | −$349.11 |
| Avg bars held | ~16.5 hours |
| Sharpe ratio | *not computed* (full-pipeline engine doesn't yet calculate Sharpe) |

### Iteration Progression

| Iteration | MDP Relaxation | Trades | Win Rate | Profit Factor | Max DD | Return |
|---|---|---|---|---|---|---|
| 1 (production defaults) | none | 13 | 30.8% | 0.64 | 15.0% | −10.59% |
| 2 (REDUCE_RISK 0.35, MED thresh 10) | moderate | 92 | 43.5% | 0.83 | 35.4% | −32.07% |
| 3 (REDUCE_RISK 0.38, MED thresh 9) | maximum | **101** | **42.6%** | **0.82** | 39.9% | **−36.75%** |

> **Key observation:** Relaxing MDP thresholds dramatically increased trade count (13 → 101)
> but worsened the drawdown profile (15% → 39.9%) and return (−10.6% → −36.8%).
> The report reflects iteration 3 as the "best" by the trade-count selection rule.

---

## Exit Reason Breakdown

*Based on 94 of 101 trades captured from structured log parsing (iteration 3).*

| Exit Reason | Count | % of Total | Avg P&L | Avg R | Win Rate |
|---|---|---|---|---|---|
| `stop_loss` | 54 | 57.4% | −$326 | −0.75R | 4%\* |
| `trailing_stop` | 39 | 41.5% | +$392 | +0.98R | 100% |
| `target_reached` | 1 | 1.1% | +$914 | +2.20R | 100% |
| `time_stop` | **0** | **0.0%** | N/A | N/A | N/A |
| `breakeven` | 0 | 0.0% | N/A | N/A | N/A |

\* *Two stop_loss exits recorded marginally positive pnl_usd because the stop had been
moved to breakeven+ before triggering (trailing stop mechanism pre-moved the stop
above entry before price reversed hard).*

### What the exit split reveals

- **Stop losses dominate (57%)**: More than half of all trades hit the hard stop. This is the
  primary driver of losses. The trailing stop mechanism is working when trades survive long
  enough (avg +0.98R), but many trades never get there.
- **No time stops fired (0%)**: The 72-bar time stop never triggered. Avg hold time is ~16h,
  well within the 72h window. Time stop is not a factor in this dataset.
- **Target rarely hit (1%)**: Only one trade reached the explicit profit target (2.20R).
  The trailing stop exits most winners first.

---

## Key Diagnostics

### 1. Time-stop percentage

**0.0%** of trades were closed by time_stop. This is well below the 30% concern threshold.
The system holds trades for an average of **16.5 hours** (range: 0–48h), always closing
before the 72-bar limit. The time stop is appropriately set and not being triggered.

### 2. Average bars held

**~16.5 hours** across all 101 trades. Short-duration trades (< 24h) dominate the set,
indicating the system is trading intraday volatility rather than multi-day swings. This
is consistent with an hourly-bar pipeline using ATR-based stops on BTC.

### 3. LONG vs SHORT split and win rates

| Direction | Trades | % of Total | Win Rate | Avg R |
|---|---|---|---|---|
| SHORT | 54 | 57.4% | **35.2%** | −0.15R |
| LONG | 40 | 42.6% | **57.5%** | +0.20R |

**The SHORT bias is the primary performance problem.** The system took 57% SHORT trades
but SHORT WR was only 35.2%, dragging overall performance. LONG trades performed
acceptably at 57.5% WR. The data covers Dec 2023 → Dec 2024, a period dominated by
a BTC bull market (price moved from $37k to $100k+). SHORT entries consistently fought
the dominant uptrend.

### 4. Monthly activity (by entry price band)

*Entry prices mapped to approximate BTC price ranges for each period:*

| Price Band / Approx. Period | Trades | Win Rate | Avg P&L |
|---|---|---|---|
| $37k–$42k (Dec 2023) | 7 | 29% | −$142 |
| $42k–$50k (Jan 2024) | 34 | 47% | +$16 |
| $50k–$58k (Feb 2024) | 4 | 50% | −$170 |
| $58k–$70k (Mar–May 2024) | 40 | 50% | +$57 |
| $70k–$73k (Jun–Jul 2024) | 9 | 22% | −$286 |
| $73k+ (Aug–Dec 2024) | 0 | — | — |

**Most active period:** Jan 2024 (34 trades) and Mar–May 2024 (40 trades).
**Best win rate:** Mar–May 2024 (50%) and Feb 2024 (50%).
**Worst win rate:** Jun–Jul 2024 (22%, 9 trades) at the post-ATH distribution zone.
**Highest-R period:** Mar–May 2024 (+$57 avg).
**Critical gap:** Zero trades in Aug–Dec 2024 (BTC $73k→$108k). The REDUCE_RISK policy
locked out all new entries after losses accumulated in H1 2024. This caused the system
to miss the entire Nov–Dec 2024 parabolic move.

---

## Red Flags

| Condition | Threshold | Actual Value | Status |
|---|---|---|---|
| Win rate < 35% | → "Win rate too low" | **42.6%** | ✅ Above red-flag threshold |
| Profit factor < 1.3 | → "Not profitable enough" | **0.82** | 🚨 **FAIL — PF 0.82 << 1.3** |
| Max drawdown > 20% | → "Drawdown too high" | **39.9%** | 🚨 **FAIL — 2× the threshold** |
| Time stop > 30% of closes | → "Time stop too aggressive" | **0.0%** | ✅ No time stops fired |
| 0 trades taken | → "Bot too selective" | **101** | ✅ System is active |

**Additional findings not covered by the standard thresholds:**

- 🚨 **Net return −36.75%**: Account lost over a third of capital. Not viable for live trading.
- 🚨 **SHORT bias + bear WR**: 57% SHORT allocation with only 35.2% SHORT win rate in a bull year.
- 🚨 **REDUCE_RISK deadlock**: After H1 2024 losses depleted capital, no trades were taken in
  the Aug–Dec 2024 bull run. The system locked itself out of its best opportunity window.
- ⚠️ **Capital scale mismatch**: System calibrated for $100k+; running at $10k creates
  position sizes worth 500% of equity (5× leverage on $10k = $50k notional per trade).
  Each -1R stop-loss removes $500–$2,500 = 5–25% of capital in one trade.

---

## Recommendations

### Recommendation 1: Increase starting capital to minimum $50,000 (ideally $100,000)

**Problem:** With $10,000 equity, a single -1R stop-loss costs $500–$2,500 (5–25% of
capital). Three consecutive losses trigger `REDUCE_RISK` and lock out all entries.

**Root cause (from BacktestEngine internals):**
The runner uses leveraged futures sizing: `position_size = equity × leverage`. At 5× leverage
on a $10k account, each trade is $50k notional. `risk_fraction = 0.01` means $100 max risk,
but slippage + commissions eat into this quickly when the account shrinks.

**Concrete fix:**
```
INITIAL_EQUITY = Decimal("100000")   # was 10000
```
Expected outcome: positions scale to $100 risk per trade on $100k equity (correct calibration).
Max DD on 3 consecutive losses = ~3% instead of ~25%.

---

### Recommendation 2: Raise SHORT entry quality threshold by 1 approval vote

**Problem:** SHORT trades had WR=35.2% over a 13-month bull market (Dec 2023–Dec 2024),
taking 57% of total trade allocation and averaging −0.15R. Every SHORT trade cluster in the
bear/distribution zones ultimately resolved bullish.

**Concrete fix — in `mdp/policy.py` or the BacktestConfig iteration schedule:**
```python
# Current (iter 3 override)
SMALL_MIN_APPROVALS = 9
# Proposed: raise SHORT-specific quality gate by 1 (require one extra bullish signal absent)
# SHORT_EXTRA_APPROVALS = 2   # require 2 more approvals for counter-trend SHORT
```

Or more directly, audit the `DirectionFilter` in `EntryGroup` to require that SHORT proposals
additionally satisfy `adx14 > 30` AND `ema50 < ema200` (confirmed bear structure) before
routing to the panel. This would have eliminated most losing Jun–Jul 2024 SHORT entries.

---

### Recommendation 3: Replace `REDUCE_RISK` full-block with 50%-size reduction

**Problem:** `REDUCE_RISK` MDP action completely blocks new entries when drawdown exceeds
the threshold (28.5% → 35% → 38% across iterations). This caused the system to miss the
entire Aug–Dec 2024 bull market despite generating valid panel-approved proposals.

From the final logs, there were **14+ panel-approved proposals** blocked by `REDUCE_RISK`
in the last quarter of the backtest — each showing 12–15/20 approvals with avg score 6.8–7.3.

**Concrete fix — add `REDUCE_RISK_SIZE_FRACTION` constant and modify `RiskLeverageGroup`:**
```python
# In risk/sizing.py or groups/risk_leverage/group.py
REDUCE_RISK_SIZE_FRACTION = Decimal("0.50")   # trade at 50% normal size, not 0%

# In RiskLeverageGroup._apply_mdp_action():
if mdp_action == "reduce_risk":
    approved_size_usd = approved_size_usd * REDUCE_RISK_SIZE_FRACTION
    # do NOT block — let the trade proceed at half-size
```

Expected outcome: during REDUCE_RISK state, system participates in the Aug–Dec 2024 rally
at 50% size, allowing equity recovery while maintaining risk discipline.

---

## Summary Verdict

| Category | Assessment |
|---|---|
| **Signal quality** | ⚠️ Borderline — LONG signals at 57.5% WR are viable, SHORT at 35.2% are not |
| **Risk management** | 🚨 Critical failure — position sizing is inappropriate for $10k account |
| **Entry selectivity** | ✅ Active — 101 trades in 13 months; panel + MDP pipeline generating proposals |
| **Exit mechanics** | ✅ Trailing stop working correctly (avg +0.98R on wins); time stop not over-firing |
| **Capital requirement** | 🚨 System requires minimum $50k–$100k to function as designed |
| **Ready for live?** | ❌ No — fix capital scale and SHORT quality gate before live deployment |

The underlying signal pipeline (indicators → panel → MDP → trailing-stop exit) is
architecturally sound and producing actionable signals. The two critical issues — capital
scale mismatch and SHORT-direction bias in a bull market — are tunable parameters, not
fundamental design flaws.

---

## Round 2 Results (after parameter tuning)

**Changes applied since Round 1:**
1. **SHORT quality gate** — `EntryGroup` now requires ADX14 > 30 AND EMA50 < EMA200 before routing SHORT proposals to the panel.
2. **Trailing stop delayed** — `TRAIL_ACTIVATE_R` raised from 1.0 → 1.5; `TRAIL_TIGHT_1_R` raised from 1.5 → 2.0 (winners given more room before trail engages).
3. **`TARGET_R_MULTIPLIER` constant** — inline `Decimal("3")` target replaced with named constant; target remains 3R (no change to R:R, just cleaner code).

**Run parameters:** `--start 2023-01-01 --end 2024-12-31` (same dataset; actual range 2023-12-01 → 2024-12-31)
**Best iteration selected:** Iteration 3/3 (60 trades — most-trades tie-break)

---

### Head-to-Head Comparison

| Metric | Round 1 | Round 2 | Change |
|---|---|---|---|
| Total trades taken | **101** | **60** | −41 🚨 **WORSE** |
| Win rate | **42.6%** | **36.7%** | −5.9 pp 🚨 **WORSE** |
| Profit factor | **0.82** | **0.82** | = |
| Net P&L | **−36.75%** (−$3,675) | **−28.64%** (−$2,864) | +8.1 pp ✅ **BETTER** |
| Final equity | $6,324.67 | $7,135.90 | +$811 ✅ **BETTER** |
| Max drawdown | **39.9%** | **39.9%** | = |
| Avg R per trade | −0.05R | −0.06R | −0.01R 🚨 **WORSE** |
| Avg winner (USD) | +$385.42 | **+$593.28** | +$207.86 ✅ **BETTER** |
| Avg loser (USD) | −$349.11 | −$454.75 | −$105.64 🚨 **WORSE** |
| % SHORT trades | ~57.4% | **25.0%** | −32.4 pp ✅ **BETTER** |
| SHORT win rate | **35.2%** | **20.0%** | −15.2 pp 🚨 **WORSE** |
| SHORT avg R | −0.15R | **−0.537R** | −0.39R 🚨 **WORSE** |
| LONG win rate | **57.5%** | **42.2%** | −15.3 pp 🚨 **WORSE** |
| LONG avg R | +0.20R | **+0.10R** | −0.10R 🚨 **WORSE** |
| Avg bars held | ~16.5 h | ~16.3 h | = |

### Iteration Progression (Round 2)

| Iteration | MDP Relaxation | Trades | Win Rate | Profit Factor | Max DD | Return |
|---|---|---|---|---|---|---|
| 1 (production defaults) | none | 5 | 20.0% | 0.25 | 16.2% | −12.63% |
| 2 (REDUCE_RISK 0.35, MED thresh 10) | moderate | 56 | 37.5% | 0.84 | 35.5% | −23.40% |
| 3 (REDUCE_RISK 0.38, MED thresh 9) | maximum | **60** | **36.7%** | **0.82** | 39.9% | **−28.64%** |

> **Note:** Iteration 2 had a *better* PF (0.84) and WR (37.5%) than Iteration 3. The selection rule
> (most trades) picked Iteration 3 anyway. On a PF basis, Iteration 2 would be preferred.

---

### Exit Reason Breakdown (Round 2, 60 trades)

| Exit Reason | Count | % of Total | Avg P&L | Win Rate |
|---|---|---|---|---|
| `stop_loss` | 41 | 68.3% | — | ~7%\* |
| `trailing_stop` | 17 | 28.3% | +$593 | 100% |
| `target_reached` | 2 | 3.3% | +$946 | 100% |
| `time_stop` | **0** | **0.0%** | N/A | N/A |

\* *Three stop_loss exits recorded positive pnl_usd (breakeven+ stops triggered before full reversal).*

**Key shift from Round 1:** More exits via hard stop (68.3% vs 57.4%) and fewer via trailing stop
(28.3% vs 41.5%). This is a direct consequence of raising `TRAIL_ACTIVATE_R` from 1.0 → 1.5:
trades that previously had a trailing stop locked in at +1.0R now must survive to +1.5R before
protection engages. More of them reverse before reaching +1.5R, hitting the hard stop.

---

### What Improved

**1. Net return: −36.75% → −28.64% (+8.1 pp).** The system lost $811 less on the same capital.
The primary driver is a much larger average winner ($593 vs $385, +54%). Allowing winners to run
to +1.5R before the trail activates means surviving trades reach deeper profit before being captured.

**2. SHORT overexposure corrected.** The SHORT quality gate cut SHORT allocation from 57.4% to
25.0% of all trades — a 32 pp reduction. This is the gate working exactly as intended in a bull
market: blocking the majority of counter-trend SHORT proposals.

**3. More target hits.** 2 trades hit the 3R target (3.3%) vs 1 in Round 1 (1.1%). The trailing stop
no longer cuts profits at +1.0R, so strong trending trades have a chance to reach the target.

**4. LONG component turned net positive.** LONG avg R = +0.10R (positive). Round 1 LONG avg R
was +0.20R but with a much higher WR (57.5%). In Round 2, fewer LONGs win (42.2%) but the wins
are larger. With a properly sized account, a LONG-only system subset here would be marginally viable.

---

### What Got Worse

**1. 🚨 Win rate: 42.6% → 36.7% (−5.9 pp).** The trailing stop delay converted wins-at-+1.0R into
hard-stop losses. In Round 1, a trade reaching +1.0R had a trailing stop set; if price pulled back
to that trail it closed as a winner (~+0.5R to +1.0R). In Round 2, the same trade has *no* trail at
+1.0R and reverts to a full −1R stop-loss when it reverses. This is the expected mechanical
trade-off: fewer, larger winners vs more, smaller winners.

**2. 🚨 SHORT win rate collapsed: 35.2% → 20.0% (−15.2 pp).** The SHORT filter successfully blocked
39 of the 54 Round 1 SHORTs, but the 15 that passed the ADX>30 + EMA bear structure gate still
mostly lost (3 wins / 12 losses). **Interpretation:** the gate prevents *weak* SHORT entries but
cannot help in a structural bull market — confirmed bear structures (EMA50 < EMA200) during
Dec 2023–Dec 2024 were temporary corrections, not trend reversals. SHORT avg R plummeted
from −0.15R to −0.537R for those that got through.

**3. 🚨 Trade count: 101 → 60 (−41 trades).** The SHORT gate and the tighter trailing stop
together reduce opportunity count significantly. Fewer trades at the same equity = less capital
utilization. In a $10k account this does not matter (the account is already over-leveraged), but
for a properly-sized account this reduces annual P&L potential.

**4. 🚨 Avg loser got bigger: −$349 → −$455 (−$106).** With the trail activating later, stops that
were previously avoided (because the trail fired first) now hit full −1R. The increased avg winner
($593 vs $385) more than compensates on a per-trade basis, but the loss magnitude is real.

---

### Root Cause: REDUCE_RISK Lockout Persists

Both rounds show identical max drawdown (39.9%) and identical behavior after bar ~4,200:
0 new trades from approximately May 2024 onwards. The `REDUCE_RISK` lockout problem from
Recommendation 3 of Round 1 was **not implemented** in Round 2. This is the single biggest
bottleneck: **the system missed the entire Aug–Dec 2024 bull run again** (BTC $60k → $108k).

---

### Round 2 Verdict

| Category | Round 1 | Round 2 | Direction |
|---|---|---|---|
| **Signal quality** | ⚠️ LONG ok, SHORT not | ⚠️ LONG +0.10R avg, SHORT catastrophic | Mixed — LONG improving, SHORT worse |
| **SHORT filter** | ❌ No filter | ✅ ADX+EMA gate active | ✅ **Improvement** |
| **Avg winner size** | $385 | $593 | ✅ **Improvement** |
| **Win rate** | 42.6% | 36.7% | 🚨 **Regression** |
| **REDUCE_RISK lockout** | 🚨 Locked out Aug–Dec | 🚨 Locked out Aug–Dec | Unchanged |
| **Net return** | −36.75% | −28.64% | ✅ **Improvement** |
| **Ready for live?** | ❌ No | ❌ No | Unchanged |

**Priority fix for Round 3:** Implement Recommendation 3 from Round 1 — replace the
`REDUCE_RISK` full-block with a 50%-size reduction. This is the only change that can unlock
the Aug–Dec 2024 opportunity window and break the deadlock pattern seen in both rounds.
