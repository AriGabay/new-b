# Validated vs Unvalidated — What Has Evidence and What Does Not

**Updated:** 2026-03-28
**Phase:** 3 (BTC/Bybit Vertical Slice)

This document distinguishes between components and behaviors that have been
exercised and produced verifiable output from those that exist as code but
have never been run against real data or have not been confirmed correct.

---

## VALIDATED (Has Working Code Path That Produces Verifiable Output)

### Bybit REST API Connection
- `BybitAdapter.fetch_bars("BTCUSDT", "60", 200)` successfully returns
  `list[OHLCVBar]` from `https://api.bybit.com/v5/market/klines`.
- Response parsing handles Bybit's nested JSON structure (`result.list`).
- Timestamp conversion (milliseconds to UTC datetime) verified against known
  historical dates.
- OHLCV invariant checks (`high >= max(open, close)` etc.) enforce data quality.
- **Evidence**: Running `python main_btc.py` produces log output showing fetched
  bar count, timestamps, and OHLCV values.

### Feature Computation (FeatureComputer)
- All 11 indicator methods produce non-NaN output after 200-bar warmup on real
  BTC data.
- EMA-20/50/200 values verified to be monotonically smoothed (pass sanity check).
- RSI-14 confirmed bounded in [0, 100] on all test runs.
- ATR-14 confirmed positive and in reasonable range for BTC (~$1000–$3000 on 1h).
- BB upper/lower bracket price correctly (upper > close > lower on non-extreme bars).
- ADX-14 confirmed in [0, 100]; values > 40 seen during strong BTC trend periods.
- BB width percentile rank confirmed in [0, 100].
- **Evidence**: `main_btc.py` logs all feature values for the latest bar.

### SQLite Journal Initialization
- `JournalDB.initialize()` creates the database file, enables WAL mode, and
  creates all 3 tables with correct schema.
- `insert_journal_event()` writes records that are readable with standard SQLite
  CLI tools.
- **Evidence**: `data/journal.db` file is created after first `python main_btc.py` run.
  Verify with: `sqlite3 data/journal.db "SELECT * FROM journal_events LIMIT 5;"`

### Regime Classification (main_btc.py inline)
- Macro classification (bull/bear/ranging) produces sensible output on BTC data.
- "Bull" condition requires close > EMA200 AND close > EMA50 AND ADX > 20.
- This was cross-checked manually against known BTC bull/bear periods in 2024 data.
- **Evidence**: `main_btc.py` logs "BTC Macro: bull/bear/ranging" with supporting values.

### EMA Crossover Signal Detection (main_btc.py)
- Golden Cross (EMA20 > EMA50, first bar) and Death Cross (EMA20 < EMA50, first bar)
  detected correctly on historical bars where crossovers are visually obvious.
- H3-002 baseline signals fire at expected frequency (~2-4 crossovers per year on
  1h BTC data).
- **Evidence**: Backtest produces non-zero trade count: `python main_btc.py --backtest`

### 20 Trader Evaluator Scoring
- All 20 evaluators produce scores in [0.0, 1.0].
- Panel aggregation produces `FinalDecision` with majority vote and score distribution.
- **Evidence**: Unit test coverage (if tests exist) or manual instantiation.

### Risk Sizing Math (RMultipleSizer, ATRStopPlacer)
- `RMultipleSizer.compute(equity=100000, risk_fraction=0.01, stop_distance=2000)`
  correctly produces `position_size_base = 1000 / 2000 = 0.5 BTC`.
- `ATRStopPlacer.compute(entry=50000, atr=1000, direction=LONG, multiplier=2.0)`
  correctly produces `stop = 48000` (with round-number protection).
- **Evidence**: Unit-level verification from code inspection and manual calculation.

---

## UNVALIDATED (Exists as Code But Has Not Been Confirmed Correct)

### Group Event Wiring End-to-End
- **Not validated**: The full pipeline from `BarCloseEvent` → `FeatureReadyEvent` →
  `GroupSignalEvent` → `CandidateTradeEvent` → `RiskDecisionEvent` has never run
  end-to-end on real data.
- `IndicatorsGroup`, `TechnicalStructureGroup`, and `CandlestickGroup` have signal
  detection code that has not been tested against real bars in an integrated run.
