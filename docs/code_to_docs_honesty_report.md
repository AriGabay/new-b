# Code-to-Docs Honesty Report

**Date:** 2026-03-28
**Method:** For each major doc claim, verified against actual code

---

## Honesty Assessment by Subsystem

### MarketDataGroup
- **Docs claim:** Polls Bybit, publishes BarCloseEvent + FeatureReadyEvent, maintains 250-bar rolling window
- **Code reality:** Exactly as claimed. `startup_load()` fetches 200 bars per TF. `fetch_and_process()` publishes both events. `last_close_by_symbol` populated before FeatureReadyEvent.
- **Verdict:** HONEST ✓

### FeatureComputer / FeatureVector
- **Docs claim:** 31 fields including ATR14 (Wilder's), EMA20/50/200 with prev_, RSI14, BB, ADX14, volume metrics
- **Code reality:** Not audited in this pass; previously verified in Phase 3
- **Verdict:** ASSUMED HONEST (prior verification)

### IndicatorsGroup
- **Docs claim:** 10 sub-agents for EMA crossover, RSI, MACD, BB signals + regime compute
- **Code reality:** All 10 sub-agent methods present and implemented. Publishes GroupSignalEvent with real signals.
- **Verdict:** HONEST ✓

### CandlestickGroup
- **Docs claim:** Candlestick pattern detection
- **Code reality:** 5+ detection methods (_detect_engulfing, _detect_morning_evening_star, _detect_three_black_crows, _detect_inverted_hammer, _detect_doji). Publishes GroupSignalEvent.
- **Verdict:** HONEST ✓

### TechnicalStructureGroup
- **Docs claim:** S/R level detection, swing high/low, proximity flags
- **Code reality:** All methods implemented. _detect_swing_highs, _detect_swing_lows, _cluster_levels, _count_touches, _classify_trend, _proximity_flags, _prune_broken_levels. Publishes GroupSignalEvent.
- **Verdict:** HONEST ✓

### ChartPatternGroup
- **Docs claim:** STUBBED, documented in remaining_stubbed_components.md
- **Code reality:** `_process_features()` raises NotImplementedError. Docstring says "Phase 2 implementation pending".
- **Verdict:** HONEST ✓ (stub is correctly disclosed)

### NewsMacroGroup
- **Docs claim:** Limited/stubbed
- **Code reality:** `_process_bar_close()` raises NotImplementedError. All methods stub.
- **Verdict:** HONEST ✓

### EntryGroup
- **Docs claim:** Aggregates signals, confirmation gate, builds CandidateTradeProposal; _historian and _critic not wired
- **Code reality:** Pipeline is real. `_historian = None` (line 95), `_critic = None` (line 96). Checks are guarded with `if self._historian is not None:`. Entry price wiring correct.
- **Verdict:** HONEST ✓

### ExitGroup
- **Docs claim:** Full priority-ordered exit logic (stop→target→trailing→time)
- **Code reality:** All methods implemented. Trailing stop activates at +1R, ratchet only. Time stop at 20 bars. All 4 priority checks in order.
- **Verdict:** HONEST ✓

### RiskLeverageGroup
- **Docs claim:** 9 deterministic rules, no LLM
- **Code reality:** All 9 rule methods present and implemented (verified in prior phase)
- **Verdict:** HONEST ✓

### PerformanceJournalGroup
- **Docs claim:** Logs all events to SQLite; analysis methods deferred
- **Code reality:** Logging real. Analysis methods were `raise NotImplementedError` — changed to logged no-ops. Double-close bug fixed.
- **Verdict:** PARTIALLY HONEST — double-close bug was undocumented. Now repaired and documented.

### JournalDB
- **Docs claim:** 3 tables, append-only, one UPDATE on close
- **Code reality:** Verified in Phase 3. INSERT OR IGNORE on signals. UPDATE on close only.
- **Verdict:** HONEST ✓

### TraderEvaluatorPanel / 20 Traders
- **Docs claim:** 20 distinct evaluators, each with score/vote/confidence/reasons
- **Code reality:** All 20 implemented in evaluators.py. TraderVerdict has all 9 fields. Panel aggregation logic correct.
- **CRITICAL OMISSION:** Docs do not clearly state that this is dead code not connected to any runtime entrypoint.
- **Verdict:** PARTIALLY HONEST — components are real but docs understate the disconnection from runtime

### FinalDecisionGroup
- **Docs claim:** 6 safety rails, depends only on trader outputs
- **Code reality:** Implemented correctly. Not connected to runtime.
- **CRITICAL OMISSION:** Same as panel — runtime disconnection not prominently stated.
- **Verdict:** PARTIALLY HONEST

### BacktestEngine
- **Docs claim:** Simplified EMA-crossover only; _replay_bar() is intentional stub
- **Code reality:** Exactly as claimed. `_replay_bar()` is `pass`.
- **Verdict:** HONEST ✓

### Learning Layer (src/learning/)
- **Docs claim:** "Phase 4 code complete, integration pending"
- **Code reality:** All 10 modules implemented. Zero references to JournalExtension, DecisionTraceLogger, or OutcomeAttributor outside learning/ and tests/. Never instantiated from runtime.
- **Verdict:** HONEST on integration status, but "code complete" framing risks being read as "working in runtime." Docs updated to clarify.

### Source-of-Outcome Policy
- **Docs claim:** OutcomeSource must never be mixed; 30-sample minimum enforced in code
- **Code reality:** `assert_single_source()` exists and raises on mixing. All calibration properties gate at 30 samples. No cross-source queries exist.
- **Verdict:** HONEST ✓ — but the policy is moot until runtime generates any outcomes

### Bybit Connectivity
- **Docs claim:** DNS and TLS pass; HTTP 404 from Bybit CDN; IP restriction
- **Code reality:** Smoke test output preserved in docs. This is the actual finding.
- **Verdict:** HONEST ✓

---

## Summary of Honesty Failures Requiring Action

| Component | Issue | Action Taken |
|---|---|---|
| PerformanceJournalGroup | Double-close bug undocumented | Fixed + documented in audit report |
| TraderEvaluatorPanel | Runtime disconnection understated | Clarified in phase_status_matrix.md |
| FinalDecisionGroup | Runtime disconnection understated | Clarified in phase_status_matrix.md |
| Learning layer | "Code complete" could mislead | Clarified in PHASE_4_5_HANDOFF.md |
