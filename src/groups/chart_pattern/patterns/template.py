"""
Template for adding a new chart pattern detector.

COPY THIS FILE and rename it to your pattern name, e.g. ascending_triangle.py.
Then:
  1. Fill in all the class attributes (name, hypothesis_refs, direction_bias, min_bars_needed).
  2. Implement advance(features) → PatternState following the state lifecycle.
  3. The @PatternRegistry.register decorator handles auto-registration — no other
     changes are required in group.py or state_machine.py.

State lifecycle:
  INACTIVE → FORMING → CANDIDATE → BREAKOUT_PENDING → CONFIRMED
                                 ↘ FAILED
                                 ↘ EXPIRED (via _check_expiry())

Rules (non-negotiable, from Phase 1 research):
  1. NEVER emit a signal before CONFIRMED state.
  2. Breakout bar must be confirmed at bar CLOSE (no intra-bar signals).
  3. Conservative target = 50% of measured move.  Set self.measured_move to the
     FULL measured move; ChartPatternSignal.__post_init__ applies the 50% discount.
  4. Call self._check_expiry() at the top of advance(); return immediately if True.
  5. Increment self.bars_in_formation on each bar while not INACTIVE.

Example: see double_bottom.py for a working reference implementation.
"""
from __future__ import annotations

# from groups.chart_pattern.registry import PatternRegistry  # uncomment when using
from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.state_machine import PatternState


# @PatternRegistry.register  ← uncomment this line when your implementation is ready
class _ExamplePatternTemplate(BasePatternDetector):
    """
    YOUR PATTERN NAME HERE.

    Replace the docstring with your pattern description and source reference.
    """

    # ------------------------------------------------------------------
    # Plugin metadata — required, override all four
    # ------------------------------------------------------------------
    name = "example_pattern"          # unique snake_case identifier
    hypothesis_refs = ["H1-XXX"]      # hypothesis ID(s) this pattern tests
    direction_bias = "long"           # "long" | "short" | "both"
    min_bars_needed = 15              # minimum bars before detection is possible

    # ------------------------------------------------------------------
    # State machine implementation
    # ------------------------------------------------------------------

    def advance(self, features) -> PatternState:
        """
        Advance the state machine by one bar.

        Args:
            features: FeatureVector from MarketDataGroup.
                      Key attributes: open, high, low, close, volume,
                      ema20, ema50, ema200, rsi14, adx14, atr14, timestamp.

        Returns:
            Current PatternState after processing this bar.
        """
        # Step 1: check expiry first
        if self._check_expiry():
            return self.state

        # Step 2: increment formation counter while not INACTIVE
        if self.state != PatternState.INACTIVE:
            self.bars_in_formation += 1

        close = float(getattr(features, "close", 0))

        # Step 3: implement state transitions
        if self.state == PatternState.INACTIVE:
            # TODO: detect first structural event that starts formation
            # Example:
            #   if <condition>:
            #       self.state = PatternState.FORMING
            #       self.bars_in_formation = 0
            pass

        elif self.state == PatternState.FORMING:
            # TODO: detect structural milestones that advance to CANDIDATE
            pass

        elif self.state == PatternState.CANDIDATE:
            # TODO: detect near-breakout condition → BREAKOUT_PENDING
            # Or detect invalidation → self.state = PatternState.FAILED
            pass

        elif self.state == PatternState.BREAKOUT_PENDING:
            # TODO: on breakout confirmation → CONFIRMED
            # Set self.neckline_price, self.breakout_level, self.measured_move
            # Example:
            #   if <breakout confirmed>:
            #       self.breakout_level = Decimal(str(close))
            #       self.measured_move = Decimal(str(abs(target - breakout)))
            #       self.neckline_price = self.breakout_level
            #       self.state = PatternState.CONFIRMED
            pass

        return self.state
