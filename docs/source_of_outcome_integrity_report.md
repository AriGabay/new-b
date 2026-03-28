# Source-of-Outcome Integrity Report

**Date:** 2026-03-28
**Policy source:** `src/learning/outcome_source.py`, `docs/source_of_outcome_policy.md`

---

## Current State of Outcome Sources

### What outcomes exist today

| Source | Active? | Outcomes Generated? | Notes |
|---|---|---|---|
| `event_driven_runtime` | Code exists | ZERO | No positions opened; EventBus pipeline not active in main_btc.py |
| `simplified_backtest` | Active via `--backtest` | YES (simulated) | BacktestEngine EMA-crossover replay generates synthetic outcomes |
| `synthetic_data` | Tests only | YES (in-memory) | test_learning_layer.py generates fake outcomes |
| `live_exchange_fed` | Not started | ZERO | Phase 5+ |

### Outcomes from BacktestEngine (`simplified_backtest`)

BacktestEngine.run() produces:
- Entry signals (EMA-20 crosses above EMA-50)
- Exit signals (stop/target/trailing/time)
- PnL calculations

These outcomes are tagged in `BacktestResult` but are **NOT fed into the
learning layer**. BacktestEngine does not call JournalExtension or OutcomeAttributor.
No `outcome_attributions` rows are written by BacktestEngine.

### Mixing Policy Enforcement

The `assert_single_source()` guard in `outcome_source.py` is the enforcement
mechanism. It is correctly implemented and tested (27/27 tests pass).

However, since no outcomes flow into the learning tables from any source,
the mixing policy has never been exercised in production. The enforcement
exists as correct code waiting for data.

### Risk: Silent Mixing If Learning Layer Is Wired Without Source Tags

When the learning layer is eventually wired into runtime, the critical risk is
that someone connects BacktestEngine outcomes and EventBus runtime outcomes
to the same calibration records.

Mitigation already in place:
1. Every learning table has an `outcome_source TEXT NOT NULL` column
2. All query methods require an `outcome_source` parameter (no cross-source queries)
3. `assert_single_source()` raises `ValueError` if mixing is attempted
4. Unit tests verify the mixing guard works

### Backtest Outcomes and Calibration

**IMPORTANT:** Backtest outcomes (simplified_backtest) are NOT valid for
calibrating the 20 trader evaluators. The BacktestEngine does not invoke
TraderEvaluatorPanel. Outcomes from backtest cannot be attributed to trader
votes because no votes were cast.

If BacktestEngine outcomes were fed into trader_calibration with source=
`simplified_backtest`, the calibration records would be meaningless — they
would show outcomes that were never associated with any trader verdict.

The system's design prevents this by requiring source tags, but the explicit
guard (connecting backtest outcomes → trader calibration) has not been added
because the connection doesn't exist yet.

### Integrity Status

| Check | Status |
|---|---|
| OutcomeSource enum has 4 distinct values | ✓ |
| assert_single_source() raises on mixing | ✓ |
| All learning tables have outcome_source column | ✓ |
| No cross-source queries provided | ✓ |
| 30-sample minimum enforced in calibration | ✓ |
| BacktestEngine outcomes tagged and separated | N/A — not fed to learning layer yet |
| Runtime outcomes tagged at source | N/A — no runtime outcomes exist yet |
| Test suite verifies source integrity | ✓ (27 tests pass) |

### Integrity Assessment

**SOUND DESIGN, ZERO ACTUAL DATA.**

The source-of-outcome integrity system is correctly designed and implemented.
All enforcement mechanisms work. No outcomes have actually flowed through the
system yet — the pipeline is not active. There is no active mixing violation
because there is no active data.

The risk is not "mixing already happened" but "mixing could happen when wiring
occurs if source tags are not enforced at the integration point."

The primary action required before going live is: when wiring
`PerformanceJournalGroup._log_position_close()` to call `OutcomeAttributor`,
ensure the `outcome_source` is set correctly based on whether the trade came
from the event-driven runtime or a backtest replay.
