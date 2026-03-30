"""
Head and Shoulders (H1-001) and Inverse Head and Shoulders (H1-002) detector.

H1-001: H&S Top — bearish. Post-neckline short entry.
H1-002: Inverse H&S Bottom — bullish. Same logic, mirrored direction.

Both patterns share this machine class. The direction is determined by the
hypothesis_ref supplied at construction time via the pattern_type parameter.

State transitions:
  INACTIVE → FORMING:            First swing high (or low for IHS) identified.
  FORMING → CANDIDATE:           Head formed (higher high), left shoulder defined.
  CANDIDATE → BREAKOUT_PENDING:  Right shoulder formed. Neckline drawn.
  BREAKOUT_PENDING → CONFIRMED:  Close below neckline (H&S) or above (IHS).

Breakout level = neckline price.
Measured move = distance from head to neckline.
Conservative target = 50% of measured move (applied in ChartPatternSignal.__post_init__).

Source: /research/hypotheses/hypothesis_registry.md (H1-001, H1-002)
        /research/source_notes/source_04_chart_patterns_audit.md
"""
from __future__ import annotations

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class HeadAndShouldersMachine(BasePatternDetector):
    """
    H1-001: Head & Shoulders Top (bearish).
    H1-002: Inverse H&S Bottom (bullish) — same logic, mirrored.
    """

    name = "head_and_shoulders"
    hypothesis_refs = ["H1-001", "H1-002"]
    direction_bias = "both"
    min_bars_needed = 20

    def advance(self, features) -> PatternState:
        if self._check_expiry():
            return self.state
        self.bars_in_formation += 1
        raise NotImplementedError(
            "HeadAndShouldersMachine.advance() — Phase 2 implementation pending"
        )
