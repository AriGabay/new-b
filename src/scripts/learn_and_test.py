#!/usr/bin/env python3
"""
Offline learning loop: train evaluator weights on historical data,
then test on out-of-sample period to measure improvement.

Workflow:
  1. Reset learning DB (optional: --reset flag)
  2. Run backtests on all historical periods (2020-2021, 2022, 2023)
     → accumulates trader_reviews + outcome_attributions in learning DB
  3. Compute Sharpe-based evaluator weights from accumulated data
  4. Save weights to data/evaluator_weights.json
  5. Run OOS backtest on 2024-2025 WITHOUT weights (baseline)
  6. Run OOS backtest on 2024-2025 WITH weights (test)
  7. Print before/after comparison

Anti-overfitting design:
  - Training periods: 2020-2021 (bull), 2022 (bear), 2023 (recovery)
  - Test period: 2024-2025 (never used for weight computation)
  - Min 30 approvals per evaluator before adjusting weight
  - 95% CI significance gate: CI must not cross zero

Usage:
  python src/scripts/learn_and_test.py                   # full loop
  python src/scripts/learn_and_test.py --reset           # reset DB first
  python src/scripts/learn_and_test.py --weights-only    # just recompute weights
  python src/scripts/learn_and_test.py --test-only       # just run OOS comparison
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
for _noisy in ("groups.entry", "groups.panel_decision", "groups.risk_leverage",
               "groups.exit", "groups.indicators", "groups.candlestick",
               "groups.chart_pattern", "groups.technical_structure",
               "groups.market_data", "groups.historian",
               "mdp.policy", "mdp.transition_logger", "learning"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

from backtest.engine import BacktestConfig, BacktestEngine, BacktestResult
from core.schemas import OHLCVBar

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR          = os.path.join(_PROJECT_ROOT, "analysis", "historical_eval", "data")
LEARNING_DB_PATH  = os.path.join(_PROJECT_ROOT, "data", "backtest_learning.db")
WEIGHTS_PATH      = os.path.join(_PROJECT_ROOT, "data", "evaluator_weights.json")
INITIAL_EQUITY    = Decimal("300")   # hard constraint: $300 initial capital

# ---------------------------------------------------------------------------
# Training periods (used to BUILD weights — never OOS test data)
# ---------------------------------------------------------------------------
TRAINING_PERIODS: dict[str, dict[str, Any]] = {
    "2020_2021": {
        "files": {
            "BTCUSDT": "btcusdt_1h_2020_2021.csv",
            "ETHUSDT": "ethusdt_1h_2020_2021.csv",
            "BNBUSDT": "bnbusdt_1h_2020_2021.csv",
        },
        "label": "2020-2021 (COVID recovery + bull run)",
    },
    "2022": {
        "files": {
            "BTCUSDT": "btcusdt_1h_2022.csv",
            "ETHUSDT": "ethusdt_1h_2022.csv",
            "BNBUSDT": "bnbusdt_1h_2022.csv",
        },
        "label": "2022 (bear market + FTX collapse)",
    },
}

# ---------------------------------------------------------------------------
# Out-of-sample test period (NEVER used for weight computation)
# ---------------------------------------------------------------------------
OOS_PERIOD = {
    "files": {
        "BTCUSDT": "btcusdt_1h_2024_2025.csv",
        "ETHUSDT": "ethusdt_1h_2024_2025.csv",
        "BNBUSDT": "bnbusdt_1h_2024_2025.csv",
    },
    "label": "2024-2025 (out-of-sample test)",
}


# ---------------------------------------------------------------------------
# Helper: load bars from CSV
# ---------------------------------------------------------------------------

def load_bars(path: str, symbol: str) -> list[OHLCVBar]:
    """Load bars from CSV. Returns empty list if file doesn't exist."""
    if not os.path.exists(path):
        return []
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


def load_period_bars(period_files: dict[str, str]) -> dict[str, list[OHLCVBar]]:
    """Load all available symbol CSVs for a period. Returns dict of symbol → bars."""
    all_bars: dict[str, list[OHLCVBar]] = {}
    for symbol, fname in period_files.items():
        path = os.path.join(DATA_DIR, fname)
        bars = load_bars(path, symbol)
        if bars:
            all_bars[symbol] = bars
            logger.info("  Loaded %d bars for %s (%s → %s)",
                        len(bars), symbol,
                        bars[0].timestamp.strftime("%Y-%m-%d"),
                        bars[-1].timestamp.strftime("%Y-%m-%d"))
        else:
            logger.debug("  Skipping %s (file not found: %s)", symbol, fname)
    return all_bars


# ---------------------------------------------------------------------------
# Step 1: Reset learning DB
# ---------------------------------------------------------------------------

def reset_learning_db() -> None:
    """Delete learning DB so weights start from scratch."""
    if os.path.exists(LEARNING_DB_PATH):
        os.remove(LEARNING_DB_PATH)
        logger.info("Learning DB reset: %s deleted.", LEARNING_DB_PATH)
    else:
        logger.info("Learning DB does not exist — nothing to reset.")


