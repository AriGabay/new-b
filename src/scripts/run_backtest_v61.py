#!/usr/bin/env python3
"""
V6.1 Full Backtest — 3 symbols (BTCUSDT, ETHUSDT, BNBUSDT), fixed thresholds.

Runs BacktestEngine.run_full_pipeline() with all 3 symbol CSVs sequentially
through a shared runner ($1,000 initial equity, matching V5 baseline).

Usage:
    PYTHONPATH=src python src/scripts/run_backtest_v61.py

Output:
    analysis/historical_eval/report_v6_1.txt
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

_SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
for _noisy in (
    "groups.entry", "groups.panel_decision", "groups.risk_leverage",
    "groups.exit", "groups.indicators", "groups.candlestick",
    "groups.chart_pattern", "groups.technical_structure",
    "groups.market_data", "groups.historian",
    "mdp.policy", "mdp.transition_logger", "learning",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

from backtest.engine import BacktestConfig, BacktestEngine, BacktestResult  # noqa
from core.schemas import OHLCVBar                                           # noqa

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
DATA_DIR    = os.path.join(_PROJECT_ROOT, "analysis", "historical_eval", "data")
REPORT_FILE = os.path.join(_PROJECT_ROOT, "analysis", "historical_eval", "report_v6_1.txt")

INITIAL_EQUITY = Decimal("1000")   # match V5 baseline
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

# Approximate weeks in the data set (18,288 bars at 1h = 762 days = 108.9 weeks)
WEEKS_IN_DATASET = 18288 / (7 * 24)

# V5 and V6.0 reference values
V5_REF  = {"trades": 34, "tpw": 0.50, "wr": 0.603, "pf": 1.21,
           "avg_w": 16, "avg_l": 19, "ratio": 0.84, "pnl": 95}
V60_REF = {"trades": 165, "tpw": 1.52, "wr": 0.461, "pf": 0.86,
           "avg_w": 260, "avg_l": 256, "ratio": 1.01, "pnl": -3092}

# Pass criteria
PASS_TPW   = 1.0
PASS_PF    = 1.3
PASS_RATIO = 1.1
PASS_PNL   = 150.0

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _csv_fname(symbol: str) -> str:
    return os.path.join(DATA_DIR, f"{symbol.lower()}_1h_2024_2025.csv")


def load_bars(symbol: str) -> list[OHLCVBar]:
    """Load 1h OHLCV bars from CSV for the given symbol."""
    path = _csv_fname(symbol)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}")
    bars: list[OHLCVBar] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_str = row["timestamp"]
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bars.append(OHLCVBar(
                symbol=symbol,
                timeframe="1h",
                timestamp=ts,
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=Decimal(row["volume"]),
                volume_usd=Decimal(row["volume_usd"]),
            ))
    return bars


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def _per_symbol_stats(trade_records: list[dict]) -> dict[str, dict]:
    """Break down trade_records by symbol."""
    by_sym: dict[str, list[dict]] = defaultdict(list)
    for t in trade_records:
        by_sym[t.get("symbol", "unknown")].append(t)

    stats: dict[str, dict] = {}
    for sym, trades in by_sym.items():
        wins   = [t for t in trades if t["pnl_usd"] > 0]
        losses = [t for t in trades if t["pnl_usd"] <= 0]
        gw = sum(t["pnl_usd"] for t in wins)
        gl = abs(sum(t["pnl_usd"] for t in losses))
        stats[sym] = {
            "count":  len(trades),
            "wins":   len(wins),
            "losses": len(losses),
            "wr":     len(wins) / len(trades) if trades else 0.0,
            "pf":     gw / gl if gl > 0 else float(len(wins)),
            "avg_w":  gw / len(wins)   if wins   else 0.0,
            "avg_l":  gl / len(losses) if losses else 0.0,
            "net":    sum(t["pnl_usd"] for t in trades),
        }
    return stats


def _gates(tpw: float, pf: float, ratio: float, net: float) -> dict[str, bool]:
    return {
        f"Trades/week >= {PASS_TPW:.1f}":  tpw   >= PASS_TPW,
        f"Profit Factor >= {PASS_PF:.1f}": pf    >= PASS_PF,
        f"AvgW/AvgL >= {PASS_RATIO:.1f}":  ratio >= PASS_RATIO,
        f"Net PnL > ${PASS_PNL:.0f}":      net   > PASS_PNL,
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(
    result: BacktestResult,
    elapsed_s: float,
) -> str:
    meta    = result.per_hypothesis.get("_meta", {})
    records = meta.get("trade_records", [])
    bars_proc = meta.get("bars_processed", 0)
    avg_w   = meta.get("avg_winner_usd", 0.0)
    avg_l   = abs(meta.get("avg_loser_usd", 0.0))
    ratio   = (avg_w / avg_l) if avg_l > 0 else 0.0
    tpw     = result.total_trades / WEEKS_IN_DATASET
    net     = float(result.total_pnl_usd)

    per_sym = _per_symbol_stats(records)
    gates   = _gates(tpw, result.profit_factor, ratio, net)
    verdict = "PASS" if all(gates.values()) else "FAIL"

    sep = "=" * 64

    lines: list[str] = [
        sep,
        "  V6.1 BACKTEST REPORT — 3-Symbol Full Pipeline",
        f"  Date        : {datetime.now().strftime('%Y-%m-%d')}",
        f"  Symbols     : {', '.join(SYMBOLS)}",
        f"  Data        : BTCUSDT/ETHUSDT/BNBUSDT 1h, {bars_proc:,} bars processed",
        f"  Equity      : ${float(INITIAL_EQUITY):,.0f}",
        f"  Run time    : {elapsed_s:.1f}s",
        f"  Changes vs V5: Exit trail (11A) + thresholds bull=14/ranging=15 (11B/11E)",
        "                 + multi-symbol infrastructure (11C) + ETH/BNB data (11E)",
        sep,
        "",
        "1. COMBINED PERFORMANCE",
        "─" * 64,
        f"  Total trades  : {result.total_trades}",
        f"  Trades/week   : {tpw:.2f}",
        f"  Win rate      : {result.win_rate:.1%}",
        f"  Profit Factor : {result.profit_factor:.2f}",
        f"  Avg Winner    : ${avg_w:.2f}",
        f"  Avg Loser     : ${avg_l:.2f}",
        f"  AvgW/AvgL     : {ratio:.3f}",
        f"  Max Drawdown  : {result.max_drawdown_pct:.1%}",
        f"  Net PnL       : ${net:+.2f}  on ${float(INITIAL_EQUITY):,.0f} equity",
        f"  Final equity  : ${float(result.final_equity):,.2f}",
        "",
        "2. PER-SYMBOL BREAKDOWN",
        "─" * 64,
    ]

    for sym in SYMBOLS:
        s = per_sym.get(sym)
        if s:
            lines.append(
                f"  {sym:<10}: {s['count']:3d} trades | "
                f"WR {s['wr']:.1%} | PF {s['pf']:.2f} | "
                f"AvgW ${s['avg_w']:.2f} / AvgL ${s['avg_l']:.2f} | "
                f"Net ${s['net']:+.2f}"
            )
        else:
            lines.append(f"  {sym:<10}: 0 trades (no signals passed all gates)")

    lines += [
        "",
        "3. VS BASELINES",
        "─" * 64,
        f"  {'Metric':<20} {'V5 (BTC T=15)':<18} {'V6.0 (BTC T=12)':<18} {'V6.1 (3-sym T=14/15)':<20}",
        "  " + "─" * 60,
        f"  {'Trades/week':<20} {V5_REF['tpw']:<18.2f} {V60_REF['tpw']:<18.2f} {tpw:<20.2f}",
        f"  {'Win rate':<20} {V5_REF['wr']:<18.1%} {V60_REF['wr']:<18.1%} {result.win_rate:<20.1%}",
        f"  {'Profit Factor':<20} {V5_REF['pf']:<18.2f} {V60_REF['pf']:<18.2f} {result.profit_factor:<20.2f}",
        f"  {'AvgW/AvgL':<20} {V5_REF['ratio']:<18.2f} {V60_REF['ratio']:<18.2f} {ratio:<20.3f}",
        f"  {'Net PnL ($1K)':<20} ${V5_REF['pnl']:<17} N/A ($10K base)      ${net:<+.2f}",
        "",
        "4. VERDICT",
        "─" * 64,
        f"  {verdict}  ({sum(gates.values())}/{len(gates)} pass criteria met)",
        "",
    ]
    for label, passed in gates.items():
        tick = "PASS ✓" if passed else "FAIL ✗"
        lines.append(f"    {label:<40} {tick}")

    if verdict == "FAIL":
        lines += [
            "",
            "  FAILED CRITERIA:",
        ]
        for label, passed in gates.items():
            if not passed:
                lines.append(f"    ✗ {label}")

    lines += [
        "",
        "5. ANALYSIS",
        "─" * 64,
        "  Exit trail fix (11A): AvgW/AvgL should be near or above 1.0.",
        f"  Threshold regime (11E): bull=14, ranging/bear=15.",
        f"    T=14 (bull/trending) — slightly more permissive than T=15,",
        f"    gives small frequency gain in trending markets.",
        f"    T=15 (ranging/bear)  — proven profitable threshold from V5 sweep.",
        f"  Multi-symbol (11C): 3×BTC bars processed sequentially then ETH then",
        f"    BNB through the same $1K account. Trade count is additive across",
        f"    symbols; trades/week = total / 108.9 weeks of data.",
        sep,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run() -> None:
    logger.info("=" * 64)
    logger.info("  V6.1 FULL PIPELINE BACKTEST — 3 symbols")
    logger.info("=" * 64)

    # Load all symbol data
    all_bars: dict[str, list[OHLCVBar]] = {}
    for sym in SYMBOLS:
        try:
            bars = load_bars(sym)
            all_bars[sym] = bars
            logger.info("Loaded %s: %d bars  (%s → %s)",
                        sym, len(bars),
                        bars[0].timestamp.strftime("%Y-%m-%d"),
                        bars[-1].timestamp.strftime("%Y-%m-%d"))
        except FileNotFoundError as exc:
            logger.warning("Skipping %s: %s", sym, exc)

    if not all_bars:
        logger.error("No data files found — aborting.")
        sys.exit(1)

    config = BacktestConfig(
        symbols        = list(all_bars.keys()),
        timeframe      = "1h",
        start_date     = list(all_bars.values())[0][0].timestamp,
        end_date       = list(all_bars.values())[0][-1].timestamp,
        initial_equity = INITIAL_EQUITY,
        enforce_holdout= False,
        output_db_path = "data/backtest_journal.db",
    )

    logger.info("Running full pipeline backtest (%d symbols × ~%d bars)...",
                len(all_bars), max(len(v) for v in all_bars.values()))
    t0 = time.perf_counter()
    engine = BacktestEngine(config)
    result = await engine.run_full_pipeline(all_bars, verbose=True)
    elapsed = time.perf_counter() - t0

    report = build_report(result, elapsed)
    print("\n" + report)

    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    logger.info("Report saved → %s", REPORT_FILE)


if __name__ == "__main__":
    asyncio.run(run())
