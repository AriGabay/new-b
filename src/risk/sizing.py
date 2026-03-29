"""
Position sizing and stop placement.

These are the two foundational risk rules applied to every approved trade.
They are stateless, deterministic, unit-testable.

R-multiple method:
  R_amount   = equity × risk_fraction  (default 1%)
  stop_dist  = abs(entry_price - stop_price)
  size_base  = R_amount / stop_dist
  size_usd   = size_base × entry_price
  size_usd   = min(size_usd, equity × max_position_fraction)

ATR stop placement:
  LONG:  stop = entry - 1.5 × ATR14
         If stop falls on round number (e.g., $10,000), shift +0.5× ATR14
         below the round number to avoid stop-hunt clusters.
  SHORT: stop = entry + 1.5 × ATR14
         If stop falls on round number, shift +0.5× ATR14 above.

Source: /docs/risk_framework/risk_contract.md
        /research/risk_rules/risk_management_rules.md
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from core.schemas import Direction

ATR_STOP_MULTIPLIER     = Decimal("1.5")
ROUND_NUMBER_SHIFT      = Decimal("0.5")    # × ATR14 away from round number
DEFAULT_RISK_FRACTION   = Decimal("0.01")   # 1% of equity per R
MAX_POSITION_FRACTION   = Decimal("0.10")   # 10% of equity max single position


class ATRStopPlacer:
    """
    Compute ATR-based stop price with anti-round-number protection.

    Usage:
        placer = ATRStopPlacer()
        stop_price = placer.compute(entry_price, direction, atr14)
    """

    def compute(
        self,
        entry_price: Decimal,
        direction: Direction,
        atr14: Decimal,
        atr_multiplier: Decimal = ATR_STOP_MULTIPLIER,
    ) -> Decimal:
        """
        Compute stop price. Applies round-number shift if needed.

        LONG:  raw_stop = entry - atr_multiplier × ATR14
        SHORT: raw_stop = entry + atr_multiplier × ATR14

        Round-number check: if raw_stop is within 0.2 × ATR14 of any
        round number (ending in 000 or 500 for BTC-scale), shift away.
        """
        if direction == Direction.LONG:
            raw_stop = entry_price - atr_multiplier * atr14
        else:
            raw_stop = entry_price + atr_multiplier * atr14

        if self._is_near_round_number(raw_stop, atr14):
            if direction == Direction.LONG:
                raw_stop = raw_stop - ROUND_NUMBER_SHIFT * atr14
            else:
                raw_stop = raw_stop + ROUND_NUMBER_SHIFT * atr14

        return raw_stop

    def _is_near_round_number(self, price: Decimal, atr14: Decimal) -> bool:
        """
        Return True if price is within 0.2 × ATR14 of a psychologically
        round number. Round numbers defined as multiples of 100 for most assets,
        multiples of 1000 for BTC-scale assets.
        """
        threshold = atr14 * Decimal("0.2")
        nearest_round = round(float(price) / 1000) * 1000
        return abs(price - Decimal(str(nearest_round))) < threshold


class RMultipleSizer:
    """
    R-multiple position sizer.

    Usage:
        sizer = RMultipleSizer(equity=Decimal("100000"), risk_fraction=Decimal("0.01"))
        size_base, size_usd, r_amount = sizer.compute(entry_price, stop_price)
    """

    def __init__(
        self,
        equity: Decimal,
        risk_fraction: Decimal = DEFAULT_RISK_FRACTION,
        max_position_fraction: Decimal = MAX_POSITION_FRACTION,
    ) -> None:
        self.equity = equity
        self.risk_fraction = risk_fraction
        self.max_position_fraction = max_position_fraction

    def compute(
        self,
        entry_price: Decimal,
        stop_price: Decimal,
        size_reduction: Decimal = Decimal("1.0"),
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Compute (position_size_base, position_size_usd, r_amount).

        size_reduction: multiplier from RiskState (1.0 = full, 0.5 = half, etc.)
        Applies max_position_fraction cap after size_reduction.

        Raises ValueError if stop_price == entry_price (zero stop distance).
        """
        if stop_price == entry_price:
            raise ValueError("stop_price cannot equal entry_price (zero stop distance)")

        stop_dist = abs(entry_price - stop_price)

        r_amount = self.equity * self.risk_fraction * size_reduction
        size_base = r_amount / stop_dist

        size_usd = size_base * entry_price
        max_size_usd = self.equity * self.max_position_fraction
        size_usd = min(size_usd, max_size_usd)

        # Recalculate size_base from capped size_usd
        size_base = size_usd / entry_price

        return (size_base, size_usd, r_amount)