# ---------------------------------------------------------------------------
# Step 2: Run training backtests
# ---------------------------------------------------------------------------

async def run_training_period(
    period_name: str,
    period_info: dict,
) -> Optional[BacktestResult]:
    """Run a single training period backtest, writing to LEARNING_DB_PATH."""
    logger.info("\n--- Training period: %s ---", period_info["label"])

    all_bars = load_period_bars(period_info["files"])
    if not all_bars:
        logger.warning("No data files found for period %s — skipping.", period_name)
        return None

    config = BacktestConfig(
        symbols        = list(all_bars.keys()),
        timeframe      = "1h",
        start_date     = next(iter(all_bars.values()))[0].timestamp,
        end_date       = next(iter(all_bars.values()))[-1].timestamp,
        initial_equity = INITIAL_EQUITY,
        enforce_holdout= False,
        output_db_path = LEARNING_DB_PATH,
    )

    engine = BacktestEngine(config)

    # Override DB to use persistent learning DB
    engine._learning_db_path = LEARNING_DB_PATH

    t0 = time.perf_counter()
    result = await engine.run_full_pipeline(all_bars, verbose=True)
    elapsed = time.perf_counter() - t0

    logger.info(
        "Period %s: trades=%d  WR=%.1f%%  PF=%.2f  MaxDD=%.1f%%  (%.0fs)",
        period_name,
        result.total_trades,
        result.win_rate * 100,
        result.profit_factor,
        result.max_drawdown_pct * 100,
        elapsed,
    )
    return result


# ---------------------------------------------------------------------------
# Step 3: Compute and save weights
# ---------------------------------------------------------------------------

def compute_and_save_weights(db_path: str) -> dict[str, float]:
    """Compute Sharpe weights from learning DB and save to JSON."""
    from learning.weight_updater import EvaluatorWeightUpdater

    updater = EvaluatorWeightUpdater()
    weights = updater.compute_from_history(db_path)

    if not weights:
        logger.warning("No weights computed — learning DB may have insufficient data.")
        return {}

    out_path = updater.save_weights(weights, path=WEIGHTS_PATH)
    logger.info("Weights saved to %s", out_path)
    updater.print_report(weights, db_path=db_path)
    return weights


# ---------------------------------------------------------------------------
# Step 4: OOS comparison test (before/after weights)
# ---------------------------------------------------------------------------

async def run_oos_test(with_weights: bool, label: str) -> Optional[BacktestResult]:
    """Run OOS backtest. with_weights=True applies the saved weights.json."""
    logger.info("\n--- OOS Test: %s ---", label)

    all_bars = load_period_bars(OOS_PERIOD["files"])
    if not all_bars:
        logger.warning("No OOS data files found — skipping OOS test.")
        return None

    if with_weights:
        # Weights are loaded by TraderEvaluatorPanel automatically from JSON
        pass
    else:
        # Temporarily rename weights file so panel uses fallback weights
        if os.path.exists(WEIGHTS_PATH):
            _tmp = WEIGHTS_PATH + ".tmp"
            shutil.move(WEIGHTS_PATH, _tmp)
            logger.info("  Temporarily hiding weights for baseline test.")
        else:
            _tmp = None

    # Use a separate OOS DB so we don't pollute the training DB
    oos_db = LEARNING_DB_PATH.replace(".db", "_oos.db")

    config = BacktestConfig(
        symbols        = list(all_bars.keys()),
        timeframe      = "1h",
        start_date     = next(iter(all_bars.values()))[0].timestamp,
        end_date       = next(iter(all_bars.values()))[-1].timestamp,
        initial_equity = INITIAL_EQUITY,
        enforce_holdout= False,
        output_db_path = oos_db,
    )

    try:
        engine = BacktestEngine(config)
        t0 = time.perf_counter()
        result = await engine.run_full_pipeline(all_bars, verbose=True)
        elapsed = time.perf_counter() - t0

        logger.info(
            "OOS (%s): trades=%d  WR=%.1f%%  PF=%.2f  MaxDD=%.1f%%  (%.0fs)",
            label, result.total_trades, result.win_rate * 100,
            result.profit_factor, result.max_drawdown_pct * 100, elapsed,
        )
        return result
    finally:
        # Restore weights file if hidden
        if not with_weights and "_tmp" in dir() and _tmp and os.path.exists(_tmp):
            shutil.move(_tmp, WEIGHTS_PATH)
            logger.info("  Weights file restored.")


# ---------------------------------------------------------------------------
# Print comparison report
# ---------------------------------------------------------------------------

