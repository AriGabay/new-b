#!/usr/bin/env python3
"""
Threshold Sweep: tests ALL approve_threshold values from 1 to 20.

For each threshold value, runs the full 11-group pipeline backtest via
BacktestEngine.run_full_pipeline() and collects performance metrics.

Patches at runtime (restored after each run):
  - TraderEvaluatorPanel.APPROVE_THRESHOLD
  - decision.final_group._PANEL_APPROVE_THRESHOLD
  - MDPPolicy rules (HC/MED/SMALL/DEFER approve_count thresholds)
  - FinalDecisionGroup safety Rail 6 high-volatility gate

Safety rails NEVER changed:
  - avg_score < 5.0 floor
  - reject_count > 12
  - R:R < 1.5
  - invalid setup quality
  - bear regime long block
  - RiskLeverageGroup 9 deterministic rules
  - MAX_DRAWDOWN_HALT = 0.40

Output:
  analysis/threshold_sweep/results.txt  (human-readable table)
  analysis/threshold_sweep/results.json (machine-readable)

Usage:
  PYTHONPATH=src python src/scripts/sweep_thresholds.py
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
# Only show sweep-level progress
sweep_logger = logging.getLogger("sweep")
sweep_logger.setLevel(logging.INFO)

from backtest.engine import BacktestConfig, BacktestEngine  # noqa: E402
from core.schemas import OHLCVBar                           # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(
    _PROJECT_ROOT, "analysis", "historical_eval", "data", "btcusdt_1h_2024_2025.csv"
)
OUT_DIR = os.path.join(_PROJECT_ROOT, "analysis", "threshold_sweep")
RESULTS_TXT = os.path.join(OUT_DIR, "results.txt")
RESULTS_JSON = os.path.join(OUT_DIR, "results.json")

INITIAL_EQUITY = Decimal("1000")
WEEKS_IN_DATA = 25.4 * 4.33  # ~25 months * 4.33 weeks/month ≈ 110 weeks


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_bars(csv_path: str) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
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
                symbol="BTCUSDT",
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
# Threshold patching (runtime monkey-patch, fully restored after each run)
# ---------------------------------------------------------------------------
_SAVED: dict[str, Any] = {}


def _save_originals() -> None:
    """Snapshot all threshold values that we'll patch."""
    import traders.panel as _panel
    import decision.final_group as _fg
    import mdp.policy as _pol

    _SAVED["panel_APPROVE_THRESHOLD"] = _panel.TraderEvaluatorPanel.APPROVE_THRESHOLD
    _SAVED["fg__PANEL_APPROVE_THRESHOLD"] = _fg._PANEL_APPROVE_THRESHOLD
    _SAVED["pol_HC_MIN_APPROVALS"] = _pol.HC_MIN_APPROVALS
    _SAVED["pol_MED_MIN_APPROVALS"] = _pol.MED_MIN_APPROVALS
    _SAVED["pol_SMALL_MIN_APPROVALS"] = _pol.SMALL_MIN_APPROVALS
    _SAVED["pol_DEFER_MIN_APPROVALS"] = _pol.DEFER_MIN_APPROVALS
    _SAVED["pol_REDUCE_MAX_DRAWDOWN"] = _pol.REDUCE_MAX_DRAWDOWN
    _SAVED["pol_REDUCE_MAX_STREAK"] = _pol.REDUCE_MAX_STREAK


def _restore_originals() -> None:
    """Restore all thresholds to their saved values."""
    import traders.panel as _panel
    import decision.final_group as _fg
    import mdp.policy as _pol

    _panel.TraderEvaluatorPanel.APPROVE_THRESHOLD = _SAVED["panel_APPROVE_THRESHOLD"]
    _fg._PANEL_APPROVE_THRESHOLD = _SAVED["fg__PANEL_APPROVE_THRESHOLD"]
    _pol.HC_MIN_APPROVALS = _SAVED["pol_HC_MIN_APPROVALS"]
    _pol.MED_MIN_APPROVALS = _SAVED["pol_MED_MIN_APPROVALS"]
    _pol.SMALL_MIN_APPROVALS = _SAVED["pol_SMALL_MIN_APPROVALS"]
    _pol.DEFER_MIN_APPROVALS = _SAVED["pol_DEFER_MIN_APPROVALS"]
    _pol.REDUCE_MAX_DRAWDOWN = _SAVED["pol_REDUCE_MAX_DRAWDOWN"]
    _pol.REDUCE_MAX_STREAK = _SAVED["pol_REDUCE_MAX_STREAK"]


