"""
Unit tests for the trailing stop tier system in ExitGroup.

Tests verify:
  1. At +2.5R the trail multiplier is 0.8×ATR (TRAIL_ATR_TIGHT_2).
  2. At +3.0R the trail multiplier is still 0.8×ATR.
  3. At +3.0R, when the ATR-based candidate would drop below entry + 0.5R,
     the stop is clamped to the floor (entry + 0.5×original_R for LONG;
     entry − 0.5×original_R for SHORT).
  4. When the ATR candidate is already above the floor, no clamping occurs.
  5. The ratchet rule still applies: the trailing stop never moves backward
     even after the floor has been applied.
  6. Integration: simulate a LONG trade reaching +3R; trail tightens to
     0.8×ATR AND stop never drops below entry + 0.5R across multiple bars.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

import pytest

from core.schemas import Direction, Position, FeatureVector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature_vector(
    close: float,
    atr14: float,
    high: float | None = None,
    low: float | None = None,
) -> FeatureVector:
    """Minimal FeatureVector for testing exit logic."""
    ts = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    price = Decimal(str(close))
    atr   = Decimal(str(atr14))
    h     = Decimal(str(high)) if high is not None else price + atr
    lo    = Decimal(str(low))  if low  is not None else price - atr
    return FeatureVector(
        symbol="BTCUSDT", timeframe="1h", timestamp=ts,
        open=price, high=h, low=lo, close=price, volume=Decimal("10000"),
        true_range=atr, atr14=atr, atr14_sma20=atr,
        ema20=price, ema50=price, ema200=price, prev_ema20=price, prev_ema50=price,
        rsi14=60.0, prev_rsi14=50.0,
        bb_upper=price + atr, bb_middle=price, bb_lower=price - atr,
        bb_width=atr * 2, bb_width_pct=2.0,
        adx14=25.0,
        volume_sma20=Decimal("8000"), volume_ratio=1.25,
        candle_body=Decimal("200"), candle_range=Decimal("2000"),
        body_ratio=0.1, upper_shadow=Decimal("900"), lower_shadow=Decimal("900"),
        impulse_flag=False, doji_flag=False,
    )


def _make_long_position(
    entry: float = 70_000.0,
    stop: float  = 68_000.0,
    r_amount: float = 2_000.0,          # USD risk = 1R distance in price × size_base
    position_size_usd: float = 70_000.0, # 1 BTC notional
    trailing_stop: float | None = None,
) -> Position:
    """
    LONG position factory.
    Default values set a clean 1R = 2 000 price points:
      entry=70 000, stop=68 000  →  r_dist_price = 2 000
    r_amount is chosen so that orig_r_dist = r_amount*entry/position_size_usd = 2 000.
    """
    pos = Position(
        symbol="BTCUSDT",
        direction=Direction.LONG,
        entry_price=Decimal(str(entry)),
        stop_price=Decimal(str(stop)),
        target_price=Decimal(str(entry + 5 * (entry - stop))),
        position_size_usd=Decimal(str(position_size_usd)),
        r_amount=Decimal(str(r_amount)),
        bars_held=1,
    )
    if trailing_stop is not None:
        pos.trailing_stop_price = Decimal(str(trailing_stop))
    return pos


def _make_short_position(
    entry: float = 70_000.0,
    stop: float  = 72_000.0,
    r_amount: float = 2_000.0,
    position_size_usd: float = 70_000.0,
    trailing_stop: float | None = None,
) -> Position:
    """
    SHORT position factory.
    Default values: entry=70 000, stop=72 000 → r_dist_price = 2 000
    """
    pos = Position(
        symbol="BTCUSDT",
        direction=Direction.SHORT,
        entry_price=Decimal(str(entry)),
        stop_price=Decimal(str(stop)),
        target_price=Decimal(str(entry - 5 * (stop - entry))),
        position_size_usd=Decimal(str(position_size_usd)),
        r_amount=Decimal(str(r_amount)),
        bars_held=1,
    )
    if trailing_stop is not None:
        pos.trailing_stop_price = Decimal(str(trailing_stop))
    return pos


def _exit_group():
    from core.state import SystemState
    from core.events import EventBus
    from core.schemas import ModeGate
    from groups.exit.group import ExitGroup
    state = SystemState(mode=ModeGate.RESEARCH)
    bus   = EventBus()
    return ExitGroup(state=state, bus=bus)


# ---------------------------------------------------------------------------
# 1. Constant checks
# ---------------------------------------------------------------------------

class TestTrailingStopConstants:

    def test_tight_2_is_0_8(self):
        """TRAIL_ATR_TIGHT_2 must be 0.8 (task requirement)."""
        from groups.exit.group import TRAIL_ATR_TIGHT_2
        assert TRAIL_ATR_TIGHT_2 == Decimal("0.8")

    def test_tight_3_r_exists_and_is_3(self):
        from groups.exit.group import TRAIL_TIGHT_3_R
        assert TRAIL_TIGHT_3_R == 3.0

    def test_floor_3r_r_exists_and_is_half(self):
        from groups.exit.group import TRAIL_FLOOR_3R_R
        assert TRAIL_FLOOR_3R_R == Decimal("0.5")

    def test_activation_and_tight_1_thresholds(self):
        """Activation and first-tighten thresholds match the updated values."""
        from groups.exit.group import (
            TRAIL_ACTIVATE_R, TRAIL_ATR_INITIAL, TRAIL_ATR_TIGHT_1,
            TRAIL_TIGHT_1_R, TRAIL_TIGHT_2_R,
        )
        assert TRAIL_ACTIVATE_R  == 1.5   # raised from 1.0
        assert TRAIL_ATR_INITIAL == Decimal("1.5")
        assert TRAIL_ATR_TIGHT_1 == Decimal("1.0")
        assert TRAIL_TIGHT_1_R   == 2.0   # raised from 1.5
        assert TRAIL_TIGHT_2_R   == 2.5


# ---------------------------------------------------------------------------
# 2. ATR multiplier selection — tier cascade
# ---------------------------------------------------------------------------

class TestTrailMultiplierSelection:
    """_update_trailing_stop selects the correct ATR multiplier per R tier."""

    def setup_method(self):
        self.eg = _exit_group()

    def test_below_1r_no_trail(self):
        """Trade below +1R: no trailing stop activated."""
        pos  = _make_long_position()
        # close at +0.9R: 70 000 + 0.9*2 000 = 71 800
        fv   = _make_feature_vector(close=71_800, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result is None

    def test_at_1r_no_trail_new_threshold(self):
        """At +1.0R, trail does NOT activate — activation threshold is now +1.5R."""
        pos = _make_long_position()
        # close at +1.0R: 70 000 + 1.0*2 000 = 72 000, ATR=500
        fv  = _make_feature_vector(close=72_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result is None

    def test_at_1_5r_uses_initial_mult(self):
        """At +1.5R, trail activates using initial distance = 1.5×ATR14.
        First tighten (TRAIL_TIGHT_1_R) is now at +2.0R, not +1.5R.
        """
        pos = _make_long_position()
        # close at +1.5R: 70 000 + 1.5*2 000 = 73 000, ATR=500
        fv  = _make_feature_vector(close=73_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        expected = Decimal("73000") - Decimal("1.5") * Decimal("500")  # TRAIL_ATR_INITIAL
        assert result == expected

    def test_at_2_0r_uses_tight_1_mult(self):
        """At +2.0R, trail tightens to 1.0×ATR14 (TRAIL_TIGHT_1_R raised to 2.0)."""
        pos = _make_long_position()
        # close at +2.0R: 70 000 + 2.0*2 000 = 74 000, ATR=500
        fv  = _make_feature_vector(close=74_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        expected = Decimal("74000") - Decimal("1.0") * Decimal("500")  # TRAIL_ATR_TIGHT_1
        assert result == expected

    def test_at_2_5r_uses_tight_2_mult(self):
        """At +2.5R, trail distance = 0.8×ATR14 (TRAIL_ATR_TIGHT_2)."""
        pos = _make_long_position()
        # close at +2.5R: 75 000, ATR=500
        fv  = _make_feature_vector(close=75_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        expected = Decimal("75000") - Decimal("0.8") * Decimal("500")
        # No floor (current_r=2.5 < TRAIL_TIGHT_3_R=3.0)
        assert result == expected

    def test_at_3r_still_uses_tight_2_mult_before_floor(self):
        """At +3.0R, ATR multiplier is still 0.8×ATR (same tier as 2.5R)."""
        pos = _make_long_position()
        # close at +3.0R: 76 000, small ATR so floor doesn't clamp
        fv  = _make_feature_vector(close=76_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        # candidate = 76 000 - 0.8*500 = 75 600; floor = 70 000 + 0.5*2 000 = 71 000
        # 75 600 > 71 000 → no clamp
        assert result == Decimal("76000") - Decimal("0.8") * Decimal("500")


# ---------------------------------------------------------------------------
# 3. +3R stop floor — LONG
# ---------------------------------------------------------------------------

class TestTrailingStopFloorLong:

    def setup_method(self):
        self.eg = _exit_group()

    # --- Setup for floor tests ---
    # entry=70 000, stop=68 000, r_amount=2 000, position_size_usd=70 000
    # orig_r_dist = 2 000*70 000/70 000 = 2 000
    # floor = 70 000 + 0.5*2 000 = 71 000

    def test_floor_clamps_when_atr_candidate_below_floor(self):
        """
        Large ATR drives candidate below the 0.5R floor.
        candidate = 76 000 - 0.8*7 000 = 70 400 < floor 71 000
        → result must be 71 000.
        """
        pos = _make_long_position()
        fv  = _make_feature_vector(close=76_000, atr14=7_000)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result == Decimal("71000"), (
            f"Expected floor 71 000, got {result}"
        )

    def test_floor_does_not_clamp_when_candidate_above_floor(self):
        """
        Small ATR: candidate is already above the floor — no clamping.
        candidate = 76 000 - 0.8*500 = 75 600 > floor 71 000.
        """
        pos = _make_long_position()
        fv  = _make_feature_vector(close=76_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result == Decimal("76000") - Decimal("0.8") * Decimal("500")
        assert result > Decimal("71000")

    def test_floor_exactly_at_candidate_equals_floor(self):
        """
        ATR set so candidate == floor exactly:
        76 000 - 0.8 * X = 71 000  →  X = 5 000 / 0.8 = 6 250.
        candidate == floor → result == floor (max picks either).
        """
        pos = _make_long_position()
        fv  = _make_feature_vector(close=76_000, atr14=6_250)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result == Decimal("71000")

    def test_floor_not_applied_below_3r(self):
        """
        At exactly 2.5R the floor must NOT be applied.
        Large ATR gives a very low candidate; since 2.5 < TRAIL_TIGHT_3_R
        the floor should be absent and the raw ATR candidate returned.
        """
        pos = _make_long_position()
        # close at +2.5R: 75 000, ATR=7 000 → candidate = 75 000 - 5 600 = 69 400
        fv  = _make_feature_vector(close=75_000, atr14=7_000)
        result = self.eg._update_trailing_stop(pos, fv)
        # No floor at 2.5R
        expected = Decimal("75000") - Decimal("0.8") * Decimal("7000")  # 69 400
        assert result == expected


# ---------------------------------------------------------------------------
# 4. +3R stop floor — SHORT
# ---------------------------------------------------------------------------

class TestTrailingStopFloorShort:

    def setup_method(self):
        self.eg = _exit_group()

    # --- Setup ---
    # entry=70 000, stop=72 000, r_amount=2 000, position_size_usd=70 000
    # orig_r_dist = 2 000*70 000/70 000 = 2 000
    # floor = 70 000 - 0.5*2 000 = 69 000   (stop must be ≤ 69 000 to lock in 0.5R)

    def test_floor_clamps_when_atr_candidate_above_floor(self):
        """
        Large ATR drives SHORT candidate above the 0.5R floor.
        At +3R: close = 70 000 - 3*2 000 = 64 000
        candidate = 64 000 + 0.8*7 000 = 69 600 > floor 69 000
        → result must be 69 000.
        """
        pos = _make_short_position()
        fv  = _make_feature_vector(close=64_000, atr14=7_000)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result == Decimal("69000"), (
            f"Expected short floor 69 000, got {result}"
        )

    def test_floor_does_not_clamp_when_candidate_below_floor(self):
        """
        Small ATR: SHORT candidate is already below the floor — no clamping.
        candidate = 64 000 + 0.8*500 = 64 400 < floor 69 000.
        """
        pos = _make_short_position()
        fv  = _make_feature_vector(close=64_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result == Decimal("64000") + Decimal("0.8") * Decimal("500")
        assert result < Decimal("69000")


# ---------------------------------------------------------------------------
# 5. Ratchet rule with floor
# ---------------------------------------------------------------------------

class TestRatchetWithFloor:
    """
    After the floor has been applied and the trailing stop is at 71 000,
    a subsequent bar where the candidate would be lower must NOT lower the stop.
    """

    def setup_method(self):
        self.eg = _exit_group()

    def test_ratchet_holds_floor_stop_on_pullback(self):
        """
        Prior stop set at 71 000 (floor locked in at +3R).
        Next bar: close drops back to +2.5R (75 000), ATR still 7 000.
        candidate = 75 000 - 0.8*7 000 = 69 400, but ratchet prevents lowering
        from 71 000 → _update_trailing_stop must return None.
        """
        pos = _make_long_position(trailing_stop=71_000)
        fv  = _make_feature_vector(close=75_000, atr14=7_000)
        result = self.eg._update_trailing_stop(pos, fv)
        # candidate (69 400) < current trailing stop (71 000) → no update
        assert result is None, (
            f"Expected None (ratchet), got {result}"
        )

    def test_ratchet_updates_when_candidate_exceeds_floor_stop(self):
        """
        Prior stop set at 71 000; price continues higher to +4R.
        New candidate > 71 000 → stop should be updated.
        """
        pos = _make_long_position(trailing_stop=71_000)
        # close at +4R: 70 000 + 4*2 000 = 78 000, ATR=500
        fv  = _make_feature_vector(close=78_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        # candidate = 78 000 - 0.8*500 = 77 600, floor = 71 000
        # 77 600 > 71 000 (floor ok) and > 71 000 (ratchet ok) → update
        assert result is not None
        assert result > Decimal("71000")


# ---------------------------------------------------------------------------
# 6. Integration — simulate LONG trade reaching +3R
# ---------------------------------------------------------------------------

class TestIntegrationLongReaches3R:
    """
    Simulate a sequence of bars for a LONG trade as it moves from entry
    to +3R.  Verify:
      (a) Trail tightens to 0.8×ATR once current_r >= 2.5.
      (b) Stop never drops below entry + 0.5R once current_r >= 3.0.
    """

    def setup_method(self):
        self.eg   = _exit_group()
        # entry=70 000, stop=68 000, orig_r_dist=2 000
        self.pos  = _make_long_position(
            entry=70_000, stop=68_000,
            r_amount=2_000, position_size_usd=70_000,
        )
        self.ATR  = Decimal("1000")
        self.FLOOR = Decimal("71000")  # 70 000 + 0.5*2 000

    def _bar(self, close: float, atr: float | None = None) -> FeatureVector:
        a = float(self.ATR) if atr is None else atr
        return _make_feature_vector(close=close, atr14=a)

    def _step(self, close: float, atr: float | None = None) -> Decimal | None:
        """Apply one bar update and return the new trailing stop (or None)."""
        fv     = self._bar(close, atr)
        result = self.eg._update_trailing_stop(self.pos, fv)
        if result is not None:
            self.pos.trailing_stop_price = result
        return result

    def test_trail_not_active_at_1r_new_threshold(self):
        """At +1.0R, trail does NOT activate — activation threshold raised to +1.5R."""
        result = self._step(72_000)
        assert result is None, "Trail must NOT activate before +1.5R (new threshold)"

    def test_trail_activates_at_1_5r(self):
        """Trail activates at +1.5R (new activation threshold)."""
        self._step(72_000)           # +1.0R — no activation
        result = self._step(73_000)  # +1.5R — activates
        assert result is not None, "Trail should activate at +1.5R"

    def test_trail_uses_0_8_atr_at_2_5r(self):
        """At +2.5R (close = 75 000), multiplier is 0.8×ATR."""
        result = self._step(75_000)
        assert result is not None
        expected = Decimal("75000") - Decimal("0.8") * self.ATR
        assert result == expected, (
            f"Expected {expected} (0.8×ATR trail), got {result}"
        )

    def test_trail_uses_0_8_atr_at_3r_with_small_atr(self):
        """At +3.0R, multiplier is still 0.8×ATR (same tier)."""
        result = self._step(76_000)
        assert result is not None
        # candidate = 76 000 - 0.8*1 000 = 75 200; floor = 71 000 → no clamp
        assert result == Decimal("75200"), (
            f"Expected 75 200 (0.8×ATR, no floor clamp), got {result}"
        )

    def test_stop_floor_enforced_at_3r_with_large_atr(self):
        """
        Large ATR (7 000) at +3R would push candidate below the floor.
        Floor must clamp the stop to entry + 0.5R = 71 000.
        """
        result = self._step(76_000, atr=7_000)
        assert result is not None
        assert result == self.FLOOR, (
            f"Expected floor {self.FLOOR}, got {result}"
        )

    def test_stop_never_below_floor_across_multiple_bars(self):
        """
        Simulate price from +1R to +3R using a large ATR (7 000) throughout,
        so the trailing stop has not been pushed above the floor before +3R.

        At each step the large ATR keeps the candidate low enough that the
        floor becomes the binding constraint once +3R is reached.

        After floor is locked in at +3R, stop must stay >= 71 000 on all
        subsequent pullback bars regardless of ATR size.

        ATR=7 000 throughout:
          +1.5R (73 000):  trail = 73 000 - 1.5*7 000 = 62 500
          +2.5R (75 000):  trail = 75 000 - 0.8*7 000 = 69 400  (>62 500 → update)
          +3.0R (76 000):  candidate = 70 400, floor = 71 000 → clamped to 71 000
          pullback (74 000): candidate = 74 000 - 1.0*7 000 = 67 000 < 71 000 → no update
        """
        self._step(73_000, atr=7_000)   # +1.5R  →  trail = 62 500
        self._step(75_000, atr=7_000)   # +2.5R  →  trail = 69 400
        self._step(76_000, atr=7_000)   # +3.0R  →  floor clamps to 71 000
        assert self.pos.trailing_stop_price == self.FLOOR, (
            f"Expected floor {self.FLOOR} after +3R bar, "
            f"got {self.pos.trailing_stop_price}"
        )

        # Subsequent bars at lower prices — ratchet prevents stop from falling
        self._step(74_000, atr=7_000)   # pullback; candidate < 71 000 → no update
        assert self.pos.trailing_stop_price >= self.FLOOR, (
            f"Stop dropped below floor after pullback: {self.pos.trailing_stop_price}"
        )

        self._step(73_000, atr=7_000)   # deeper pullback
        assert self.pos.trailing_stop_price >= self.FLOOR, (
            f"Stop dropped below floor on deeper pullback: {self.pos.trailing_stop_price}"
        )

    def test_stop_rises_with_price_after_floor_is_set(self):
        """
        After floor is locked in (71 000), price continues higher to +4R.
        The trailing stop should rise above the floor once the new ATR-based
        candidate exceeds the current stop.

        Uses large ATR=7 000 to reach +3R so that floor is the binding
        constraint, then switches to small ATR=1 000 for the +4R bar so
        the candidate rises well above the floor.
        """
        # Reach +3R using large ATR so floor locks in at 71 000
        self._step(73_000, atr=7_000)   # +1.5R  →  trail = 62 500
        self._step(75_000, atr=7_000)   # +2.5R  →  trail = 69 400
        self._step(76_000, atr=7_000)   # +3.0R  →  floor = 71 000 (clamped)
        assert self.pos.trailing_stop_price == self.FLOOR, (
            f"Expected floor {self.FLOOR} after +3R bar, "
            f"got {self.pos.trailing_stop_price}"
        )

        # Continue higher to +4R with small ATR so candidate > floor and > current stop
        result = self._step(78_000, atr=1_000)
        # candidate = 78 000 - 0.8*1 000 = 77 200 > 71 000 (floor) > 71 000 (current) → update
        assert result is not None
        assert result > self.FLOOR, (
            f"Expected stop above floor after price rises past +3R, got {result}"
        )


# ---------------------------------------------------------------------------
# 7. Updated activation threshold — TRAIL_ACTIVATE_R = 1.5, TRAIL_TIGHT_1_R = 2.0
# ---------------------------------------------------------------------------

class TestNewActivationThreshold:
    """
    Verify the new trailing stop configuration:
      TRAIL_ACTIVATE_R = 1.5  (raised from 1.0)
      TRAIL_TIGHT_1_R  = 2.0  (raised from 1.5)

    Key assertion from the task: a trade reaching +2.8R DOES have an active
    trailing stop (trail is set), since 2.8R >= activation threshold of 1.5R.
    The companion test confirms that at +1.0R the trail is NOT yet active,
    demonstrating that the old threshold (1.0R) no longer triggers activation.
    """

    def setup_method(self):
        self.eg = _exit_group()

    def test_2_8r_trail_active_uses_tight_2_mult(self):
        """
        A trade reaching +2.8R must have an active trailing stop.
        +2.8R >= TRAIL_TIGHT_2_R (2.5) → multiplier = 0.8×ATR14.
        """
        pos = _make_long_position()
        # close at +2.8R: 70 000 + 2.8*2 000 = 75 600, ATR=500
        fv  = _make_feature_vector(close=75_600, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result is not None, (
            "Trailing stop must be active at +2.8R (well above activation threshold 1.5R)"
        )
        expected = Decimal("75600") - Decimal("0.8") * Decimal("500")
        assert result == expected, (
            f"At +2.8R (>= TRAIL_TIGHT_2_R=2.5), expected 0.8×ATR trail: {expected}, got {result}"
        )

    def test_1_0r_trail_not_active_with_new_threshold(self):
        """
        At +1.0R a fresh position must NOT have an active trailing stop.
        Activation was raised from +1.0R → +1.5R, so +1.0R no longer triggers.
        """
        pos = _make_long_position()
        # close at +1.0R: 70 000 + 1.0*2 000 = 72 000
        fv  = _make_feature_vector(close=72_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result is None, (
            "Trailing stop must NOT activate at +1.0R — threshold is now +1.5R"
        )

    def test_1_5r_is_exact_activation_boundary(self):
        """
        At exactly +1.5R the trailing stop activates for the first time,
        using the initial ATR multiplier (1.5×ATR14).
        """
        pos = _make_long_position()
        # close at +1.5R: 70 000 + 1.5*2 000 = 73 000, ATR=500
        fv  = _make_feature_vector(close=73_000, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result is not None, "Trailing stop must activate at exactly +1.5R"
        expected = Decimal("73000") - Decimal("1.5") * Decimal("500")  # TRAIL_ATR_INITIAL
        assert result == expected, (
            f"At +1.5R activation, expected initial trail (1.5×ATR): {expected}, got {result}"
        )

    def test_tight_1_not_applied_until_2_0r(self):
        """
        At +1.9R the initial multiplier (1.5×ATR) is still in effect.
        TRAIL_ATR_TIGHT_1 (1.0×ATR) only kicks in at TRAIL_TIGHT_1_R = 2.0R.
        """
        pos = _make_long_position()
        # close at +1.9R: 70 000 + 1.9*2 000 = 73 800, ATR=500
        fv  = _make_feature_vector(close=73_800, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result is not None, "Trail must be active at +1.9R"
        # Should still use TRAIL_ATR_INITIAL (1.5), not TRAIL_ATR_TIGHT_1 (1.0)
        expected_initial = Decimal("73800") - Decimal("1.5") * Decimal("500")
        assert result == expected_initial, (
            f"At +1.9R (< TRAIL_TIGHT_1_R=2.0), expected 1.5×ATR trail: "
            f"{expected_initial}, got {result}"
        )

    def test_short_2_8r_trail_active(self):
        """
        Equivalent check for a SHORT position at +2.8R: trailing stop active.
        SHORT +2.8R: close = 70 000 - 2.8*2 000 = 64 400.
        """
        pos = _make_short_position()
        fv  = _make_feature_vector(close=64_400, atr14=500)
        result = self.eg._update_trailing_stop(pos, fv)
        assert result is not None, (
            "Trailing stop must be active for SHORT at +2.8R"
        )
        # SHORT: candidate = close + 0.8*ATR (TRAIL_ATR_TIGHT_2, since 2.8 >= 2.5)
        expected = Decimal("64400") + Decimal("0.8") * Decimal("500")
        assert result == expected
