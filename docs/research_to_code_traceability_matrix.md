# Research-to-Code Traceability Matrix

## Date: 2026-03-28
## Purpose: Full traceability from research source → design concept → implementation file → runtime usage → test coverage

---

## How to Read This Matrix

Each row represents one distinct concept, rule, indicator, or pattern that was learned during Phase 1 research.

**Status definitions:**
- ✅ `FULLY_IMPLEMENTED` — Real executable Python logic exists; no NotImplementedError in call path
- ⚠️ `IMPLEMENTED_NOT_WIRED` — Code logic exists but is not called at runtime
- 🔧 `STUBBED` — Method/class exists with NotImplementedError; wired by name only
- 📄 `DOCUMENTED_ONLY` — Appears in docs/markdown; has no Python representation
- ❌ `INTENTIONALLY_EXCLUDED` — In rejected_ideas registry; must never be implemented
- 🚫 `MISSING_INCONSISTENT` — Referenced in code as a dependency but has no implementation path

---

## Section 1: Feature Computation Concepts

| Concept | Source | Extracted Rule | Implementation File | Runtime Usage | Tests | Status |
|---------|--------|---------------|---------------------|---------------|-------|--------|
| ATR14 (Wilder's) | source_04, risk_rules.md | ATR stop multiplier 2× | `src/features/compute.py::_atr_wilder()` | Called by `MarketDataGroup._compute_features()` (stub) | None | 🔧 STUBBED |
| ATR14 SMA-20 | data_contracts.md | Volatility regime comparison | `src/features/compute.py` (field in FeatureVector) | Called by IndicatorsGroup._compute_regime() (stub) | None | 🔧 STUBBED |
| EMA20 | source_04 | Trend direction filter | `src/features/compute.py::_ema()` | IndicatorsGroup (stub) | None | 🔧 STUBBED |
| EMA50 | source_04 | 20/50 crossover (H3-002) | `src/features/compute.py::_ema()` | IndicatorsGroup (stub) | None | 🔧 STUBBED |
| EMA200 | source_04 | BTC macro regime | `src/features/compute.py::_ema()` | IndicatorsGroup._compute_regime() (stub) | None | 🔧 STUBBED |
| RSI14 (Wilder's) | source_02, hypothesis H3-001 | Divergence detection | `src/features/compute.py::_rsi_wilder()` | IndicatorsGroup._detect_rsi_divergence() (stub) | None | 🔧 STUBBED |
| Bollinger Bands (20, 2σ) | hypothesis H3-004 | BB squeeze detection | `src/features/compute.py::_bollinger_bands()` | IndicatorsGroup._detect_bb_squeeze_breakout() (stub) | None | 🔧 STUBBED |
| BB Width Percentile | hypothesis H3-004 | Squeeze threshold (< 20th pctile) | `src/features/compute.py::_bb_width_percentile()` | IndicatorsGroup (stub) | None | 🔧 STUBBED |
| ADX14 (Wilder's) | source_02, ADX regime | Trend filter (ADX > 25 → trending) | `src/features/compute.py::_adx()` | IndicatorsGroup._compute_regime() (stub) | None | 🔧 STUBBED |
| True Range | risk_contract.md (ATR base) | Input to ATR computation | `src/features/compute.py::_true_range()` | ATR computation chain (stub) | None | 🔧 STUBBED |
| Volume SMA-20 | data_contracts.md | Volume ratio normalization | `src/features/compute.py` (field in FeatureVector) | MarketDataGroup (stub) | None | 🔧 STUBBED |
| Volume Ratio | hypothesis H5-002, pump_detection | volume / volume_sma20 | `src/features/compute.py` (field in FeatureVector) | PumpDetector.is_pump_active() (stub) | None | 🔧 STUBBED |
| Candle anatomy | data_contracts.md | Body, range, shadows, ratios | `src/features/compute.py::_candle_anatomy()` | CandlestickGroup (stub) | None | ✅ FULLY_IMPLEMENTED |
| Impulse flag | source_02 (divergence filter) | candle_range > 2× ATR14 | `src/core/schemas.py::FeatureVector.impulse_flag` | IndicatorsGroup.RSI divergence filter (stub) | None | 📄 DOCUMENTED_ONLY (field defined; logic to populate it is stub) |
| Doji flag | source_03, hypothesis H2-005 | body_ratio < 0.1 | `src/core/schemas.py::FeatureVector.doji_flag` | CandlestickGroup._detect_doji() (stub) | None | 📄 DOCUMENTED_ONLY (field defined; logic to populate it is stub) |
| MACD | source materials (general TA) | NOT selected — not in any hypothesis | None | None | None | ❌ INTENTIONALLY_EXCLUDED (not in hypothesis registry; EMA crossover chosen instead) |

---

## Section 2: Chart Pattern Hypotheses (H1 Series)

| Hypothesis | Source | Pattern Class | State Machine | Signal Type | Runtime Path | Tests | Status |
|------------|--------|---------------|---------------|-------------|--------------|-------|--------|
| H1-001: Head & Shoulders Top | source_04, Bulkowski (~7% failure) | `HeadAndShouldersMachine` | `advance()` — STUB | `ChartPatternSignal` | ChartPatternGroup → EntryGroup → Risk | None | 🔧 STUBBED |
| H1-002: Inverse H&S Bottom | source_04, Bulkowski (high reliability) | `HeadAndShouldersMachine` | `advance()` — STUB | `ChartPatternSignal` | ChartPatternGroup → EntryGroup → Risk | None | 🔧 STUBBED |
| H1-003: Double Bottom (confirmed) | source_04, Bulkowski (3% failure confirmed, 64% unconfirmed) | `DoubleBottomMachine` | `advance()` — STUB | `ChartPatternSignal` | ChartPatternGroup → EntryGroup → Risk | None | 🔧 STUBBED |
| H1-004: Descending Triangle | source_04, Bulkowski (4% failure) | `DescendingTriangleMachine` | `advance()` — STUB | `ChartPatternSignal` | ChartPatternGroup → EntryGroup → Risk | None | 🔧 STUBBED |
| H1-005: Triple Bottom | source_04, Bulkowski (4% failure) | `TripleBottomMachine` | `advance()` — STUB | `ChartPatternSignal` | ChartPatternGroup → EntryGroup → Risk | None | 🔧 STUBBED |
| H1-006: Bull Flag | source_04, Bulkowski (12-13% failure) | **No class** | **No stub** | **None** | **None** | None | 🚫 MISSING_INCONSISTENT |
| H1-007: High & Tight Flag | source_04, Bulkowski (17% failure) | **No class** | **No stub** | **None** | **None** | None | 🚫 MISSING_INCONSISTENT |
| H1-008: Falling Wedge | source_04, Bulkowski (10% failure) | **No class** | **No stub** | **None** | **None** | None | 🚫 MISSING_INCONSISTENT |
| H1-009: Pipe Bottom | source_04, Bulkowski (12% failure) | **No class** | **No stub** | **None** | **None** | None | 🚫 MISSING_INCONSISTENT |

**Note on H1-006 through H1-009:** These four hypotheses are listed in `HYPOTHESIS_REGISTRY` in `src/core/registry.py` (sprint S3, priority HIGH). They are also in `GROUP_REGISTRY` under `chart_pattern.active_hypotheses`. However, there is no state machine class, no stub, and no reference to them anywhere in `src/groups/chart_pattern/`. This is an inconsistency: the registry declares them as active but the group has zero code for them.

---

## Section 3: Candlestick Pattern Hypotheses (H2 Series)

| Hypothesis | Source | Detector Method | Structural Level Required | Inverted Logic Note | Tests | Status |
|------------|--------|----------------|--------------------------|---------------------|-------|--------|
| H2-001: Engulfing (Bullish/Bearish) | source_03, Bulkowski | `CandlestickGroup._detect_engulfing()` | YES — at_resistance or at_support | Standard interpretation | None | 🔧 STUBBED |
| H2-002: Morning/Evening Star | source_03 | `CandlestickGroup._detect_morning_evening_star()` | YES — at S/R | Standard interpretation | None | 🔧 STUBBED |
| H2-003: Three Black Crows | source_03 | `CandlestickGroup._detect_three_black_crows()` | NO — trend continuation | Standard; requires uptrend (EMA20 > EMA50) | None | 🔧 STUBBED |
| H2-004: Inverted Hammer | source_03, Bulkowski (60% bearish) | `CandlestickGroup._detect_inverted_hammer()` | Preferred at resistance | **SHORT signal — inverts textbook** | None | 🔧 STUBBED |
| H2-005: Doji | source_03 | `CandlestickGroup._detect_doji()` | Preferred at S/R | After 2+ same-direction candles | None | 🔧 STUBBED |
| Hanging Man | source_03, Bulkowski (33% reversal) | — | — | — | None | ❌ INTENTIONALLY_EXCLUDED (RJ-001) |
| Shooting Star (standalone) | source_03, Bulkowski (60% reversal) | — | — | — | None | ❌ INTENTIONALLY_EXCLUDED (RJ-002) |
| Hammer (standalone long) | source_03 | — | — | — | None | ❌ INTENTIONALLY_EXCLUDED (RJ-010) |

---

## Section 4: Indicator Signal Hypotheses (H3 Series)

| Hypothesis | Source | Detector Method | Context Filters | Tests | Status |
|------------|--------|----------------|-----------------|-------|--------|
| H3-001: RSI Divergence | source_02, Bulkowski context | `IndicatorsGroup._detect_rsi_divergence()` | ADX14 > 25; suppress if impulse_flag=True; 2 pivot minimum | None | 🔧 STUBBED |
| H3-002: EMA 20/50 Crossover | source_01, Bulkowski baseline | `IndicatorsGroup._detect_ema_crossover()` | ADX14 > 20; regime filter for longs | None | 🔧 STUBBED |
| H3-003: ATR vs Fixed Stops Sharpe | source_04 risk rules | **No detector method** | — | None | 🚫 MISSING_INCONSISTENT (in HYPOTHESIS_REGISTRY; no code implementation path) |
| H3-004: BB Squeeze Breakout | hypothesis registry | `IndicatorsGroup._detect_bb_squeeze_breakout()` | bb_width_pct < 20th pctile; volume_ratio > 1.5 | None | 🔧 STUBBED |

**Note on H3-003:** H3-003 (ATR-scaled stops improve Sharpe vs fixed stops) is a meta-hypothesis about risk parameters, not a signal-generating hypothesis. It is in the registry but has no signal detector. It should be evaluated by the backtest engine as a parameter comparison, not by IndicatorsGroup. This inconsistency in the registry needs resolution.

---

## Section 5: Macro/Fundamental Hypotheses (H4 Series)

| Hypothesis | Source | Code Presence | Expected Group | Tests | Status |
|------------|--------|--------------|----------------|-------|--------|
| H4-001: High volume (>$10M/day) → lower failure rate | source_05, economics | `MarketDataConfig.min_volume_usd` constant (1e7) in config/settings.py | MarketDataGroup.refresh_universe() (stub) | None | 🔧 STUBBED |
| H4-002: BTC MVRV > 3.0 → lower forward returns | source_05, economics | Referenced in NewsMacroGroup._btc_mvrv field; `_classify_btc_macro()` stub | NewsMacroGroup | None | 🔧 STUBBED |
| H4-003: Bounce + bearish signal after >15% drop | source_02 | **No code** — not in any group's detector methods | Candlestick or Indicators group (unresolved) | None | 🚫 MISSING_INCONSISTENT |
| H4-004: Inside bar closing bottom 25% → breakout | source_03, Bulkowski (70% downside) | **No code** — no inside bar detector in CandlestickGroup | CandlestickGroup (not wired) | None | 🚫 MISSING_INCONSISTENT |

---

## Section 6: Meta/Structural Hypotheses (H5 Series)

| Hypothesis | Source | Code Presence | Expected Group | Tests | Status |
|------------|--------|--------------|----------------|-------|--------|
| H5-001: Round-number stop hunts | research_notes | No signal detector; referenced in ATRStopPlacer anti-round-number logic (stub) | Entry or Indicators | None | 🚫 MISSING_INCONSISTENT |
| H5-002: Pump/volume anomaly filter | source_05 | `PumpDetector.is_pump_active()` in risk/checks.py (stub); `RiskLeverageGroup._check_pump_signal()` (stub) | RiskLeverageGroup | None | 🔧 STUBBED |

---

## Section 7: Risk Rules

| Rule | Source | Implementation File | Implementation Method | Tests | Status |
|------|--------|--------------------|----------------------|-------|--------|
| R-1: R-Multiple Position Sizing (1% default) | risk_rules.md | `src/risk/sizing.py::RMultipleSizer.compute()` | STUB | None | 🔧 STUBBED |
| R-2: ATR Stop Placement (2× ATR) | risk_rules.md | `src/risk/sizing.py::ATRStopPlacer.compute()` | STUB | None | 🔧 STUBBED |
| R-2a: Anti-Round-Number Stop Shift | risk_rules.md | `src/risk/sizing.py::ATRStopPlacer._is_near_round_number()` | STUB | None | 🔧 STUBBED |
| R-3: Portfolio Exposure (25% total, 15% cluster) | risk_rules.md | `src/risk/checks.py::PortfolioExposureChecker.check()` | STUB | None | 🔧 STUBBED |
| R-4: Liquidity Filter ($10M daily vol) | risk_rules.md | `RiskLeverageGroup._check_liquidity()` (eligible_symbols check only) | PARTIAL — checks membership, not volume | None | ⚠️ IMPLEMENTED_NOT_WIRED |
| R-5: Drawdown Controls (5% daily, 20% halt) | risk_rules.md | `src/risk/checks.py::DrawdownController.get_size_reduction()` | IMPLEMENTED | None | ✅ FULLY_IMPLEMENTED |
| R-6: Leverage Governance (max 3×) | risk_rules.md | `src/risk/checks.py::LeverageGovernor.check()` | IMPLEMENTED | None | ⚠️ IMPLEMENTED_NOT_WIRED (not called in RiskLeverageGroup) |
| R-7: Pump Detection (5× volume) | risk_rules.md | `src/risk/checks.py::PumpDetector.is_pump_active()` | STUB | None | 🔧 STUBBED |
| R-8: Event Risk (size reduction) | risk_rules.md | `RiskLeverageGroup._check_event_risk()` | STUB | None | 🔧 STUBBED |
| R-9: Trading Plan Completeness | risk_rules.md | `RiskLeverageGroup._check_plan_completeness()` | IMPLEMENTED | None | ✅ FULLY_IMPLEMENTED |

**Note on R-6:** `LeverageGovernor.check()` is implemented in `src/risk/checks.py` but is not imported or called in `src/groups/risk_leverage/group.py`. It exists in isolation. It is not in the `_evaluate_proposal()` call chain.

---

## Section 8: Validation & Learning Concepts

| Concept | Source | Implementation File | Method | Tests | Status |
|---------|--------|--------------------|---------|----|--------|
| Bonferroni correction (p < 0.002) | ADR-004 | `src/backtest/metrics.py` | `BONFERRONI_THRESHOLD = 0.002` constant ✓ | None | ✅ FULLY_IMPLEMENTED (constant); backtest that computes it is STUB |
| Gate 1 criteria (PF>1.2, WR>45%, DD<30%, n≥30) | ADR-004 | `src/backtest/metrics.py::check_gate1()` | IMPLEMENTED | None | ✅ FULLY_IMPLEMENTED |
| Gate 2 criteria (PF>1.15, n≥20, OOS retention) | ADR-004 | `src/backtest/metrics.py::check_gate2()` | IMPLEMENTED | None | ✅ FULLY_IMPLEMENTED |
| OOS retention (≥60%) | ADR-004 | `src/backtest/metrics.py::check_oos_retention()` | IMPLEMENTED | None | ✅ FULLY_IMPLEMENTED |
| Win rate computation | learning_contract.md | `src/backtest/metrics.py::compute_win_rate()` | IMPLEMENTED | None | ✅ FULLY_IMPLEMENTED |
| Profit factor computation | learning_contract.md | `src/backtest/metrics.py::compute_profit_factor()` | STUB | None | 🔧 STUBBED |
| Max drawdown computation | learning_contract.md | `src/backtest/metrics.py::compute_max_drawdown()` | STUB | None | 🔧 STUBBED |
| Sharpe ratio computation | learning_contract.md | `src/backtest/metrics.py::compute_sharpe()` | STUB | None | 🔧 STUBBED |
| Edge decay detection (50 vs 200 trades) | learning_contract.md | `src/groups/performance_journal/group.py::_check_edge_decay()` | STUB | None | 🔧 STUBBED |
| Holdout enforcement (2023–2025 locked) | ADR-004 | `src/backtest/holdout.py::HoldoutManager` | IMPLEMENTED (all 4 methods) | None | ✅ FULLY_IMPLEMENTED |
| Parameter sensitivity (±20%) | validation_methodology.md | **No code** | **No method, no stub** | None | 📄 DOCUMENTED_ONLY |
| Bootstrap CI (10,000 draws) | validation_methodology.md | **No code** | **No method, no stub** | None | 📄 DOCUMENTED_ONLY |
| IS t-test on R-multiples | validation_methodology.md | **No code** | **No method, no stub** | None | 📄 DOCUMENTED_ONLY |
| Hypothesis status promotion | registry.md, learning_contract | `src/core/registry.py::HypothesisStatus` (enum) | Enum defined; no method mutates hypothesis status | None | 📄 DOCUMENTED_ONLY |
| Hypothesis status mutation | learning_contract.md | **No code** | There is no function that calls `HYPOTHESIS_REGISTRY[id].status = ...` | None | 🚫 MISSING_INCONSISTENT |

---

## Section 9: Structural Concepts

| Concept | Source | Implementation | Tests | Status |
|---------|--------|---------------|-------|--------|
| Swing high/low (5-bar fractal) | architecture docs | `TechnicalStructureGroup._detect_swing_high()` / `_detect_swing_low()` — STUB | None | 🔧 STUBBED |
| S/R level clustering (min 2 touches) | architecture docs | `TechnicalStructureGroup._merge_pivot_into_levels()` — STUB | None | 🔧 STUBBED |
| at_resistance / at_support flags | data_contracts.md | `StructuralLevelBundle.at_resistance/at_support` fields defined; `_build_bundle()` — STUB | None | 🔧 STUBBED |
| S/R level decay (level broken) | architecture docs (mentioned) | Not mentioned in code at all | None | 📄 DOCUMENTED_ONLY |
| Trend direction (higher highs / higher lows) | architecture docs (Stage 3) | Not mentioned in code | None | 📄 DOCUMENTED_ONLY |
| Structural level proximity (1× ATR) | CandlestickGroup docstring | AT_LEVEL_ATR_MULT=1.0 constant defined ✓ | None | ✅ FULLY_IMPLEMENTED (constant); usage is stub |

---

## Section 10: Scoring & Entry Aggregation

| Concept | Source | Implementation | Tests | Status |
|---------|--------|---------------|-------|--------|
| Composite score formula (35/25/20/10/10) | entry/group.py docstring | Constants NOT declared; formula NOT coded | None | 📄 DOCUMENTED_ONLY |
| Confirmation gate (≥2 groups, ≥1 chart/candle) | entry/group.py docstring | `CONFIRMATION_GATE_MIN_GROUPS=2` declared; gate logic is stub | None | 🔧 STUBBED |
| Conflict resolution (highest score wins; tie → skip) | ConflictReport schema | ConflictReport dataclass defined; no ConflictAgent implementation | None | 🔧 STUBBED |
| Regime filter (no longs in bear) | entry/group.py docstring | Not even mentioned as a constant or check in code | None | 📄 DOCUMENTED_ONLY |
| HistorianAgent query | entry/group.py | `self._historian = None`; no factory or implementation | None | 🚫 MISSING_INCONSISTENT |
| CriticAgent invocation | entry/group.py, ADR-003 | `self._critic = None`; `_call_llm()` raises NotImplementedError | None | 🔧 STUBBED (abstract method exists; no concrete implementation) |

---

## Section 11: Intentionally Excluded Concepts (Full List)

| Concept | Registry Code | Reason | Correctly Absent |
|---------|--------------|--------|-----------------|
| MACD | — | Not selected; EMA crossover used | ✅ Yes |
| Stochastic Oscillator | — | Not in hypothesis list | ✅ Yes |
| Elliott Wave | — | Unfalsifiable | ✅ Yes |
| Wyckoff phases | — | No testable rules | ✅ Yes |
| Harmonic patterns | — | No empirical validation | ✅ Yes |
| Hanging Man | RJ-001 | 33% reversal rate | ✅ Yes |
| Shooting Star (standalone) | RJ-002 | 60% reversal, needs S/R context | ✅ Yes |
| Hammer (standalone long) | RJ-010 | No confirmation | ✅ Yes |
| Failed breakout retry < 5 bars | RJ-007 | Implemented as cooldown check | ✅ Yes |
| Tight stops < 0.5× ATR | RJ-008 | Stop-hunt risk | ✅ Yes |
| Patterns in ranging market (ADX < 20) | RJ-009 | Noise | ✅ Yes |
| CNBC reverse indicator | — | Not systematic | ✅ Yes |
| Halving cycle trading | — | Not falsifiable | ✅ Yes |
| DOGE/meme cycles | — | No systematic basis | ✅ Yes |
| Fibonacci retracements | — | Mysticism | ✅ Yes |
| MVRV as direct trade signal | — | Macro filter only, not entry | ✅ Yes |

All 16 intentional exclusions are correctly absent from implementation.

---

## Summary by Status

| Status | Count | Examples |
|--------|-------|---------|
| ✅ FULLY_IMPLEMENTED | 18 | Core schemas, EventBus, SystemState, HoldoutManager, Gate checks |
| ⚠️ IMPLEMENTED_NOT_WIRED | 2 | LeverageGovernor (not in RiskLeverageGroup call chain), R-4 liquidity (partial) |
| 🔧 STUBBED | 47 | All signal detectors, all feature computations, position sizing |
| 📄 DOCUMENTED_ONLY | 9 | Composite score weights, parameter sensitivity, statistical tests, status mutation |
| 🚫 MISSING_INCONSISTENT | 9 | H1-006 through H1-009, H4-003, H4-004, H3-003 framing, HistorianAgent, hypothesis status mutation |
| ❌ INTENTIONALLY_EXCLUDED | 16 | MACD, Elliott Wave, Hanging Man, etc. |