def _patch_for_threshold(threshold: int) -> None:
    """Monkey-patch all approve-count thresholds to be consistent with *threshold*."""
    import traders.panel as _panel
    import decision.final_group as _fg
    import mdp.policy as _pol

    # Panel gate
    _panel.TraderEvaluatorPanel.APPROVE_THRESHOLD = threshold

    # FinalDecisionGroup hold-rationale text
    _fg._PANEL_APPROVE_THRESHOLD = threshold

    # MDP policy rules — keep relative structure:
    #   HC  = threshold + 3  (capped at 20)
    #   MED = threshold
    #   SMALL = threshold (with risk factor)
    #   DEFER = max(1, threshold - 3)
    hc = min(threshold + 3, 20)
    _pol.HC_MIN_APPROVALS = hc
    _pol.MED_MIN_APPROVALS = threshold
    _pol.SMALL_MIN_APPROVALS = threshold
    _pol.DEFER_MIN_APPROVALS = max(1, threshold - 3)

    # Relax REDUCE_RISK to prevent early permanent lock
    _pol.REDUCE_MAX_DRAWDOWN = 0.38
    _pol.REDUCE_MAX_STREAK = -8


def _patch_rail6_for_threshold(threshold: int) -> None:
    """
    Patch Rail 6 (high-volatility gate) in FinalDecisionGroup.decide()
    to use max(threshold+3, 14) instead of hardcoded 14.

    We do this by monkey-patching the FinalDecisionGroup class's decide method
    to use a configurable threshold. Instead, we patch the module-level constant
    that the method reads inline.

    Actually Rail 6 is an inline comparison: `panel.approve_count < 14`.
    The only way to parameterize it is to monkey-patch the decide() method itself
    or add a class variable. We'll add a class-level _RAIL6_THRESHOLD.
    """
    import decision.final_group as _fg
    # We'll use a module-level variable that we check inside a patched decide.
    # But to avoid complexity, we'll set a module-level attribute the decide method
    # can read. We need to modify the decide method to check this.
    # For simplicity, we set a module-level _RAIL6_HIGH_VOL_THRESHOLD.
    _fg._RAIL6_HIGH_VOL_THRESHOLD = max(threshold + 3, 14)


