"""
Walk-forward optimization reporting.

Generates human-readable and machine-readable reports from WalkForwardResult.
All bar-based metrics include elapsed time display.

Report types:
  - Fold-by-fold summary (markdown table)
  - Parameter stability analysis (how often each param was selected)
  - OOS equity curve (theoretical)
  - Overfitting diagnostics (train vs OOS gap)
  - Final recommendation
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from optimization.walk_forward_runner import WalkForwardResult, FoldResult
from optimization.parameter_space import get_baseline_params
from utils.bar_duration import format_bars

logger = logging.getLogger(__name__)


def generate_summary_report(result: WalkForwardResult, timeframe: str = "1h") -> str:
    """Generate a markdown summary report from walk-forward results."""
    lines: list[str] = []

    lines.append("# Walk-Forward Optimization Report")
    lines.append("")
    lines.append(f"**Run ID:** {result.run_id}")
    lines.append(f"**Started:** {result.started_at}")
    lines.append(f"**Finished:** {result.finished_at or 'in progress'}")
    lines.append(f"**Status:** {result.status}")
    lines.append(f"**Folds:** {result.folds_completed}/{result.total_folds}")
    lines.append("")

    if result.errors:
        lines.append("## Errors")
        for err in result.errors:
            lines.append(f"- {err}")
        lines.append("")

    # Fold-by-fold table
    if result.fold_results:
        lines.append("## Fold Results")
        lines.append("")
        lines.append(
            "| Fold | Train Bars | Test Bars | Train Score | OOS Score | "
            "Trades (OOS) | Win Rate | Accepted | Reason |"
        )
        lines.append(
            "|------|-----------|----------|-------------|-----------|"
            "-------------|----------|----------|--------|"
        )

        for fr in result.fold_results:
            train_bars = fr.fold_summary.get("train_bars", 0)
            test_bars = fr.fold_summary.get("test_bars", 0)
            train_score = (
                f"{fr.best_train.objective.score:.4f}"
                if fr.best_train else "N/A"
            )
            oos_score = (
                f"{fr.oos_result.objective.score:.4f}"
                if fr.oos_result and fr.oos_result.objective.is_valid
                else "N/A"
            )
            oos_trades = (
                str(fr.oos_result.objective.metrics.trade_count)
                if fr.oos_result else "N/A"
            )
            oos_wr = (
                f"{fr.oos_result.objective.metrics.win_rate:.1%}"
                if fr.oos_result and fr.oos_result.objective.metrics.trade_count > 0
                else "N/A"
            )
            accepted = "YES" if fr.accepted else "NO"
            reason = fr.reject_reason[:40] if fr.reject_reason else ""

            lines.append(
                f"| {fr.fold_index} | "
                f"{format_bars(train_bars, timeframe)} | "
                f"{format_bars(test_bars, timeframe)} | "
                f"{train_score} | {oos_score} | "
                f"{oos_trades} | {oos_wr} | {accepted} | {reason} |"
            )
        lines.append("")

    # Parameter changes from baseline
    if result.best_params:
        diff = result.best_params.diff_from_baseline()
        if diff:
            lines.append("## Recommended Parameter Changes")
            lines.append("")
            lines.append("| Parameter | Baseline | Recommended |")
            lines.append("|-----------|----------|-------------|")
            for name, (old, new) in diff.items():
                lines.append(f"| {name} | {old} | {new} |")
            lines.append("")
        else:
            lines.append("## Recommendation: Keep Baseline Parameters")
            lines.append("")
            lines.append("No parameter changes improved OOS performance.")
            lines.append("")

    # Overfitting diagnostics
    lines.append("## Overfitting Diagnostics")
    lines.append("")
    gaps = []
    for fr in result.fold_results:
        if (fr.best_train and fr.oos_result
                and fr.best_train.objective.is_valid
                and fr.oos_result.objective.is_valid):
            gap = fr.best_train.objective.score - fr.oos_result.objective.score
            gaps.append((fr.fold_index, gap))

    if gaps:
        avg_gap = sum(g for _, g in gaps) / len(gaps)
        max_gap = max(g for _, g in gaps)
        lines.append(f"- Average train-OOS gap: {avg_gap:.4f}")
        lines.append(f"- Max train-OOS gap: {max_gap:.4f}")
        if avg_gap > 0.2:
            lines.append(
                "- **WARNING**: Large average gap suggests overfitting. "
                "Consider reducing parameter space or increasing train window."
            )
        elif avg_gap < 0.05:
            lines.append("- Gap is small — parameters generalize well.")
        lines.append("")
    else:
        lines.append("- No valid train/OOS pairs to compare.")
        lines.append("")

    # Regression summary
    regression_results = [
        fr.regression for fr in result.fold_results if fr.regression
    ]
    if regression_results:
        lines.append("## Regression Guard Results")
        lines.append("")
        passed = sum(1 for r in regression_results if r.passed)
        failed = sum(1 for r in regression_results if not r.passed)
        lines.append(f"- Passed: {passed}/{len(regression_results)} folds")
        if failed:
            lines.append(f"- **FAILED**: {failed} folds broke baseline fixtures")
        lines.append("")

    return "\n".join(lines)


def generate_json_report(result: WalkForwardResult) -> dict:
    """Generate a machine-readable JSON report."""
    return result.to_dict()


def save_report(
    result: WalkForwardResult,
    output_dir: str | Path,
    timeframe: str = "1h",
) -> dict[str, str]:
    """
    Save both markdown and JSON reports to output directory.

    Returns dict of {format: filepath}.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"wfo_{result.run_id}_{timestamp}"

    # Markdown report
    md_path = output_dir / f"{base_name}.md"
    md_content = generate_summary_report(result, timeframe)
    md_path.write_text(md_content)

    # JSON report
    json_path = output_dir / f"{base_name}.json"
    json_content = generate_json_report(result)
    json_path.write_text(json.dumps(json_content, indent=2, default=str))

    logger.info(
        "Reports saved: %s, %s",
        md_path.name, json_path.name,
    )

    return {
        "markdown": str(md_path),
        "json": str(json_path),
    }


def parameter_stability_summary(result: WalkForwardResult) -> dict[str, list]:
    """
    Analyze how stable parameter selections are across folds.

    Returns {param_name: [values_selected_per_fold]}.
    Stable parameters have low variance across folds.
    """
    baseline = get_baseline_params()
    param_values: dict[str, list] = {}

    for fr in result.fold_results:
        if not fr.accepted or not fr.best_train:
            continue
        for name, value in fr.best_train.params.values.items():
            if name not in param_values:
                param_values[name] = []
            param_values[name].append(value)

    return param_values
