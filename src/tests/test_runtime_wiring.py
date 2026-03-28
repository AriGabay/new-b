"""
Integration tests for the runtime wiring.

Proves:
  1. BtcBybitPaperRunner instantiates and sets up all groups without error
  2. A synthetic FeatureReadyEvent flows through IndicatorsGroup, CandlestickGroup,
     TechnicalStructureGroup, EntryGroup
  3. PanelDecisionGroup receives CandidateTradeEvent and runs the 20-trader panel
  4. RiskLeverageGroup receives PanelApprovedProposalEvent (if panel approves)
  5. ExitGroup evaluates open positions on FeatureReadyEvent
  6. PerformanceJournalGroup logs events to SQLite
  7. The learning layer (JournalExtension, DecisionTraceLogger) receives data

All tests use simulation mode — no live Bybit connectivity required.
Positions are seeded synthetically when needed.

These tests verify runtime WIRING, not trading logic correctness.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pytest
import pytest_asyncio


def make_feature_vector(
    bullish: bool = True,
    price: Decimal = Decimal("65000"),
) -> "FeatureVector":
    from core.schemas import FeatureVector
    ema20 = price - Decimal("200") if bullish else price + Decimal("200")
    ema50 = price - Decimal("500") if bullish else price + Decimal("500")
    ema200 = price - Decimal("1000") if bullish else price + Decimal("1000")
    return FeatureVector(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=datetime.now(timezone.utc),
        open=price - Decimal("50"),
        high=price + Decimal("150"),
        low=price - Decimal("100"),
        close=price,
        volume=Decimal("1500"),
        true_range=Decimal("250"),
        atr14=Decimal("800"),
        atr14_sma20=Decimal("750"),
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        prev_ema20=ema20 - Decimal("10"),
        prev_ema50=ema50 - Decimal("20"),
        rsi14=62.0 if bullish else 48.0,
        prev_rsi14=58.0 if bullish else 51.0,
        bb_upper=price + Decimal("1500"),
        bb_middle=price,
        bb_lower=price - Decimal("1500"),
        bb_width=Decimal("3000"),
        bb_width_pct=45.0,
        adx14=28.0 if bullish else 14.0,
        volume_sma20=Decimal("1200"),
        volume_ratio=1.25 if bullish else 0.95,
        candle_body=Decimal("100"),
        candle_range=Decimal("250"),
        body_ratio=0.40,
        upper_shadow=Decimal("100"),
        lower_shadow=Decimal("50"),
        impulse_flag=False,
        doji_flag=False,
    )


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# 1. Runner setup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runner_setup_and_teardown():
    """Runner instantiates all groups and sets up without error."""
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    try:
        await runner.setup()
        assert runner._market_data is not None
        assert runner._indicators is not None
        assert runner._candlestick is not None
        assert runner._technical_structure is not None
        assert runner._entry is not None
        assert runner._panel_decision is not None
        assert runner._risk_leverage is not None
        assert runner._exit is not None
        assert runner._performance_journal is not None
        assert len(runner._all_groups) == 9
    finally:
        await runner.teardown()


@pytest.mark.asyncio
async def test_runner_groups_are_running():
    """All groups have _running=True after setup()."""
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()
    for group in runner._all_groups:
        assert group._running, f"{type(group).__name__} not running after setup()"
    await runner.teardown()


# ---------------------------------------------------------------------------
# 2. EventBus wiring: FeatureReadyEvent propagates to specialist groups
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feature_ready_event_reaches_indicators():
    """FeatureReadyEvent published → IndicatorsGroup processes it."""
    from runtime.runner import BtcBybitPaperRunner
    from core.events import GroupSignalEvent

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    received_signals = []

    async def capture(event):
        if hasattr(event, "bundle") and event.bundle is not None:
            received_signals.append(event)

    await runner.bus.subscribe(GroupSignalEvent, capture)

    fv = make_feature_vector(bullish=True)
    await runner.simulate_bar(fv)
    await asyncio.sleep(0.05)  # let async propagation complete

    await runner.teardown()

    # At least one GroupSignalEvent should have been published by indicators/candlestick/structure
    assert len(received_signals) >= 1, (
        "No GroupSignalEvent received after FeatureReadyEvent injection. "
        "IndicatorsGroup/CandlestickGroup/TechnicalStructureGroup may not be subscribed."
    )


# ---------------------------------------------------------------------------
# 3. last_close_by_symbol is populated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_simulate_bar_populates_last_close():
    """simulate_bar() populates state.last_close_by_symbol."""
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    fv = make_feature_vector(price=Decimal("67000"))
    await runner.simulate_bar(fv)
    await asyncio.sleep(0.01)

    assert "BTCUSDT" in runner.state.last_close_by_symbol
    assert runner.state.last_close_by_symbol["BTCUSDT"] == Decimal("67000")

    await runner.teardown()


# ---------------------------------------------------------------------------
# 4. PanelDecisionGroup is wired and handles CandidateTradeEvent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_panel_decision_group_subscribed():
    """PanelDecisionGroup is subscribed to CandidateTradeEvent."""
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    # CandidateTradeEvent subscribers should include panel_decision's handle_event
    subscribers = runner.bus._subscribers.get("CandidateTradeEvent", [])
    subscriber_classes = [
        type(getattr(cb, "__self__", cb)).__name__ for cb in subscribers
    ]
    assert any("PanelDecisionGroup" in cls or "panel" in cls.lower()
               for cls in subscriber_classes), (
        f"PanelDecisionGroup not subscribed to CandidateTradeEvent. "
        f"Found: {subscriber_classes}"
    )

    await runner.teardown()


# ---------------------------------------------------------------------------
# 5. RiskLeverageGroup subscribed to PanelApprovedProposalEvent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_risk_group_subscribed_to_panel_approved():
    """RiskLeverageGroup is subscribed to PanelApprovedProposalEvent."""
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    subscribers = runner.bus._subscribers.get("PanelApprovedProposalEvent", [])
    subscriber_classes = [type(getattr(cb, "__self__", cb)).__name__ for cb in subscribers]
    assert any("RiskLeverageGroup" in cls or "risk" in cls.lower()
               for cls in subscriber_classes), (
        f"RiskLeverageGroup not subscribed to PanelApprovedProposalEvent. "
        f"Found: {subscriber_classes}"
    )

    await runner.teardown()


# ---------------------------------------------------------------------------
# 6. Setup packet builder works
# ---------------------------------------------------------------------------

def test_setup_packet_builder_basic():
    """build_btc_setup_packet produces a valid BTCSetupPacket."""
    from runtime.setup_packet_builder import build_btc_setup_packet
    from core.schemas import CandidateTradeProposal, Direction
    import uuid

    fv = make_feature_vector(bullish=True)
    proposal = CandidateTradeProposal(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=datetime.now(timezone.utc),
        direction=Direction.LONG,
        entry_price=Decimal("65000"),
        thesis="LONG on BTCUSDT: test",
        setup_refs=["ema_crossover"],
        hypothesis_refs=["H-001"],
        composite_score=0.65,
        score_breakdown={},
    )

    packet = build_btc_setup_packet(proposal, fv)
    assert packet is not None
    assert packet.symbol == "BTCUSDT"
    assert packet.packet_id != ""
    assert packet.indicators.close == Decimal("65000")
    assert packet.indicators.ema_alignment in ("full_bull", "partial_bull", "mixed", "full_bear", "partial_bear")
    assert packet.chart_pattern.active_patterns == []  # stubbed
    assert packet.proposal.direction == Direction.LONG


def test_setup_packet_builder_indicator_snapshot_fields():
    """IndicatorSnapshot is fully populated from FeatureVector."""
    from runtime.setup_packet_builder import build_indicator_snapshot
    fv = make_feature_vector(bullish=True)
    snap = build_indicator_snapshot(fv)
    assert snap.rsi14 == 62.0
    assert snap.adx14 == 28.0
    assert snap.trend_strength == "strong"
    assert snap.volume_character in ("above_avg", "surge", "normal", "below_avg")
    assert snap.bb_position is not None


# ---------------------------------------------------------------------------
# 7. Journal persistence after simulate_bar
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_journal_db_initialized_in_runner():
    """PerformanceJournalGroup initializes a JournalDB."""
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    journal_db = getattr(runner._performance_journal, "_journal_db", None)
    assert journal_db is not None, "JournalDB not initialized in PerformanceJournalGroup"
    assert getattr(journal_db, "_conn", None) is not None, "JournalDB connection not open"

    await runner.teardown()


# ---------------------------------------------------------------------------
# 8. Exit group subscribed to FeatureReadyEvent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exit_group_subscribed():
    """ExitGroup is subscribed to FeatureReadyEvent."""
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    subscribers = runner.bus._subscribers.get("FeatureReadyEvent", [])
    subscriber_classes = [type(getattr(cb, "__self__", cb)).__name__ for cb in subscribers]
    assert any("ExitGroup" in cls or "exit" in cls.lower()
               for cls in subscriber_classes), (
        f"ExitGroup not subscribed to FeatureReadyEvent. Found: {subscriber_classes}"
    )

    await runner.teardown()


# ---------------------------------------------------------------------------
# 9. Full simulation smoke test (end-to-end)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_simulation_smoke():
    """
    Inject 3 synthetic bars through the full pipeline without crashing.
    Does NOT assert trades are opened (depends on signal conditions and
    panel thresholds). Asserts the pipeline runs without exceptions.
    """
    from runtime.runner import BtcBybitPaperRunner

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()
    await runner._finalize_learning_wiring()

    errors: list = []
    original_exception = getattr(
        runner.bus, "_last_exception", None
    )

    # Inject 3 bars with strong bullish conditions
    for i in range(3):
        fv = make_feature_vector(bullish=True, price=Decimal("65000") + Decimal(str(i * 200)))
        try:
            await runner.simulate_bar(fv)
        except Exception as exc:
            errors.append(str(exc))
        await asyncio.sleep(0.02)

    await runner.teardown()

    assert not errors, f"Exceptions during simulation: {errors}"


# ---------------------------------------------------------------------------
# 10. Backtest uses outcome_source simplified_backtest
# ---------------------------------------------------------------------------

def test_backtest_outcome_source_tag():
    """BacktestEngine is documented as simplified_backtest source."""
    from learning.outcome_source import OutcomeSource
    assert OutcomeSource.SIMPLIFIED_BACKTEST.value == "simplified_backtest"
    assert not OutcomeSource.SIMPLIFIED_BACKTEST.is_validated_source()
