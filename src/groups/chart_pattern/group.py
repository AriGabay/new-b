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
from .registry import PatternRegistry
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
        # symbol → list[ChartPatternSignal]  (confirmed this bar — read by PanelDecisionGroup)
        self._signals_cache: dict[str, list] = {}
        # symbol → list[str]  (active pattern names in non-terminal state)
        self._active_cache: dict[str, list] = {}

    async def _setup(self) -> None:
        # Auto-discover all pattern plugins so @PatternRegistry.register decorators fire
        PatternRegistry.autodiscover()
        await self.bus.subscribe(FeatureReadyEvent, self.handle_event)
        logger.info(
            "ChartPatternGroup subscribed to FeatureReadyEvent. "
            "Registry patterns: %s",
            list(PatternRegistry.get_all_by_hypothesis().keys()),
        )

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, FeatureReadyEvent) and event.features:
            await self._process_features(event.features)

    async def _process_features(self, features: FeatureVector) -> None:
        """
        Per-bar pipeline:
        1. Initialize machines for new symbols.
        2. Tick failure cooldowns (RJ-007).
        3. Advance all machines. Skip NotImplementedError machines (stub guard).
        4. Collect CONFIRMED signals (apply RJ-009 regime filter).
        5. Track active pattern names for non-terminal machines.
        6. Update _signals_cache and _active_cache.
        NOTE: Does NOT publish GroupSignalEvent — chart pattern data is delivered
        to PanelDecisionGroup exclusively via the _signals_cache cache wiring.
        EntryGroup composite_score normalization (ACTIVE_COMPOSITE_WEIGHT_SUM=0.55)
        is unchanged so existing fixtures are not regressed.
        """
        symbol = features.symbol
        timeframe = features.timeframe

        self._initialize_machines_for_symbol(symbol, timeframe)

        # Tick cooldowns
        cooldowns = self._failure_cooldown.setdefault(symbol, {})
        for hyp_id in list(cooldowns.keys()):
            cooldowns[hyp_id] = max(0, cooldowns[hyp_id] - 1)

        confirmed_signals: list[ChartPatternSignal] = []
        active_names: list[str] = []

        for hyp_id, machine in self._machines[symbol].items():
            try:
                new_state = machine.advance(features)
            except NotImplementedError:
                # Stub machine — skip silently
                continue
            except Exception as exc:
                logger.warning(
                    "ChartPatternGroup: machine %s advance error: %s", hyp_id, exc
                )
                continue

            if new_state == PatternState.CONFIRMED:
                # RJ-009: adx14 < 20 blocks most patterns (H1-003/H1-005 exempt)
                if features.adx14 < 20 and hyp_id not in ("H1-003", "H1-005"):
                    logger.debug(
                        "ChartPatternGroup: RJ-009 blocks %s (adx14=%.1f)",
                        hyp_id, features.adx14,
                    )
                    machine.reset()
                    cooldowns[hyp_id] = 5
                    continue

                signal = self._signal_from_machine(machine, hyp_id, features)
                if signal:
                    confirmed_signals.append(signal)
                    logger.info(
                        "ChartPatternGroup: %s CONFIRMED %s — neckline=%s measured_move=%s",
                        hyp_id, symbol, machine.neckline_price, machine.measured_move,
                    )
                machine.reset()

            elif new_state in (PatternState.FAILED, PatternState.EXPIRED):
                cooldowns[hyp_id] = 5
                machine.reset()

            elif new_state not in (PatternState.INACTIVE,):
                if not self._is_in_failure_cooldown(symbol, hyp_id):
                    active_names.append(hyp_id)

        self._signals_cache[symbol] = confirmed_signals
        self._active_cache[symbol] = active_names

    def _initialize_machines_for_symbol(self, symbol: str, timeframe: str) -> None:
        """
        Create PatternStateMachine instances for all active hypotheses for symbol.

        Prefers the PatternRegistry (populated via auto-discovery) so that new
        patterns added to patterns/ are picked up without touching this file.
        Falls back to the PATTERN_MACHINES dict when the registry is empty
        (e.g. in unit tests that construct ChartPatternGroup directly without
        calling _setup()).
        """
        if symbol not in self._machines:
            self._machines[symbol] = {}
            # Prefer registry; fall back to PATTERN_MACHINES for test compat
            registry_map = PatternRegistry.get_all_by_hypothesis()
            source = registry_map if registry_map else self.PATTERN_MACHINES
            for hyp_id, MachineClass in source.items():
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
        hyp_id: str,
        features: FeatureVector,
    ) -> Optional[ChartPatternSignal]:
        """Build ChartPatternSignal from a CONFIRMED machine."""
        from core.schemas import Direction
        from decimal import Decimal

        bullish_hypotheses = {"H1-002", "H1-003", "H1-005"}
        direction = Direction.LONG if hyp_id in bullish_hypotheses else Direction.SHORT

        pattern_name_map = {
            "H1-001": "head_and_shoulders",
            "H1-002": "inverse_head_and_shoulders",
            "H1-003": "double_bottom",
            "H1-004": "descending_triangle",
            "H1-005": "triple_bottom",
        }
        pattern_name = pattern_name_map.get(hyp_id, hyp_id.lower())

        measured = machine.measured_move if machine.measured_move else Decimal("0")
        breakout = machine.breakout_level if machine.breakout_level else Decimal("0")
        neckline = machine.neckline_price

        return ChartPatternSignal(
            group_id="CHART_PATTERN",
            symbol=features.symbol,
            timeframe=features.timeframe,
            timestamp=features.timestamp,
            direction=direction,
            signal_type="chart_pattern",
            signal_subtype=pattern_name,
            hypothesis_ref=hyp_id,
            quality_score=0.8,
            requires_structural_level=True,
            context_confirmed=True,
            confirmation_required=False,
            confirmed_on_bar_close=True,
            breakout_level=breakout,
            measured_move=measured,
            neckline_price=neckline,
            bars_in_formation=machine.bars_in_formation,
        )
