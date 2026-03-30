"""
Ascending Channel Breakout detector (H1-018).

H1-018: Ascending Channel breakdown (bearish on breakdown from rising channel).
Two parallel upward-sloping trendlines with 2+ touches each.
CONFIRMED: close below lower trendline.
Target: channel_width projected down from breakdown.
Quality: 0.60.

Source: Fidelity Identifying Chart Patterns guide.
"""
from __future__ import annotations

from decimal import Decimal

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class AscendingChannelMachine(BasePatternDetector):
    """H1-018: Ascending Channel Breakout (bearish on breakdown)."""

    name = "ascending_channel"
    hypothesis_refs = ["H1-018"]
    direction_bias = "short"
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
            # Track lows to detect upward-sloping support line
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
                # Check ascending pattern: lows trending up, highs trending up
                first_q_lows = sum(lows[:5]) / 5
                last_q_lows = sum(lows[-5:]) / 5
                first_q_highs = sum(highs[:5]) / 5
                last_q_highs = sum(highs[-5:]) / 5

                if last_q_lows > first_q_lows * 1.01 and last_q_highs > first_q_highs * 1.01:
                    # Channel width = avg(high - low) over the period
                    channel_width = last_q_highs - last_q_lows
                    lower_trendline = last_q_lows
                    self.metadata["channel_width"] = channel_width
                    self.metadata["lower_trendline"] = lower_trendline
                    self.breakout_level = Decimal(str(round(lower_trendline, 2)))
                    self.measured_move = Decimal(str(round(channel_width, 2)))
                    self.started_at = getattr(features, "timestamp", None)
                    self.bars_in_formation = 0
                    self.state = PatternState.BREAKOUT_PENDING

        elif self.state == PatternState.BREAKOUT_PENDING:
            lower_tl = self.metadata.get("lower_trendline", 0)
            if close < lower_tl:
                self.state = PatternState.CONFIRMED

        return self.state
