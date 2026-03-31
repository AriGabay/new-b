"""
Unit tests for EntryGroup._check_4h_alignment (multi-timeframe confirmation).

Coverage:
  1. Pure EMA computation (_ema_from_closes)
  2. Alignment logic — all four (direction × trend) combinations
  3. Edge cases: no provider wired, insufficient bars, provider exception
  4. Integration: gate correctly suppresses misaligned proposals in the
     full entry pipeline (via injected bar provider)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(
    symbol: str,
    close: float,
    i: int = 0,
) -> "OHLCVBar":
    """Create a minimal OHLCVBar centred on `close` for testing."""
    from core.schemas import OHLCVBar
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=4 * i)
    c = Decimal(str(close))
    # Satisfy high >= max(open, close) and low <= min(open, close)
    return OHLCVBar(
        symbol=symbol,
        timeframe="4h",
        timestamp=ts,
        open=c,
        high=c + Decimal("1"),
        low=c - Decimal("1"),
        close=c,
        volume=Decimal("100"),
        volume_usd=Decimal("100") * c,
    )


def _bullish_bars(symbol: str = "BTCUSDT", n: int = 60) -> List["OHLCVBar"]:
    """
    60 bars with steadily rising closes: price increases by 100 per bar.
    This guarantees EMA20 > EMA50 (recent bars are higher than older ones).
    """
    base = 50_000.0
    return [_make_bar(symbol, base + i * 100, i) for i in range(n)]


def _bearish_bars(symbol: str = "BTCUSDT", n: int = 60) -> List["OHLCVBar"]:
    """
    60 bars with steadily falling closes: price decreases by 100 per bar.
    This guarantees EMA20 < EMA50 (recent bars are lower than older ones).
    """
    base = 56_000.0
    return [_make_bar(symbol, base - i * 100, i) for i in range(n)]


def _make_entry_group():
    """Return a minimal EntryGroup with no EventBus subscriptions."""
    from unittest.mock import MagicMock, AsyncMock
    from core.state import SystemState
    from core.events import EventBus
    from core.schemas import ModeGate
    from groups.entry.group import EntryGroup

    state = SystemState(mode=ModeGate.RESEARCH)
    bus = EventBus()
    return EntryGroup(state=state, bus=bus)


# ===========================================================================
# 1. Pure EMA computation
# ===========================================================================

class TestEmaFromCloses:

    def test_constant_series_returns_constant(self):
        from groups.entry.group import EntryGroup
        eg = _make_entry_group()
        closes = [Decimal("100")] * 60
        ema20 = eg._ema_from_closes(closes, 20)
        ema50 = eg._ema_from_closes(closes, 50)
        assert ema20 == Decimal("100")
        assert ema50 == Decimal("100")

    def test_rising_series_ema20_above_ema50(self):
        """In a rising market EMA20 (shorter, more responsive) > EMA50."""
        from groups.entry.group import EntryGroup
        eg = _make_entry_group()
        closes = [Decimal(str(50_000 + i * 100)) for i in range(60)]
        ema20 = eg._ema_from_closes(closes, 20)
        ema50 = eg._ema_from_closes(closes, 50)
        assert ema20 > ema50, (
            f"Rising series: expected EMA20 ({ema20}) > EMA50 ({ema50})"
        )

    def test_falling_series_ema20_below_ema50(self):
        """In a falling market EMA20 < EMA50."""
        from groups.entry.group import EntryGroup
        eg = _make_entry_group()
        closes = [Decimal(str(56_000 - i * 100)) for i in range(60)]
        ema20 = eg._ema_from_closes(closes, 20)
        ema50 = eg._ema_from_closes(closes, 50)
        assert ema20 < ema50, (
            f"Falling series: expected EMA20 ({ema20}) < EMA50 ({ema50})"
        )

    def test_insufficient_bars_returns_last_close(self):
        from groups.entry.group import EntryGroup
        eg = _make_entry_group()
        closes = [Decimal("42000")] * 10
        # period=20 but only 10 values — should return last value
        result = eg._ema_from_closes(closes, 20)
        assert result == Decimal("42000")


# ===========================================================================
# 2. Alignment logic — all four (direction × trend) combinations
# ===========================================================================

class TestCheck4hAlignmentLogic:

    def _make_group_with_provider(self, bars):
        eg = _make_entry_group()
        eg._4h_bar_provider = lambda sym, n: bars[-n:] if len(bars) >= n else bars
        return eg

    def test_long_bullish_aligned_returns_true(self):
        """LONG with EMA20 > EMA50 → aligned."""
        from core.schemas import Direction
        bars = _bullish_bars()
        eg = self._make_group_with_provider(bars)
        assert eg._check_4h_alignment("BTCUSDT", Direction.LONG) is True

    def test_long_bearish_misaligned_returns_false(self):
        """LONG with EMA20 < EMA50 → misaligned → False."""
        from core.schemas import Direction
        bars = _bearish_bars()
        eg = self._make_group_with_provider(bars)
        assert eg._check_4h_alignment("BTCUSDT", Direction.LONG) is False

    def test_short_bearish_aligned_returns_true(self):
        """SHORT with EMA20 < EMA50 → aligned."""
        from core.schemas import Direction
        bars = _bearish_bars()
        eg = self._make_group_with_provider(bars)
        assert eg._check_4h_alignment("BTCUSDT", Direction.SHORT) is True

    def test_short_bullish_misaligned_returns_false(self):
        """SHORT with EMA20 > EMA50 → misaligned → False."""
        from core.schemas import Direction
        bars = _bullish_bars()
        eg = self._make_group_with_provider(bars)
        assert eg._check_4h_alignment("BTCUSDT", Direction.SHORT) is False


# ===========================================================================
# 3. Edge cases
# ===========================================================================

class TestCheck4hAlignmentEdgeCases:

    def test_no_provider_skips_check_returns_true(self):
        """When _4h_bar_provider is None the check is skipped (True)."""
        from core.schemas import Direction
        eg = _make_entry_group()
        assert eg._4h_bar_provider is None
        assert eg._check_4h_alignment("BTCUSDT", Direction.LONG) is True
        assert eg._check_4h_alignment("BTCUSDT", Direction.SHORT) is True

    def test_fewer_than_min_bars_skips_check_returns_true(self):
        """Only 10 4H bars available — insufficient for EMA50, skip check."""
        from core.schemas import Direction
        eg = _make_entry_group()
        # Bearish bars — but too few; check should be skipped, not rejected
        eg._4h_bar_provider = lambda sym, n: _bearish_bars(n=10)
        assert eg._check_4h_alignment("BTCUSDT", Direction.LONG) is True

    def test_provider_exception_skips_check_returns_true(self):
        """If the bar provider raises, the check is skipped (True)."""
        from core.schemas import Direction
        eg = _make_entry_group()
        eg._4h_bar_provider = lambda sym, n: (_ for _ in ()).throw(
            RuntimeError("test provider failure")
        )
        assert eg._check_4h_alignment("BTCUSDT", Direction.LONG) is True

    def test_exactly_min_bars_passes_check(self):
        """Exactly _4H_MIN_BARS_FOR_EMA bars: check runs, not skipped."""
        from core.schemas import Direction
        from groups.entry.group import EntryGroup
        min_n = EntryGroup._4H_MIN_BARS_FOR_EMA
        # Bullish bars at the minimum count
        bars = _bullish_bars(n=min_n)
        eg = _make_entry_group()
        eg._4h_bar_provider = lambda sym, n: bars
        # Bullish + LONG → should return True (aligned)
        assert eg._check_4h_alignment("BTCUSDT", Direction.LONG) is True


# ===========================================================================
# 4. Integration: gate suppresses misaligned proposals in the full pipeline
# ===========================================================================

class TestCheck4hAlignmentIntegration:
    """
    Exercise _check_4h_alignment through _evaluate_trade_opportunity by
    publishing synthetic signal bundles to a fully constructed EntryGroup.
    """

    def _make_bundle(self, symbol: str, direction_str: str, adx14: float = 28.0):
        """Build a minimal GroupSignalBundle carrying one strong indicator signal.

        adx14: regime ADX value embedded in the bundle's RegimeContext.
               LONG tests can use the default 28.0.
               SHORT tests that need to pass the SHORT quality gate (ADX > 30)
               should pass adx14=35.0 (or any value > 30).
        """
        from core.schemas import (
            CandidateSignal, Direction, GroupSignalBundle, RegimeContext,
        )
        from decimal import Decimal
        sig = CandidateSignal(
            group_id="indicators",
            symbol=symbol,
            timeframe="1h",
            direction=Direction.LONG if direction_str == "long" else Direction.SHORT,
            signal_type="indicator",
            quality_score=0.85,
            hypothesis_ref="H3-005",
            metadata={
                "rsi14": 60.0,
                "prev_rsi14": 50.0 if direction_str == "long" else 65.0,
                "volume_ratio": 1.5,
            },
        )
        # A matching candlestick signal so the gate fires
        csig = CandidateSignal(
            group_id="candlestick",
            symbol=symbol,
            timeframe="1h",
            direction=Direction.LONG if direction_str == "long" else Direction.SHORT,
            signal_type="candlestick",
            quality_score=0.75,
        )
        regime = RegimeContext(
            btc_macro="bull",
            trending=True,
            volatility_regime="normal",
            adx14=adx14,
            atr14=Decimal("1000"),
            atr14_vs_sma20=1.0,
        )
        now = datetime.now(timezone.utc)
        return GroupSignalBundle(
            group_id="indicators",
            symbol=symbol,
            timeframe="1h",
            timestamp=now,
            signals=[sig],
            regime=regime,
        ), GroupSignalBundle(
            group_id="candlestick",
            symbol=symbol,
            timeframe="1h",
            timestamp=now,
            signals=[csig],
        )

    @pytest.mark.asyncio
    async def test_long_aligned_proposal_published(self):
        """LONG with bullish 4H bars → CandidateTradeEvent is published."""
        from core.events import CandidateTradeEvent, EventBus, GroupSignalEvent
        from core.state import SystemState
        from core.schemas import ModeGate, Direction
        from groups.entry.group import EntryGroup

        captured = []
        state = SystemState(mode=ModeGate.RESEARCH)
        # Provide a non-zero entry price
        state.last_close_by_symbol["BTCUSDT"] = Decimal("70000")
        bus = EventBus()
        await bus.subscribe(CandidateTradeEvent, lambda e: captured.append(e))

        eg = EntryGroup(state=state, bus=bus)
        await eg.setup()

        # Wire bullish 4H bars → LONG is aligned
        eg._4h_bar_provider = lambda sym, n: _bullish_bars(n=60)

        ind_bundle, cs_bundle = self._make_bundle("BTCUSDT", "long")
        await bus.publish(GroupSignalEvent(bundle=ind_bundle))
        await bus.publish(GroupSignalEvent(bundle=cs_bundle))
        # Give the event loop a tick to process
        await asyncio.sleep(0)

        assert len(captured) >= 1, (
            "Expected at least one CandidateTradeEvent for aligned LONG."
        )

    @pytest.mark.asyncio
    async def test_long_misaligned_proposal_suppressed(self):
        """LONG with bearish 4H bars → CandidateTradeEvent is NOT published."""
        from core.events import CandidateTradeEvent, EventBus, GroupSignalEvent
        from core.state import SystemState
        from core.schemas import ModeGate
        from groups.entry.group import EntryGroup

        captured = []
        state = SystemState(mode=ModeGate.RESEARCH)
        state.last_close_by_symbol["BTCUSDT"] = Decimal("70000")
        bus = EventBus()
        await bus.subscribe(CandidateTradeEvent, lambda e: captured.append(e))

        eg = EntryGroup(state=state, bus=bus)
        await eg.setup()

        # Wire bearish 4H bars → LONG is misaligned
        eg._4h_bar_provider = lambda sym, n: _bearish_bars(n=60)

        ind_bundle, cs_bundle = self._make_bundle("BTCUSDT", "long")
        await bus.publish(GroupSignalEvent(bundle=ind_bundle))
        await bus.publish(GroupSignalEvent(bundle=cs_bundle))
        await asyncio.sleep(0)

        assert len(captured) == 0, (
            f"Expected no CandidateTradeEvent for misaligned LONG, "
            f"but got {len(captured)}."
        )

    @pytest.mark.asyncio
    async def test_short_aligned_proposal_published(self):
        """SHORT with bearish 4H bars → CandidateTradeEvent is published.

        The SHORT quality gate requires ADX > 30.  We pass adx14=35.0 to
        satisfy this condition.  The EMA50 < EMA200 bear-structure check is
        skipped because no _feature_provider is wired (provider is None →
        skipped gracefully, per the gate's documented fallback behaviour).
        """
        from core.events import CandidateTradeEvent, EventBus, GroupSignalEvent
        from core.state import SystemState
        from core.schemas import ModeGate
        from groups.entry.group import EntryGroup

        captured = []
        state = SystemState(mode=ModeGate.RESEARCH)
        state.last_close_by_symbol["BTCUSDT"] = Decimal("70000")
        bus = EventBus()
        await bus.subscribe(CandidateTradeEvent, lambda e: captured.append(e))

        eg = EntryGroup(state=state, bus=bus)
        await eg.setup()

        # Wire bearish 4H bars → SHORT is aligned on the multi-timeframe check.
        # ADX=35 satisfies the SHORT quality gate (requires ADX > 30).
        # No _feature_provider wired → EMA50/EMA200 check skipped gracefully.
        eg._4h_bar_provider = lambda sym, n: _bearish_bars(n=60)

        ind_bundle, cs_bundle = self._make_bundle("BTCUSDT", "short", adx14=35.0)
        await bus.publish(GroupSignalEvent(bundle=ind_bundle))
        await bus.publish(GroupSignalEvent(bundle=cs_bundle))
        await asyncio.sleep(0)

        assert len(captured) >= 1, (
            "Expected at least one CandidateTradeEvent for aligned SHORT "
            "(ADX=35 > 30, bearish 4H structure, EMA check skipped — provider not wired)."
        )

    @pytest.mark.asyncio
    async def test_short_misaligned_proposal_suppressed(self):
        """SHORT with bullish 4H bars → CandidateTradeEvent is NOT published."""
        from core.events import CandidateTradeEvent, EventBus, GroupSignalEvent
        from core.state import SystemState
        from core.schemas import ModeGate
        from groups.entry.group import EntryGroup

        captured = []
        state = SystemState(mode=ModeGate.RESEARCH)
        state.last_close_by_symbol["BTCUSDT"] = Decimal("70000")
        bus = EventBus()
        await bus.subscribe(CandidateTradeEvent, lambda e: captured.append(e))

        eg = EntryGroup(state=state, bus=bus)
        await eg.setup()

        # Wire bullish 4H bars → SHORT is misaligned
        eg._4h_bar_provider = lambda sym, n: _bullish_bars(n=60)

        ind_bundle, cs_bundle = self._make_bundle("BTCUSDT", "short")
        await bus.publish(GroupSignalEvent(bundle=ind_bundle))
        await bus.publish(GroupSignalEvent(bundle=cs_bundle))
        await asyncio.sleep(0)

        assert len(captured) == 0, (
            f"Expected no CandidateTradeEvent for misaligned SHORT, "
            f"but got {len(captured)}."
        )

    @pytest.mark.asyncio
    async def test_no_provider_does_not_suppress_proposal(self):
        """When _4h_bar_provider is None, proposals are NOT suppressed."""
        from core.events import CandidateTradeEvent, EventBus, GroupSignalEvent
        from core.state import SystemState
        from core.schemas import ModeGate
        from groups.entry.group import EntryGroup

        captured = []
        state = SystemState(mode=ModeGate.RESEARCH)
        state.last_close_by_symbol["BTCUSDT"] = Decimal("70000")
        bus = EventBus()
        await bus.subscribe(CandidateTradeEvent, lambda e: captured.append(e))

        eg = EntryGroup(state=state, bus=bus)
        await eg.setup()
        # Deliberately leave _4h_bar_provider = None

        ind_bundle, cs_bundle = self._make_bundle("BTCUSDT", "long")
        await bus.publish(GroupSignalEvent(bundle=ind_bundle))
        await bus.publish(GroupSignalEvent(bundle=cs_bundle))
        await asyncio.sleep(0)

        # Without a provider the check is skipped — proposal passes through
        assert len(captured) >= 1, (
            "Expected CandidateTradeEvent when provider is None (check skipped)."
        )
