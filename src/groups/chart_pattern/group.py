"""
Chart Pattern Group (Group 5 — always_on=False, implementation_priority=2).

Responsibilities:
  - Maintain per-symbol pattern state machines for H1-001 through H1-005.
  - Advance state machines on each BarCloseEvent.
  - Emit ChartPatternSignal ONLY when state reaches CONFIRMED.
  - Enforce: conservative target = 50% of measured move (ChartPatternSignal invariant).
  - Block rejected patterns: RJ-007 (failed breakout retry), RJ-008 (tight stop),
    RJ-009 (ranging market).

LLM: NOT permitted.
Trigger: FeatureReadyEvent.
Depends on: MARKET_DATA.
Always-on: NO.

Phase 2 deliverable:
  State machines for H1-001 through H1-005 (5 critical patterns).

Blocked patterns:
  RJ-007: Do not retry a pattern that already failed on first breakout attempt.
  RJ-008: Do not trade H&S with stop < 0.5× ATR14 (too tight, stop hunt risk).
  RJ-009: No patterns in ranging market (adx14 < 20, unless H1-003/H1-005 near S/R).

Source: /docs/agent_registry/group_registry.md (CHART_PATTERN entry)
        /research/hypotheses/hypothesis_registry.md (H1-001 through H1-005)
        /research/source_notes/source_04_chart_patterns_audit.md
"""
from __future__ import annotations

import logging
from typing import Optional

from agents.base.group import BaseGroup
from core.events import EventBus, FeatureReadyEvent, GroupSignalEvent, SystemEvent
from core.registry import GroupID
from core.schemas import ChartPatternSignal, FeatureVector, GroupSignalBundle
from core.state import SystemState
from .state_machine import (
    DescendingTriangleMachine,
    DoubleBottomMachine,
    HeadAndShouldersMachine,
    PatternState,
    PatternStateMachine,
    TripleBottomMachine,
)

logger = logging.getLogger(__name__)


class ChartPatternGroup(BaseGroup):
    """
    Chart pattern detector using per-symbol state machines.

    Cross-bar state (per symbol):
    -   One PatternStateMachine per pattern type per symbol.
    -   State machines persist across bars until CONFIRMED, FAILED, or EXPIRED.
    -   On CONFIRMED: emit ChartPatternSignal, then reset machine.
    -   On FAILED/EXPIRED: reset machine.
    -   RJ-007 enforcement: track last_failed_breakout[symbol][pattern] → datetime.
      Do not restart machine for same pattern within 5 bars of failure.
    """

    group_id = GroupID.CHART_PATTERN

    # Hypothesis → state machine class mapping
    PATTERN_MACHINES = {
        "H1-001": HeadAndShouldersMachine,   # H&S Top
        "H1-002": HeadAndShouldersMachine,   # Inverse H&S (direction flag differs)
        "H1-003": DoubleBottomMachine,
        "H1-004": DescendingTriangleMachine,
        "H1-005": TripleBottomMachine,
    }

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)
        # symbol → {hypothesis_id: PatternStateMachine}
        self._machines: dict[str, dict[str, PatternStateMachine]] = {}
        # symbol → {hypothesis_id: bars_since_failure} (RJ-007)
        self._failure_cooldown: dict[str, dict[str, int]] = {}

    async def _setup(self) -> None:
        await self.bus.subscribe(FeatureReadyEvent, self.handle_event)
        logger.info("ChartPatternGroup subscribed to FeatureReadyEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, FeatureReadyEvent) and event.features:
            await self._process_features(event.features)

    async def _process_features(self, features: FeatureVector) -> None:
        """
        Per-bar pipeline:
        1. Initialize machines for new symbols.
        2. Advance all active machines.
        3. Collect CONFIRMED signals, skip FAILED/EXPIRED.
        4. Apply regime filter (RJ-009: adx14 < 20 blocks most patterns).
        5. Apply cooldown filter (RJ-007: failed breakout retry block).
        6. Publish GroupSignalEvent.
        """
        raise NotImplementedError("ChartPatternGroup._process_features() — Phase 2 implementation pending")

    def _initialize_machines_for_symbol(self, symbol: str, timeframe: str) -> None:
        """Create PatternStateMachine instances for all active hypotheses for symbol."""
        if symbol not in self._machines:
            self._machines[symbol] = {}
            for hyp_id, MachineClass in self.PATTERN_MACHINES.items():
                self._machines[symbol][hyp_id] = MachineClass(
                    pattern_type=hyp_id,
                    symbol=symbol,
                    timeframe=timeframe,
                )

    def _is_in_failure_cooldown(self, symbol: str, hyp_id: str) -> bool:
        """RJ-007: Returns True if this pattern failed within last 5 bars."""
        cooldown = self._failure_cooldown.get(symbol, {}).get(hyp_id, 0)
        return cooldown > 0

    def _signal_from_machine(
        self,
        machine: PatternStateMachine,
    ) -> Optional[ChartPatternSignal]:
        """
        Build ChartPatternSignal from a CONFIRMED machine.
        ChartPatternSignal.__post_init__ enforces conservative_target = 50% measured_move.
        """
        raise NotImplementedError("Phase 2 pending")
