"""
Diamond Top detector (H1-016).

H1-016: Diamond Top (bearish reversal). Rare but reliable (~70%).

Shape: broadening formation that transitions to symmetrical triangle,
creating a diamond/rhombus shape at market top.

State transitions:
  INACTIVE → FORMING:           Expanding swings detected (higher highs + lower lows).
  FORMING → CANDIDATE:          Swings start contracting (lower highs + higher lows).
  CANDIDATE → BREAKOUT_PENDING: Diamond boundary identified.
  BREAKOUT_PENDING → CONFIRMED: Close below lower-right boundary.

Target: max_height × 0.50 projected down from breakout.

Source: Fidelity chart patterns guide, GoodCrypto patterns.
"""
from __future__ import annotations

from decimal import Decimal

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class DiamondTopMachine(BasePatternDetector):
    """H1-016: Diamond Top (bearish reversal)."""

    name = "diamond_top"
    hypothesis_refs = ["H1-016"]
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
            # Track swing highs and lows to detect expanding formation
            swings = self.metadata.get("_swings", [])
            swings.append({"high": high, "low": low, "close": close})
            if len(swings) > 40:
                swings.pop(0)
            self.metadata["_swings"] = swings

            if len(swings) >= 10:
                # Check for expanding swings (broadening): higher highs AND lower lows
                recent = swings[-10:]
                highs = [s["high"] for s in recent]
                lows = [s["low"] for s in recent]
                h_expanding = highs[-1] > highs[0] and highs[-3] > highs[-6]
                l_expanding = lows[-1] < lows[0] and lows[-3] < lows[-6]
                if h_expanding and l_expanding:
                    self.metadata["max_high"] = max(highs)
                    self.metadata["min_low"] = min(lows)
                    self.metadata["expand_count"] = len(swings)
                    self.started_at = getattr(features, "timestamp", None)
                    self.bars_in_formation = 0
                    self.state = PatternState.FORMING

        elif self.state == PatternState.FORMING:
            # Update max/min, then detect contraction (swings narrowing)
            max_h = max(self.metadata.get("max_high", high), high)
            min_l = min(self.metadata.get("min_low", low), low)
            self.metadata["max_high"] = max_h
            self.metadata["min_low"] = min_l

            # Check if swings are now contracting (lower highs + higher lows)
            if self.bars_in_formation >= 5:
                recent_highs = self.metadata.get("_recent_highs", [])
                recent_lows = self.metadata.get("_recent_lows", [])
                recent_highs.append(high)
                recent_lows.append(low)
                if len(recent_highs) > 8:
                    recent_highs.pop(0)
                    recent_lows.pop(0)
                self.metadata["_recent_highs"] = recent_highs
                self.metadata["_recent_lows"] = recent_lows

                if len(recent_highs) >= 5:
                    h_contracting = recent_highs[-1] < max_h * 0.998
                    l_contracting = recent_lows[-1] > min_l * 1.002
                    if h_contracting and l_contracting:
                        pattern_height = max_h - min_l
                        lower_boundary = min_l + pattern_height * 0.25
                        self.metadata["lower_boundary"] = lower_boundary
                        self.metadata["pattern_height"] = pattern_height
                        self.breakout_level = Decimal(str(round(lower_boundary, 2)))
                        self.measured_move = Decimal(str(round(pattern_height * 0.50, 2)))
                        self.state = PatternState.BREAKOUT_PENDING

        elif self.state == PatternState.BREAKOUT_PENDING:
            lower_boundary = self.metadata.get("lower_boundary", 0)
            if close < lower_boundary:
                self.state = PatternState.CONFIRMED

        return self.state
