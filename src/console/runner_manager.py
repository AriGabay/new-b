"""
RunnerManager: manages the lifecycle of BtcBybitPaperRunner.

Responsibilities:
- Start/stop the runner on demand
- Report runner status (mode, running, groups, error)
- Provide safe access to SystemState for the REST API
- Expose group health info
- Support simulation mode and (when Bybit connectivity available) live mode
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

ACTIVE_GROUPS = [
    "MarketDataGroup",
    "IndicatorsGroup",
    "CandlestickGroup",
    "TechnicalStructureGroup",
    "EntryGroup",
    "PanelDecisionGroup",
    "RiskLeverageGroup",
    "ExitGroup",
    "PerformanceJournalGroup",
]

EXCLUDED_GROUPS = [
    "ChartPatternGroup",
    "NewsMacroGroup",
    "HistorianAgent",
    "CriticAgent",
]


@dataclass
class GroupStatus:
    name: str
    status: str          # "active" | "excluded" | "error" | "unknown"
    last_event_ts: Optional[str]
    note: str


@dataclass
class RunnerStatus:
    running: bool
    mode: str            # "simulation" | "live" | "stopped"
    simulation_mode: bool
    started_at: Optional[str]
    bars_processed: int
    error: Optional[str]
    groups: list[dict]


class RunnerManager:
    """
    Manages one optional BtcBybitPaperRunner instance.

    This class is instantiated once at server startup and referenced
    by all API endpoints.
    """

    def __init__(self, journal_db_path: str = "src/data/journal.db") -> None:
        self._runner = None
        self._runner_task: Optional[asyncio.Task] = None
        self._simulation_mode = True
        self._running = False
        self._started_at: Optional[str] = None
        self._bars_processed = 0
        self._error: Optional[str] = None
        self._journal_db_path = journal_db_path

    async def start(self, simulation_mode: bool = True) -> dict:
        """Start the runner. Returns {ok, message}."""
        if self._running:
            return {"ok": False, "message": "Runner already running."}

        self._simulation_mode = simulation_mode
        self._error = None
        self._bars_processed = 0

        try:
            from runtime.runner import BtcBybitPaperRunner
            self._runner = BtcBybitPaperRunner(
                simulation_mode=simulation_mode,
                journal_db_path=self._journal_db_path,
            )
            await self._runner.setup()
            self._running = True
            self._started_at = datetime.utcnow().isoformat() + "Z"

            if not simulation_mode:
                # Start the polling loop in a background task
                self._runner_task = asyncio.create_task(
                    self._run_loop()
                )

            logger.info(
                "RunnerManager: runner started. simulation=%s", simulation_mode
            )
            return {"ok": True, "message": f"Runner started (simulation={simulation_mode})."}
        except Exception as e:
            self._error = str(e)
            self._running = False
            logger.error("RunnerManager: start failed: %s", e)
            return {"ok": False, "message": str(e)}

    async def _run_loop(self) -> None:
        """Background task for the live polling loop."""
        try:
            await self._runner.run_paper_loop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._error = str(e)
            logger.error("RunnerManager: run loop error: %s", e)
        finally:
            self._running = False

    async def stop(self) -> dict:
        """Stop the runner."""
        if not self._running and self._runner is None:
            return {"ok": False, "message": "Runner not running."}
        try:
            if self._runner_task and not self._runner_task.done():
                self._runner_task.cancel()
                try:
                    await self._runner_task
                except asyncio.CancelledError:
                    pass
            if self._runner:
                await self._runner.teardown()
            self._runner = None
            self._runner_task = None
            self._running = False
            logger.info("RunnerManager: runner stopped.")
            return {"ok": True, "message": "Runner stopped."}
        except Exception as e:
            logger.error("RunnerManager: stop failed: %s", e)
            return {"ok": False, "message": str(e)}

    async def simulate_bar(self, feature_vector_dict: dict) -> dict:
        """
        Inject a synthetic bar into the running simulation-mode runner.
        The dict should match FeatureVector fields.
        """
        if not self._running or self._runner is None:
            return {"ok": False, "message": "Runner not running."}
        if not self._simulation_mode:
            return {"ok": False, "message": "Runner is in live mode."}
        try:
            from core.schemas import FeatureVector
            fv = FeatureVector(**feature_vector_dict)
            await self._runner.simulate_bar(fv)
            self._bars_processed += 1
            return {"ok": True, "message": f"Bar injected. bars_processed={self._bars_processed}"}
        except Exception as e:
            logger.error("RunnerManager: simulate_bar failed: %s", e)
            return {"ok": False, "message": str(e)}

    def get_status(self) -> dict:
        """Return current runner status as a JSON-safe dict."""
        groups = []
        if self._runner is not None:
            for name in ACTIVE_GROUPS:
                groups.append({
                    "name": name,
                    "status": "active",
                    "note": "Wired and running.",
                })
            for name in EXCLUDED_GROUPS:
                groups.append({
                    "name": name,
                    "status": "excluded",
                    "note": "Not wired in Phase 3.",
                })
        else:
            for name in ACTIVE_GROUPS:
                groups.append({
                    "name": name,
                    "status": "unknown",
                    "note": "Runner not started.",
                })
            for name in EXCLUDED_GROUPS:
                groups.append({
                    "name": name,
                    "status": "excluded",
                    "note": "Not wired in Phase 3.",
                })

        return {
            "running": self._running,
            "mode": (
                "stopped" if not self._running
                else ("simulation" if self._simulation_mode else "live")
            ),
            "simulation_mode": self._simulation_mode,
            "started_at": self._started_at,
            "bars_processed": self._bars_processed,
            "error": self._error,
            "groups": groups,
            "active_group_names": ACTIVE_GROUPS,
            "excluded_group_names": EXCLUDED_GROUPS,
        }

    def get_system_state(self) -> dict:
        """Snapshot of SystemState for the overview panel."""
        if self._runner is None:
            return {"available": False, "reason": "Runner not started."}

        state = self._runner.state
        portfolio = state.portfolio
        regime = state.regime
        risk_state = state.risk_state

        positions = []
        for pid, pos in portfolio.open_positions.items():
            positions.append({
                "position_id": pid,
                "symbol": getattr(pos, "symbol", ""),
                "direction": str(getattr(pos, "direction", "")),
                "entry_price": float(getattr(pos, "entry_price", 0)),
                "stop_price": float(getattr(pos, "stop_price", 0)),
                "target_price": float(getattr(pos, "target_price", 0)),
                "position_size_usd": float(getattr(pos, "position_size_usd", 0)),
                "opened_at": str(getattr(pos, "opened_at", "")),
            })

        return {
            "available": True,
            "mode": state.mode.value if hasattr(state.mode, "value") else str(state.mode),
            "portfolio": {
                "equity": float(portfolio.equity),
                "available": float(portfolio.available),
                "open_positions_count": len(portfolio.open_positions),
                "daily_pnl": float(portfolio.daily_pnl),
                "daily_pnl_pct": portfolio.daily_pnl_pct,
                "drawdown_pct": portfolio.drawdown_pct,
                "consecutive_losses": portfolio.consecutive_losses,
                "total_trades": portfolio.total_trades,
                "high_water_mark": float(portfolio.high_water_mark),
            },
            "positions": positions,
            "regime": {
                "btc_macro": regime.btc_macro if regime else "unknown",
                "trending": regime.trending if regime else False,
                "volatility_regime": regime.volatility_regime if regime else "unknown",
                "adx14": float(regime.adx14) if regime and regime.adx14 else 0.0,
            },
            "risk": {
                "halted": risk_state.halted,
                "halt_reason": risk_state.halt_reason,
                "size_reduction": risk_state.size_reduction,
            },
            "eligible_symbols": list(state.eligible_symbols),
            "last_close": {
                k: float(v) for k, v in state.last_close_by_symbol.items()
            },
        }

    @property
    def runner(self):
        return self._runner

    @property
    def is_running(self) -> bool:
        return self._running


# Global manager instance
_manager: Optional[RunnerManager] = None


def get_runner_manager() -> RunnerManager:
    global _manager
    if _manager is None:
        _manager = RunnerManager()
    return _manager


def set_runner_manager(m: RunnerManager) -> None:
    global _manager
    _manager = m
