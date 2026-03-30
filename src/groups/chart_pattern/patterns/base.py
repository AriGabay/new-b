"""
BasePatternDetector: plugin base class for all chart pattern detectors.

Every pattern in the patterns/ directory should:
  1. Inherit from BasePatternDetector.
  2. Declare class-level metadata: name, hypothesis_refs, direction_bias, min_bars_needed.
  3. Implement advance(features) → PatternState.
  4. Register itself with the PatternRegistry using @PatternRegistry.register.

See template.py for a complete, annotated example.
"""
from __future__ import annotations

from groups.chart_pattern.state_machine import PatternState, PatternStateMachine


class BasePatternDetector(PatternStateMachine):
    """
    Plugin base class extending PatternStateMachine with metadata and a
    detect() interface.

    Class attributes (set at the class level in each subclass):
      name:            str        Unique pattern identifier, e.g. "double_bottom".
                                  Used as the registry key and displayed in logs.
      hypothesis_refs: list[str]  One or more hypothesis IDs handled by this class,
                                  e.g. ["H1-003"]. Two entries for classes that cover
                                  both a bullish and bearish variant (e.g. H1-001/H1-002).
      direction_bias:  str        "long" | "short" | "both" — indicates the trade
                                  direction(s) this pattern generates signals for.
      min_bars_needed: int        Minimum bars of OHLCV history required before the
                                  detector's advance() logic can produce a non-INACTIVE
                                  state.  Used by callers as a short-circuit guard.
    """

    # Override in every subclass
    name: str = ""
    hypothesis_refs: list = []
    direction_bias: str = "both"
    min_bars_needed: int = 10

    def detect(self, features) -> PatternState:
        """
        Plugin detection interface.

        Delegates to advance() so existing callers that use advance() directly
        continue to work without modification.  New callers should prefer detect()
        to signal intent clearly.
        """
        return self.advance(features)
