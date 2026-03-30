#!/usr/bin/env python3
"""
V6.3 Backtest — 3 symbols, independent equity slices, +1 threshold for ETH/BNB.

Key fix vs V6.2:
  V6.2 confirmed ETH (PF 0.56) and BNB (PF 0.88) have poor edge with the
  BTC-calibrated panel even with separate equity slices.

  V6.3 adds a +1 approval-threshold offset for non-BTC symbols:
    BTC : bull=14 / ranging=15       (unchanged)
    ETH : bull=15 / ranging=16       (+1 vs BTC)
    BNB : bull=15 / ranging=16       (+1 vs BTC)

  This filters out marginal ETH/BNB setups where the panel is less reliable,
  at the cost of slightly fewer trades per symbol.

Usage:
    PYTHONPATH=src python src/scripts/run_backtest_v63.py

Output:
    analysis/historical_eval/report_v6_3.txt
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

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
REPORT_FILE = os.path.join(_PROJECT_ROOT, "analysis", "historical_eval", "report_v6_3.txt")

INITIAL_EQUITY_PER_SYMBOL = Decimal("1000")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
WEEKS_IN_DATASET = 18288 / (7 * 24)   # 108.9 weeks

# Threshold summary for this run
THRESHOLDS = {
    "BTCUSDT": {"bull": 14, "ranging": 15},
    "ETHUSDT": {"bull": 15, "ranging": 16},
    "BNBUSDT": {"bull": 15, "ranging": 16},
}

# Reference values
V5_REF  = {"trades": 34,  "tpw": 0.50, "wr": 0.603, "pf": 1.21, "ratio": 0.84,  "pnl": 95}
V62_REF = {"trades": 225, "tpw": 2.07, "wr": 0.480, "pf": 0.92, "ratio": 0.995, "pnl_avg": -92}

# Pass criteria (per-symbol for the per-$1K slice check; combined for verdict)
PASS_TPW   = 1.0
PASS_PF    = 1.3
PASS_RATIO = 1.1
PASS_PNL   = 150.0


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(symbol: str) -> list[OHLCVBar]:
    path = os.path.join(DATA_DIR, f"{symbol.lower()}_1h_2024_2025.csv")
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
# Metrics
# ---------------------------------------------------------------------------

def _sym_stats(records: list[dict]) -> dict:
    if not records:
        return {"count": 0, "wins": 0, "losses": 0, "wr": 0.0,
                "pf": 0.0, "avg_w": 0.0, "avg_l": 0.0, "net": 0.0}
    wins   = [t for t in records if t["pnl_usd"] > 0]
    losses = [t for t in records if t["pnl_usd"] <= 0]
    gw = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    return {
        "count":  len(records),
        "wins":   len(wins),
        "losses": len(losses),
        "wr":     len(wins) / len(records),
        "pf":     gw / gl if gl > 0 else float(len(wins)),
        "avg_w":  gw / len(wins)   if wins   else 0.0,
        "avg_l":  gl / len(losses) if losses else 0.0,
        "net":    sum(t["pnl_usd"] for t in records),
    }


def _gates(tpw: float, pf: float, ratio: float, avg_pnl: float) -> dict[str, bool]:
    return {
        f"Trades/week >= {PASS_TPW:.1f}":   tpw      >= PASS_TPW,
        f"Profit Factor >= {PASS_PF:.1f}":  pf       >= PASS_PF,
        f"AvgW/AvgL >= {PASS_RATIO:.1f}":   ratio    >= PASS_RATIO,
        f"Avg PnL > ${PASS_PNL:.0f}/slice": avg_pnl  > PASS_PNL,
    }


# ---------------------------------------------------------------------------
# Per-symbol runner
# ---------------------------------------------------------------------------

async def run_symbol(sym: str, bars: list[OHLCVBar]) -> tuple[BacktestResult, float]:
    config = BacktestConfig(
        symbols        = [sym],
        timeframe      = "1h",
        start_date     = bars[0].timestamp,
        end_date       = bars[-1].timestamp,
        initial_equity = INITIAL_EQUITY_PER_SYMBOL,
        enforce_holdout= False,
        output_db_path = "data/backtest_journal.db",
    )
    t0 = time.perf_counter()
    result = await BacktestEngine(config).run_full_pipeline({sym: bars}, verbose=True)
    return result, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(
    per_sym_results: dict[str, BacktestResult],
    per_sym_elapsed: dict[str, float],
    total_elapsed: float,
) -> str:
    all_records: list[dict] = []
    sym_stats: dict[str, dict] = {}
    bars_total = 0

    for sym in SYMBOLS:
        res = per_sym_results.get(sym)
        if res is None:
            sym_stats[sym] = _sym_stats([])
            continue
        meta    = res.per_hypothesis.get("_meta", {})
        records = meta.get("trade_records", [])
        bars_total += meta.get("bars_processed", 0)
        all_records.extend(records)
        sym_stats[sym] = _sym_stats(records)

    comb         = _sym_stats(all_records)
    tpw          = comb["count"] / WEEKS_IN_DATASET
    ratio        = (comb["avg_w"] / comb["avg_l"]) if comb["avg_l"] > 0 else 0.0
    combined_net = sum(float(r.total_pnl_usd) for r in per_sym_results.values())
    avg_pnl      = combined_net / max(1, len(per_sym_results))
    max_dd       = max((r.max_drawdown_pct for r in per_sym_results.values()), default=0.0)

    gates   = _gates(tpw, comb["pf"], ratio, avg_pnl)
    verdict = "PASS" if all(gates.values()) else "FAIL"

    sep = "=" * 64
    lines: list[str] = [
        sep,
        "  V6.3 BACKTEST REPORT — 3-Symbol, +1 Threshold for ETH/BNB",
        f"  Date        : {datetime.now().strftime('%Y-%m-%d')}",
        f"  Symbols     : {', '.join(SYMBOLS)}",
        f"  Data        : 1h bars, {bars_total:,} bars processed",
        f"  Equity      : ${float(INITIAL_EQUITY_PER_SYMBOL):,.0f} per symbol (independent slices)",
        f"  Run time    : {total_elapsed:.1f}s",
        f"  Thresholds  : BTC bull=14/ranging=15 | ETH bull=15/ranging=16 | BNB bull=15/ranging=16",
        f"  Change vs V6.2: +1 panel approve threshold for non-BTC symbols",
        sep,
        "",
        "1. COMBINED PERFORMANCE  (aggregated, avg PnL per $1K slice)",
        "─" * 64,
        f"  Total trades  : {comb['count']}",
        f"  Trades/week   : {tpw:.2f}",
        f"  Win rate      : {comb['wr']:.1%}",
        f"  Profit Factor : {comb['pf']:.2f}",
        f"  Avg Winner    : ${comb['avg_w']:.2f}",
        f"  Avg Loser     : ${comb['avg_l']:.2f}",
        f"  AvgW/AvgL     : {ratio:.3f}",
        f"  Max Drawdown  : {max_dd:.1%}  (worst single symbol)",
        f"  Combined PnL  : ${combined_net:+.2f}  across {len(per_sym_results)} × $1K slices",
        f"  Avg PnL/slice : ${avg_pnl:+.2f}  per $1K deployed",
        "",
        "2. PER-SYMBOL BREAKDOWN",
        "─" * 64,
    ]

    for sym in SYMBOLS:
        res = per_sym_results.get(sym)
        s   = sym_stats[sym]
        th  = THRESHOLDS.get(sym, {})
        th_str = f"T={th.get('bull','?')}/{th.get('ranging','?')}"
        if s["count"] > 0 and res is not None:
            lines.append(
                f"  {sym:<10} [{th_str}]: {s['count']:3d} trades | "
                f"WR {s['wr']:.1%} | PF {s['pf']:.2f} | "
                f"AvgW ${s['avg_w']:.2f} / AvgL ${s['avg_l']:.2f} | "
                f"Net ${s['net']:+.2f} | DD {res.max_drawdown_pct:.1%}"
            )
        else:
            lines.append(f"  {sym:<10} [{th_str}]: 0 trades")

    lines += [
        "",
        "3. VS BASELINES",
        "─" * 64,
        f"  {'Metric':<20} {'V5 (BTC T=15)':<18} {'V6.2 (indep)':<18} {'V6.3 (ETH+1)':<20}",
        "  " + "─" * 60,
        f"  {'Trades/week':<20} {V5_REF['tpw']:<18.2f} {V62_REF['tpw']:<18.2f} {tpw:<20.2f}",
        f"  {'Win rate':<20} {V5_REF['wr']:<18.1%} {V62_REF['wr']:<18.1%} {comb['wr']:<20.1%}",
        f"  {'Profit Factor':<20} {V5_REF['pf']:<18.2f} {V62_REF['pf']:<18.2f} {comb['pf']:<20.2f}",
        f"  {'AvgW/AvgL':<20} {V5_REF['ratio']:<18.2f} {V62_REF['ratio']:<18.3f} {ratio:<20.3f}",
        f"  {'Avg PnL/slice':<20} ${V5_REF['pnl']:<17} ${V62_REF['pnl_avg']:<17} ${avg_pnl:<+.2f}",
        "",
        "4. VERDICT",
        "─" * 64,
        f"  {verdict}  ({sum(gates.values())}/{len(gates)} pass criteria met)",
        "",
    ]
    for label, passed in gates.items():
        tick = "PASS ✓" if passed else "FAIL ✗"
        lines.append(f"    {label:<44} {tick}")

    if verdict == "FAIL":
        lines += ["", "  FAILED CRITERIA:"]
        for label, passed in gates.items():
            if not passed:
                lines.append(f"    ✗ {label}")

    lines += [
        "",
        "5. ANALYSIS",
        "─" * 64,
        "  The +1 offset raises ETH/BNB thresholds to bull=15, ranging=16.",
        "  Fewer but higher-quality setups should improve PF toward 1.0+.",
        "",
        "  If combined PF >= 1.3 and AvgW/AvgL >= 1.1 → enable all 3 symbols.",
        "  If only BTC passes → deploy BTC-only; ETH/BNB need further study.",
        "  If ETH PF > 1.0 but < 1.3 → paper trade ETH/BNB for 60 more days",
        "  before committing live capital.",
        sep,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run() -> None:
    logger.info("=" * 64)
    logger.info("  V6.3 BACKTEST — 3 symbols | ETH/BNB threshold +1")
    logger.info("=" * 64)

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
        import sys; sys.exit(1)

    per_sym_results: dict[str, BacktestResult] = {}
    per_sym_elapsed: dict[str, float] = {}
    wall_t0 = time.perf_counter()

    for sym, bars in all_bars.items():
        logger.info("-" * 64)
        logger.info("  %s — threshold bull=%d ranging=%d, equity=$%s",
                    sym,
                    THRESHOLDS[sym]["bull"],
                    THRESHOLDS[sym]["ranging"],
                    INITIAL_EQUITY_PER_SYMBOL)
        result, elapsed = await run_symbol(sym, bars)
        per_sym_results[sym] = result
        per_sym_elapsed[sym] = elapsed
        logger.info(
            "  %s done %.1fs | trades=%d | WR=%.1f%% | PF=%.2f | PnL=$%+.2f",
            sym, elapsed,
            result.total_trades, result.win_rate * 100,
            result.profit_factor, float(result.total_pnl_usd),
        )

    total_elapsed = time.perf_counter() - wall_t0
    logger.info("=" * 64)
    logger.info("All symbols complete in %.1fs", total_elapsed)

    report = build_report(per_sym_results, per_sym_elapsed, total_elapsed)
    print("\n" + report)

    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    logger.info("Report saved → %s", REPORT_FILE)


if __name__ == "__main__":
    asyncio.run(run())