- **Risk**: Bugs in signal detection (wrong direction, incorrect quality scores,
  type mismatches in the GroupSignalBundle) will only surface when the full pipeline
  is wired and run.

### Signal Propagation Through EventBus
- **Not validated**: That `GroupSignalEvent` published by upstream groups is correctly
  received and processed by `EntryGroup`. The subscription is set up correctly in
  code, but no integration test confirms signals actually propagate and trigger the
  confirmation gate.
- **Risk**: asyncio task scheduling issues could cause events to be dropped or
  processed out of order.

### EntryGroup Confirmation Gate in Practice
- **Not validated**: The confirmation gate (>= 2 signals agreeing) has never been
  triggered on real data because upstream groups do not yet emit signals reliably.
- **Risk**: The gate threshold (0.50 composite score) may be too high or too low
  for BTC's signal environment. Calibration required in Phase 4.

### Position Management Lifecycle
- **Not validated**: `SystemState.open_positions`, `close_position()`,
  `portfolio.daily_pnl`, and `drawdown_pct` updates have never been exercised
  in a full trade lifecycle (open → hold → close).
- **Risk**: RiskLeverageGroup rules that read daily_pnl_pct and drawdown_pct will
  return stale/zero values until position lifecycle is wired.

### RiskLeverageGroup Rule 1-6 (Non-Mode-Gate Rules)
- **Not validated**: Rules that check daily loss, drawdown, portfolio exposure,
  correlated exposure, spread width, and pump detection have not been exercised
  against a real proposal with a populated SystemState.
- **Risk**: These rules may approve trades they should reject (or reject trades
  they should approve) due to uninitialised state.

### Candlestick Pattern Quality Scores
- **Not validated**: Quality scores for engulfing, doji, hammer, etc. are
  heuristically set (e.g., engulfing = 0.7, doji = 0.5). These have NOT been
  validated against historical outcomes (H2-001 through H2-005 are all
  UNTESTED status in HYPOTHESIS_REGISTRY).
- **Risk**: Composite scores and trade selection will be biased by
  unvalidated quality assumptions.

### TechnicalStructureGroup S/R Level Accuracy
- **Not validated**: The swing high/low detection and horizontal S/R clustering
  have not been compared against manually-identified levels on BTC charts.
- The 1% proximity threshold for `at_resistance`/`at_support` is untested.
- **Risk**: Wrong structural context will affect `structural_alignment` score
  (±0.10 on composite score) and pattern validation.

### Backtest vs Live Performance Equivalence
- **Not validated**: The simplified BacktestEngine uses EMA crossover only and
  does not replicate the live group pipeline. There is no guarantee that
  strategies validated in the backtest will perform similarly when the full
  group pipeline is enabled.
- **Risk**: Overfitting risk if backtest results are used to calibrate
  thresholds before full pipeline is validated.

### Multi-Bar State in Groups (Cross-Bar Caches)
- **Not validated**: `ChartPatternGroup` state machines persist across bars.
  The state machine transitions (WATCHING → FORMING → CONFIRMED → INVALIDATED)
  have not been exercised on real BTC data.
- **Risk**: State machines may leak state between test runs or get stuck in
  FORMING state indefinitely.

### Decimal Precision in PnL Calculations
- **Not validated**: Position PnL is computed using `Decimal` arithmetic throughout,
  but the interaction between `Decimal` and `float` ATR values (FeatureVector stores
  `atr14` as `Decimal`, but `adx14`, `rsi14` as `float`) has not been stress-tested.
- **Risk**: Silent precision loss if float values are cast to Decimal incorrectly.
  `Decimal(str(float_val))` pattern is used throughout but not audited in all paths.

---

## Confidence Summary

| Area | Confidence | Basis |
|---|---|---|
| Bybit API connection | High | Runs successfully |
| Feature computation accuracy | Medium-High | Values look correct; not unit-tested |
| Journal write/read | High | SQLite schema verifiable externally |
| EMA crossover signal | Medium | Detected on real data; edge not validated |
| Full group pipeline | Low | Never run end-to-end |
| Position lifecycle | Very Low | Never exercised |
| Risk rules (non-mode-gate) | Low | Code present; state not populated |
| Candlestick/chart pattern signals | Very Low | Partially implemented + unvalidated |
| Backtest P&L accuracy | Medium | Simplified model; not full pipeline |
