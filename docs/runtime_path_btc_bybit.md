# BTC/Bybit Runtime Data Flow

**Phase 3 — RESEARCH mode**
**Updated:** 2026-03-28

This document describes the actual data flow when `python main_btc.py` is executed.
It covers both the simplified `main_btc.py` path and the intended live group pipeline
path (which is partially wired but not yet fully operational).

---

## Path A: main_btc.py Analysis Mode (WORKING)

This is the runnable path in Phase 3.

```
1. main_btc.py starts
   └── parse_args() → setup_logging()
   └── asyncio.run(run_analysis(timeframe, bars))

2. fetch_btc_bars("BTCUSDT", "60", 500)
   ├── BybitAdapter.setup() → httpx.AsyncClient initialized
   ├── Loop: adapter.fetch_bars(symbol="BTCUSDT", interval="60", limit=200)
   │   ├── GET https://api.bybit.com/v5/market/klines
   │   │   ?category=linear&symbol=BTCUSDT&interval=60&limit=200[&end=...]
   │   ├── Response: {"retCode": 0, "result": {"list": [[ts, o, h, l, c, vol, volUsd], ...]}}
   │   ├── Parse each row → OHLCVBar (Decimal prices, UTC datetime)
   │   └── OHLCVBar.__post_init__ validates: high >= max(open,close), low <= min(open,close)
   ├── Paginate backwards until 500 bars accumulated (200 bars/page × 3 pages)
   └── Return list[OHLCVBar], oldest-first, len ≈ 500

3. compute_features_for_bars(bar_list)
   ├── FeatureComputer() instantiated (stateless)
   ├── For each bar[i], accumulate bar_buffer[0..i]
   ├── If len(bar_buffer) < 200: skip (warmup)
   └── FeatureComputer.compute(bar_buffer):
       ├── ATR14 (Wilder's smoothing, 14-period)
       ├── ATR14 SMA-20 (rolling ATR history)
       ├── EMA-20, EMA-50, EMA-200 (exponential, oldest-first)
       ├── prev_ema20, prev_ema50 (prior bar values)
       ├── RSI-14 (Wilder's method, 14 changes)
       ├── Bollinger Bands (20-period, 2σ)
       ├── BB width percentile rank (100-bar lookback)
       ├── ADX-14 (14-bar DX + 14-bar smoothing)
       ├── Volume SMA-20 and ratio
       ├── Candle anatomy (body, shadows, ratios)
       ├── impulse_flag (range > 2 × ATR14)
       └── doji_flag (body_ratio < 0.1)
   └── Returns list[(OHLCVBar, FeatureVector)], len ≈ 300 (last 300 of 500 bars)

4. Regime Classification (in run_analysis)
   ├── close vs EMA200, EMA50 → "bull" / "bear" / "ranging"
   ├── ADX > 25 → trending = True
   └── ATR14 / ATR14_SMA20 → "high" / "normal" / "low" volatility

5. Signal Detection (simplified, in run_analysis)
   ├── H3-002: prev_ema20 < prev_ema50 AND ema20 > ema50 → Golden Cross LONG
   ├── H3-002: prev_ema20 > prev_ema50 AND ema20 < ema50 → Death Cross SHORT
   ├── H3-001: RSI14 < 30 → oversold watch (LONG)
   ├── H3-001: RSI14 > 70 → overbought watch (SHORT)
   └── H3-004: bb_width_pct < 20 → BB squeeze alert

6. JournalDB.insert_journal_event("analysis_complete", ...)
   └── SQLite write to data/journal.db (created if not exists)

7. Output to stdout via logging (INFO level by default)
```

---

## Path B: main_btc.py Backtest Mode (WORKING, simplified)

```
1. asyncio.run(run_backtest(timeframe, start, end))

2. fetch_btc_bars() → same as Path A step 2

3. Filter bars to [start_dt, end_dt]

4. BacktestConfig created with initial_equity=$100k, risk_fraction=1%

5. BacktestEngine.run({BTCUSDT: filtered_bars})
   ├── FeatureComputer() per symbol
   ├── Bar-by-bar loop:
   │   ├── Accumulate bar_buffer
   │   ├── Skip until 200 bars (warmup)
   │   ├── FeatureComputer.compute(bar_buffer) → FeatureVector
   │   ├── POSITION CHECK (if open_position):
   │   │   ├── bar.low <= stop → stop loss exit
   │   │   ├── bar.high >= target → target hit exit
   │   │   └── bars_held >= 20 → time stop exit
   │   ├── DRAWDOWN UPDATE
   │   └── SIGNAL CHECK (if no open position):
   │       ├── EMA20 crosses above EMA50 AND ADX > 20 → LONG entry
   │       ├── EMA20 crosses below EMA50 AND ADX > 20 → SHORT entry
   │       └── Size: equity × 1% / (2 × ATR14) = base units
   └── Return BacktestResult (trades, WR, PF, maxDD, final equity)

6. Log results summary
```

