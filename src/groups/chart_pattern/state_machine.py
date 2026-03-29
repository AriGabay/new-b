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
# Concrete pattern state machines (stubs for Phase 2 implementation)
# ---------------------------------------------------------------------------

class HeadAndShouldersMachine(PatternStateMachine):
    """
    H1-001: Head & Shoulders Top (bearish).
    H1-002: Inverse H&S Bottom (bullish) — same logic, mirrored.

    State transitions:
    INACTIVE → FORMING:          First swing high (or low for IHS) identified.
    FORMING → CANDIDATE:         Head formed (higher high), left shoulder defined.
    CANDIDATE → BREAKOUT_PENDING: Right shoulder formed. Neckline drawn.
    BREAKOUT_PENDING → CONFIRMED: Close below neckline (H&S) or above (IHS).

    Breakout level = neckline price.
    Measured move = distance from head to neckline.
    Conservative target = 50% of measured move.
    """

    def advance(self, features: object) -> PatternState:
        if self._check_expiry():
            return self.state
        self.bars_in_formation += 1
        raise NotImplementedError("HeadAndShouldersMachine.advance() — Phase 2 implementation pending")


class DoubleBottomMachine(PatternStateMachine):
    """
    H1-003: Double Bottom (bullish). CONFIRMED only — unconfirmed doubles rejected.

    State transitions:
    INACTIVE → FORMING:          First trough identified.
    FORMING → CANDIDATE:         Second trough formed at similar price (±3%).
    CANDIDATE → BREAKOUT_PENDING: Confirmation neckline identified.
    BREAKOUT_PENDING → CONFIRMED: Close above neckline resistance.

    Acceptance: Confirmed < 15% failure; Unconfirmed > 40% failure.
    Phase 2 implementation MUST enforce the CONFIRMED state gate.
    """

    def advance(self, features: object) -> PatternState:
        if self._check_expiry():
            return self.state
        self.bars_in_formation += 1

        close = float(getattr(features, "close", 0))

        if self.state == PatternState.INACTIVE:
            # Track 20-bar window to detect first trough via 2.5% decline from peak
            window = self.metadata.get("_window", [])
            window.append(close)
            if len(window) > 20:
                window.pop(0)
            self.metadata["_window"] = window

            if len(window) >= 10:
                peak = max(window)
                if peak > 0 and close < peak * 0.975:
                    self.key_prices = [close]
                    self.metadata["first_trough"] = close
                    self.metadata["neckline_candidate"] = close
                    self.started_at = getattr(features, "timestamp", None)
                    self.bars_in_formation = 0
                    self.state = PatternState.FORMING

        elif self.state == PatternState.FORMING:
            first_trough = self.metadata.get("first_trough", 0.0)
            # Update neckline candidate (highest close between the two troughs)
            if close > self.metadata.get("neckline_candidate", 0.0):
                self.metadata["neckline_candidate"] = close
            # Second trough: price is at most 0.1% above first trough,
            # AND we have seen a recovery of > 0.3% above first trough (neckline set)
            has_recovery = (
                first_trough > 0
                and self.metadata["neckline_candidate"] > first_trough * 1.003
            )
            at_second_trough = first_trough > 0 and close <= first_trough * 1.001
            if has_recovery and at_second_trough:
                self.metadata["second_trough"] = close
                neckline = self.metadata["neckline_candidate"]
                self.neckline_price = Decimal(str(round(neckline, 2)))
                self.breakout_level = self.neckline_price
                first_trough_d = Decimal(str(round(first_trough, 2)))
                self.measured_move = self.neckline_price - first_trough_d
                self.key_prices.append(close)
                self.state = PatternState.BREAKOUT_PENDING

        elif self.state == PatternState.BREAKOUT_PENDING:
            # Confirmed: close strictly above neckline
            if self.neckline_price and Decimal(str(close)) > self.neckline_price:
                self.state = PatternState.CONFIRMED

        return self.state


class DescendingTriangleMachine(PatternStateMachine):
    """
    H1-004: Descending Triangle (bearish). 4% failure rate (Bulkowski).

    State transitions:
    INACTIVE → FORMING:         Horizontal support + declining resistance identified.
    FORMING → CANDIDATE:        3+ touches of support, 2+ touches of declining resistance.
    CANDIDATE → BREAKOUT_PENDING: Price approaches support for confirmation bar.
    BREAKOUT_PENDING → CONFIRMED: Close below support level.

    Must not emit signal on break above resistance (failed pattern — mark FAILED).
    """

    def advance(self, features: object) -> PatternState:
        if self._check_expiry():
            return self.state
        self.bars_in_formation += 1
        raise NotImplementedError("DescendingTriangleMachine.advance() — Phase 2 implementation pending")


class TripleBottomMachine(PatternStateMachine):
    """
    H1-005: Triple Bottom (bullish). 4% failure rate (Bulkowski).

    State transitions:
    INACTIVE → FORMING:         First trough.
    FORMING → CANDIDATE:        Second trough at similar level.
    CANDIDATE → BREAKOUT_PENDING: Third trough, neckline resistance clear.
    BREAKOUT_PENDING → CONFIRMED: Close above neckline.
    """

    def advance(self, features: object) -> PatternState:
        if self._check_expiry():
            return self.state
        self.bars_in_formation += 1
        raise NotImplementedError("TripleBottomMachine.advance() — Phase 2 implementation pending")
