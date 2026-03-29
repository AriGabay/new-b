"""
Tests for the walk-forward optimization framework.

Covers:
  1. data_loader — CSV parsing, validation, chronological ordering
  2. featurevector_builder — OHLCV → FeatureVector conversion
  3. fold_builder — rolling train/test window construction
  4. parameter_space — grid generation, bounds, baseline
  5. objective — multi-factor scoring, edge cases
  6. regression_guard — baseline expectations, check structure
  7. reporting — report generation
  8. Integration — small end-to-end walk-forward run

Phase: 7.2 — Walk-Forward Optimization
"""
from __future__ import annotations

import csv
import math
import os
import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from core.schemas import FeatureVector, OHLCVBar


# ---------------------------------------------------------------------------
# 1. Data Loader
# ---------------------------------------------------------------------------

class TestDataLoader:

    def _write_csv(self, rows: list[dict], path: str) -> None:
        """Helper to write a CSV file from row dicts."""
        if not rows:
            return
        fieldnames = list(rows[0].keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _make_rows(self, n: int, start_ts: datetime = None) -> list[dict]:
        """Generate n valid OHLCV rows."""
        if start_ts is None:
            start_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        rows = []
        price = Decimal("65000")
        for i in range(n):
            ts = start_ts + timedelta(hours=i)
            close = price + Decimal(i) * Decimal("10")
            rows.append({
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": str(close - Decimal("5")),
                "high": str(close + Decimal("50")),
                "low": str(close - Decimal("50")),
                "close": str(close),
                "volume": "100.5",
            })
        return rows

    def test_load_valid_csv(self):
        from optimization.data_loader import load_csv

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            rows = self._make_rows(250)
            self._write_csv(rows, path)
            result = load_csv(path, min_bars=200)
            assert result.ok
            assert result.bar_count == 250
            assert result.symbol == "BTCUSDT"
            assert result.timeframe == "1h"
            assert len(result.warnings) == 0
        finally:
            os.unlink(path)

    def test_load_insufficient_rows_raises(self):
        from optimization.data_loader import load_csv

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            rows = self._make_rows(50)
            self._write_csv(rows, path)
            with pytest.raises(ValueError, match="valid bars"):
                load_csv(path, min_bars=200)
        finally:
            os.unlink(path)

    def test_load_missing_file_raises(self):
        from optimization.data_loader import load_csv
        with pytest.raises(FileNotFoundError):
            load_csv("/nonexistent/path.csv")

    def test_load_missing_columns_raises(self):
        from optimization.data_loader import load_csv

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
            f.write("timestamp,open,high,low\n")
            f.write("2024-01-01T00:00:00Z,100,101,99\n")
        try:
            with pytest.raises(ValueError, match="missing required columns"):
                load_csv(path, min_bars=1)
        finally:
            os.unlink(path)

    def test_chronological_order_enforced(self):
        from optimization.data_loader import load_csv

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            rows = self._make_rows(210)
            # Swap two rows to break order
            rows[100], rows[101] = rows[101], rows[100]
            self._write_csv(rows, path)
            result = load_csv(path, min_bars=200)
            # Should skip the out-of-order row
            assert result.bar_count == 209
            assert len(result.warnings) > 0
        finally:
            os.unlink(path)

    def test_unix_epoch_timestamp_parsing(self):
        from optimization.data_loader import _parse_timestamp

        ts = _parse_timestamp("1704067200000")  # 2024-01-01 00:00:00 UTC
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 1

    def test_gap_warning(self):
        from optimization.data_loader import load_csv

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            rows = self._make_rows(210)
            # Insert a 5-hour gap at row 100
            for i in range(100, 210):
                ts = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i + 4)
                rows[i]["timestamp"] = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            self._write_csv(rows, path)
            result = load_csv(path, min_bars=200)
            assert result.ok
            gap_warnings = [w for w in result.warnings if "gap" in w.lower()]
            assert len(gap_warnings) > 0
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 2. FeatureVector Builder
# ---------------------------------------------------------------------------

