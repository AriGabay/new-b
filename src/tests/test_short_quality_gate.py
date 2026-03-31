"""
Unit tests for the SHORT entry quality gate in EntryGroup.

Gate conditions (applied to SHORT proposals only; LONG is unaffected):
  1. ADX14 > 30  — require strong directional trend before shorting.
  2. EMA50 < EMA200 — require confirmed bear structure (death cross).

Rejection log messages:
  - "SHORT rejected: weak trend (ADX={adx14:.1f} <= 30)"
  - "SHORT rejected: no bear structure (EMA50={ema50:.0f} >= EMA200={ema200:.0f})"

Test categories:
  A. ADX gate — reject SHORT when ADX ≤ 30
  B. Bear structure gate — reject SHORT when EMA50 ≥ EMA200
  C. Both conditions pass — SHORT proceeds to panel
  D. LONG is not affected by this gate
  E. Graceful fallback — gate skipped when provider is None / raises
  F. Boundary conditions — ADX exactly at 30, EMA50 exactly equal to EMA200
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events import CandidateTradeEvent
from core.schemas import (
    Direction,
    FeatureVector,
    GroupSignalBundle,
    IndicatorSignal,
    RegimeContext,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ts() -> datetime:
    return datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def _make_feature_vector(
    close: float = 45_000.0,
    ema50: float = 44_000.0,
    ema200: float = 48_000.0,
) -> FeatureVector:
    """Minimal FeatureVector for testing.  ema50 < ema200 = bear structure by default."""
    p = Decimal(str(close))
    atr = Decimal("1000")
    return FeatureVector(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=_ts(),
        open=p,
        high=p + Decimal("500"),
        low=p - Decimal("500"),
        close=p,
        volume=Decimal("10000"),
        true_range=atr,
        atr14=atr,
        atr14_sma20=atr,
        ema20=p,
        ema50=Decimal(str(ema50)),
        ema200=Decimal(str(ema200)),
        prev_ema20=p,
        prev_ema50=Decimal(str(ema50)),
        rsi14=38.0,          # RSI falling → SHORT-aligned
        prev_rsi14=45.0,
        bb_upper=p + Decimal("2000"),
        bb_middle=p,
        bb_lower=p - Decimal("2000"),
        bb_width=Decimal("4000"),
        bb_width_pct=50.0,
        adx14=35.0,
        volume_sma20=Decimal("8000"),
        volume_ratio=1.5,
        candle_body=Decimal("300"),
        candle_range=Decimal("1000"),
        body_ratio=0.3,
        upper_shadow=Decimal("350"),
        lower_shadow=Decimal("350"),
        impulse_flag=False,
        doji_flag=False,
    )


def _make_regime(adx14: float, btc_macro: str = "bear") -> RegimeContext:
    return RegimeContext(
        btc_macro=btc_macro,
        trending=adx14 > 25,
        volatility_regime="normal",
        adx14=adx14,
        atr14=Decimal("1000"),
        atr14_vs_sma20=1.0,
    )


def _make_short_indicator_signal() -> IndicatorSignal:
    return IndicatorSignal(
        group_id="GroupID.INDICATORS",
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=_ts(),
        direction=Direction.SHORT,
        signal_type="indicator",
        quality_score=0.8,
        indicator_values={
            "rsi14": 38.0,
            "prev_rsi14": 45.0,
        },
    )


def _make_long_indicator_signal() -> IndicatorSignal:
    return IndicatorSignal(
        group_id="GroupID.INDICATORS",
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=_ts(),
        direction=Direction.LONG,
        signal_type="indicator",
        quality_score=0.8,
        indicator_values={
            "rsi14": 65.0,
            "prev_rsi14": 55.0,
        },
    )


def _make_pending_bundles(
    adx14: float,
    direction: Direction = Direction.SHORT,
    btc_macro: str = "bear",
) -> dict:
    """
    Build the dict that EntryGroup._pending_bundles["BTCUSDT"] is pre-populated with.
    Includes both an 'indicators' bundle (with the signal) and an empty
    'candlestick' bundle (required to satisfy the has_indicators+has_candlestick trigger).
    """
    signal = (
        _make_short_indicator_signal()
        if direction == Direction.SHORT
        else _make_long_indicator_signal()
    )
    regime = _make_regime(adx14=adx14, btc_macro=btc_macro)

    indicators_bundle = GroupSignalBundle(
        group_id="GroupID.INDICATORS",
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=_ts(),
        signals=[signal],
        regime=regime,
    )
    # Candlestick bundle must exist to satisfy the has_candlestick trigger;
    # no signals needed — EntryGroup handles empty candlestick bundles fine.
    candlestick_bundle = GroupSignalBundle(
        group_id="GroupID.CANDLESTICK",
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=_ts(),
        signals=[],
        regime=None,
    )
    return {
        "GroupID.INDICATORS": indicators_bundle,
        "GroupID.CANDLESTICK": candlestick_bundle,
    }


def _build_entry_group(
    feature_vector: FeatureVector | None = None,
    provider_raises: bool = False,
) -> tuple:
    """
    Construct an EntryGroup with:
      - a mock SystemState whose last_close_by_symbol returns a valid price,
      - a mock EventBus that captures published events,
      - an optional feature_provider returning the given FeatureVector.

    Returns (group, published_events_list).
    """
    from groups.entry.group import EntryGroup

    state = MagicMock()
    state.last_close_by_symbol = {"BTCUSDT": Decimal("45000")}

    published_events: list = []

    async def _capture(event) -> None:  # noqa: RUF029
        published_events.append(event)

    bus = MagicMock()
    bus.subscribe = AsyncMock()
    bus.publish = _capture          # real async func, not AsyncMock (avoids side-effect issues)

    group = EntryGroup(state, bus)

    if provider_raises:
        def _raising_provider(sym: str) -> FeatureVector:
            raise RuntimeError("provider failure injected by test")
        group._feature_provider = _raising_provider
    elif feature_vector is not None:
        group._feature_provider = lambda sym: feature_vector

    # Leave _4h_bar_provider = None  → 4H alignment check is skipped (returns True).
    # Leave _historian = None         → historian block is skipped.
    # Leave _critic    = None         → critic block is skipped.

    return group, published_events


async def _run_evaluation(
    group,
    adx14: float,
    direction: Direction = Direction.SHORT,
    btc_macro: str = "bear",
) -> None:
    """Pre-populate bundles and call _evaluate_trade_opportunity."""
    group._pending_bundles["BTCUSDT"] = _make_pending_bundles(
        adx14=adx14,
        direction=direction,
        btc_macro=btc_macro,
    )
    await group._evaluate_trade_opportunity("BTCUSDT")


# ---------------------------------------------------------------------------
# A. ADX gate — SHORT rejected when ADX ≤ 30
# ---------------------------------------------------------------------------

class TestShortADXGate:
    """SHORT is blocked whenever regime.adx14 ≤ 30."""

    @pytest.mark.asyncio
    async def test_short_rejected_when_adx_is_20(self):
        """ADX=20 is well below threshold — SHORT must be rejected."""
        fv = _make_feature_vector(ema50=44_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=20.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, (
            "SHORT with ADX=20 should be rejected (weak trend)"
        )

    @pytest.mark.asyncio
    async def test_short_rejected_when_adx_is_25(self):
        """ADX=25 — trending but below threshold — SHORT must be rejected."""
        fv = _make_feature_vector(ema50=44_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=25.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, (
            "SHORT with ADX=25 should be rejected (trend not strong enough)"
        )

    @pytest.mark.asyncio
    async def test_short_rejected_when_adx_exactly_30(self):
        """ADX=30.0 is the boundary — condition is strict >, so 30.0 must be rejected."""
        fv = _make_feature_vector(ema50=44_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=30.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, (
            "SHORT with ADX=30.0 should be rejected (> 30 required, not >= 30)"
        )

    @pytest.mark.asyncio
    async def test_short_rejected_when_adx_zero(self):
        """ADX=0 (no data) — SHORT must be rejected."""
        fv = _make_feature_vector(ema50=44_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=0.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, "SHORT with ADX=0 should be rejected"

    @pytest.mark.asyncio
    async def test_short_passes_adx_gate_when_adx_just_above_30(self):
        """ADX=30.01 is just over threshold — ADX gate should pass.

        Bear structure (EMA50 < EMA200) is also satisfied so proposal proceeds.
        """
        fv = _make_feature_vector(ema50=44_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=30.01)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "SHORT with ADX=30.01 and EMA50<EMA200 should pass to the panel"
        )


# ---------------------------------------------------------------------------
# B. Bear structure gate — SHORT rejected when EMA50 ≥ EMA200
# ---------------------------------------------------------------------------

class TestShortBearStructureGate:
    """SHORT is blocked whenever EMA50 >= EMA200 (bull structure or neutral)."""

    @pytest.mark.asyncio
    async def test_short_rejected_when_ema50_above_ema200(self):
        """EMA50=50000 > EMA200=47000 — bull structure (golden cross) → reject."""
        fv = _make_feature_vector(ema50=50_000, ema200=47_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=35.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, (
            "SHORT with EMA50 > EMA200 (bull structure) should be rejected"
        )

    @pytest.mark.asyncio
    async def test_short_rejected_when_ema50_equals_ema200(self):
        """EMA50 == EMA200 — no confirmed structure → reject (condition is strict <)."""
        fv = _make_feature_vector(ema50=48_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=35.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, (
            "SHORT with EMA50 == EMA200 should be rejected (no confirmed death cross)"
        )

    @pytest.mark.asyncio
    async def test_short_passes_when_ema50_just_below_ema200(self):
        """EMA50=47999 < EMA200=48000 — confirmed death cross → bear structure satisfied."""
        fv = _make_feature_vector(ema50=47_999, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=35.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "SHORT with EMA50 just below EMA200 and ADX>30 should pass to panel"
        )

    @pytest.mark.asyncio
    async def test_short_rejected_with_wide_ema_gap_bull(self):
        """EMA50=55000 >> EMA200=40000 — strong bull structure → reject even with ADX=60."""
        fv = _make_feature_vector(ema50=55_000, ema200=40_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=60.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, (
            "SHORT with strongly bullish EMA structure must be rejected "
            "regardless of ADX strength"
        )


# ---------------------------------------------------------------------------
# C. Both conditions satisfied — SHORT proceeds to panel
# ---------------------------------------------------------------------------

class TestShortGatePasses:
    """When ADX>30 AND EMA50<EMA200, SHORT should not be blocked by this gate."""

    @pytest.mark.asyncio
    async def test_short_passes_both_conditions(self):
        """ADX=35 > 30, EMA50=44000 < EMA200=48000 → both conditions met → pass."""
        fv = _make_feature_vector(ema50=44_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=35.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "SHORT with ADX>30 and EMA50<EMA200 should produce a CandidateTradeEvent"
        )

    @pytest.mark.asyncio
    async def test_short_passes_with_strong_adx_large_ema_gap(self):
        """ADX=50, EMA50=40000, EMA200=50000 — strong bear setup → pass."""
        fv = _make_feature_vector(ema50=40_000, ema200=50_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=50.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "SHORT with strong ADX and clear death cross should proceed to panel"
        )

    @pytest.mark.asyncio
    async def test_candidate_event_direction_is_short(self):
        """The CandidateTradeEvent that passes the gate must have direction=SHORT."""
        fv = _make_feature_vector(ema50=44_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=35.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1
        proposal = trade_events[0].proposal
        assert proposal.direction == Direction.SHORT, (
            f"Expected direction=SHORT, got {proposal.direction}"
        )


# ---------------------------------------------------------------------------
# D. LONG is not affected by this gate
# ---------------------------------------------------------------------------

class TestLongNotAffected:
    """The SHORT quality gate must have zero effect on LONG proposals."""

    @pytest.mark.asyncio
    async def test_long_passes_when_adx_is_15(self):
        """LONG with ADX=15 (would block a SHORT) must not be blocked by the SHORT gate.

        Using btc_macro='bull' so step 5b (bear regime LONG block) does not fire.
        """
        # ema50 > ema200 = bull structure (would block SHORT, must not block LONG)
        fv = _make_feature_vector(ema50=50_000, ema200=47_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=15.0, direction=Direction.LONG, btc_macro="bull")
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "LONG with low ADX should not be blocked by the SHORT quality gate"
        )

    @pytest.mark.asyncio
    async def test_long_passes_when_ema50_above_ema200(self):
        """LONG with EMA50 > EMA200 (bull structure) must not be blocked by SHORT gate."""
        fv = _make_feature_vector(ema50=52_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=20.0, direction=Direction.LONG, btc_macro="bull")
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "LONG must not be blocked by the SHORT quality gate regardless of EMA values"
        )

    @pytest.mark.asyncio
    async def test_long_direction_in_passed_event(self):
        """CandidateTradeEvent from a LONG proposal must report direction=LONG."""
        fv = _make_feature_vector(ema50=50_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        await _run_evaluation(group, adx14=25.0, direction=Direction.LONG, btc_macro="bull")
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1
        assert trade_events[0].proposal.direction == Direction.LONG


# ---------------------------------------------------------------------------
# E. Graceful fallback — gate behaviour without a feature provider
# ---------------------------------------------------------------------------

class TestShortGateGracefulFallback:
    """When the feature_provider is unavailable, condition 2 (EMA check) is skipped.
    Condition 1 (ADX) still applies because it comes from regime context."""

    @pytest.mark.asyncio
    async def test_adx_gate_still_applies_when_provider_is_none(self):
        """Without a feature provider, ADX gate still fires and rejects weak-ADX SHORTs."""
        group, events = _build_entry_group(feature_vector=None)
        # No provider → feature_provider is None
        assert group._feature_provider is None
        await _run_evaluation(group, adx14=20.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, (
            "ADX gate must still apply even when feature_provider is None"
        )

    @pytest.mark.asyncio
    async def test_ema_check_skipped_when_provider_is_none(self):
        """Without a feature provider, EMA check is skipped — SHORT with ADX>30 passes."""
        group, events = _build_entry_group(feature_vector=None)
        assert group._feature_provider is None
        # ADX=35 > 30 — ADX gate passes.
        # No EMA check → proposal should proceed to panel.
        await _run_evaluation(group, adx14=35.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "SHORT with ADX>30 and no provider (EMA check skipped) should pass gate"
        )

    @pytest.mark.asyncio
    async def test_ema_check_skipped_when_provider_raises(self):
        """When the feature_provider raises, EMA check is skipped gracefully."""
        group, events = _build_entry_group(provider_raises=True)
        # ADX=35 > 30, provider raises but we skip gracefully
        await _run_evaluation(group, adx14=35.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "SHORT should proceed when feature_provider raises (EMA check skipped)"
        )

    @pytest.mark.asyncio
    async def test_adx_gate_applies_even_when_provider_raises(self):
        """ADX gate must still reject weak-ADX SHORTs even if provider raises."""
        group, events = _build_entry_group(provider_raises=True)
        await _run_evaluation(group, adx14=25.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 0, (
            "ADX gate must apply regardless of feature_provider state"
        )

    @pytest.mark.asyncio
    async def test_provider_returns_none(self):
        """If provider returns None (e.g. still warming up), EMA check is skipped."""
        group, events = _build_entry_group(feature_vector=None)
        # Set a provider that returns None (warm-up phase)
        group._feature_provider = lambda sym: None
        await _run_evaluation(group, adx14=35.0)
        trade_events = [e for e in events if isinstance(e, CandidateTradeEvent)]
        assert len(trade_events) == 1, (
            "SHORT with ADX>30 and provider returning None should pass gate"
        )


# ---------------------------------------------------------------------------
# F. Combined rejection log message content
# ---------------------------------------------------------------------------

class TestShortGateLogMessages:
    """Verify that the correct log message string is emitted for each rejection."""

    @pytest.mark.asyncio
    async def test_adx_rejection_log_contains_adx_value(self, caplog):
        """ADX rejection log must include the actual ADX value."""
        import logging
        fv = _make_feature_vector(ema50=44_000, ema200=48_000)
        group, events = _build_entry_group(feature_vector=fv)
        with caplog.at_level(logging.INFO, logger="groups.entry.group"):
            await _run_evaluation(group, adx14=22.5)
        assert any(
            "SHORT rejected" in r.message and "ADX=22.5" in r.message
            for r in caplog.records
        ), f"Expected ADX rejection log; got: {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_ema_rejection_log_contains_ema_values(self, caplog):
        """EMA rejection log must include EMA50 and EMA200 values."""
        import logging
        # EMA50=50000 > EMA200=47000 — bull structure
        fv = _make_feature_vector(ema50=50_000, ema200=47_000)
        group, events = _build_entry_group(feature_vector=fv)
        with caplog.at_level(logging.INFO, logger="groups.entry.group"):
            await _run_evaluation(group, adx14=40.0)
        assert any(
            "no bear structure" in r.message
            and "EMA50=50000" in r.message
            and "EMA200=47000" in r.message
            for r in caplog.records
        ), f"Expected EMA rejection log; got: {[r.message for r in caplog.records]}"