---

## Path C: Intended Live Group Pipeline (PARTIALLY WIRED, not fully operational)

This is what Phase 4 needs to complete. Documented here to show the intended
architecture.

```
1. main_btc.py (or a future main_live.py) starts event loop
   └── EventBus initialized (in-process asyncio pub/sub)
   └── SystemState initialized (mode=RESEARCH)

2. All groups call .setup() → subscribe to EventBus

3. MarketDataGroup polls Bybit REST every ~60s (1h bars)
   └── On new bar close:
       └── Publish BarCloseEvent(bar)

4. FeatureComputerGroup receives BarCloseEvent
   └── Compute FeatureVector from last 200+ bars
   └── Publish FeatureReadyEvent(features)

5. IndicatorsGroup receives FeatureReadyEvent
   ├── Compute regime (EMA/ADX-based)
   ├── Detect EMA crossover, RSI divergence, BB squeeze signals
   ├── Build GroupSignalBundle with IndicatorSignal list
   └── Publish GroupSignalEvent(bundle)

6. TechnicalStructureGroup receives FeatureReadyEvent
   ├── Detect swing highs/lows
   ├── Build S/R levels (min 2 touches)
   ├── Set at_resistance / at_support flags
   ├── Build StructuralLevelBundle
   └── Publish GroupSignalEvent(bundle)

7. CandlestickGroup receives FeatureReadyEvent + StructuralLevelBundle
   ├── Detect candlestick patterns (engulfing, doji, star patterns)
   ├── Score patterns (quality higher if at structural level)
   └── Publish GroupSignalEvent(bundle)

8. ChartPatternGroup receives FeatureReadyEvent (ongoing)
   ├── Update state machines for each active pattern (H1-001 through H1-005)
   ├── On CONFIRMED: emit ChartPatternSignal
   └── Publish GroupSignalEvent(bundle)

9. EntryGroup receives GroupSignalEvent from each upstream group
   ├── _collect_bundle: store in _pending_bundles[symbol][group_id]
   ├── Trigger when indicators bundle received
   ├── _evaluate_trade_opportunity:
   │   ├── Flatten all signals
   │   ├── Count LONG vs SHORT
   │   ├── Confirmation gate: need >= 2 signals agreeing
   │   ├── Regime filter: block LONG in bear macro
   │   ├── Composite score = 0.35×chart + 0.25×candle + 0.20×indicator + 0.10×structure + 0.10×history
   │   ├── Gate: score >= 0.50
   │   ├── (Phase 4) Historian query → HistoricalAnalog
   │   ├── (Phase 4) Critic if score >= 0.60 → CriticReport
   │   └── Publish CandidateTradeEvent(proposal)

10. RiskLeverageGroup receives CandidateTradeEvent
    ├── Run 9 risk rules (daily loss, drawdown, exposure, spread, pump, mode gate...)
    ├── If all pass: Publish RiskDecisionEvent(approved=True, order=RiskApprovedOrder)
    └── If any fail: Publish RiskDecisionEvent(approved=False, rejection=...)

11. (Phase 4) ExecutionGroup receives RiskDecisionEvent
    ├── Mode gate check (RESEARCH → log only; SHADOW → paper order; LIVE → real order)
    └── Open position, update SystemState

12. ExitGroup monitors open positions on each BarCloseEvent
    └── Publish PositionCloseEvent on stop/target/time-stop hit

13. PerformanceJournalGroup writes all events to JournalDB (SQLite)
```

---

## Key Timing Constraints

- FeatureComputer requires 200 bars before producing output.
- On 1h bars: 200 bars = ~8.3 days of history before any signal can fire.
- On 4h bars: 200 bars = ~33 days of history required.
- Bybit REST API: max 200 bars per request. Pagination needed for > 200 bars.
- Rate limit: Bybit public endpoints allow ~120 requests/minute. The system
  uses `asyncio.sleep(0.2)` between pages as a courtesy delay.

---

## Error Paths

- **Bybit API unavailable**: `BybitAdapter.fetch_bars` raises `httpx.HTTPError`.
  `main_btc.py` does not catch this — it will propagate and terminate. Add retry
  logic in Phase 4.
- **Insufficient bars (< 200)**: `run_analysis` checks and returns early with
  an error log. No crash.
- **FeatureComputer returns None**: Silently skipped in bar loop. Will eventually
  produce output once warmup is satisfied.
- **JournalDB fails to write**: Error is logged but does not crash the analysis.
  (`insert_journal_event` has a broad `except Exception` that logs and continues.)
