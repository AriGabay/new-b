"""
ReplayManager: launches replay runs through the real runtime pipeline.

Wraps TrueReplayHarness and RuntimeReplayHarness.
Replay runs execute in background asyncio tasks.
Results are stored in memory indexed by run_id.

Fixture resolution:
  Each AVAILABLE_FIXTURES entry maps a fixture_id to a builder function
  that returns a ReplayFixture with .feature_vectors and .name.

  Builder functions are imported lazily to avoid circular imports.

Harness types:
  "simulation"  — RuntimeReplayHarness (source: event_driven_runtime_simulation)
                   Feeds fixture.feature_vectors into run_sequence(fv_sequence, label).
  "true_replay" — TrueReplayHarness (source: event_driven_runtime_replay)
                   Feeds fixture into run_fixture(fixture).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixture registry — maps fixture_id to (builder_function_path, label, description)
#
# Builder functions are resolved lazily via _resolve_fixture_builder().
# Every id here must correspond to a real function in the fixtures package.
# ---------------------------------------------------------------------------

def _builder_bull_breakout():
    from validation.fixtures.btc_replay_fixture import get_bull_breakout_fixture
    return get_bull_breakout_fixture()

def _builder_bear_breakdown():
    from validation.fixtures.btc_replay_fixture import get_bear_breakdown_fixture
    return get_bear_breakdown_fixture()

def _builder_ranging():
    from validation.fixtures.btc_replay_fixture import get_ranging_fixture
    return get_ranging_fixture()

def _builder_bull_continuation_pullback():
    from validation.fixtures.btc_established_trend_fixture import get_bull_continuation_pullback_fixture
    return get_bull_continuation_pullback_fixture()

def _builder_bear_continuation_pullback():
    from validation.fixtures.btc_established_trend_fixture import get_bear_continuation_pullback_fixture
    return get_bear_continuation_pullback_fixture()

def _builder_long_established_trend():
    from validation.fixtures.btc_established_trend_fixture import get_long_established_trend_fixture
    return get_long_established_trend_fixture()

def _builder_w_bottom_long_v1():
    from validation.fixtures.btc_structure_fixture import get_w_bottom_long_fixture
    return get_w_bottom_long_fixture()

def _builder_m_top_short_v1():
    from validation.fixtures.btc_structure_fixture import get_m_top_short_fixture
    return get_m_top_short_fixture()

def _builder_triple_touch_long_v1():
    from validation.fixtures.btc_structure_fixture import get_triple_touch_long_fixture
    return get_triple_touch_long_fixture()

def _builder_w_bottom_long_v2():
    from validation.fixtures.btc_structure_fixture import get_w_bottom_long_v2_fixture
    return get_w_bottom_long_v2_fixture()

def _builder_double_bottom_long_v1():
    from validation.fixtures.btc_structure_fixture import get_double_bottom_long_v1_fixture
    return get_double_bottom_long_v1_fixture()


_FIXTURE_BUILDERS: dict[str, Callable] = {
    "btc_bull_breakout_v1":              _builder_bull_breakout,
    "btc_bear_breakdown_v1":             _builder_bear_breakdown,
    "btc_ranging_v1":                    _builder_ranging,
    "btc_bull_continuation_pullback_v1": _builder_bull_continuation_pullback,
    "btc_bear_continuation_pullback_v1": _builder_bear_continuation_pullback,
    "btc_long_established_trend_v1":     _builder_long_established_trend,
    "btc_w_bottom_long_v1":              _builder_w_bottom_long_v1,
    "btc_m_top_short_v1":                _builder_m_top_short_v1,
    "btc_triple_touch_long_v1":          _builder_triple_touch_long_v1,
    "btc_w_bottom_long_v2":              _builder_w_bottom_long_v2,
    "btc_double_bottom_long_v1":         _builder_double_bottom_long_v1,
}


AVAILABLE_FIXTURES = [
    {
        "id": "btc_bull_breakout_v1",
        "label": "BTC Bull Breakout (350 bars / ~14.5 days)",
        "description": "Crossover-transition bars. Expected: 0 natural entries (weak setups).",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_bear_breakdown_v1",
        "label": "BTC Bear Breakdown (350 bars / ~14.5 days)",
        "description": "Bear crossover bars. Expected: 0 natural entries.",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_ranging_v1",
        "label": "BTC Ranging (200 bars / ~8.3 days)",
        "description": "Sideways bars. Expected: 0 natural entries.",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_bull_continuation_pullback_v1",
        "label": "BTC Bull Continuation Pullback (320 bars / ~13.3 days)",
        "description": "Established uptrend with pullback. Expected: 2 natural entries (14/20 approval).",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_bear_continuation_pullback_v1",
        "label": "BTC Bear Continuation Pullback (330 bars / ~13.8 days)",
        "description": "Established downtrend with pullback. Expected: 0 natural entries.",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_long_established_trend_v1",
        "label": "BTC Long Established Trend (300 bars / 12.5 days)",
        "description": "Mature uptrend. Expected: 0 natural entries (near-miss 13/20).",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_w_bottom_long_v1",
        "label": "BTC W-Bottom Long V1 (257 bars / ~10.7 days)",
        "description": "W-bottom structure. Expected: 0 natural entries (13/20 hold).",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_m_top_short_v1",
        "label": "BTC M-Top Short V1 (267 bars / ~11.1 days)",
        "description": "M-top structure. Expected: 0 natural entries (13/20 hold).",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_triple_touch_long_v1",
        "label": "BTC Triple Touch Long V1 (261 bars / ~10.9 days)",
        "description": "Triple-touch support structure. Expected: 0 natural entries (13/20 hold).",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_w_bottom_long_v2",
        "label": "BTC W-Bottom Long V2 (260 bars / ~10.8 days)",
        "description": "Enhanced W-bottom with volume confirmation. Expected: 1 natural entry (14/20 threshold ENTER).",
        "harness_types": ["simulation", "true_replay"],
    },
    {
        "id": "btc_double_bottom_long_v1",
        "label": "BTC Double Bottom Long (260 bars / ~10.8 days)",
        "description": "Double bottom with chart pattern confirmation. Expected: 1 natural entry (16/20 strong ENTER).",
        "harness_types": ["simulation", "true_replay"],
    },
]


@dataclass
class ReplayRunResult:
    run_id: str
    fixture_id: str
    harness_type: str    # "true_replay" | "simulation"
    status: str          # "pending" | "running" | "done" | "error"
    started_at: str
    finished_at: Optional[str]
    bars_run: int
    proposals_generated: int
    panel_approvals: int
    positions_opened: int
    positions_closed: int
    errors: list[str]
    summary: str
    raw_report: Optional[dict]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "fixture_id": self.fixture_id,
            "harness_type": self.harness_type,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "bars_run": self.bars_run,
            "proposals_generated": self.proposals_generated,
            "panel_approvals": self.panel_approvals,
            "positions_opened": self.positions_opened,
            "positions_closed": self.positions_closed,
            "errors": self.errors,
            "summary": self.summary,
            "raw_report": self.raw_report,
        }


class ReplayManager:
    """Manages replay runs."""

    def __init__(self) -> None:
        self._runs: dict[str, ReplayRunResult] = {}

    def list_fixtures(self) -> list[dict]:
        return AVAILABLE_FIXTURES

    def _resolve_fixture(self, fixture_id: str):
        """
        Resolve fixture_id to a built ReplayFixture.
        Returns (fixture, None) on success or (None, error_string) on failure.
        """
        builder = _FIXTURE_BUILDERS.get(fixture_id)
        if builder is None:
            valid = ", ".join(sorted(_FIXTURE_BUILDERS.keys()))
            return None, f"Unknown fixture_id '{fixture_id}'. Valid IDs: {valid}"
        try:
            fixture = builder()
            return fixture, None
        except Exception as exc:
            return None, f"Fixture builder for '{fixture_id}' failed: {exc}"

    async def run(self, fixture_id: str, harness_type: str = "simulation") -> str:
        run_id = str(uuid.uuid4())[:8]
        result = ReplayRunResult(
            run_id=run_id,
            fixture_id=fixture_id,
            harness_type=harness_type,
            status="pending",
            started_at=datetime.utcnow().isoformat() + "Z",
            finished_at=None,
            bars_run=0,
            proposals_generated=0,
            panel_approvals=0,
            positions_opened=0,
            positions_closed=0,
            errors=[],
            summary="",
            raw_report=None,
        )
        self._runs[run_id] = result
        asyncio.create_task(self._run_task(run_id, fixture_id, harness_type))
        return run_id

    async def _run_task(self, run_id: str, fixture_id: str, harness_type: str) -> None:
        result = self._runs[run_id]
        result.status = "running"

        try:
            if harness_type == "simulation":
                await self._run_simulation_replay(run_id, fixture_id)
            elif harness_type == "true_replay":
                await self._run_true_replay(run_id, fixture_id)
            else:
                result.errors.append(f"Unknown harness_type: '{harness_type}'. Use 'simulation' or 'true_replay'.")
                result.status = "error"
        except Exception as e:
            logger.exception("ReplayManager [%s]: error", run_id)
            result.errors.append(str(e))
            result.status = "error"
        finally:
            if result.status == "running":
                result.status = "done"
            result.finished_at = datetime.utcnow().isoformat() + "Z"

    async def _run_true_replay(self, run_id: str, fixture_id: str) -> None:
        """Run a fixture through TrueReplayHarness (event_driven_runtime_replay)."""
        result = self._runs[run_id]

        # Resolve fixture
        fixture, err = self._resolve_fixture(fixture_id)
        if err:
            result.errors.append(err)
            result.status = "error"
            return

        try:
            from validation.true_replay_harness import TrueReplayHarness
        except ImportError as e:
            result.errors.append(f"Import error: {e}")
            result.status = "error"
            return

        harness = TrueReplayHarness()
        try:
            await harness.setup()
            report = await harness.run_fixture(fixture)

            result.bars_run = getattr(report, "bars_processed", 0)
            result.positions_opened = getattr(report, "positions_opened", 0)
            result.positions_closed = getattr(report, "positions_closed", 0)
            result.errors.extend(getattr(report, "errors", []))
            result.summary = (
                f"true_replay: {fixture.name} — "
                f"bars={result.bars_run} opens={result.positions_opened} "
                f"closes={result.positions_closed}"
            )

            try:
                result.raw_report = {
                    k: str(v) for k, v in vars(report).items()
                    if not k.startswith("_")
                }
            except Exception:
                pass

            result.status = "done"
        except Exception as e:
            result.errors.append(str(e))
            result.status = "error"
        finally:
            try:
                await harness.teardown()
            except Exception:
                pass

    async def _run_simulation_replay(self, run_id: str, fixture_id: str) -> None:
        """Run a fixture through RuntimeReplayHarness (event_driven_runtime_simulation)."""
        result = self._runs[run_id]

        # Resolve fixture
        fixture, err = self._resolve_fixture(fixture_id)
        if err:
            result.errors.append(err)
            result.status = "error"
            return

        try:
            from validation.replay_harness import RuntimeReplayHarness
        except ImportError as e:
            result.errors.append(f"Import error: {e}")
            result.status = "error"
            return

        harness = RuntimeReplayHarness()
        try:
            await harness.setup()
            summary = await harness.run_sequence(
                fv_sequence=fixture.feature_vectors,
                label=fixture.name,
            )

            result.bars_run = getattr(summary, "bars_run", 0)
            result.positions_opened = getattr(summary, "positions_opened", 0)
            result.errors.extend([str(e) for e in getattr(summary, "errors", [])])
            result.summary = (
                f"simulation: {fixture.name} — "
                f"bars={result.bars_run} opens={result.positions_opened}"
            )
            result.status = "done"
        except Exception as e:
            result.errors.append(str(e))
            result.status = "error"
        finally:
            try:
                await harness.teardown()
            except Exception:
                pass

    def get_result(self, run_id: str) -> Optional[dict]:
        r = self._runs.get(run_id)
        return r.to_dict() if r else None

    def list_results(self) -> list[dict]:
        return [r.to_dict() for r in self._runs.values()]


# Global instance
_replay_manager: Optional[ReplayManager] = None


def get_replay_manager() -> ReplayManager:
    global _replay_manager
    if _replay_manager is None:
        _replay_manager = ReplayManager()
    return _replay_manager
