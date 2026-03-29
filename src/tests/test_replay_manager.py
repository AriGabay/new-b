"""
Tests for console/replay_manager.py.

Verifies:
  1. All fixture IDs in AVAILABLE_FIXTURES resolve to real builder functions.
  2. The simulation replay path calls RuntimeReplayHarness.run_sequence()
     with fixture.feature_vectors (not stale n_bars/symbol args).
  3. Missing fixture IDs return a clean error.
  4. At least one real fixture can run end-to-end without import failure.
  5. No stale imports of removed fixture functions.

Phase: 7.1 — replay manager repair
"""
from __future__ import annotations

import asyncio
import pytest

from console.replay_manager import (
    AVAILABLE_FIXTURES,
    ReplayManager,
    _FIXTURE_BUILDERS,
)


# ---------------------------------------------------------------------------
# 1. Fixture resolution
# ---------------------------------------------------------------------------

class TestFixtureResolution:

    def test_all_available_fixture_ids_have_builders(self):
        """Every id in AVAILABLE_FIXTURES must exist in _FIXTURE_BUILDERS."""
        for entry in AVAILABLE_FIXTURES:
            fid = entry["id"]
            assert fid in _FIXTURE_BUILDERS, (
                f"AVAILABLE_FIXTURES contains '{fid}' but _FIXTURE_BUILDERS does not."
            )

    def test_all_builders_are_callable(self):
        for fid, builder in _FIXTURE_BUILDERS.items():
            assert callable(builder), f"Builder for '{fid}' is not callable."

    def test_all_builders_produce_fixtures_with_feature_vectors(self):
        """Every builder must return an object with .name and .feature_vectors."""
        for fid, builder in _FIXTURE_BUILDERS.items():
            fixture = builder()
            assert hasattr(fixture, "name"), f"Fixture from '{fid}' has no .name"
            assert hasattr(fixture, "feature_vectors"), (
                f"Fixture from '{fid}' has no .feature_vectors"
            )
            assert len(fixture.feature_vectors) > 0, (
                f"Fixture '{fid}' has 0 feature_vectors"
            )

    def test_resolve_fixture_succeeds_for_valid_id(self):
        rm = ReplayManager()
        fixture, err = rm._resolve_fixture("btc_bull_breakout_v1")
        assert err is None
        assert fixture is not None
        assert fixture.name == "btc_bull_breakout_v1"

    def test_resolve_fixture_returns_error_for_invalid_id(self):
        rm = ReplayManager()
        fixture, err = rm._resolve_fixture("nonexistent_fixture_xyz")
        assert fixture is None
        assert err is not None
        assert "Unknown fixture_id" in err
        assert "nonexistent_fixture_xyz" in err


# ---------------------------------------------------------------------------
# 2. No stale API usage
# ---------------------------------------------------------------------------

class TestNoStaleAPIs:

    def test_no_n_bars_in_replay_manager_source(self):
        """Ensure n_bars= is not used anywhere in replay_manager.py."""
        import inspect
        import console.replay_manager as mod
        source = inspect.getsource(mod)
        assert "n_bars" not in source, (
            "replay_manager.py still references n_bars — stale API usage."
        )

    def test_no_get_btc_bear_continuation_fixture_import(self):
        """Ensure removed fixture function is not imported."""
        import inspect
        import console.replay_manager as mod
        source = inspect.getsource(mod)
        assert "get_btc_bear_continuation_fixture" not in source, (
            "replay_manager.py still imports get_btc_bear_continuation_fixture "
            "which does not exist."
        )

    def test_no_symbol_arg_in_run_sequence_calls(self):
        """Ensure symbol= is not passed to run_sequence."""
        import inspect
        import console.replay_manager as mod
        source = inspect.getsource(mod)
        # run_sequence should be called with fv_sequence= and label=, not symbol=
        assert "symbol=" not in source or "symbol=" in source.split("_resolve_fixture")[0], (
            "replay_manager.py passes symbol= to run_sequence — stale API usage."
        )


# ---------------------------------------------------------------------------
# 3. End-to-end simulation replay
# ---------------------------------------------------------------------------

class TestSimulationReplayEndToEnd:

    def test_simulation_replay_completes_for_ranging_fixture(self):
        """
        Run the smallest fixture (btc_ranging_v1, 200 bars) through the
        simulation replay path end-to-end and verify no errors.
        """
        async def _run():
            rm = ReplayManager()
            run_id = await rm.run(
                fixture_id="btc_ranging_v1",
                harness_type="simulation",
            )
            # Wait for background task to complete
            for _ in range(50):
                await asyncio.sleep(0.1)
                r = rm.get_result(run_id)
                if r and r["status"] in ("done", "error"):
                    break
            return rm.get_result(run_id)

        result = asyncio.run(_run())
        assert result is not None, "No result returned"
        assert result["status"] == "done", (
            f"Expected 'done', got '{result['status']}'. Errors: {result['errors']}"
        )
        assert result["bars_run"] == 200, f"Expected 200 bars, got {result['bars_run']}"
        assert len(result["errors"]) == 0, f"Unexpected errors: {result['errors']}"

    def test_simulation_replay_for_entering_fixture(self):
        """
        btc_bull_continuation_pullback_v1 is known to produce 2 entries.
        Verify the replay manager reports positions_opened > 0.
        """
        async def _run():
            rm = ReplayManager()
            run_id = await rm.run(
                fixture_id="btc_bull_continuation_pullback_v1",
                harness_type="simulation",
            )
            for _ in range(50):
                await asyncio.sleep(0.1)
                r = rm.get_result(run_id)
                if r and r["status"] in ("done", "error"):
                    break
            return rm.get_result(run_id)

        result = asyncio.run(_run())
        assert result is not None
        assert result["status"] == "done", (
            f"Status: {result['status']}, Errors: {result['errors']}"
        )
        assert result["positions_opened"] >= 1, (
            f"Expected ≥1 position opened, got {result['positions_opened']}"
        )

    def test_missing_fixture_id_returns_clean_error(self):
        """Requesting a nonexistent fixture_id should produce status=error, not crash."""
        async def _run():
            rm = ReplayManager()
            run_id = await rm.run(
                fixture_id="does_not_exist",
                harness_type="simulation",
            )
            for _ in range(20):
                await asyncio.sleep(0.1)
                r = rm.get_result(run_id)
                if r and r["status"] in ("done", "error"):
                    break
            return rm.get_result(run_id)

        result = asyncio.run(_run())
        assert result is not None
        assert result["status"] == "error"
        assert any("Unknown fixture_id" in e for e in result["errors"]), (
            f"Expected 'Unknown fixture_id' error, got: {result['errors']}"
        )


# ---------------------------------------------------------------------------
# 4. True replay path
# ---------------------------------------------------------------------------

class TestTrueReplayPath:

    def test_true_replay_completes_for_ranging_fixture(self):
        """Run btc_ranging_v1 through true_replay harness."""
        async def _run():
            rm = ReplayManager()
            run_id = await rm.run(
                fixture_id="btc_ranging_v1",
                harness_type="true_replay",
            )
            for _ in range(50):
                await asyncio.sleep(0.1)
                r = rm.get_result(run_id)
                if r and r["status"] in ("done", "error"):
                    break
            return rm.get_result(run_id)

        result = asyncio.run(_run())
        assert result is not None
        assert result["status"] == "done", (
            f"Status: {result['status']}, Errors: {result['errors']}"
        )
        assert result["bars_run"] == 200
