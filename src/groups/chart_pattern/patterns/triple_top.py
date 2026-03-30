"""
Triple Top detector (H1-023).

H1-023: Triple Top (bearish reversal).
Three peaks at roughly same level (within 1%).
CONFIRMED: close below support connecting the two troughs.
Target: pattern_height × 0.50 projected down.
Quality: 0.70.

Source: Fidelity Identifying Chart Patterns, TrustedBrokers crypto guide.
"""
from __future__ import annotations

from decimal import Decimal

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class TripleTopMachine(BasePatternDetector):
    """H1-023: Triple Top (bearish reversal)."""

    name = "triple_top"
    hypothesis_refs = ["H1-023"]
    direction_bias = "short"
    min_bars_needed = 15

    def advance(self, features) -> PatternState:
        if self._check_expiry():
            return self.state
        if self.state != PatternState.INACTIVE:
            self.bars_in_formation += 1

        close = float(getattr(features, "close", 0))
        high = float(getattr(features, "high", 0))
        low = float(getattr(features, "low", 0))

        if self.state == PatternState.INACTIVE:
            window = self.metadata.get("_window", [])
            window.append({"high": high, "low": low, "close": close})
            if len(window) > 50:
                window.pop(0)
            self.metadata["_window"] = window

            if len(window) >= 15:
                # Find three peaks at similar levels
                highs = [w["high"] for w in window]
                lows = [w["low"] for w in window]
                peak = max(highs)

                if peak > 0:
                    # Count touches near the peak (within 1%)
                    peak_zone = peak * 0.99
                    touches = [i for i, h in enumerate(highs) if h >= peak_zone]

                    # Need at least 3 touches separated by troughs
                    if len(touches) >= 3:
                        first, last = touches[0], touches[-1]
                        if last - first >= 8:  # min 8 bars span
                            # Find troughs between the peaks
                            between_lows = lows[first:last + 1]
                            if between_lows:
                                support = min(between_lows)
                                pattern_height = peak - support
                                if pattern_height > peak * 0.01:  # at least 1% height
                                    self.metadata["peak"] = peak
                                    self.metadata["support"] = support
                                    self.metadata["pattern_height"] = pattern_height
                                    self.breakout_level = Decimal(str(round(support, 2)))
                                    self.neckline_price = self.breakout_level
                                    self.measured_move = Decimal(str(round(pattern_height * 0.50, 2)))
                                    self.started_at = getattr(features, "timestamp", None)
                                    self.bars_in_formation = 0
                                    self.state = PatternState.BREAKOUT_PENDING

        elif self.state == PatternState.BREAKOUT_PENDING:
            support = self.metadata.get("support", 0)
            if close < support:
                self.state = PatternState.CONFIRMED

        return self.state
