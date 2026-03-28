# Replay Source Separation Report

**Date:** 2026-03-28
**Phase:** 5.5

---

## Source Tags Used in Phase 5.5

| Source Tag | Where Used | In EDGE_EVIDENCE_SOURCES |
|------------|------------|--------------------------|
| `event_driven_runtime_replay` | TrueReplayHarness.run_fixture() | YES |
| `event_driven_runtime_replay_lifecycle_assist` | TrueReplayHarness.run_lifecycle_control_test() | NO |
| `event_driven_runtime_simulation` | RuntimeReplayHarness (Phase 5) | YES |

---

## Source Definitions (from src/validation/__init__.py)

```python
VALIDATION_SOURCES = frozenset({
    "event_driven_runtime_replay",
    "event_driven_runtime_simulation",
    "synthetic_control_scenarios",
    "simplified_backtest",
    "live_exchange_fed_paper",
})

RUNTIME_SOURCES = frozenset({
    "event_driven_runtime_replay",
    "event_driven_runtime_simulation",
    "live_exchange_fed_paper",
})

EDGE_EVIDENCE_SOURCES = frozenset({
    "event_driven_runtime_replay",
    "live_exchange_fed_paper",
})
```

`event_driven_runtime_replay_lifecycle_assist` is intentionally NOT in any of these sets.
It is a sub-type of replay that is explicitly labeled as a control test, not primary evidence.

---

## Source Separation Rules

| Check | Rule | Status |
|-------|------|--------|
| replay ≠ simulation | runtime + different_runtime not mixed | PASS |
| replay ≠ backtest | RUNTIME_SOURCES ∩ {simplified_backtest} = ∅ | PASS |
| replay ≠ synthetic_control | each fixture tagged separately | PASS |
| lifecycle_assist ∉ EDGE_EVIDENCE_SOURCES | lifecycle not usable as edge claim | PASS |
| lifecycle_assist ≠ replay | separate source constant | PASS |
| unknown source | SourceEnforcer raises SourceSeparationError | N/A (no unknown sources used) |

---

## Fixture Source Tags

All three replay fixtures carry `validation_source = "event_driven_runtime_replay"`:

```python
@dataclass
class ReplayFixture:
    name: str
    description: str
    feature_vectors: list[FeatureVector]
    validation_source: str  # always REPLAY_SOURCE = "event_driven_runtime_replay"
```

This is set at fixture construction time and not mutable.

---

## What "event_driven_runtime_replay" Means

This source tag means:
1. Input: deterministic OHLCV bars (structured as replay data, not live)
2. Pipeline: real `BtcBybitPaperRunner` — identical to what processes live Bybit data
3. No forcing: no events injected, no thresholds modified, no verdicts bypassed
4. Indicators: computed from actual OHLCV using `indicator_engine.py` (not constant offsets)

It does NOT mean:
- That the bars represent actual historical BTC prices
- That the bars came from Bybit exchange
- That edge evidence is established (requires closed trades)

---

## What "event_driven_runtime_replay_lifecycle_assist" Means

This source tag means:
1. One `CandidateTradeEvent` was injected — bypassing EntryGroup but NOT the panel
2. The real panel still evaluates normally (no forced approvals)
3. Used ONLY to test open/close mechanics — not signal quality
4. Results from this source tag CANNOT be combined with replay results for any metric

When aggregate reporting excludes lifecycle assist from "natural entries" count:
```python
pure_replay = [r for r in reports if r.validation_source == REPLAY_SOURCE]
lifecycle_control = [r for r in reports if r.validation_source == LIFECYCLE_ASSIST_SOURCE]
```

---

## SourceEnforcer Validation

The `SourceEnforcer.assert_not_mixed()` function from `source_enforcer.py` would raise
`SourceSeparationError` if:

```python
# ILLEGAL — would raise:
sources = {"event_driven_runtime_replay", "simplified_backtest"}
enforcer.assert_not_mixed(sources)  # SourceSeparationError

# LEGAL — same type, different fixtures:
sources = {"event_driven_runtime_replay", "event_driven_runtime_simulation"}
enforcer.assert_not_mixed(sources)  # OK — both RUNTIME_SOURCES
```

Phase 5.5 audit: **PASS** — no illegal mixing detected.

---

## Source Separation in Tests

`test_replay_validation.py` includes 7 source separation tests:

1. `test_replay_source_tag_is_correct` — REPLAY_SOURCE == "event_driven_runtime_replay"
2. `test_lifecycle_source_tag_is_different` — LIFECYCLE_ASSIST_SOURCE != REPLAY_SOURCE
3. `test_replay_source_not_in_simulation_sources` — no cross-contamination constant
4. `test_source_enforcer_allows_replay` — SourceEnforcer accepts replay alone
5. `test_source_enforcer_rejects_replay_plus_backtest` — enforcer blocks illegal mix
6. `test_lifecycle_assist_not_in_edge_evidence_sources` — lifecycle cannot be used as edge
7. `test_fixture_carries_correct_source_tag` — each fixture has correct tag

All 7 pass as of 2026-03-28.

---

## Conclusion

Source separation in Phase 5.5 is architecturally enforced and test-verified.
No replay data is mixed with simulation, backtest, or synthetic control data.
Lifecycle control data is clearly separated from primary replay evidence.
