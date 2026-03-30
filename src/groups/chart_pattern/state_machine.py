"""
Pattern State Machine for chart pattern detection.

All chart patterns follow the same lifecycle:
  INACTIVE → FORMING → CANDIDATE → BREAKOUT_PENDING → CONFIRMED

Key rules (from Phase 1 research — non-negotiable):
  1. NEVER emit a signal before CONFIRMED state.
  2. Breakout bar must be confirmed at bar CLOSE (no intra-bar signals).
  3. Conservative target = 50% of measured move (hard-coded in ChartPatternSignal.__post_init__).
  4. Volume at breakout is checked but NOT a veto (tracked in signal metadata).
  5. Neckline break = breakout confirmation for H&S patterns.

Architecture (plugin system):
  PatternState and PatternStateMachine are defined here and are the canonical
  base types.  Concrete detectors live in patterns/ and inherit from
  BasePatternDetector (which extends PatternStateMachine).

  This module re-exports all concrete classes from patterns/ so that existing
  code importing from state_machine continues to work without modification:

      from groups.chart_pattern.state_machine import DoubleBottomMachine  # still works

Source: /docs/architecture/master_decision_flow.md (Stage 3, Group 5)
        /research/extracted_rules/candidate_rule_families.md (Breakout Confirmation)
        /research/source_notes/source_04_chart_patterns_audit.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class PatternState(str, Enum):
    INACTIVE          = "INACTIVE"
    FORMING           = "FORMING"
    CANDIDATE         = "CANDIDATE"
    BREAKOUT_PENDING  = "BREAKOUT_PENDING"
    CONFIRMED         = "CONFIRMED"
    FAILED            = "FAILED"
    EXPIRED           = "EXPIRED"


@dataclass
class PatternStateMachine:
    """
    Tracks the state of a single chart pattern attempt for one symbol.

    Subclasses implement:
    -   advance(features) → PatternState: transitions state based on new bar.
    -   to_signal() → ChartPatternSignal: called ONLY when state == CONFIRMED.
    """
    pattern_type:     str
    symbol:           str
    timeframe:        str
    state:            PatternState = PatternState.INACTIVE
    started_at:       Optional[datetime] = None
    bars_in_formation: int = 0
    max_bars:         int = 60          # Expire pattern if not confirmed within max_bars
    measured_move:    Decimal = Decimal("0")
    breakout_level:   Decimal = Decimal("0")
    neckline_price:   Optional[Decimal] = None
    key_prices:       list = field(default_factory=list)  # Swing highs/lows
    metadata:         dict = field(default_factory=dict)

    def advance(self, features: object) -> PatternState:
        """
        Advance state machine by one bar.
        Implementations must call _check_expiry() first.
        Returns new state.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.advance() not implemented")

    def _check_expiry(self) -> bool:
        """Return True if pattern has exceeded max_bars and should be marked EXPIRED."""
        if self.state not in (PatternState.INACTIVE, PatternState.CONFIRMED,
                              PatternState.FAILED, PatternState.EXPIRED):
            if self.bars_in_formation >= self.max_bars:
                self.state = PatternState.EXPIRED
                return True
        return False

    def reset(self) -> None:
        """Return to INACTIVE for next attempt."""
        self.state = PatternState.INACTIVE
        self.started_at = None
        self.bars_in_formation = 0
        self.measured_move = Decimal("0")
        self.breakout_level = Decimal("0")
        self.neckline_price = None
        self.key_prices = []
        self.metadata = {}

    @property
    def is_terminal(self) -> bool:
        """True if pattern is in a terminal state (no further advancement)."""
        return self.state in (
            PatternState.CONFIRMED,
            PatternState.FAILED,
            PatternState.EXPIRED,
        )


# ---------------------------------------------------------------------------
# Backward-compatibility re-exports
#
# The canonical implementations have moved to patterns/.  These imports keep
# all existing code that does:
#     from groups.chart_pattern.state_machine import DoubleBottomMachine
# working without any changes.
#
# Python handles the apparent circular import safely: by the time these
# bottom-of-file imports run, PatternState and PatternStateMachine are already
# defined in this module, so the patterns/ modules can import them normally.
# ---------------------------------------------------------------------------
from groups.chart_pattern.patterns.double_bottom import DoubleBottomMachine          # noqa: E402,F401
from groups.chart_pattern.patterns.head_and_shoulders import HeadAndShouldersMachine  # noqa: E402,F401
from groups.chart_pattern.patterns.descending_triangle import DescendingTriangleMachine  # noqa: E402,F401
from groups.chart_pattern.patterns.triple_bottom import TripleBottomMachine          # noqa: E402,F401
# Phase 4 new patterns
from groups.chart_pattern.patterns.diamond_top import DiamondTopMachine              # noqa: E402,F401
from groups.chart_pattern.patterns.diamond_bottom import DiamondBottomMachine        # noqa: E402,F401
from groups.chart_pattern.patterns.ascending_channel import AscendingChannelMachine  # noqa: E402,F401
from groups.chart_pattern.patterns.descending_channel import DescendingChannelMachine  # noqa: E402,F401
from groups.chart_pattern.patterns.rounding_bottom import RoundingBottomMachine      # noqa: E402,F401
from groups.chart_pattern.patterns.bump_and_run import BumpAndRunMachine             # noqa: E402,F401
from groups.chart_pattern.patterns.broadening_top import BroadeningTopMachine        # noqa: E402,F401
from groups.chart_pattern.patterns.triple_top import TripleTopMachine                # noqa: E402,F401

__all__ = [
    "PatternState",
    "PatternStateMachine",
    "DoubleBottomMachine",
    "HeadAndShouldersMachine",
    "DescendingTriangleMachine",
    "TripleBottomMachine",
    # Phase 4 new patterns
    "DiamondTopMachine",
    "DiamondBottomMachine",
    "AscendingChannelMachine",
    "DescendingChannelMachine",
    "RoundingBottomMachine",
    "BumpAndRunMachine",
    "BroadeningTopMachine",
    "TripleTopMachine",
]
