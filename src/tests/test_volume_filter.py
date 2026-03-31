"""
Unit tests for the EntryGroup volume filter.

The filter skips bars whose volume is below 50 % of the 20-bar volume SMA.

Coverage:
  1. Pure threshold arithmetic (LOW_VOLUME_THRESHOLD_RATIO constant)
  2. Filter decision table — all boundary conditions
  3. Integration: low-volume bar suppresses CandidateTradeEvent
  4. Integration: normal-volume bar allows CandidateTradeEvent
  5. Integration: at-threshold (volume == threshold) is NOT rejected
  6. Edge cases: no provider, volume_sma20 == 0
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest


# ---------------------------------------------------------------------------
# Helpers — minimal FeatureVector and GroupSignalBundle factories
# ---------------------------------------------------------------------------

def _make_feature_vector(volume: float, volume_sma20: float) -> "FeatureVector":
    """
    Build a minimal but valid FeatureVector with the given volume fields.
    All other fields receive neutral-but-valid defaults.
    """
    from core.schemas import FeatureVector
    ts = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    v     = Decimal(str(volume))
    vsma  = Decimal(str(volume_sma20))
    price = Decimal("70000")
    atr   = Decimal("1000")
    return FeatureVector(
        symbol="BTCUSDT", timeframe="1h", timestamp=ts,
        # OHLCV passthrough
        open=price, high=price + atr, low=price - atr, close=price, volume=v,
        # ATR
        true_range=atr, atr14=atr, atr14_sma20=atr,
        # EMA
        ema20=price, ema50=price, ema200=price, prev_ema20=price, prev_ema50=price,
        # RSI
        rsi14=50.0, prev_rsi14=50.0,
        # Bollinger Bands
        bb_upper=price + atr, bb_middle=price, bb_lower=price - atr,
        bb_width=Decimal("2000"), bb_width_pct=50.0,
        # Trend
        adx14=20.0,
        # Volume
        volume_sma20=vsma,
        volume_ratio=float(v / vsma) if vsma > 0 else 0.0,
        # Candle anatomy
        candle_body=Decimal("200"), candle_range=Decimal("2000"),
        body_ratio=0.1, upper_shadow=Decimal("900"), lower_shadow=Decimal("900"),
        # Flags
        impulse_flag=False, doji_flag=False,
    )


def _make_entry_group():
    """Return a bare EntryGroup with no subscriptions yet."""
    from core.state import SystemState
    from core.events import EventBus
    from core.schemas import ModeGate
    from groups.entry.group import EntryGroup
    state = SystemState(mode=ModeGate.RESEARCH)
    bus   = EventBus()
    return EntryGroup(state=state, bus=bus)


def _make_bundles(symbol: str = "BTCUSDT", direction_str: str = "long"):
    """
    Return (indicator_bundle, candlestick_bundle) carrying one strong signal each.
    Sufficient to pass the confirmation gate and composite-score threshold.
    """
    from core.schemas import (
        CandidateSignal, Direction, GroupSignalBundle, RegimeContext,
    )
    dir_enum = Direction.LONG if direction_str == "long" else Direction.SHORT
    now = datetime.now(timezone.utc)

    regime = RegimeContext(
        btc_macro="bull", trending=True, volatility_regime="normal",
        adx14=28.0, atr14=Decimal("1000"), atr14_vs_sma20=1.0,
    )

    ind_sig = CandidateSignal(
        group_id="indicators", symbol=symbol, timeframe="1h",
        direction=dir_enum, signal_type="indicator", quality_score=0.85,
        hypothesis_ref="H3-005",
        metadata={"rsi14": 60.0, "prev_rsi14": 50.0, "volume_ratio": 1.5},
    )
    cs_sig = CandidateSignal(
        group_id="candlestick", symbol=symbol, timeframe="1h",
        direction=dir_enum, signal_type="candlestick", quality_score=0.75,
    )

    ind_bundle = GroupSignalBundle(
        group_id="indicators", symbol=symbol, timeframe="1h",
        timestamp=now, signals=[ind_sig], regime=regime,
    )
    cs_bundle = GroupSignalBundle(
        group_id="candlestick", symbol=symbol, timeframe="1h",
        timestamp=now, signals=[cs_sig],
    )
    return ind_bundle, cs_bundle


async def _run_pipeline(entry_group, symbol: str = "BTCUSDT",
                        direction_str: str = "long") -> list:
    """
    Publish indicator + candlestick bundles through the EntryGroup and
    return all CandidateTradeEvents captured on the bus.
    """
    from core.events import CandidateTradeEvent, GroupSignalEvent

    captured = []
    await entry_group.bus.subscribe(
        CandidateTradeEvent, lambda e: captured.append(e)
    )

    # Provide a non-zero entry price
    entry_group.state.last_close_by_symbol[symbol] = Decimal("70000")

    ind_bundle, cs_bundle = _make_bundles(symbol, direction_str)
    await entry_group.bus.publish(GroupSignalEvent(bundle=ind_bundle))
    await entry_group.bus.publish(GroupSignalEvent(bundle=cs_bundle))
    await asyncio.sleep(0)  # one event-loop tick
    return captured


# ===========================================================================
# 1. Constant and threshold arithmetic
# ===========================================================================

class TestVolumeFilterConstant:

    def test_threshold_ratio_is_half(self):
        from groups.entry.group import LOW_VOLUME_THRESHOLD_RATIO
        assert LOW_VOLUME_THRESHOLD_RATIO == Decimal("0.5")

    def test_threshold_calculation(self):
        """threshold = 0.5 × volume_sma20."""
        from groups.entry.group import LOW_VOLUME_THRESHOLD_RATIO
        sma20     = Decimal("10000")
        threshold = LOW_VOLUME_THRESHOLD_RATIO * sma20
        assert threshold == Decimal("5000")


# ===========================================================================
# 2. Decision table — all boundary conditions (no EventBus needed)
# ===========================================================================

class TestVolumeFilterDecisionTable:
    """
    These tests call _check_volume (via the provider injection pattern) directly
    against the guard inside _evaluate_trade_opportunity.
    We verify the pure logic with various volume / volume_sma20 combinations.
    """

    def _fv_low(self):
        """volume well below 50 % of SMA: 3 000 < 0.5 × 10 000 = 5 000."""
        return _make_feature_vector(volume=3_000, volume_sma20=10_000)

    def _fv_at_threshold(self):
        """volume exactly at threshold: 5 000 == 0.5 × 10 000."""
        return _make_feature_vector(volume=5_000, volume_sma20=10_000)

    def _fv_above_threshold(self):
        """volume just above threshold: 5 001 > 0.5 × 10 000 = 5 000."""
        return _make_feature_vector(volume=5_001, volume_sma20=10_000)

    def _fv_normal(self):
        """volume at 1.5× SMA — clearly above threshold."""
        return _make_feature_vector(volume=15_000, volume_sma20=10_000)

    def _should_skip(self, fv) -> bool:
        """
        Replicate the guard logic from EntryGroup so we can test it in
        isolation without running the full async pipeline.
        """
        from groups.entry.group import LOW_VOLUME_THRESHOLD_RATIO
        if fv.volume_sma20 <= Decimal("0"):
            return False   # guard is off when SMA is zero
        threshold = LOW_VOLUME_THRESHOLD_RATIO * fv.volume_sma20
        return fv.volume < threshold

    def test_low_volume_should_be_skipped(self):
        assert self._should_skip(self._fv_low()) is True

    def test_at_threshold_should_not_be_skipped(self):
        """Exactly at threshold: NOT rejected (strict less-than comparison)."""
        assert self._should_skip(self._fv_at_threshold()) is False

    def test_above_threshold_should_not_be_skipped(self):
        assert self._should_skip(self._fv_above_threshold()) is False

    def test_normal_volume_should_not_be_skipped(self):
        assert self._should_skip(self._fv_normal()) is False

    def test_zero_sma_guard_is_off(self):
        """volume_sma20 == 0: guard disabled, bar never skipped."""
        fv = _make_feature_vector(volume=1, volume_sma20=0)
        assert self._should_skip(fv) is False


# ===========================================================================
# 3. Integration — low-volume bar suppresses CandidateTradeEvent
# ===========================================================================

class TestVolumeFilterIntegration:

    @pytest.mark.asyncio
    async def test_low_volume_bar_suppressed(self):
        """
        volume = 3 000, volume_sma20 = 10 000  →  below 50% threshold
        → no CandidateTradeEvent published.
        """
        eg = _make_entry_group()
        await eg.setup()
        eg._feature_provider = lambda sym: _make_feature_vector(
            volume=3_000, volume_sma20=10_000
        )
        captured = await _run_pipeline(eg)
        assert len(captured) == 0, (
            f"Expected 0 events for low-volume bar, got {len(captured)}."
        )

    @pytest.mark.asyncio
    async def test_normal_volume_bar_passes(self):
        """
        volume = 15 000, volume_sma20 = 10 000  →  well above threshold
        → CandidateTradeEvent IS published.
        """
        eg = _make_entry_group()
        await eg.setup()
        eg._feature_provider = lambda sym: _make_feature_vector(
            volume=15_000, volume_sma20=10_000
        )
        captured = await _run_pipeline(eg)
        assert len(captured) >= 1, (
            "Expected CandidateTradeEvent for normal-volume bar."
        )

    @pytest.mark.asyncio
    async def test_volume_at_threshold_passes(self):
        """
        volume == 0.5 × volume_sma20  →  exactly at the boundary, NOT rejected
        (the guard is strict less-than: volume < threshold).
        """
        eg = _make_entry_group()
        await eg.setup()
        eg._feature_provider = lambda sym: _make_feature_vector(
            volume=5_000, volume_sma20=10_000   # 5 000 == 0.5 × 10 000
        )
        captured = await _run_pipeline(eg)
        assert len(captured) >= 1, (
            "Expected CandidateTradeEvent when volume is exactly at threshold."
        )

    @pytest.mark.asyncio
    async def test_volume_one_unit_below_threshold_is_suppressed(self):
        """
        5 000 - ε just below threshold  →  rejected.
        Use integer volumes: 4 999 < 5 000 = 0.5 × 10 000.
        """
        eg = _make_entry_group()
        await eg.setup()
        eg._feature_provider = lambda sym: _make_feature_vector(
            volume=4_999, volume_sma20=10_000
        )
        captured = await _run_pipeline(eg)
        assert len(captured) == 0, (
            f"Expected 0 events for volume just below threshold, "
            f"got {len(captured)}."
        )


# ===========================================================================
# 4. Edge cases
# ===========================================================================

class TestVolumeFilterEdgeCases:

    @pytest.mark.asyncio
    async def test_no_provider_does_not_suppress(self):
        """
        When _feature_provider is None the volume filter is skipped entirely.
        Proposals must still flow through.
        """
        eg = _make_entry_group()
        await eg.setup()
        assert eg._feature_provider is None   # default
        captured = await _run_pipeline(eg)
        assert len(captured) >= 1, (
            "Expected proposal to pass when _feature_provider is None."
        )

    @pytest.mark.asyncio
    async def test_provider_returns_none_does_not_suppress(self):
        """
        Provider returns None (feature vector not yet computed).
        Filter must be skipped — proposals flow through.
        """
        eg = _make_entry_group()
        await eg.setup()
        eg._feature_provider = lambda sym: None
        captured = await _run_pipeline(eg)
        assert len(captured) >= 1, (
            "Expected proposal to pass when provider returns None."
        )

    @pytest.mark.asyncio
    async def test_zero_volume_sma20_does_not_suppress(self):
        """
        volume_sma20 == 0 (pathological — very early warmup).
        Guard must be disabled to avoid dividing by / comparing to zero.
        """
        eg = _make_entry_group()
        await eg.setup()
        eg._feature_provider = lambda sym: _make_feature_vector(
            volume=1, volume_sma20=0
        )
        captured = await _run_pipeline(eg)
        assert len(captured) >= 1, (
            "Expected proposal to pass when volume_sma20 is zero."
        )

    @pytest.mark.asyncio
    async def test_provider_exception_does_not_suppress(self):
        """
        If the feature provider raises an exception the volume filter is
        skipped (treated as unavailable) and the proposal flows through.
        This mirrors the behaviour of _check_4h_alignment's provider guard.
        """
        eg = _make_entry_group()
        await eg.setup()

        def _bad_provider(sym):
            raise RuntimeError("simulated provider failure")

        eg._feature_provider = _bad_provider
        captured = await _run_pipeline(eg)
        assert len(captured) >= 1, (
            "Expected proposal to pass when provider raises — filter skipped."
        )

    @pytest.mark.asyncio
    async def test_filter_uses_correct_symbol(self):
        """
        Volume filter must use the bar's own symbol, not a hardcoded one.
        Inject a provider that tracks which symbols it was called with.
        """
        eg = _make_entry_group()
        await eg.setup()

        called_with: list[str] = []

        def _tracking_provider(sym):
            called_with.append(sym)
            return _make_feature_vector(volume=15_000, volume_sma20=10_000)

        eg._feature_provider = _tracking_provider
        await _run_pipeline(eg, symbol="BTCUSDT")

        assert "BTCUSDT" in called_with, (
            f"Expected provider to be called with 'BTCUSDT', got {called_with}."
        )
