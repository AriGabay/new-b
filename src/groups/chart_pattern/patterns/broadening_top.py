"""
Broadening Top / Megaphone detector (H1-022).

H1-022: Broadening Top / Megaphone (bearish).
Expanding swings: higher highs AND lower lows (diverging trendlines).
Min 5 swing points.
CONFIRMED: close below lower trendline after failing to reach upper.
Target: width at breakout × 0.50.
Quality: 0.55 (tricky to trade).

Source: Fidelity chart patterns, GoodCrypto presentation.
"""
from __future__ import annotations

from decimal import Decimal

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class BroadeningTopMachine(BasePatternDetector):
    """H1-022: Broadening Top / Megaphone (bearish)."""

    name = "broadening_top"
    hypothesis_refs = ["H1-022"]
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
            # Track swing highs and lows
            swing_highs = self.metadata.get("_swing_highs", [])
            swing_lows = self.metadata.get("_swing_lows", [])
            swing_highs.append(high)
            swing_lows.append(low)
            if len(swing_highs) > 30:
                swing_highs.pop(0)
                swing_lows.pop(0)
            self.metadata["_swing_highs"] = swing_highs
            self.metadata["_swing_lows"] = swing_lows

            if len(swing_highs) >= 15:
                # Check for diverging pattern: higher highs + lower lows
                h1 = max(swing_highs[:5])
                h2 = max(swing_highs[5:10])
                h3 = max(swing_highs[10:])
                l1 = min(swing_lows[:5])
                l2 = min(swing_lows[5:10])
                l3 = min(swing_lows[10:])

                expanding_highs = h3 > h2 > h1
                expanding_lows = l3 < l2 < l1

                if expanding_highs and expanding_lows:
                    width = h3 - l3
                    lower_boundary = l3
                    self.metadata["lower_boundary"] = lower_boundary
                    self.metadata["upper_boundary"] = h3
                    self.metadata["width"] = width
                    self.breakout_level = Decimal(str(round(lower_boundary, 2)))
                    self.measured_move = Decimal(str(round(width * 0.50, 2)))
                    self.started_at = getattr(features, "timestamp", None)
                    self.bars_in_formation = 0
                    self.state = PatternState.BREAKOUT_PENDING

        elif self.state == PatternState.BREAKOUT_PENDING:
            lower_boundary = self.metadata.get("lower_boundary", 0)
            if close < lower_boundary:
                self.state = PatternState.CONFIRMED

        return self.state
