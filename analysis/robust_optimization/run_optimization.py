"""
Walk-Forward Robust Optimization: 2020-2022 Learning, 2023-2026 Holdout.

Methodology:
  - Learning period: 2020-03-25 → 2022-12-31 (earliest available → end of 2022)
  - Holdout period: 2023-01-01 → 2026-03-29 (completely untouched until final eval)
  - Walk-forward: 6-month rolling train, 3-month OOS test, 3-month step
  - Grid search over 6 key parameters
  - Anti-overfitting: train-OOS gap detection, cross-fold stability, min trade count
  - Final candidate: most stable across OOS folds, not highest single-fold score

Usage:
    python analysis/robust_optimization/run_optimization.py
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from optimization.data_loader import load_csv
from optimization.featurevector_builder import build_feature_vectors
from optimization.fold_builder import build_folds
from optimization.objective import compute_objective, RunMetrics, TradeResult
from optimization.parameter_space import (
    PARAMETER_SPACE,
    ParameterSet,
    build_grid,
    get_baseline_params,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("robust_optimization")
logger.setLevel(logging.INFO)

# ── Configuration ──────────────────────────────────────────────────────
DATA_FILE = "analysis/robust_optimization/data/btcusdt_1h_full.csv"
OUT_DIR = "analysis/robust_optimization"

LEARN_END = datetime(2022, 12, 31, 23, 0, 0, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2023, 1, 1, tzinfo=timezone.utc)

INITIAL_EQUITY = Decimal("10000")   # $10k for meaningful sizing

# Walk-forward fold config
WARMUP_BARS = 250       # ~10 days indicator warmup
TRAIN_BARS = 4320       # 6 months
TEST_BARS = 2160        # 3 months
STEP_BARS = 2160        # 3 months (non-overlapping OOS)

# Parameters to optimize (6 key levers)
OPTIMIZE_PARAMS = [
    "composite_score_threshold",
    "atr_stop_multiplier",
    "time_stop_bars",
    "panel_approve_threshold",
    "min_leverage",
    "max_risk_per_trade",
]

OVERFITTING_THRESHOLD = 0.30  # Flag if train-OOS gap > 30%

# Coarser grid values to keep total combinations under 2000
# (full parameter_space steps produce 57k+ combos — too many for grid search)
GRID_OVERRIDES = {
    "composite_score_threshold": [0.35, 0.50, 0.65],           # 3 values
    "atr_stop_multiplier":       [1.5, 2.25, 3.0],             # 3 values
    "time_stop_bars":            [24, 48, 96],                  # 3 values
    "panel_approve_threshold":   [12, 15, 17],                  # 3 values
    "min_leverage":              [5.0, 10.0],                   # 2 values
    "max_risk_per_trade":        [0.05, 0.10, 0.20],           # 3 values
}
# Total: 3 × 3 × 3 × 3 × 2 × 3 = 486 combinations
# At ~1.3s/eval: ~10.5 min/fold × 9 folds ≈ 95 min total


def _build_coarse_grid() -> list[ParameterSet]:
    """Build a grid using coarser step sizes suitable for walk-forward."""
    import itertools
    baseline = get_baseline_params()
    axes = [GRID_OVERRIDES[p] for p in OPTIMIZE_PARAMS]
    results = []
    for combo in itertools.product(*axes):
        values = dict(baseline.values)
        for name, val in zip(OPTIMIZE_PARAMS, combo):
            values[name] = val
        results.append(ParameterSet(values=values))
    logger.info(
        "Coarse grid: %d combinations for %s", len(results), OPTIMIZE_PARAMS
    )
    return results


# ── Core evaluation function ──────────────────────────────────────────
async def evaluate_params_on_window(
    params: dict,
    feature_vectors: list,
    equity: Decimal = INITIAL_EQUITY,
) -> dict:
    """Evaluate a parameter set on a window of FeatureVectors.
    Returns dict with metrics and objective score."""
    from runtime.runner import BtcBybitPaperRunner
    from core.events import PositionCloseEvent
    from optimization.regression_guard import _apply_overrides, _save_module_state, _restore_module_state
    import tempfile, uuid

    saved = _save_module_state()
    tmp_dir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp_dir, f"opt_{uuid.uuid4().hex[:8]}.db")

        runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=db_path)
        await runner.setup()
        runner.state.portfolio.equity = equity
        runner.state.portfolio.available = equity
        runner.state.portfolio.high_water_mark = equity

        _apply_overrides(runner, params)

        # Track trades via event subscription
        trades: list[TradeResult] = []
        peak_eq = float(equity)
        max_dd = 0.0

        async def on_close(event):
            nonlocal peak_eq, max_dd
            if hasattr(event, "exit_signal") and event.exit_signal:
                es = event.exit_signal
                fp = event.final_position if hasattr(event, "final_position") else None
                direction = "long"
                entry_price = Decimal("0")
                if fp:
                    direction = "long" if str(fp.direction).upper() in ("LONG", "DIRECTION.LONG") else "short"
                    entry_price = fp.entry_price
                trades.append(TradeResult(
                    entry_price=entry_price,
                    exit_price=es.exit_price,
                    direction=direction,
                    r_multiple=es.pnl_r,
                    bars_held=es.bars_held,
                    pnl_usd=float(es.pnl_usd),
                ))
            eq = float(runner.state.portfolio.equity)
            if eq > peak_eq:
                peak_eq = eq
            dd = (peak_eq - eq) / peak_eq if peak_eq > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        await runner._bus.subscribe(PositionCloseEvent, on_close)

        # Feed bars with daily PnL reset
        last_date = None
        for fv in feature_vectors:
            bar_date = fv.timestamp.date() if fv.timestamp else None
            if bar_date and bar_date != last_date:
                await runner.state.reset_daily_pnl()
                last_date = bar_date
            await runner.simulate_bar(fv)

        # Build metrics
        metrics = RunMetrics(
            bars_run=len(feature_vectors),
            trades=trades,
            positions_opened=len(trades) + len(runner.state.portfolio.open_positions),
            positions_closed=len(trades),
            final_equity=float(runner.state.portfolio.equity),
            starting_equity=float(equity),
            max_drawdown_pct=max_dd,
            peak_equity=peak_eq,
        )
        obj = compute_objective(metrics)

        await runner.teardown()

        return {
            "objective": obj.score,
            "is_valid": obj.is_valid,
            "reason": obj.reason,
            "metrics": {
                "trade_count": metrics.trade_count,
                "win_rate": metrics.win_rate,
                "expectancy": metrics.expectancy,
                "profit_factor": metrics.profit_factor,
                "max_drawdown": max_dd,
                "total_pnl": metrics.total_pnl,
                "return_pct": (float(runner.state.portfolio.equity) - float(equity)) / float(equity) * 100,
                "avg_bars_held": metrics.avg_bars_held,
            },
            "component_scores": obj.component_scores,
        }
    finally:
        _restore_module_state(saved)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Walk-Forward Engine ───────────────────────────────────────────────
async def run_walk_forward(learn_fvs: list) -> dict:
    """Run walk-forward optimization on learning period FVs."""
    logger.info("Building folds...")
    folds = build_folds(
        learn_fvs,
        warmup_bars=WARMUP_BARS,
        train_bars=TRAIN_BARS,
        test_bars=TEST_BARS,
        step_bars=STEP_BARS,
    )
    logger.info(f"Built {len(folds)} folds")

    # Build parameter grid with coarser steps (1,728 combos)
    grid = _build_coarse_grid()
    logger.info(f"Grid size: {len(grid)} combinations")

    baseline = get_baseline_params()
    all_fold_results = []

    for fold in folds:
        fold_start = time.time()
        fold_idx = fold.fold_index
        logger.info(
            f"\n{'='*60}\n"
            f"FOLD {fold_idx}: train {fold.train_start.date()}→{fold.train_end.date()}, "
            f"test {fold.test_start.date()}→{fold.test_end.date()}\n"
            f"{'='*60}"
        )

        # ── Grid search on TRAIN ──
        train_fvs = fold.train_with_warmup
        best_train_score = -999
        best_train_params = None
        best_train_result = None
        train_results = []

        for i, pset in enumerate(grid):
            params = pset.values
            result = await evaluate_params_on_window(params, train_fvs)
            train_results.append({"params": params, "result": result})

            if result["objective"] > best_train_score:
                best_train_score = result["objective"]
                best_train_params = params
                best_train_result = result

            if (i + 1) % 50 == 0:
                logger.info(f"  Fold {fold_idx}: {i+1}/{len(grid)} combos evaluated, best so far: {best_train_score:.4f}")

        logger.info(f"  Fold {fold_idx} TRAIN best: score={best_train_score:.4f}, "
                     f"trades={best_train_result['metrics']['trade_count']}, "
                     f"return={best_train_result['metrics']['return_pct']:.1f}%")

        # ── Evaluate best on TEST (OOS) ──
        test_fvs = list(fold.warmup) + list(fold.test)
        oos_result = await evaluate_params_on_window(best_train_params, test_fvs)

        # ── Overfitting check ──
        gap = best_train_score - oos_result["objective"]
        overfit_flag = gap > OVERFITTING_THRESHOLD

        logger.info(f"  Fold {fold_idx} OOS: score={oos_result['objective']:.4f}, "
                     f"trades={oos_result['metrics']['trade_count']}, "
                     f"return={oos_result['metrics']['return_pct']:.1f}%, "
                     f"gap={gap:.4f} {'⚠️ OVERFIT' if overfit_flag else '✓'}")

        # ── Also evaluate baseline on TEST for comparison ──
        baseline_oos = await evaluate_params_on_window(baseline.values, test_fvs)

        fold_elapsed = time.time() - fold_start
        fold_result = {
            "fold_index": fold_idx,
            "train_start": fold.train_start.isoformat(),
            "train_end": fold.train_end.isoformat(),
            "test_start": fold.test_start.isoformat(),
            "test_end": fold.test_end.isoformat(),
            "best_params": best_train_params,
            "train_score": best_train_score,
            "train_metrics": best_train_result["metrics"],
            "oos_score": oos_result["objective"],
            "oos_metrics": oos_result["metrics"],
            "oos_valid": oos_result["is_valid"],
            "overfit_gap": gap,
            "overfit_flag": overfit_flag,
            "baseline_oos_score": baseline_oos["objective"],
            "baseline_oos_metrics": baseline_oos["metrics"],
            "elapsed_seconds": fold_elapsed,
            "grid_size": len(grid),
        }
        all_fold_results.append(fold_result)

    return {
        "folds": all_fold_results,
        "grid_size": len(grid),
        "params_optimized": OPTIMIZE_PARAMS,
    }


def select_best_candidate(wf_results: dict) -> dict:
    """Select the best candidate from walk-forward results.

    Selection criteria (in priority order):
    1. Must have valid OOS results in majority of folds
    2. Prefer candidates with low overfit gap
    3. Rank by average OOS score across valid folds
    4. Prefer stable parameters (low variance across folds)
    """
    folds = wf_results["folds"]
    valid_folds = [f for f in folds if f["oos_valid"] and not f["overfit_flag"]]
    all_valid = [f for f in folds if f["oos_valid"]]

    if not valid_folds and not all_valid:
        return {
            "selected": False,
            "reason": "No valid OOS results in any fold",
            "params": get_baseline_params().values,
        }

    # Use valid non-overfit folds if available, else all valid
    use_folds = valid_folds if valid_folds else all_valid

    # Average OOS metrics
    avg_oos_score = sum(f["oos_score"] for f in use_folds) / len(use_folds)
    avg_oos_return = sum(f["oos_metrics"]["return_pct"] for f in use_folds) / len(use_folds)
    avg_oos_trades = sum(f["oos_metrics"]["trade_count"] for f in use_folds) / len(use_folds)
    avg_oos_dd = sum(f["oos_metrics"]["max_drawdown"] for f in use_folds) / len(use_folds)

    avg_baseline = sum(f["baseline_oos_score"] for f in use_folds) / len(use_folds)

    # Select params from best OOS fold
    best_fold = max(use_folds, key=lambda f: f["oos_score"])

    # Check parameter stability across folds
    param_values = {}
    for p in OPTIMIZE_PARAMS:
        vals = [f["best_params"].get(p) for f in use_folds if p in f["best_params"]]
        if vals:
            param_values[p] = vals

    # Compute most-common value for each param (mode)
    consensus_params = {}
    for p, vals in param_values.items():
        from collections import Counter
        counter = Counter([str(v) for v in vals])
        most_common_str = counter.most_common(1)[0][0]
        # Find original value
        for v in vals:
            if str(v) == most_common_str:
                consensus_params[p] = v
                break

    # Use consensus params if stability is reasonable
    unique_ratio = {p: len(set(str(v) for v in vals)) / len(vals) for p, vals in param_values.items()}
    avg_unique_ratio = sum(unique_ratio.values()) / len(unique_ratio) if unique_ratio else 1.0

    if avg_unique_ratio < 0.7:
        # Good stability — use consensus
        selected_params = consensus_params
        selection_method = "consensus (mode across folds)"
    else:
        # Poor stability — use best fold's params
        selected_params = best_fold["best_params"]
        selection_method = f"best OOS fold ({best_fold['fold_index']})"

    # Fill in missing params from baseline
    baseline = get_baseline_params().values
    for k, v in baseline.items():
        if k not in selected_params:
            selected_params[k] = v

    return {
        "selected": True,
        "params": selected_params,
        "selection_method": selection_method,
        "avg_oos_score": avg_oos_score,
        "avg_oos_return": avg_oos_return,
        "avg_oos_trades": avg_oos_trades,
        "avg_oos_drawdown": avg_oos_dd,
        "avg_baseline_score": avg_baseline,
        "improvement_vs_baseline": avg_oos_score - avg_baseline,
        "valid_folds": len(use_folds),
        "total_folds": len(folds),
        "overfit_folds": sum(1 for f in folds if f["overfit_flag"]),
        "param_stability": unique_ratio,
    }


async def run_holdout_evaluation(
    holdout_fvs: list,
    params: dict,
    equity: Decimal = INITIAL_EQUITY,
) -> dict:
    """Run final untouched holdout evaluation with frozen params."""
    logger.info(f"\n{'='*60}\nFINAL HOLDOUT EVALUATION (2023-2026)\n{'='*60}")
    logger.info(f"Bars: {len(holdout_fvs)}, Equity: ${equity}")
    logger.info(f"Params: {json.dumps({k: v for k, v in params.items() if k in OPTIMIZE_PARAMS}, indent=2)}")

    result = await evaluate_params_on_window(params, holdout_fvs, equity)

    # Also run baseline for comparison
    baseline = get_baseline_params().values
    baseline_result = await evaluate_params_on_window(baseline, holdout_fvs, equity)

    return {
        "optimized": result,
        "baseline": baseline_result,
        "params_used": {k: v for k, v in params.items() if k in OPTIMIZE_PARAMS},
    }


def save_results(wf_results, candidate, holdout, out_dir):
    """Save all results to files."""
    os.makedirs(out_dir, exist_ok=True)

    # fold_results.csv
    with open(os.path.join(out_dir, "fold_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fold", "train_start", "train_end", "test_start", "test_end",
                     "train_score", "oos_score", "overfit_gap", "overfit_flag",
                     "oos_trades", "oos_return_pct", "oos_win_rate", "oos_drawdown",
                     "baseline_oos_score", "elapsed_sec"])
        for fold in wf_results["folds"]:
            w.writerow([
                fold["fold_index"], fold["train_start"][:10], fold["train_end"][:10],
                fold["test_start"][:10], fold["test_end"][:10],
                f"{fold['train_score']:.4f}", f"{fold['oos_score']:.4f}",
                f"{fold['overfit_gap']:.4f}", fold["overfit_flag"],
                fold["oos_metrics"]["trade_count"],
                f"{fold['oos_metrics']['return_pct']:.2f}",
                f"{fold['oos_metrics']['win_rate']:.3f}",
                f"{fold['oos_metrics']['max_drawdown']:.4f}",
                f"{fold['baseline_oos_score']:.4f}",
                f"{fold['elapsed_seconds']:.1f}",
            ])

    # best_params.json
    with open(os.path.join(out_dir, "best_params.json"), "w") as f:
        json.dump(candidate, f, indent=2, default=str)

    # candidate_results.csv
    with open(os.path.join(out_dir, "candidate_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "optimized", "baseline"])
        if holdout:
            opt = holdout["optimized"]["metrics"]
            base = holdout["baseline"]["metrics"]
            for key in opt:
                w.writerow([key, f"{opt[key]:.4f}" if isinstance(opt[key], float) else opt[key],
                           f"{base[key]:.4f}" if isinstance(base[key], float) else base[key]])

    # final_holdout_2023_2026.csv
    if holdout:
        with open(os.path.join(out_dir, "final_holdout_2023_2026.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["metric", "value"])
            for k, v in holdout["optimized"]["metrics"].items():
                w.writerow([k, f"{v:.4f}" if isinstance(v, float) else v])
            w.writerow(["objective_score", f"{holdout['optimized']['objective']:.4f}"])
            w.writerow(["is_valid", holdout["optimized"]["is_valid"]])

    # Full JSON dump
    with open(os.path.join(out_dir, "results", "full_results.json"), "w") as f:
        json.dump({
            "walk_forward": wf_results,
            "candidate": candidate,
            "holdout": holdout,
            "config": {
                "learning_end": LEARN_END.isoformat(),
                "holdout_start": HOLDOUT_START.isoformat(),
                "warmup_bars": WARMUP_BARS,
                "train_bars": TRAIN_BARS,
                "test_bars": TEST_BARS,
                "step_bars": STEP_BARS,
                "initial_equity": float(INITIAL_EQUITY),
                "params_optimized": OPTIMIZE_PARAMS,
                "overfitting_threshold": OVERFITTING_THRESHOLD,
            },
        }, f, indent=2, default=str)


def generate_report(wf_results, candidate, holdout) -> str:
    """Generate human-readable final report."""
    lines = []
    lines.append("# Walk-Forward Robust Optimization Report")
    lines.append(f"\nGenerated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"\n## Configuration")
    lines.append(f"- Learning period: 2020-03-25 → 2022-12-31")
    lines.append(f"- Holdout period: 2023-01-01 → 2026-03-29")
    lines.append(f"- Initial equity: ${INITIAL_EQUITY}")
    lines.append(f"- Walk-forward: {TRAIN_BARS} train / {TEST_BARS} test / {STEP_BARS} step (1h bars)")
    lines.append(f"- Parameters optimized: {', '.join(OPTIMIZE_PARAMS)}")
    lines.append(f"- Grid size: {wf_results['grid_size']} combinations per fold")
    lines.append(f"- Overfitting threshold: {OVERFITTING_THRESHOLD}")

    lines.append(f"\n## Fold-by-Fold Results")
    lines.append(f"\n| Fold | Train Period | Test Period | Train Score | OOS Score | Gap | Overfit? | OOS Trades | OOS Return | OOS DD |")
    lines.append(f"|------|-------------|------------|-------------|-----------|-----|----------|------------|------------|--------|")
    for f in wf_results["folds"]:
        lines.append(
            f"| {f['fold_index']} | "
            f"{f['train_start'][:10]}→{f['train_end'][:10]} | "
            f"{f['test_start'][:10]}→{f['test_end'][:10]} | "
            f"{f['train_score']:.3f} | "
            f"{f['oos_score']:.3f} | "
            f"{f['overfit_gap']:.3f} | "
            f"{'⚠️' if f['overfit_flag'] else '✓'} | "
            f"{f['oos_metrics']['trade_count']} | "
            f"{f['oos_metrics']['return_pct']:+.1f}% | "
            f"{f['oos_metrics']['max_drawdown']:.1%} |"
        )

    lines.append(f"\n## Candidate Selection")
    if candidate["selected"]:
        lines.append(f"- Method: {candidate['selection_method']}")
        lines.append(f"- Valid folds: {candidate['valid_folds']}/{candidate['total_folds']}")
        lines.append(f"- Overfit folds: {candidate['overfit_folds']}")
        lines.append(f"- Avg OOS score: {candidate['avg_oos_score']:.4f}")
        lines.append(f"- Avg OOS return: {candidate['avg_oos_return']:+.2f}%")
        lines.append(f"- Avg baseline OOS: {candidate['avg_baseline_score']:.4f}")
        lines.append(f"- Improvement vs baseline: {candidate['improvement_vs_baseline']:+.4f}")
        lines.append(f"\n### Selected Parameters")
        for p in OPTIMIZE_PARAMS:
            if p in candidate["params"]:
                lines.append(f"- `{p}`: {candidate['params'][p]}")
        lines.append(f"\n### Parameter Stability")
        for p, ratio in candidate.get("param_stability", {}).items():
            stability = "stable" if ratio < 0.5 else "moderate" if ratio < 0.75 else "unstable"
            lines.append(f"- `{p}`: unique ratio {ratio:.2f} ({stability})")
    else:
        lines.append(f"- **No valid candidate found**: {candidate['reason']}")

    if holdout:
        lines.append(f"\n## Final Holdout Evaluation (2023-01-01 → 2026-03-29)")
        lines.append(f"\n**This period was NEVER seen during optimization.**\n")
        opt = holdout["optimized"]
        base = holdout["baseline"]
        lines.append(f"| Metric | Optimized | Baseline |")
        lines.append(f"|--------|-----------|----------|")
        for key in opt["metrics"]:
            ov = opt["metrics"][key]
            bv = base["metrics"][key]
            of = f"{ov:.4f}" if isinstance(ov, float) else str(ov)
            bf = f"{bv:.4f}" if isinstance(bv, float) else str(bv)
            lines.append(f"| {key} | {of} | {bf} |")
        lines.append(f"| objective_score | {opt['objective']:.4f} | {base['objective']:.4f} |")

        # Honest assessment
        lines.append(f"\n## Honest Assessment")
        opt_ret = opt["metrics"]["return_pct"]
        base_ret = base["metrics"]["return_pct"]
        if opt_ret > 0 and opt_ret > base_ret:
            lines.append("The optimized parameters **improved** holdout performance vs baseline.")
        elif opt_ret > base_ret:
            lines.append("The optimized parameters **improved** vs baseline, but both are negative.")
        elif opt_ret <= base_ret:
            lines.append("The optimized parameters did **NOT improve** holdout performance vs baseline.")

        if opt["metrics"]["max_drawdown"] > 0.40:
            lines.append(f"\n⚠️ **WARNING**: Max drawdown {opt['metrics']['max_drawdown']:.1%} is dangerously high.")
        if opt["metrics"]["trade_count"] < 10:
            lines.append(f"\n⚠️ **WARNING**: Only {opt['metrics']['trade_count']} trades — low statistical confidence.")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────
async def main():
    overall_start = time.time()

    # Load data
    logger.info("Loading data...")
    result = load_csv(DATA_FILE)
    bars = result.bars
    logger.info(f"Loaded {len(bars)} bars: {bars[0].timestamp.date()} → {bars[-1].timestamp.date()}")

    # Split into learning and holdout
    learn_bars = [b for b in bars if b.timestamp <= LEARN_END]
    holdout_bars = [b for b in bars if b.timestamp >= HOLDOUT_START]
    logger.info(f"Learning bars: {len(learn_bars)}")
    logger.info(f"Holdout bars: {len(holdout_bars)}")

    # Build FeatureVectors
    logger.info("Building FeatureVectors for learning period...")
    learn_fvs = build_feature_vectors(learn_bars)
    logger.info(f"Learning FVs: {len(learn_fvs)}")

    # ── Phase 3: Walk-Forward on Learning Period ──
    logger.info("\n" + "="*60 + "\nPHASE 3: WALK-FORWARD OPTIMIZATION\n" + "="*60)
    wf_results = await run_walk_forward(learn_fvs)

    # ── Phase 5: Candidate Selection ──
    logger.info("\n" + "="*60 + "\nPHASE 5: CANDIDATE SELECTION\n" + "="*60)
    candidate = select_best_candidate(wf_results)
    if candidate["selected"]:
        logger.info(f"Selected candidate via {candidate['selection_method']}")
        logger.info(f"Avg OOS score: {candidate['avg_oos_score']:.4f}")
        logger.info(f"Params: {json.dumps({k: v for k, v in candidate['params'].items() if k in OPTIMIZE_PARAMS}, indent=2)}")
    else:
        logger.warning(f"No valid candidate: {candidate['reason']}")

    # ── Phase 6: Final Holdout Evaluation ──
    logger.info("\nBuilding FeatureVectors for holdout period...")
    # Include some learning bars at the end for warmup
    warmup_holdout_bars = learn_bars[-300:] + holdout_bars
    holdout_fvs = build_feature_vectors(warmup_holdout_bars)
    # Only use FVs from holdout period
    holdout_fvs = [fv for fv in holdout_fvs if fv.timestamp >= HOLDOUT_START]
    logger.info(f"Holdout FVs: {len(holdout_fvs)}")

    holdout = await run_holdout_evaluation(holdout_fvs, candidate["params"])

    # ── Save Results ──
    save_results(wf_results, candidate, holdout, OUT_DIR)

    # Generate report
    report = generate_report(wf_results, candidate, holdout)
    with open(os.path.join(OUT_DIR, "final_report.md"), "w") as f:
        f.write(report)

    # Also save cleanup report
    cleanup_report = """# Cleanup Report

