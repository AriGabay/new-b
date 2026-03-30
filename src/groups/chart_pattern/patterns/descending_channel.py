"""
Descending Channel Breakout detector (H1-019).

H1-019: Descending Channel breakout (bullish on upward breakout).
Two parallel downward-sloping trendlines with 2+ touches each.
CONFIRMED: close above upper trendline.
Target: channel_width projected up.
Quality: 0.60.

Note: This replaces the previous stub H1-004 descending_triangle detector.

Source: Fidelity Identifying Chart Patterns guide.
"""
from __future__ import annotations

from decimal import Decimal

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class DescendingChannelMachine(BasePatternDetector):
    """H1-019: Descending Channel Breakout (bullish on breakout)."""

    name = "descending_channel"
    hypothesis_refs = ["H1-019"]
    direction_bias = "long"
    min_bars_needed = 20

    def advance(self, features) -> PatternState:
        if self._check_expiry():
            return self.state
        if self.state != PatternState.INACTIVE:
            self.bars_in_formation += 1

        close = float(getattr(features, "close", 0))
        high = float(getattr(features, "high", 0))
        low = float(getattr(features, "low", 0))

        if self.state == PatternState.INACTIVE:
            lows = self.metadata.get("_lows", [])
            highs = self.metadata.get("_highs", [])
            lows.append(low)
            highs.append(high)
            if len(lows) > 30:
                lows.pop(0)
                highs.pop(0)
            self.metadata["_lows"] = lows
            self.metadata["_highs"] = highs

            if len(lows) >= 20:
                first_q_lows = sum(lows[:5]) / 5
                last_q_lows = sum(lows[-5:]) / 5
                first_q_highs = sum(highs[:5]) / 5
                last_q_highs = sum(highs[-5:]) / 5

                if last_q_lows < first_q_lows * 0.99 and last_q_highs < first_q_highs * 0.99:
                    channel_width = last_q_highs - last_q_lows
                    upper_trendline = last_q_highs
                    self.metadata["channel_width"] = channel_width
                    self.metadata["upper_trendline"] = upper_trendline
                    self.breakout_level = Decimal(str(round(upper_trendline, 2)))
                    self.measured_move = Decimal(str(round(channel_width, 2)))
                    self.started_at = getattr(features, "timestamp", None)
                    self.bars_in_formation = 0
                    self.state = PatternState.BREAKOUT_PENDING

        elif self.state == PatternState.BREAKOUT_PENDING:
            upper_tl = self.metadata.get("upper_trendline", float("inf"))
            if close > upper_tl:
                self.state = PatternState.CONFIRMED

        return self.state
