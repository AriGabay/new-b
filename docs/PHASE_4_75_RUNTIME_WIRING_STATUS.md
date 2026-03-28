# Phase 4.75 Runtime Wiring — Status

**Phase:** 4.75
**Date:** 2026-03-28
**Status:** WIRING COMPLETE — Bybit connectivity still environment-blocked

---

## What Was Built

### New Files

| File | Description |
|---|---|
| `src/runtime/__init__.py` | Package marker |
| `src/runtime/runner.py` | `BtcBybitPaperRunner` — runtime orchestrator |
| `src/runtime/setup_packet_builder.py` | FeatureVector → BTCSetupPacket mapping |
| `src/groups/panel_decision/__init__.py` | Package marker |
| `src/groups/panel_decision/group.py` | `PanelDecisionGroup` — Layer B+C bridge |

### Modified Files

| File | Change |
|---|---|
| `src/core/events.py` | Added `PanelApprovedProposalEvent` |
| `src/groups/risk_leverage/group.py` | Subscribes to `PanelApprovedProposalEvent` (primary) + `CandidateTradeEvent` (legacy) |
| `src/main_btc.py` | Replaced legacy analysis script with 4-mode runner entrypoint |

### New Tests

| File | Tests |
|---|---|
| `src/tests/test_runtime_wiring.py` | 10 integration tests: runner setup, event propagation, panel subscription, risk subscription, setup packet builder, journal init, full smoke |

---

## The 3-Layer Pipeline Is Now Executable

Before this phase:
- Layer B (TraderEvaluatorPanel) and Layer C (FinalDecisionGroup) were dead code
- No runner existed to wire groups to a shared EventBus
- `main_btc.py` bypassed the architecture entirely

After this phase:
- `BtcBybitPaperRunner` instantiates all 9 active groups
- All groups share a single `EventBus` and `SystemState`
- `PanelDecisionGroup` wires the Layer B+C path between Entry and Risk
- `RiskLeverageGroup` now requires panel approval before risk evaluation
- `DecisionTraceLogger` logs full 4-step decision traces to SQLite
- `python main_btc.py --simulate 5` exercises the full pipeline without Bybit

---

## Proof of Integration

1. **Runner exists:** `src/runtime/runner.py` ✓
2. **main_btc.py uses it:** `--run` and `--simulate` modes both use `BtcBybitPaperRunner` ✓
3. **Layer A → Layer B → Layer C path:** CandidateTradeEvent → PanelDecisionGroup → TraderEvaluatorPanel → FinalDecisionGroup → PanelApprovedProposalEvent ✓
4. **Journal receives runtime data:** PerformanceJournalGroup subscribes to all events ✓
5. **DecisionTraceLogger active:** wired post-setup via `_finalize_learning_wiring()` ✓
6. **Position open/close path:** RiskLeverageGroup → PositionOpenEvent → ExitGroup → PositionCloseEvent ✓
7. **Tests prove wiring:** 10 integration tests pass in simulation mode ✓

---

## What Remains Limited

| Limitation | Impact | When to Fix |
|---|---|---|
| Bybit HTTP 404 (environment) | --run mode blocked | Deploy to clean machine |
| RESEARCH mode gate | Positions never open (Rule 1 blocks) | Change mode to PAPER explicitly |
| ChartPatternGroup stubbed | chart_pattern_quality = 0.0 | Phase 5+ |
| NewsMacroGroup stubbed | No event risk signals | Phase 5+ |
| OutcomeAttributor not wired | Calibration never updates | Phase 5 |
| composite_score = 0.0 in journal | Score not persisted | Phase 5 (schema extension) |
| startup_load() one-bar lag | First bar can't propose | Acceptable |
| MACD = zeros in SetupPacket | 20 traders use 0 MACD | Phase 5 (add to FeatureVector) |

---

## Verification Command

```bash
cd /Users/arigabay/Code/new-b/src
python -m pytest tests/test_runtime_wiring.py -v
```

And end-to-end simulation:
```bash
python main_btc.py --simulate 5 --log-level DEBUG
```