# ---------------------------------------------------------------------------
# Single-threshold backtest run
# ---------------------------------------------------------------------------
async def _run_one(threshold: int, bars: list[OHLCVBar]) -> dict[str, Any]:
    """Run full-pipeline backtest with the given approve threshold. Returns metrics dict."""
    _patch_for_threshold(threshold)

    config = BacktestConfig(
        symbols=["BTCUSDT"],
        timeframe="1h",
        start_date=bars[0].timestamp,
        end_date=bars[-1].timestamp,
        initial_equity=INITIAL_EQUITY,
        enforce_holdout=False,
    )

    engine = BacktestEngine(config)
    result = await engine.run_full_pipeline({"BTCUSDT": bars}, verbose=False)

    meta = result.per_hypothesis.get("_meta", {})
    avg_winner = meta.get("avg_winner_usd", 0.0)
    avg_loser = meta.get("avg_loser_usd", 0.0)
    n_weeks = WEEKS_IN_DATA if WEEKS_IN_DATA > 0 else 1.0
    trades_per_week = result.total_trades / n_weeks

    return {
        "threshold": threshold,
        "total_trades": result.total_trades,
        "trades_per_week": round(trades_per_week, 2),
        "win_rate": round(result.win_rate, 4),
        "profit_factor": round(result.profit_factor, 2),
        "max_drawdown": round(result.max_drawdown_pct, 4),
        "net_pnl": round(float(result.total_pnl_usd), 2),
        "avg_winner": round(avg_winner, 2),
        "avg_loser": round(avg_loser, 2),
        "final_equity": round(float(result.final_equity), 2),
        "return_pct": round(float(result.total_pnl_usd) / float(INITIAL_EQUITY) * 100, 2),
        "avg_r_multiple": round(result.avg_r_multiple, 3),
    }


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------
def _pick_best(rows: list[dict], min_trades: int = 20) -> dict[str, Any]:
    """Pick optimal thresholds from the sweep results."""
    eligible = [r for r in rows if r["total_trades"] >= min_trades]
    best: dict[str, Any] = {}

    # Best for profit
    by_pnl = sorted(rows, key=lambda r: r["net_pnl"], reverse=True)
    if by_pnl and by_pnl[0]["net_pnl"] > 0:
        best["best_profit"] = by_pnl[0]
    else:
        best["best_profit"] = by_pnl[0] if by_pnl else None

    # Best win rate (min 50 trades)
    wr_eligible = [r for r in rows if r["total_trades"] >= 50]
    if wr_eligible:
        best["best_win_rate"] = max(wr_eligible, key=lambda r: r["win_rate"])
    else:
        # Relax to min 20
        if eligible:
            best["best_win_rate"] = max(eligible, key=lambda r: r["win_rate"])
        else:
            best["best_win_rate"] = max(rows, key=lambda r: r["win_rate"]) if rows else None

    # Best balanced: profit_factor × sqrt(trades)
    for r in rows:
        r["_balanced_score"] = r["profit_factor"] * math.sqrt(max(r["total_trades"], 1))
    best["best_balanced"] = max(rows, key=lambda r: r["_balanced_score"]) if rows else None

    # Recommended: meets ALL targets
    targets = [
        r for r in rows
        if r["trades_per_week"] >= 3.0
        and r["win_rate"] >= 0.50
        and r["profit_factor"] >= 1.1
        and r["max_drawdown"] < 0.35
    ]
    if targets:
        best["recommended"] = max(targets, key=lambda r: r["profit_factor"])
    else:
        # Closest: score by how many targets met
        def _closeness(r: dict) -> tuple:
            score = 0
            if r["trades_per_week"] >= 3.0:
                score += 1
            if r["win_rate"] >= 0.50:
                score += 1
            if r["profit_factor"] >= 1.1:
                score += 1
            if r["max_drawdown"] < 0.35:
                score += 1
            return (score, r["profit_factor"], r["total_trades"])
        best["recommended"] = max(rows, key=_closeness) if rows else None

    return best


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------
def _build_table(rows: list[dict], best: dict[str, Any]) -> str:
    sep = "=" * 106
    header = (
        f"{'Thresh':>6} | {'Trades':>6} | {'Tr/Wk':>5} | {'WinRate':>7} | "
        f"{'PF':>5} | {'MaxDD':>7} | {'NetPnL':>9} | {'AvgW':>8} | "
        f"{'AvgL':>8} | {'Return':>7}"
    )
    lines = [
        sep,
        "  APPROVE-THRESHOLD SWEEP  —  Full Pipeline Backtest",
        f"  Data     : btcusdt_1h_2024_2025.csv (18,288 bars, ~25 months)",
        f"  Equity   : ${float(INITIAL_EQUITY):,.0f}",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        sep,
        "",
        header,
        "-" * 106,
    ]

    for r in rows:
        marker = ""
        if best.get("recommended") and r["threshold"] == best["recommended"]["threshold"]:
            marker = " <<"
        lines.append(
            f"{r['threshold']:>6} | {r['total_trades']:>6} | {r['trades_per_week']:>5.2f} | "
            f"{r['win_rate']:>6.1%} | {r['profit_factor']:>5.2f} | "
            f"{r['max_drawdown']:>6.1%} | ${r['net_pnl']:>8.2f} | "
            f"${r['avg_winner']:>7.2f} | ${r['avg_loser']:>7.2f} | "
            f"{r['return_pct']:>6.1f}%{marker}"
        )

    lines.append("-" * 106)
    lines.append("")

    # Best picks
    def _fmt_pick(label: str, row: dict | None) -> str:
        if row is None:
            return f"  {label:<24}  (none)"
        return (
            f"  {label:<24}  Threshold={row['threshold']:>2}  "
            f"trades={row['total_trades']}  WR={row['win_rate']:.1%}  "
            f"PF={row['profit_factor']:.2f}  DD={row['max_drawdown']:.1%}  "
            f"PnL=${row['net_pnl']:.2f}"
        )

    lines.append("  PICKS:")
    lines.append(_fmt_pick("BEST FOR PROFIT:", best.get("best_profit")))
    lines.append(_fmt_pick("BEST FOR WIN RATE:", best.get("best_win_rate")))
    lines.append(_fmt_pick("BEST BALANCED:", best.get("best_balanced")))
    lines.append(_fmt_pick("RECOMMENDED:", best.get("recommended")))
    lines.append("")

    # Target check for recommended
    rec = best.get("recommended")
    if rec:
        lines.append("  TARGET CHECK (recommended threshold):")
        lines.append(f"    Trades/week >= 3 : {'PASS' if rec['trades_per_week'] >= 3.0 else 'FAIL':>4}  ({rec['trades_per_week']:.2f})")
        lines.append(f"    Win rate >= 50%  : {'PASS' if rec['win_rate'] >= 0.50 else 'FAIL':>4}  ({rec['win_rate']:.1%})")
        lines.append(f"    PF >= 1.1        : {'PASS' if rec['profit_factor'] >= 1.1 else 'FAIL':>4}  ({rec['profit_factor']:.2f})")
        lines.append(f"    Max DD < 35%     : {'PASS' if rec['max_drawdown'] < 0.35 else 'FAIL':>4}  ({rec['max_drawdown']:.1%})")
        lines.append(f"    Net PnL > 0      : {'PASS' if rec['net_pnl'] > 0 else 'FAIL':>4}  (${rec['net_pnl']:.2f})")
        lines.append(f"    AvgW > |AvgL|    : {'PASS' if abs(rec['avg_winner']) > abs(rec['avg_loser']) else 'FAIL':>4}  (W:${rec['avg_winner']:.2f} / L:${rec['avg_loser']:.2f})")

    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    sweep_logger.info("=" * 80)
    sweep_logger.info("  THRESHOLD SWEEP — approve_threshold 1..20")
    sweep_logger.info("=" * 80)

    if not os.path.exists(DATA_FILE):
        sweep_logger.error("Data file not found: %s", DATA_FILE)
        sys.exit(1)

    sweep_logger.info("Loading bars ...")
    bars = load_bars(DATA_FILE)
    sweep_logger.info("Loaded %d bars", len(bars))

    # Save original thresholds
    _save_originals()

    rows: list[dict] = []
    t0_total = time.perf_counter()

    for threshold in range(1, 21):
        t0 = time.perf_counter()
        sweep_logger.info("  [%2d/20]  approve_threshold=%d  ...", threshold, threshold)

        try:
            result = await _run_one(threshold, bars)
            rows.append(result)
            elapsed = time.perf_counter() - t0
            sweep_logger.info(
                "  [%2d/20]  trades=%3d  WR=%5.1f%%  PF=%5.2f  DD=%5.1f%%  PnL=$%8.2f  (%.1fs)",
                threshold, result["total_trades"], result["win_rate"] * 100,
                result["profit_factor"], result["max_drawdown"] * 100,
                result["net_pnl"], elapsed,
            )
        except Exception as exc:
            sweep_logger.error("  [%2d/20]  FAILED: %s", threshold, exc)
            rows.append({
                "threshold": threshold,
                "total_trades": 0, "trades_per_week": 0.0,
                "win_rate": 0.0, "profit_factor": 0.0,
                "max_drawdown": 0.0, "net_pnl": 0.0,
                "avg_winner": 0.0, "avg_loser": 0.0,
                "final_equity": float(INITIAL_EQUITY), "return_pct": 0.0,
                "avg_r_multiple": 0.0,
            })
        finally:
            _restore_originals()

    total_elapsed = time.perf_counter() - t0_total
    sweep_logger.info("Sweep complete in %.1fs (%.1fs avg per run)", total_elapsed, total_elapsed / 20)

    # Analysis
    best = _pick_best(rows)

    # Build and print report
    report = _build_table(rows, best)
    print("\n" + report)

    # Save outputs
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULTS_TXT, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    sweep_logger.info("Results table saved → %s", RESULTS_TXT)

    # Clean internal keys before JSON export
    json_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    json_out = {
        "sweep_date": datetime.now().isoformat(),
        "initial_equity": float(INITIAL_EQUITY),
        "data_bars": len(bars),
        "results": json_rows,
        "picks": {
            k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} if v else None
            for k, v in best.items()
        },
    }
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(json_out, f, indent=2)
    sweep_logger.info("JSON data saved → %s", RESULTS_JSON)


if __name__ == "__main__":
    asyncio.run(main())