def print_comparison(
    baseline: Optional[BacktestResult],
    weighted: Optional[BacktestResult],
    training_results: dict[str, BacktestResult],
) -> None:
    sep = "=" * 68
    print()
    print(sep)
    print("  OFFLINE LEARNING LOOP RESULTS")
    print(sep)

    # Training summary
    total_training_trades = sum(r.total_trades for r in training_results.values())
    print(f"\n  Training periods: {len(training_results)}")
    for name, r in training_results.items():
        print(f"    {name:<15}: {r.total_trades:>4} trades  WR={r.win_rate:.1%}  PF={r.profit_factor:.2f}")
    print(f"    {'TOTAL':<15}: {total_training_trades:>4} trades")

    # OOS comparison
    print(f"\n  Out-of-Sample Test (2024-2025):")
    print(f"  {'Metric':<25} {'Baseline':>12} {'With Weights':>12} {'Delta':>10}")
    print("  " + "-" * 62)

    def _fmt_r(r: Optional[BacktestResult], attr: str, pct: bool = False) -> str:
        if r is None:
            return "N/A"
        v = getattr(r, attr, None)
        if v is None:
            return "N/A"
        if pct:
            return f"{v:.1%}"
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    def _delta(
        a: Optional[BacktestResult],
        b: Optional[BacktestResult],
        attr: str,
        pct: bool = False,
    ) -> str:
        if a is None or b is None:
            return "N/A"
        va = getattr(a, attr, None)
        vb = getattr(b, attr, None)
        if va is None or vb is None:
            return "N/A"
        d = float(vb) - float(va)
        if pct:
            return f"{d:+.1%}"
        return f"{d:+.2f}"

    rows = [
        ("Total trades",          "total_trades",      False),
        ("Win rate",               "win_rate",          True),
        ("Profit factor",          "profit_factor",     False),
        ("Max drawdown",           "max_drawdown_pct",  True),
        ("Avg R-multiple",         "avg_r_multiple",    False),
    ]
    for label, attr, pct in rows:
        print(
            f"  {label:<25} {_fmt_r(baseline, attr, pct):>12} "
            f"{_fmt_r(weighted, attr, pct):>12} {_delta(baseline, weighted, attr, pct):>10}"
        )

    # PnL
    if baseline and weighted:
        b_pnl = float(baseline.total_pnl_usd)
        w_pnl = float(weighted.total_pnl_usd)
        b_roi = b_pnl / float(INITIAL_EQUITY) * 100
        w_roi = w_pnl / float(INITIAL_EQUITY) * 100
        print(f"  {'PnL (USD)':<25} ${b_pnl:>10.2f} ${w_pnl:>10.2f} {w_pnl - b_pnl:>+10.2f}")
        print(f"  {'ROI':<25} {b_roi:>11.1f}% {w_roi:>11.1f}% {w_roi - b_roi:>+9.1f}%")

    # Verdict
    if baseline and weighted:
        if weighted.win_rate > baseline.win_rate and weighted.profit_factor > baseline.profit_factor:
            print(f"\n  VERDICT: Weights IMPROVED performance ✓")
        elif weighted.win_rate < baseline.win_rate and weighted.profit_factor < baseline.profit_factor:
            print(f"\n  VERDICT: Weights HURT performance — investigate evaluators")
        else:
            print(f"\n  VERDICT: Mixed results — check individual evaluator weights")

    print(sep)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> None:
    logger.info("=" * 68)
    logger.info("  OFFLINE LEARNING LOOP")
    logger.info("=" * 68)
    logger.info("  Capital: $%s  |  DB: %s", INITIAL_EQUITY, LEARNING_DB_PATH)

    training_results: dict[str, BacktestResult] = {}

    if args.reset:
        reset_learning_db()

    if not args.test_only and not args.weights_only:
        # Step 2: Run training backtests
        logger.info("\n[STEP 2] Running training backtests...")
        for period_name, period_info in TRAINING_PERIODS.items():
            result = await run_training_period(period_name, period_info)
            if result is not None:
                training_results[period_name] = result

        if not training_results:
            logger.warning(
                "No training data available. "
                "Run: python src/scripts/download_history.py"
            )

    if not args.test_only:
        # Step 3: Compute and save weights
        logger.info("\n[STEP 3] Computing evaluator weights...")
        weights = compute_and_save_weights(LEARNING_DB_PATH)
        if not weights:
            logger.info("  Insufficient data for weights — run more backtests first.")

    if not args.weights_only:
        # Step 4: OOS comparison
        logger.info("\n[STEP 4] Out-of-sample comparison test...")
        baseline = await run_oos_test(with_weights=False, label="baseline (no weights)")
        weighted = await run_oos_test(with_weights=True, label="with Sharpe weights")

        print_comparison(baseline, weighted, training_results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline learning loop for evaluator weights.")
    parser.add_argument("--reset", action="store_true", help="Reset learning DB before training")
    parser.add_argument("--weights-only", action="store_true", help="Only recompute weights from existing DB")
    parser.add_argument("--test-only", action="store_true", help="Only run OOS comparison test")
    args = parser.parse_args()
    asyncio.run(main(args))
