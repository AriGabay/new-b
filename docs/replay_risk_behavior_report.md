# Replay Risk Behavior Report

**Date:** 2026-03-28
**Source:** event_driven_runtime_replay
**Phase:** 5.5

---

## Status: NO RISK GATE EVALUATIONS FROM REPLAY

No proposals reached the risk gates during replay validation.

The pipeline requires: EntryGroup fires → Panel approves → Risk gates evaluate.
Since EntryGroup never fired (composite_score ceiling 0.4875 < 0.50), the risk
gates were never invoked.

---

## Risk Architecture (for Reference)

`RiskLeverageGroup` implements 9 rules evaluated in order on each approved proposal:

| Rule | Description | Notes |
|------|-------------|-------|
| Rule 1: mode_gate | Paper/shadow mode only | Always passes in simulation |
| Rule 2: daily_loss | Max daily loss limit | Requires portfolio state |
| Rule 3: max_drawdown | Portfolio drawdown limit | Requires portfolio state |
| Rule 4: portfolio_exposure | Total exposure cap | Requires open positions |
| Rule 5: correlated_exposure | Correlated position cap | Requires open positions |
| Rule 6: liquidity | Minimum notional required | Always passes for BTCUSDT |
| Rule 7: pump_signal | volume_ratio > 5.0 threshold | ADX > 30 override |
| Rule 8: event_risk | High-impact event flag | Requires external event feed |
| Rule 9: completeness | All required fields present | Simple schema check |

All 9 rules passed against clean-state proposals in Phase 5 (risk analyzer tests).
These results hold — but they are tagged `event_driven_runtime_simulation` from
that test run, not `event_driven_runtime_replay`.

---

## Replay Risk Assessment

### Clean State Expectations

At bar 200 of each fixture, the runner is in clean state:
- portfolio equity: 100,000 USDT
- open positions: 0
- daily PnL: 0
- drawdown: 0%

Under these conditions:
- Rule 2 (daily_loss): PASS (no losses taken)
- Rule 3 (max_drawdown): PASS (0% drawdown)
- Rule 4 (portfolio_exposure): PASS (0 positions open)
- Rule 5 (correlated_exposure): PASS (0 positions open)

### Volume Ratio Assessment

Volume ratios across replay fixtures ranged from 0.74 to 1.33. No bar had
`volume_ratio > 5.0`. Rule 7 (pump_signal) would not trigger on any replay bar.

### ADX Assessment

- Bull breakout final ADX: 98.1 (ADX override for pump signal would apply if Rule 7 triggered)
- Bear breakdown final ADX: 99.6 (same)
- Ranging final ADX: 29.8 (no override needed — pump signal wouldn't trigger anyway)

---

## Comparison with Phase 5 Risk Tests

Phase 5 ran 8 explicit risk proposals through `RiskRuleRunner`:

| Test | Result | Source |
|------|--------|--------|
| complete_valid_proposal | PASS | event_driven_runtime_simulation |
| below_threshold_score | REJECT | event_driven_runtime_simulation |
| incomplete_trade_plan | REJECT | event_driven_runtime_simulation |
| hypothesis_not_active | REJECT | event_driven_runtime_simulation |
| extreme_leverage | PASS (at 0.1×) | event_driven_runtime_simulation |
| high_volatility_period | PASS | event_driven_runtime_simulation |
| shadow_mode_test | PASS | event_driven_runtime_simulation |
| correlated_exposure_clean_state | PASS | event_driven_runtime_simulation |

Phase 5 pass rate: 62.5% (5/8). Phase 5.5 has no comparable data (zero evaluations).

---

## What Risk Testing Needs for Replay Evidence

For meaningful risk rule validation from replay data:
1. Natural entries must fire (requires ChartPatternGroup or threshold change)
2. Approved proposals must reach RiskLeverageGroup
3. Rules 2-5 (portfolio state dependent) require multiple positions
4. Rule 7 requires a fixture with volume_ratio > 5.0 on a bar

None of these conditions were met in Phase 5.5.

---

## Conclusion

Risk gate behavior during replay: unobservable (pipeline did not reach risk evaluation).
Phase 5 risk rule tests (8 proposals) remain the most current risk behavior data,
but tagged with simulation source — not replay.