class TestFeatureVectorBuilder:

    def _make_bars(self, n: int) -> list[OHLCVBar]:
        """Generate n synthetic OHLCVBars."""
        bars = []
        base_price = Decimal("65000")
        for i in range(n):
            close = base_price + Decimal(i) * Decimal("10")
            bars.append(OHLCVBar(
                symbol="BTCUSDT",
                timeframe="1h",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                open=close - Decimal("5"),
                high=close + Decimal("50"),
                low=close - Decimal("55"),
                close=close,
                volume=Decimal("100"),
                volume_usd=close * Decimal("100"),
            ))
        return bars

    def test_build_feature_vectors_basic(self):
        from optimization.featurevector_builder import build_feature_vectors
        bars = self._make_bars(250)
        fvs = build_feature_vectors(bars)
        assert len(fvs) > 0
        # First FV uses bars[0:200], so we get 51 FVs (bars 199 through 249)
        assert len(fvs) == 51
        assert all(isinstance(fv, FeatureVector) for fv in fvs)

    def test_build_feature_vectors_insufficient_bars_raises(self):
        from optimization.featurevector_builder import build_feature_vectors
        bars = self._make_bars(100)
        with pytest.raises(ValueError, match="Need at least"):
            build_feature_vectors(bars)

    def test_build_with_indices(self):
        from optimization.featurevector_builder import build_feature_vectors_with_indices
        bars = self._make_bars(210)
        results = build_feature_vectors_with_indices(bars)
        assert len(results) > 0
        for bar_idx, fv in results:
            assert isinstance(bar_idx, int)
            assert isinstance(fv, FeatureVector)
            assert bar_idx >= 199


# ---------------------------------------------------------------------------
# 3. Fold Builder
# ---------------------------------------------------------------------------

class TestFoldBuilder:

    def _make_fvs(self, n: int) -> list[FeatureVector]:
        """Generate n minimal FeatureVectors with sequential timestamps."""
        fvs = []
        for i in range(n):
            fvs.append(FeatureVector(
                symbol="BTCUSDT",
                timeframe="1h",
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                open=Decimal("65000"), high=Decimal("65050"),
                low=Decimal("64950"), close=Decimal("65000"),
                volume=Decimal("100"),
                true_range=Decimal("100"), atr14=Decimal("80"),
                atr14_sma20=Decimal("80"),
                ema20=Decimal("65000"), ema50=Decimal("64900"),
                ema200=Decimal("64500"),
                prev_ema20=Decimal("64990"), prev_ema50=Decimal("64890"),
                rsi14=55.0, prev_rsi14=54.0,
                bb_upper=Decimal("65200"), bb_middle=Decimal("65000"),
                bb_lower=Decimal("64800"), bb_width=Decimal("400"),
                bb_width_pct=50.0,
                adx14=25.0,
                volume_sma20=Decimal("95"), volume_ratio=1.05,
                candle_body=Decimal("50"), candle_range=Decimal("100"),
                body_ratio=0.5, upper_shadow=Decimal("25"),
                lower_shadow=Decimal("25"),
                impulse_flag=False, doji_flag=False,
            ))
        return fvs

    def test_build_folds_basic(self):
        from optimization.fold_builder import build_folds
        # warmup=10, train=50, test=20, step=20 → need 80 minimum
        fvs = self._make_fvs(120)
        folds = build_folds(fvs, warmup_bars=10, train_bars=50,
                            test_bars=20, step_bars=20)
        assert len(folds) >= 1
        # Verify non-overlapping
        for fold in folds:
            assert len(fold.warmup) == 10
            assert len(fold.train) == 50
            assert len(fold.test) == 20

    def test_build_folds_insufficient_data(self):
        from optimization.fold_builder import build_folds
        fvs = self._make_fvs(50)
        folds = build_folds(fvs, warmup_bars=10, train_bars=50,
                            test_bars=20, step_bars=20)
        assert len(folds) == 0

    def test_fold_count_matches_estimate(self):
        from optimization.fold_builder import build_folds, estimate_fold_count
        fvs = self._make_fvs(200)
        folds = build_folds(fvs, warmup_bars=10, train_bars=50,
                            test_bars=20, step_bars=20)
        estimated = estimate_fold_count(200, warmup_bars=10, train_bars=50,
                                         test_bars=20, step_bars=20)
        assert len(folds) == estimated

    def test_fold_summary_has_duration(self):
        from optimization.fold_builder import build_folds
        fvs = self._make_fvs(100)
        folds = build_folds(fvs, warmup_bars=10, train_bars=50,
                            test_bars=20, step_bars=20)
        assert len(folds) >= 1
        summary = folds[0].summary()
        assert "train_duration" in summary
        assert "bars" in summary["train_duration"]

    def test_train_with_warmup_includes_both(self):
        from optimization.fold_builder import build_folds
        fvs = self._make_fvs(100)
        folds = build_folds(fvs, warmup_bars=10, train_bars=50,
                            test_bars=20, step_bars=20)
        fold = folds[0]
        assert len(fold.train_with_warmup) == 60  # 10 warmup + 50 train

    def test_no_overlap_between_train_and_test(self):
        from optimization.fold_builder import build_folds
        fvs = self._make_fvs(200)
        folds = build_folds(fvs, warmup_bars=10, train_bars=50,
                            test_bars=20, step_bars=20)
        for fold in folds:
            train_end = fold.train_end
            test_start = fold.test_start
            assert test_start > train_end, (
                f"Fold {fold.fold_index}: train_end={train_end} >= test_start={test_start}"
            )