## Archived
- `analysis/historical_eval/results.json` → `archived_pre_leverage_fix/` (stale: used old 0.1x leverage model)
- `analysis/historical_eval/report.txt` → `archived_pre_leverage_fix/` (stale: used old 0.1x leverage model)

## Preserved
- `analysis/historical_eval/run_eval.py` — reference evaluation script
- `analysis/historical_eval/data/btcusdt_1h_2024_2025.csv` — historical data (overlaps with new full dataset)
- All source code under `src/`
- All tests under `src/tests/`
- All documentation under `docs/`
- All validation fixtures

## Created
- `analysis/robust_optimization/data/btcusdt_1h_full.csv` — full 2020-2026 dataset (52,687 bars)
- `analysis/robust_optimization/run_optimization.py` — walk-forward optimization script
- `analysis/robust_optimization/fold_results.csv` — fold-by-fold OOS results
- `analysis/robust_optimization/candidate_results.csv` — optimized vs baseline comparison
- `analysis/robust_optimization/best_params.json` — selected parameter set
- `analysis/robust_optimization/final_holdout_2023_2026.csv` — holdout evaluation
- `analysis/robust_optimization/final_report.md` — human-readable report
- `analysis/robust_optimization/results/full_results.json` — machine-readable full results
"""
    with open(os.path.join(OUT_DIR, "cleanup_report.md"), "w") as f:
        f.write(cleanup_report)

    elapsed = time.time() - overall_start
    logger.info(f"\n{'='*60}")
    logger.info(f"COMPLETE in {elapsed:.0f}s ({elapsed/60:.1f}m)")
    logger.info(f"Results saved to {OUT_DIR}/")
    logger.info(f"{'='*60}")

    # Print summary
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
