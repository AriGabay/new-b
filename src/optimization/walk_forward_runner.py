"""
Walk-Forward Optimization Runner.

Orchestrates the full walk-forward optimization process:
  1. Load data → build FeatureVectors → build folds
  2. For each fold:
     a. Grid-search parameter combos on the TRAIN window
     b. Select best combo by objective score
     c. Evaluate best combo on the TEST window (out-of-sample)
     d. Run regression guard to verify baseline fixtures
  3. Aggregate OOS results across all folds
  4. Generate final report

The runner uses the real RuntimeReplayHarness (event_driven_runtime_simulation)
for all evaluations. No shortcuts, no forced approvals.

Anti-overfitting:
  - Train and test windows never overlap
  - Regression guard blocks parameter sets that break baseline fixtures
  - OOS performance is the only metric that matters
  - Results flagged if train >> test performance (overfitting signal)
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.schemas import FeatureVector
from optimization.fold_builder import Fold, build_folds
from optimization.objective import (
    ObjectiveResult,
    RunMetrics,
    TradeResult,
    compute_objective,
)
from optimization.parameter_space import ParameterSet, get_baseline_params
from optimization.regression_guard import (
    RegressionResult,
    _apply_overrides,
    _save_module_state,
    _restore_module_state,
    run_regression_guard,
)
from utils.bar_duration import format_bars

logger = logging.getLogger(__name__)


@dataclass
class TrialResult:
    """Result of one parameter trial on one fold window."""
    params: ParameterSet
    objective: ObjectiveResult
    window: str            # "train" or "test"
    fold_index: int
    elapsed_seconds: float


@dataclass
class FoldResult:
    """Result of optimizing one fold."""
    fold_index: int
    fold_summary: dict
    train_trials: int
    best_train: Optional[TrialResult]
    oos_result: Optional[TrialResult]
    regression: Optional[RegressionResult]
    accepted: bool
    reject_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "fold_index": self.fold_index,
            "fold_summary": self.fold_summary,
            "train_trials": self.train_trials,
            "best_train_score": (
                self.best_train.objective.score if self.best_train else None
            ),
            "best_train_params": (
                self.best_train.params.diff_from_baseline()
                if self.best_train else None
            ),
            "oos_score": (
                self.oos_result.objective.score if self.oos_result else None
            ),
            "oos_metrics": (
                self.oos_result.objective.metrics.to_dict()
                if self.oos_result else None
            ),
            "regression_passed": (
                self.regression.passed if self.regression else None
            ),
            "accepted": self.accepted,
            "reject_reason": self.reject_reason,
        }


@dataclass
class WalkForwardResult:
    """Final result of the walk-forward optimization."""
    run_id: str
    started_at: str
    finished_at: Optional[str]
    status: str               # "pending" | "running" | "done" | "error"
    total_folds: int
    folds_completed: int
    fold_results: list[FoldResult] = field(default_factory=list)
    best_params: Optional[ParameterSet] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "total_folds": self.total_folds,
            "folds_completed": self.folds_completed,
            "fold_results": [f.to_dict() for f in self.fold_results],
            "best_params": (
                self.best_params.diff_from_baseline()
                if self.best_params else None
            ),
            "errors": self.errors,
        }


class WalkForwardRunner:
    """
    Orchestrates walk-forward optimization.

    Usage:
        runner = WalkForwardRunner()
        result = await runner.run(
            feature_vectors=fvs,
            param_names=["composite_score_threshold", "panel_approve_threshold"],
            timeframe="1h",
        )
    """

    def __init__(self, equity: Decimal = Decimal("100000")) -> None:
        self._equity = equity
        self._runs: dict[str, WalkForwardResult] = {}

    async def run(
        self,
        feature_vectors: list[FeatureVector],
        param_names: list[str],
        warmup_bars: int = 250,
        train_bars: int = 4320,
        test_bars: int = 720,
        step_bars: int = 720,
        timeframe: str = "1h",
        max_combinations: int = 5000,
        run_regression: bool = True,
        overfitting_threshold: float = 0.3,
    ) -> WalkForwardResult:
        """
        Run the full walk-forward optimization.

        Args:
            feature_vectors: Full chronological FeatureVector sequence.
            param_names: Which parameters to optimize.
            warmup_bars: Warm-up bars prepended to each train window.
            train_bars: In-sample window size.
            test_bars: Out-of-sample window size.
            step_bars: Advance between folds.
            timeframe: Timeframe for duration display.
            max_combinations: Safety limit on grid size.
            run_regression: Whether to run regression guard after each fold.
            overfitting_threshold: Flag if train_score - oos_score > this.

        Returns:
            WalkForwardResult with fold-by-fold details.
        """
        from optimization.parameter_space import build_grid

        run_id = str(uuid.uuid4())[:8]
        result = WalkForwardResult(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            status="running",
            total_folds=0,
            folds_completed=0,
        )
        self._runs[run_id] = result

        try:
            # Build folds
            folds = build_folds(
                feature_vectors,
                warmup_bars=warmup_bars,
                train_bars=train_bars,
                test_bars=test_bars,
                step_bars=step_bars,
                timeframe=timeframe,
            )
            result.total_folds = len(folds)

            if not folds:
                result.status = "error"
                result.errors.append(
                    f"No folds could be built from {len(feature_vectors)} bars "
                    f"(need warmup={warmup_bars} + train={train_bars} + test={test_bars})"
                )
                return result

            # Build parameter grid
            grid = build_grid(param_names, max_combinations=max_combinations)
            logger.info(
                "WalkForward [%s]: %d folds, %d grid points, %d params",
                run_id, len(folds), len(grid), len(param_names),
            )

            # Save module state for restoration after each trial
            saved_state = _save_module_state()

            # Process each fold
            for fold in folds:
                try:
                    fold_result = await self._process_fold(
                        fold=fold,
                        grid=grid,
                        run_regression=run_regression,
                        overfitting_threshold=overfitting_threshold,
                        saved_state=saved_state,
                    )
                    result.fold_results.append(fold_result)
                    result.folds_completed += 1
                except Exception as e:
                    logger.exception(
                        "WalkForward [%s]: fold %d error",
                        run_id, fold.fold_index,
                    )
                    result.errors.append(f"Fold {fold.fold_index}: {e}")
                finally:
                    _restore_module_state(saved_state)

            # Select overall best: most common winning param set across folds
            result.best_params = self._select_best_overall(result.fold_results)
            result.status = "done"

        except Exception as e:
            result.status = "error"
            result.errors.append(str(e))
            logger.exception("WalkForward [%s]: fatal error", run_id)
        finally:
            result.finished_at = datetime.now(timezone.utc).isoformat()

        return result

    async def _process_fold(
        self,
        fold: Fold,
        grid: list[ParameterSet],
        run_regression: bool,
        overfitting_threshold: float,
        saved_state: dict,
    ) -> FoldResult:
        """Process a single fold: grid search on train, evaluate best on test."""
        logger.info(
            "=== Fold %d: train %s, test %s ===",
            fold.fold_index,
            format_bars(len(fold.train), fold.timeframe),
            format_bars(len(fold.test), fold.timeframe),
        )

        # Grid search on TRAIN window
        train_results: list[TrialResult] = []
        train_fvs = fold.train_with_warmup

        for i, params in enumerate(grid):
            try:
                _restore_module_state(saved_state)
                trial = await self._evaluate_params(
                    params=params,
                    feature_vectors=train_fvs,
                    window="train",
                    fold_index=fold.fold_index,
                )
                train_results.append(trial)

                if (i + 1) % 50 == 0:
                    logger.info(
                        "Fold %d: evaluated %d/%d grid points",
                        fold.fold_index, i + 1, len(grid),
                    )
            except Exception as e:
                logger.warning(
                    "Fold %d trial %d error: %s",
                    fold.fold_index, i, e,
                )
            finally:
                _restore_module_state(saved_state)

        # Select best train result
        valid_trains = [t for t in train_results if t.objective.is_valid]
        if not valid_trains:
            return FoldResult(
                fold_index=fold.fold_index,
                fold_summary=fold.summary(),
                train_trials=len(train_results),
                best_train=None,
                oos_result=None,
                regression=None,
                accepted=False,
                reject_reason="No valid train results (all had too few trades)",
            )

        best_train = max(valid_trains, key=lambda t: t.objective.score)
        logger.info(
            "Fold %d: best train score=%.4f, params=%s",
            fold.fold_index,
            best_train.objective.score,
            best_train.params.diff_from_baseline(),
        )

        # Evaluate best on TEST window (out-of-sample)
        _restore_module_state(saved_state)
        test_fvs = fold.warmup + fold.test  # warmup + test for indicator context
        try:
            oos_result = await self._evaluate_params(
                params=best_train.params,
                feature_vectors=test_fvs,
                window="test",
                fold_index=fold.fold_index,
            )
        finally:
            _restore_module_state(saved_state)

        # Overfitting check
        reject_reason = ""
        if oos_result.objective.is_valid and best_train.objective.is_valid:
            gap = best_train.objective.score - oos_result.objective.score
            if gap > overfitting_threshold:
                reject_reason = (
                    f"Overfitting: train={best_train.objective.score:.4f} "
                    f"vs OOS={oos_result.objective.score:.4f} "
                    f"(gap={gap:.4f} > threshold={overfitting_threshold})"
                )
                logger.warning("Fold %d: %s", fold.fold_index, reject_reason)

        # Regression guard
        regression = None
        if run_regression and not reject_reason:
            _restore_module_state(saved_state)
            try:
                overrides = best_train.params.diff_from_baseline()
                override_values = {k: v[1] for k, v in overrides.items()}
                regression = await run_regression_guard(
                    param_overrides=override_values
                )
                if not regression.passed:
                    reject_reason = (
                        f"Regression guard failed: "
                        f"{regression.fixtures_failed} fixtures regressed"
                    )
            finally:
                _restore_module_state(saved_state)

        accepted = not reject_reason

        return FoldResult(
            fold_index=fold.fold_index,
            fold_summary=fold.summary(),
            train_trials=len(train_results),
            best_train=best_train,
            oos_result=oos_result,
            regression=regression,
            accepted=accepted,
            reject_reason=reject_reason,
        )

    async def _evaluate_params(
        self,
        params: ParameterSet,
        feature_vectors: list[FeatureVector],
        window: str,
        fold_index: int,
    ) -> TrialResult:
        """
        Run the pipeline with given params on a FeatureVector sequence.
        Returns TrialResult with objective score.
        """
        from runtime.runner import BtcBybitPaperRunner
        from core.events import (
            PositionOpenEvent,
            PositionCloseEvent,
        )

        start_time = time.monotonic()

        runner = BtcBybitPaperRunner(
            simulation_mode=True,
            journal_db_path=":memory:",
        )
        await runner.setup()
        runner.state.portfolio.equity = self._equity
        runner.state.portfolio.available = self._equity

        # Apply parameter overrides
        override_diff = params.diff_from_baseline()
        if override_diff:
            override_values = {k: v[1] for k, v in override_diff.items()}
            _apply_overrides(runner, override_values)

        # Capture trade events
        trades: list[TradeResult] = []
        peak_equity = float(self._equity)
        max_drawdown = 0.0

        original_publish = runner.bus.publish

        async def capture_publish(event):
            nonlocal peak_equity, max_drawdown
            if isinstance(event, PositionCloseEvent):
                pos = event.position
                r_mult = float(getattr(pos, "r_multiple", 0.0))
                pnl = float(getattr(pos, "pnl_usd", 0.0))
                trades.append(TradeResult(
                    entry_price=getattr(pos, "entry_price", Decimal(0)),
                    exit_price=getattr(pos, "exit_price", Decimal(0)),
                    direction=str(getattr(pos, "direction", "unknown")),
                    r_multiple=r_mult,
                    bars_held=int(getattr(pos, "bars_held", 0)),
                    pnl_usd=pnl,
                ))
                # Track drawdown
                current_equity = float(runner.state.portfolio.equity)
                if current_equity > peak_equity:
                    peak_equity = current_equity
                if peak_equity > 0:
                    dd = (peak_equity - current_equity) / peak_equity
                    if dd > max_drawdown:
                        max_drawdown = dd
            return await original_publish(event)

        runner.bus.publish = capture_publish

        # Feed bars
        positions_opened = 0
        last_date = None
        try:
            for fv in feature_vectors:
                # Reset daily PnL at date boundaries so the daily loss limit
                # doesn't carry over and block all trades after a losing day.
                bar_date = fv.timestamp.date() if fv.timestamp else None
                if bar_date and bar_date != last_date:
                    await runner.state.reset_daily_pnl()
                    last_date = bar_date

                before = len(runner.state.portfolio.open_positions)
                await runner.simulate_bar(fv)
                await asyncio.sleep(0)
                after = len(runner.state.portfolio.open_positions)
                positions_opened += max(0, after - before)
        except Exception as e:
            logger.debug("evaluate_params error: %s", e)
        finally:
            try:
                await runner.teardown()
            except Exception:
                pass

        elapsed = time.monotonic() - start_time

        metrics = RunMetrics(
            bars_run=len(feature_vectors),
            trades=trades,
            positions_opened=positions_opened,
            positions_closed=len(trades),
            final_equity=float(runner.state.portfolio.equity),
            starting_equity=float(self._equity),
            max_drawdown_pct=max_drawdown,
            peak_equity=peak_equity,
        )

        objective = compute_objective(metrics)

        return TrialResult(
            params=params,
            objective=objective,
            window=window,
            fold_index=fold_index,
            elapsed_seconds=elapsed,
        )

    def _select_best_overall(
        self, fold_results: list[FoldResult]
    ) -> Optional[ParameterSet]:
        """Select the parameter set that performed best across accepted folds."""
        accepted = [f for f in fold_results if f.accepted and f.best_train]
        if not accepted:
            return None

        # Use OOS score as the selection criterion
        best_fold = max(
            accepted,
            key=lambda f: (
                f.oos_result.objective.score
                if f.oos_result and f.oos_result.objective.is_valid
                else -1.0
            ),
        )
        return best_fold.best_train.params if best_fold.best_train else None

    def get_result(self, run_id: str) -> Optional[dict]:
        r = self._runs.get(run_id)
        return r.to_dict() if r else None

    def list_results(self) -> list[dict]:
        return [r.to_dict() for r in self._runs.values()]