# ---------------------------------------------------------------------------
# 4. Parameter Space
# ---------------------------------------------------------------------------

class TestParameterSpace:

    def test_baseline_params_has_all_parameters(self):
        from optimization.parameter_space import (
            PARAMETER_SPACE, get_baseline_params,
        )
        baseline = get_baseline_params()
        for p in PARAMETER_SPACE:
            assert p.name in baseline.values

    def test_grid_values_cover_range(self):
        from optimization.parameter_space import get_parameter
        p = get_parameter("composite_score_threshold")
        values = p.grid_values()
        assert values[0] == p.min_value
        assert values[-1] <= p.max_value
        assert len(values) > 1

    def test_grid_values_int_parameter(self):
        from optimization.parameter_space import get_parameter
        p = get_parameter("panel_approve_threshold")
        values = p.grid_values()
        assert all(isinstance(v, int) for v in values)
        assert 12 in values
        assert 14 in values

    def test_build_grid_single_param(self):
        from optimization.parameter_space import build_grid
        grid = build_grid(["composite_score_threshold"])
        assert len(grid) > 1
        # All should have the same baseline for other params
        for ps in grid:
            assert "composite_score_threshold" in ps.values

    def test_build_grid_two_params(self):
        from optimization.parameter_space import build_grid, get_parameter
        grid = build_grid(["composite_score_threshold", "panel_approve_threshold"])
        p1 = get_parameter("composite_score_threshold")
        p2 = get_parameter("panel_approve_threshold")
        expected = len(p1.grid_values()) * len(p2.grid_values())
        assert len(grid) == expected

    def test_build_grid_unknown_param_raises(self):
        from optimization.parameter_space import build_grid
        with pytest.raises(ValueError, match="Unknown"):
            build_grid(["nonexistent_param"])

    def test_build_grid_max_combinations_limit(self):
        from optimization.parameter_space import build_grid
        with pytest.raises(ValueError, match="exceeds limit"):
            build_grid(
                ["composite_score_threshold", "panel_approve_threshold"],
                max_combinations=2,
            )

    def test_parameter_set_diff_from_baseline(self):
        from optimization.parameter_space import ParameterSet, get_baseline_params
        baseline = get_baseline_params()
        modified = ParameterSet(values={**baseline.values, "composite_score_threshold": 0.40})
        diff = modified.diff_from_baseline()
        assert "composite_score_threshold" in diff
        assert diff["composite_score_threshold"] == (0.50, 0.40)


