# Source Separation Validation Report

**Date:** 2026-03-28
**Framework:** Phase 5 validation layer

---

## Policy

All validation outputs must carry an explicit `validation_source` field.
Sources must never be silently mixed. Aggregate metrics must only be computed
within a single source.

The `SourceEnforcer` class enforces this at runtime — any mixing attempt raises
`SourceSeparationError` before metrics are computed.

---

## Valid Validation Sources

| Source | Use Case | Edge Evidence? |
|--------|----------|----------------|
| `event_driven_runtime_replay` | Real runner + real historical bars | ✅ Yes |
| `event_driven_runtime_simulation` | Real runner + synthetic bars | ❌ No |
| `synthetic_control_scenarios` | Forced-approval + controlled path tests | ❌ No |
| `simplified_backtest` | BacktestEngine EMA-crossover only | ❌ No |
| `live_exchange_fed_paper` | Future: live Bybit paper mode | ✅ Yes |

Only `event_driven_runtime_replay` and `live_exchange_fed_paper` constitute
**edge evidence** — sources from which win rates, expectancy, and profit factor
can be used to assess system quality.

---

## Mixing Rules

### Illegal Combinations

1. `event_driven_runtime_*` + `simplified_backtest`
   - Backtest uses EMA-crossover only. Runtime uses the full 20-trader panel + 9 risk rules.
   - Combining these would dilute runtime performance metrics with simplified proxy data.

2. `event_driven_runtime_*` + `synthetic_control_scenarios`
   - Synthetic_control uses forced approvals. Runtime does not.
   - Forced approval data would inflate enter rates if mixed with real runtime data.

3. Any source + `sensitivity_analysis_only`
   - Threshold sensitivity analysis is a meta-analysis, not a runtime source.
   - It cannot be treated as validation data.

### SourceEnforcer Behaviour

```python
# Will raise SourceSeparationError:
SourceEnforcer.assert_not_mixed([
    "event_driven_runtime_simulation",
    "simplified_backtest",
])

SourceEnforcer.assert_not_edge_evidence("synthetic_control_scenarios")
# → SourceSeparationError: Source 'synthetic_control_scenarios' is NOT in EDGE_EVIDENCE_SOURCES

SourceEnforcer.validate_report(
    {"validation_source": "synthetic_control_scenarios"},
    expected="event_driven_runtime_simulation",
)
# → SourceSeparationError: Report source mismatch

# These pass:
SourceEnforcer.assert_single_source(["event_driven_runtime_simulation"] * 10)
SourceEnforcer.assert_not_edge_evidence("event_driven_runtime_replay")
```

---

## Phase 5 Validation Source Audit

Run date: 2026-03-28

### Panel behavior report
- Source: `event_driven_runtime_simulation` ✅
- All 10 PanelBatchRecords carry this source tag
- SourceEnforcer.validate_report() applied on every add()

### Risk gate report
- Source: `event_driven_runtime_simulation` ✅
- All 8 RiskRuleResult records carry this source tag

### Threshold sensitivity
- Source: `sensitivity_analysis_only` ✅
- Intentionally separate from runtime sources
- All non-production rows carry "sensitivity_analysis_only — NOT for edge conclusions" note
- Production row carries "← PRODUCTION THRESHOLD (not mutated)"

### Calibration report
- Source: Not available (zero closed trades)
- When available, will be tagged `event_driven_runtime` (OutcomeSource enum)

### Source audit result: **PASS**
Runtime sources found: `event_driven_runtime_simulation`
No mixing of runtime + backtest detected.
No synthetic_control contamination detected.

---

## Learning Layer Source Separation

The `OutcomeSource` enum in `learning/outcome_source.py` mirrors the validation source
separation for calibration data:

| OutcomeSource | Maps To |
|---------------|---------|
| `EVENT_DRIVEN_RUNTIME` | `event_driven_runtime_*` validation |
| `SIMPLIFIED_BACKTEST` | `simplified_backtest` validation |
| `SYNTHETIC_DATA` | `synthetic_control_scenarios` validation |
| `LIVE_EXCHANGE_FED` | `live_exchange_fed_paper` validation |

`assert_single_source()` in both `learning/outcome_source.py` and
`validation/source_enforcer.py` enforce this at every aggregation point.

---

## Test Coverage

The following tests verify source separation enforcement (in `test_validation.py`):

- `test_source_enforcer_mixed_sources_raises` — mixing raises
- `test_source_enforcer_unknown_source_raises` — unknown source raises
- `test_source_enforcer_not_edge_evidence_raises` — non-edge source raises on claim
- `test_source_enforcer_validate_report_mismatch_raises` — mismatch raises
- `test_source_enforcer_validate_report_missing_field_raises` — missing field raises
- `test_source_enforcer_assert_not_mixed_runtime_backtest_raises` — mixed raises
- `test_source_enforcer_assert_not_mixed_runtime_synthetic_raises` — mixed raises
- `test_panel_behavior_analyzer_source_enforcer_rejects_wrong_source` — add() rejects wrong source
- `test_source_separation_panel_not_synthetic` — panel results use correct source
- `test_source_separation_risk_not_synthetic` — risk results use correct source
- `test_source_separation_no_backtest_mixed_with_runtime` — mixing raises

All 11 source-separation tests pass.
