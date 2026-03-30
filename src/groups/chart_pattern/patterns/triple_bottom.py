"""
Triple Bottom detector (H1-005).

H1-005: Triple Bottom (bullish). 4% failure rate (Bulkowski equities).

State transitions:
  INACTIVE → FORMING:            First trough.
  FORMING → CANDIDATE:           Second trough at similar level.
  CANDIDATE → BREAKOUT_PENDING:  Third trough, neckline resistance clear.
  BREAKOUT_PENDING → CONFIRMED:  Close above neckline.

Source: /research/hypotheses/hypothesis_registry.md (H1-005)
        /research/source_notes/source_04_chart_patterns_audit.md
        Bulkowski: 4% failure rate, 38% average rise.
"""
from __future__ import annotations

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class TripleBottomMachine(BasePatternDetector):
    """
    H1-005: Triple Bottom (bullish).
    4% failure rate, 38% average rise (Bulkowski).
    """

    name = "triple_bottom"
    hypothesis_refs = ["H1-005"]
    direction_bias = "long"
    min_bars_needed = 20

    def advance(self, features) -> PatternState:
        if self._check_expiry():
            return self.state
        self.bars_in_formation += 1
        raise NotImplementedError(
            "TripleBottomMachine.advance() — Phase 2 implementation pending"
        )
