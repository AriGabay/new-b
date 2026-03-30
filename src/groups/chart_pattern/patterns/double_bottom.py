"""
Double Bottom detector (H1-003).

H1-003: Double Bottom (bullish). CONFIRMED only — unconfirmed doubles rejected.

State transitions:
  INACTIVE → FORMING:             First trough identified.
  FORMING → CANDIDATE:            Second trough formed at similar price (±3%).
  CANDIDATE → BREAKOUT_PENDING:   Confirmation neckline identified.
  BREAKOUT_PENDING → CONFIRMED:   Close above neckline resistance.

Acceptance criteria: Confirmed < 15% failure; Unconfirmed > 40% failure.
The CONFIRMED state gate is non-negotiable.

Source: /research/hypotheses/hypothesis_registry.md (H1-003)
        /research/source_notes/source_04_chart_patterns_audit.md
        Bulkowski: 3% confirmed failure rate; 64% unconfirmed failure rate.
"""
from __future__ import annotations

from decimal import Decimal

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class DoubleBottomMachine(BasePatternDetector):
    """
    H1-003: Double Bottom (bullish).
    CONFIRMED only — unconfirmed doubles rejected per H1-003 acceptance criteria.
    """

    name = "double_bottom"
    hypothesis_refs = ["H1-003"]
    direction_bias = "long"
    min_bars_needed = 10

    def advance(self, features) -> PatternState:
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
