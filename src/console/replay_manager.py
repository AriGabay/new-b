"""
ReplayManager: launches replay runs through the real runtime pipeline.

Wraps TrueReplayHarness and RuntimeReplayHarness.
Replay runs execute in background asyncio tasks.
Results are stored in memory indexed by run_id.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

AVAILABLE_FIXTURES = [
    {
        "id": "btc_bear_continuation",
        "label": "BTC Bear Continuation (Phase 5.75 fixture)",
        "description": "8-bar fixture with EMA crossover transition bars. "
                       "Used in Phase 5.75 viability audit. "
                       "Expected: 0 natural entries (weak crossover-only setups).",
    },
    {
        "id": "ideal_short_synthetic",
        "label": "Ideal SHORT Synthetic (Phase 5.9 panel viability proof)",
        "description": "Full_bear EMA alignment, evening_star pattern, R:R=3.5. "
                       "Expected: 16/20 approve, avg=7.78 → ENTER. "
                       "Source: event_driven_runtime_simulation.",
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

    async def run(self, fixture_id: str, harness_type: str = "true_replay") -> str:
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
            if harness_type == "true_replay":
                await self._run_true_replay(run_id, fixture_id)
            elif harness_type == "simulation":
                await self._run_simulation_replay(run_id, fixture_id)
            else:
                result.errors.append(f"Unknown harness_type: {harness_type}")
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
        result = self._runs[run_id]
        try:
            from validation.true_replay_harness import TrueReplayHarness
            from validation.fixtures.btc_replay_fixture import get_btc_bear_continuation_fixture
        except ImportError as e:
            result.errors.append(f"Import error: {e}")
            result.status = "error"
            return

        harness = TrueReplayHarness()
        try:
            await harness.setup()
            fixture = get_btc_bear_continuation_fixture()
            report = await harness.run_fixture(fixture)

            result.bars_run = getattr(report, "bars_run", 0)
            result.proposals_generated = getattr(report, "proposals_generated", 0)
            result.panel_approvals = getattr(report, "panel_approvals", 0)
            result.positions_opened = getattr(report, "positions_opened", 0)
            result.positions_closed = getattr(report, "positions_closed", 0)
            result.errors.extend(getattr(report, "errors", []))
            result.summary = (
                f"bars={result.bars_run} proposals={result.proposals_generated} "
                f"approvals={result.panel_approvals} opens={result.positions_opened}"
            )

            # Serialize the report
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
        result = self._runs[run_id]
        try:
            from validation.replay_harness import RuntimeReplayHarness
        except ImportError as e:
            result.errors.append(f"Import error: {e}")
            result.status = "error"
            return

        harness = RuntimeReplayHarness()
        try:
            await harness.setup()
            summary = await harness.run_sequence(n_bars=8, symbol="BTCUSDT")

            result.bars_run = getattr(summary, "bars_run", 0)
            result.positions_opened = getattr(summary, "positions_opened", 0)
            result.errors.extend([str(e) for e in getattr(summary, "errors", [])])
            result.summary = (
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
