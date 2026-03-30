"""
Rounding Bottom / Saucer detector (H1-020).

H1-020: Rounding Bottom (bullish reversal).
Gradual U-shaped decline and recovery over 30-80 bars.
Bottom must be rounded (min 10 bars within 2% range at bottom).
CONFIRMED: close above left rim level.
Target: depth × 0.50.
Quality: 0.65.

Source: Fidelity Identifying Chart Patterns guide, GoodCrypto.
"""
from __future__ import annotations

from decimal import Decimal

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class RoundingBottomMachine(BasePatternDetector):
    """H1-020: Rounding Bottom / Saucer (bullish reversal)."""

    name = "rounding_bottom"
    hypothesis_refs = ["H1-020"]
    direction_bias = "long"
    min_bars_needed = 30
    max_bars: int = 100  # Rounding bottoms take longer

    def advance(self, features) -> PatternState:
        if self._check_expiry():
            return self.state
        if self.state != PatternState.INACTIVE:
            self.bars_in_formation += 1

        close = float(getattr(features, "close", 0))

        if self.state == PatternState.INACTIVE:
            # Track closes to detect the U-shape
            window = self.metadata.get("_window", [])
            window.append(close)
            if len(window) > 80:
                window.pop(0)
            self.metadata["_window"] = window

            if len(window) >= 30:
                # Find the minimum (bottom of the saucer)
                min_price = min(window)
                min_idx = window.index(min_price)
                left_rim = max(window[:max(min_idx, 1)])

                # The bottom should be in the middle third
                if len(window) // 4 < min_idx < 3 * len(window) // 4:
                    # Check that bottom is rounded (10+ bars within 2% of min)
                    bottom_range = [p for p in window if p <= min_price * 1.02]
                    if len(bottom_range) >= 10:
                        # Check that price is now recovering toward left rim
                        if close > min_price * 1.02 and left_rim > min_price * 1.03:
                            depth = left_rim - min_price
                            self.metadata["left_rim"] = left_rim
                            self.metadata["bottom"] = min_price
                            self.metadata["depth"] = depth
                            self.breakout_level = Decimal(str(round(left_rim, 2)))
                            self.measured_move = Decimal(str(round(depth * 0.50, 2)))
                            self.started_at = getattr(features, "timestamp", None)
                            self.bars_in_formation = 0
                            self.state = PatternState.BREAKOUT_PENDING

        elif self.state == PatternState.BREAKOUT_PENDING:
            left_rim = self.metadata.get("left_rim", float("inf"))
            if close > left_rim:
                self.state = PatternState.CONFIRMED

        return self.state
