"""
Bump and Run Reversal detector (H1-021).

H1-021: Bump and Run Reversal (bearish).
Three phases:
  1. Lead-in: moderate upward trendline.
  2. Bump: price accelerates away, angle roughly doubles.
  3. Run: collapse through lead-in trendline.

Bump height >= 2× lead-in height.
CONFIRMED: close below lead-in trendline.
Target: price returns to start of lead-in.
Quality: 0.60.

Source: Bulkowski's Encyclopedia of Chart Patterns, TrustedBrokers guide.
"""
from __future__ import annotations

from decimal import Decimal

from groups.chart_pattern.patterns.base import BasePatternDetector
from groups.chart_pattern.registry import PatternRegistry
from groups.chart_pattern.state_machine import PatternState


@PatternRegistry.register
class BumpAndRunMachine(BasePatternDetector):
    """H1-021: Bump and Run Reversal (bearish)."""

    name = "bump_and_run"
    hypothesis_refs = ["H1-021"]
    direction_bias = "short"
    min_bars_needed = 20
    max_bars: int = 80

    def advance(self, features) -> PatternState:
        if self._check_expiry():
            return self.state
        if self.state != PatternState.INACTIVE:
            self.bars_in_formation += 1

        close = float(getattr(features, "close", 0))
        high = float(getattr(features, "high", 0))

        if self.state == PatternState.INACTIVE:
            # Phase 1: Track moderate uptrend (lead-in)
            window = self.metadata.get("_window", [])
            window.append({"close": close, "high": high})
            if len(window) > 40:
                window.pop(0)
            self.metadata["_window"] = window

            if len(window) >= 15:
                # Lead-in: moderate uptrend over first 10 bars
                leadin = window[:10]
                leadin_start = leadin[0]["close"]
                leadin_end = leadin[-1]["close"]
                leadin_height = leadin_end - leadin_start

                if leadin_height > 0 and leadin_start > 0:
                    leadin_pct = leadin_height / leadin_start

                    # Moderate lead-in: 1-5% gain
                    if 0.01 < leadin_pct < 0.05:
                        # Check for bump: price accelerates above lead-in trend
                        bump_bars = window[10:]
                        if bump_bars:
                            bump_peak = max(b["high"] for b in bump_bars)
                            bump_height = bump_peak - leadin_end

                            # Bump must be >= 2× lead-in height
                            if bump_height >= 2 * leadin_height:
                                # Check if price is now declining (run phase beginning)
                                if close < bump_peak * 0.97:
                                    self.metadata["leadin_start"] = leadin_start
                                    self.metadata["leadin_end"] = leadin_end
                                    self.metadata["leadin_trendline"] = leadin_end
                                    self.metadata["bump_peak"] = bump_peak
                                    self.breakout_level = Decimal(str(round(leadin_end, 2)))
                                    target_move = bump_peak - leadin_start
                                    self.measured_move = Decimal(str(round(target_move, 2)))
                                    self.started_at = getattr(features, "timestamp", None)
                                    self.bars_in_formation = 0
                                    self.state = PatternState.BREAKOUT_PENDING

        elif self.state == PatternState.BREAKOUT_PENDING:
            leadin_tl = self.metadata.get("leadin_trendline", 0)
            if close < leadin_tl:
                self.state = PatternState.CONFIRMED

        return self.state
