"""
Descending Triangle detector (H1-004).

H1-004: Descending Triangle (bearish). 4% failure rate (Bulkowski equities).

State transitions:
  INACTIVE → FORMING:          Horizontal support + declining resistance identified.
  FORMING → CANDIDATE:         3+ touches of support, 2+ touches of declining resistance.
  CANDIDATE → BREAKOUT_PENDING: Price approaches support for confirmation bar.
  BREAKOUT_PENDING → CONFIRMED: Close below support level.

Rule: must not emit signal on break above resistance (failed pattern — mark FAILED).

Source: /research/hypotheses/hypothesis_registry.md (H1-004)
        /research/source_notes/source_04_chart_patterns_audit.md
"""
from __future__ import annotations

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class DescendingTriangleMachine(BasePatternDetector):
    """
    H1-004: Descending Triangle (bearish).
    4% failure rate with confirmed downside breakout (Bulkowski).
    """

    name = "descending_triangle"
    hypothesis_refs = ["H1-004"]
    direction_bias = "short"
    min_bars_needed = 15

    def advance(self, features) -> PatternState:
        if self._check_expiry():
            return self.state
        self.bars_in_formation += 1
        raise NotImplementedError(
            "DescendingTriangleMachine.advance() — Phase 2 implementation pending"
        )