# ---------------------------------------------------------------------------
# 5. Objective Function
# ---------------------------------------------------------------------------

class TestObjective:

    def _make_metrics(self, trades=None, bars_run=1000) -> "RunMetrics":
        from optimization.objective import RunMetrics, TradeResult
        if trades is None:
            trades = [
                TradeResult(
                    entry_price=Decimal("65000"),
                    exit_price=Decimal("66000"),
                    direction="long",
                    r_multiple=1.5,
                    bars_held=10,
                    pnl_usd=1500.0,
                ),
                TradeResult(
                    entry_price=Decimal("66000"),
                    exit_price=Decimal("65500"),
                    direction="long",
                    r_multiple=-0.5,
                    bars_held=5,
                    pnl_usd=-500.0,
                ),
                TradeResult(
                    entry_price=Decimal("65500"),
                    exit_price=Decimal("66500"),
                    direction="long",
                    r_multiple=1.0,
                    bars_held=8,
                    pnl_usd=1000.0,
                ),
            ]
        return RunMetrics(
            bars_run=bars_run,
            trades=trades,
            positions_opened=len(trades),
            positions_closed=len(trades),
            max_drawdown_pct=0.02,
        )

    def test_compute_objective_valid(self):
        from optimization.objective import compute_objective
        metrics = self._make_metrics()
        result = compute_objective(metrics)
        assert result.is_valid
        assert result.score > 0
        assert "expectancy" in result.component_scores

    def test_compute_objective_too_few_trades(self):
        from optimization.objective import compute_objective, RunMetrics
        metrics = RunMetrics(bars_run=1000, trades=[], max_drawdown_pct=0.0)
        result = compute_objective(metrics)
        assert not result.is_valid
        assert result.score == -1.0

    def test_win_rate_calculation(self):
        metrics = self._make_metrics()
        assert metrics.wins == 2
        assert metrics.losses == 1
        assert abs(metrics.win_rate - 2/3) < 0.01

    def test_expectancy_calculation(self):
        metrics = self._make_metrics()
        expected = (1.5 + (-0.5) + 1.0) / 3
        assert abs(metrics.expectancy - expected) < 0.01

    def test_profit_factor_calculation(self):
        metrics = self._make_metrics()
        gross_profit = 1500 + 1000
        gross_loss = 500
        assert abs(metrics.profit_factor - gross_profit / gross_loss) < 0.01

    def test_drawdown_penalty_increases_with_drawdown(self):
        from optimization.objective import _drawdown_score
        score_low = _drawdown_score(0.02)
        score_high = _drawdown_score(0.10)
        assert score_low > score_high

    def test_sigmoid_score_symmetry(self):
        from optimization.objective import _sigmoid_score
        at_midpoint = _sigmoid_score(1.0, midpoint=1.0, scale=1.0)
        assert abs(at_midpoint - 0.5) < 0.01

    def test_metrics_to_dict(self):
        metrics = self._make_metrics()
        d = metrics.to_dict()
        assert "trade_count" in d
        assert "win_rate" in d
        assert "expectancy" in d

    def test_objective_result_to_dict(self):
        from optimization.objective import compute_objective
        metrics = self._make_metrics()
        result = compute_objective(metrics)
        d = result.to_dict()
        assert "score" in d
        assert "is_valid" in d
        assert "component_scores" in d


# ---------------------------------------------------------------------------
# 6. Regression Guard
# ---------------------------------------------------------------------------

