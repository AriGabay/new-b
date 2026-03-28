# Runtime Mode Matrix

**Phase:** 4.75 Runtime Wiring
**Date:** 2026-03-28

---

## Mode Summary

| Mode | Command | Bybit Required | Group Pipeline | Panel+Decision | Learning Layer |
|---|---|---|---|---|---|
| `--run` | `python main_btc.py --run` | YES | FULL | YES | YES |
| `--simulate N` | `python main_btc.py --simulate 5` | NO | FULL | YES | YES |
| `--backtest` | `python main_btc.py --backtest` | YES (historical) | NO | NO | NO |
| `--analyze` | `python main_btc.py` | YES | NO | NO | NO |

---

## Component Activity by Mode

| Component | --run | --simulate | --backtest | --analyze |
|---|---|---|---|---|
| MarketDataGroup | ACTIVE | BYPASSED | BYPASSED | BYPASSED |
| IndicatorsGroup | ACTIVE | ACTIVE | NO | NO |
| CandlestickGroup | ACTIVE | ACTIVE | NO | NO |
| TechnicalStructureGroup | ACTIVE | ACTIVE | NO | NO |
| EntryGroup | ACTIVE | ACTIVE | NO | NO |
| PanelDecisionGroup (Layer B+C) | ACTIVE | ACTIVE | NO | NO |
| TraderEvaluatorPanel (20 traders) | ACTIVE | ACTIVE | NO | NO |
| FinalDecisionGroup | ACTIVE | ACTIVE | NO | NO |
| RiskLeverageGroup | ACTIVE | ACTIVE | NO | NO |
| ExitGroup | ACTIVE | ACTIVE | NO | NO |
| PerformanceJournalGroup | ACTIVE | ACTIVE | PARTIAL | NO |
| JournalExtension | ACTIVE | ACTIVE | NO | NO |
| DecisionTraceLogger | ACTIVE | ACTIVE | NO | NO |
| BacktestEngine | NO | NO | ACTIVE | NO |
| BybitAdapter | YES | NO | YES | YES |

---

## Outcome Source Tags

| Mode | OutcomeSource | Valid for calibration? |
|---|---|---|
| `--run` | `event_driven_runtime` | YES (after 30+ samples) |
| `--simulate` | `event_driven_runtime` | NO (synthetic input, not real market) |
| `--backtest` | `simplified_backtest` | NO (EMA-only, no trader panel) |
| `--analyze` | N/A (no trades) | N/A |

**IMPORTANT:** `--simulate` uses `event_driven_runtime` source tagging because
it exercises the full pipeline code. However, synthetic inputs are not real
market conditions. Calibration from simulation data is not valid for predicting
live performance.

---

## Running Modes

### --simulate (for development and testing)
```bash
cd /Users/arigabay/Code/new-b/src
python main_btc.py --simulate 10 --log-level DEBUG
```
Injects 10 synthetic bars with alternating bullish/neutral conditions.
Full pipeline runs without Bybit. Useful for verifying wiring, not trading logic.

### --run (for paper trading when Bybit available)
```bash
cd /Users/arigabay/Code/new-b/src
python main_btc.py --run --log-level INFO
```
Requires Bybit connectivity. Currently blocked (HTTP 404 from CDN).
Run from clean deployment environment.

### --backtest (for EMA baseline analysis)
```bash
cd /Users/arigabay/Code/new-b/src
python main_btc.py --backtest --bars 500 --log-level INFO
```
Runs EMA-crossover backtest. Does NOT exercise group pipeline.
Do NOT use results for trader calibration.