class TestRegressionGuard:

    def test_baseline_expectations_cover_all_fixtures(self):
        from optimization.regression_guard import BASELINE_EXPECTATIONS
        from console.replay_manager import _FIXTURE_BUILDERS

        for fid in _FIXTURE_BUILDERS:
            assert fid in BASELINE_EXPECTATIONS, (
                f"Fixture '{fid}' has a builder but no baseline expectation"
            )

    def test_baseline_expectations_have_correct_structure(self):
        from optimization.regression_guard import BASELINE_EXPECTATIONS
        for fid, (must_enter, min_approve, desc) in BASELINE_EXPECTATIONS.items():
            assert isinstance(must_enter, bool)
            assert isinstance(min_approve, int)
            assert 0 <= min_approve <= 20
            assert isinstance(desc, str)

    def test_entering_fixtures_have_high_approve_counts(self):
        from optimization.regression_guard import BASELINE_EXPECTATIONS
        for fid, (must_enter, min_approve, _) in BASELINE_EXPECTATIONS.items():
            if must_enter:
                assert min_approve >= 14, (
                    f"Entering fixture '{fid}' has min_approve={min_approve} < 14"
                )

    def test_save_restore_module_state(self):
        from optimization.regression_guard import (
            _save_module_state, _restore_module_state,
        )
        import groups.entry.group as entry_mod

        original = entry_mod.COMPOSITE_SCORE_THRESHOLD
        state = _save_module_state()

        # Modify
        entry_mod.COMPOSITE_SCORE_THRESHOLD = 0.99

        # Restore
        _restore_module_state(state)
        assert entry_mod.COMPOSITE_SCORE_THRESHOLD == original


# ---------------------------------------------------------------------------
# 7. Reporting
# ---------------------------------------------------------------------------

class TestReporting:

    def test_generate_summary_report_empty(self):
        from optimization.reporting import generate_summary_report
        from optimization.walk_forward_runner import WalkForwardResult
        result = WalkForwardResult(
            run_id="test123",
            started_at="2024-01-01T00:00:00Z",
            finished_at="2024-01-01T01:00:00Z",
            status="done",
            total_folds=0,
            folds_completed=0,
        )
        report = generate_summary_report(result)
        assert "Walk-Forward Optimization Report" in report
        assert "test123" in report

    def test_generate_json_report(self):
        from optimization.reporting import generate_json_report
        from optimization.walk_forward_runner import WalkForwardResult
        result = WalkForwardResult(
            run_id="test456",
            started_at="2024-01-01T00:00:00Z",
            finished_at=None,
            status="running",
            total_folds=3,
            folds_completed=1,
        )
        report = generate_json_report(result)
        assert report["run_id"] == "test456"
        assert report["total_folds"] == 3


# ---------------------------------------------------------------------------
# 8. Integration: Parameter grid round-trip
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_parameter_grid_round_trip(self):
        """Build a grid, verify all sets are valid ParameterSets."""
        from optimization.parameter_space import (
            build_grid, get_baseline_params, ParameterSet,
        )
        grid = build_grid(["composite_score_threshold"])
        assert all(isinstance(ps, ParameterSet) for ps in grid)
        # At least one should match baseline
        baseline = get_baseline_params()
        baseline_found = any(
            ps.values["composite_score_threshold"] == baseline.values["composite_score_threshold"]
            for ps in grid
        )
        assert baseline_found

    def test_fold_builder_with_real_defaults(self):
        """Verify default fold parameters are consistent."""
        from optimization.fold_builder import (
            DEFAULT_WARMUP_BARS, DEFAULT_TRAIN_BARS,
            DEFAULT_TEST_BARS, DEFAULT_STEP_BARS,
            estimate_fold_count,
        )
        # With 1 year of 1h data: 8760 bars
        n_bars = 8760
        n_folds = estimate_fold_count(n_bars)
        # warmup=250 + train=4320 + test=720 = 5290 minimum
        # remaining = 8760 - 5290 = 3470, step=720
        # 1 + 3470 // 720 = 1 + 4 = 5 folds
        assert n_folds == 5, f"Expected 5 folds for 1 year, got {n_folds}"
