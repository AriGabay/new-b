"""
Tests for NewsMacroGroup — event calendar, Fear & Greed, BTC macro classification,
SystemState integration, RiskLeverageGroup integration, and MDP state fields.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.events import BarCloseEvent, EventBus, FeatureReadyEvent
from core.schemas import FeatureVector, ModeGate, OHLCVBar
from core.state import SystemState
from groups.news_macro.group import NewsMacroGroup, _parse_event_datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(**kwargs) -> SystemState:
    state = SystemState(mode=ModeGate.SHADOW)
    for k, v in kwargs.items():
        setattr(state, k, v)
    return state


def make_bus() -> EventBus:
    return EventBus()


def make_group(state=None, config=None) -> NewsMacroGroup:
    if state is None:
        state = make_state()
    return NewsMacroGroup(state=state, bus=make_bus(), config=config or {})


def make_bar(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    ts: datetime = None,
    close: float = 50000.0,
) -> OHLCVBar:
    ts = ts or datetime(2025, 6, 1, 12, 0)
    c = Decimal(str(close))
    return OHLCVBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=ts,
        open=c,
        high=c * Decimal("1.001"),
        low=c * Decimal("0.999"),
        close=c,
        volume=Decimal("100"),
        volume_usd=Decimal("5000000"),
    )


def make_feature_vector(
    symbol: str = "BTCUSDT",
    ema20: float = 55000.0,
    ema50: float = 52000.0,
    ema200: float = 48000.0,
    ts: datetime = None,
) -> FeatureVector:
    ts = ts or datetime(2025, 6, 1, 12, 0)
    c = Decimal("50000")
    return FeatureVector(
        symbol=symbol,
        timeframe="1h",
        timestamp=ts,
        open=c,
        high=c * Decimal("1.01"),
        low=c * Decimal("0.99"),
        close=c,
        volume=Decimal("100"),
        true_range=Decimal("500"),
        atr14=Decimal("500"),
        atr14_sma20=Decimal("480"),
        ema20=Decimal(str(ema20)),
        ema50=Decimal(str(ema50)),
        ema200=Decimal(str(ema200)),
        prev_ema20=Decimal(str(ema20)),
        prev_ema50=Decimal(str(ema50)),
        rsi14=55.0,
        prev_rsi14=52.0,
        bb_upper=Decimal("51000"),
        bb_middle=Decimal("50000"),
        bb_lower=Decimal("49000"),
        bb_width=Decimal("2000"),
        bb_width_pct=30.0,
        adx14=25.0,
        volume_sma20=Decimal("90"),
        volume_ratio=1.1,
        candle_body=Decimal("100"),
        candle_range=Decimal("200"),
        body_ratio=0.5,
        upper_shadow=Decimal("50"),
        lower_shadow=Decimal("50"),
        impulse_flag=False,
        doji_flag=False,
    )


def make_calendar_entry(
    hours_from_now: float,
    impact: str = "high",
    reference: datetime = None,
) -> dict:
    ref = reference or datetime(2025, 6, 1, 12, 0)
    event_dt = ref + timedelta(hours=hours_from_now)
    return {
        "date": event_dt.strftime("%Y-%m-%d"),
        "time": event_dt.strftime("%H:%M"),
        "event": "Test Event",
        "impact": impact,
        "asset": "all",
    }


# ---------------------------------------------------------------------------
# _parse_event_datetime
# ---------------------------------------------------------------------------

def test_parse_event_datetime_hhmm():
    entry = {"date": "2025-03-20", "time": "18:00"}
    dt = _parse_event_datetime(entry)
    assert dt == datetime(2025, 3, 20, 18, 0, 0)


def test_parse_event_datetime_hhmmss():
    entry = {"date": "2025-03-20", "time": "18:00:00"}
    dt = _parse_event_datetime(entry)
    assert dt == datetime(2025, 3, 20, 18, 0, 0)


# ---------------------------------------------------------------------------
# _classify_btc_macro
# ---------------------------------------------------------------------------

def test_classify_btc_macro_bull():
    group = make_group()
    fv = make_feature_vector(ema20=55000, ema50=52000, ema200=48000)
    assert group._classify_btc_macro(fv) == "bull"


def test_classify_btc_macro_bear():
    group = make_group()
    fv = make_feature_vector(ema20=45000, ema50=48000, ema200=52000)
    assert group._classify_btc_macro(fv) == "bear"


def test_classify_btc_macro_ranging_ema20_above_50_not_200():
    group = make_group()
    # ema20 > ema200 but ema50 > ema200 too and ema20 < ema50 — mixed
    fv = make_feature_vector(ema20=49000, ema50=51000, ema200=48000)
    assert group._classify_btc_macro(fv) == "ranging"


def test_classify_btc_macro_all_equal():
    group = make_group()
    fv = make_feature_vector(ema20=50000, ema50=50000, ema200=50000)
    # Not strictly ordered either way → ranging
    assert group._classify_btc_macro(fv) == "ranging"


# ---------------------------------------------------------------------------
# _compute_position_modifier
# ---------------------------------------------------------------------------

def test_modifier_no_events():
    group = make_group()
    group._event_calendar = []
    ref = datetime(2025, 6, 1, 12, 0)
    assert group._compute_position_modifier(ref) == 1.0


def test_modifier_low_impact_event_ignored():
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(2.0, impact="low", reference=ref)]
    assert group._compute_position_modifier(ref) == 1.0


def test_modifier_medium_impact_ignored():
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(2.0, impact="medium", reference=ref)]
    assert group._compute_position_modifier(ref) == 1.0


def test_modifier_high_impact_3h_before():
    """3h before high-impact event → 0.50"""
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(3.0, reference=ref)]
    assert group._compute_position_modifier(ref) == 0.50


def test_modifier_high_impact_30min_before():
    """30min before high-impact event → 0.0 (block)"""
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(0.5, reference=ref)]
    assert group._compute_position_modifier(ref) == 0.0


def test_modifier_high_impact_45min_after():
    """45min after high-impact event → 0.50"""
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(-0.75, reference=ref)]
    assert group._compute_position_modifier(ref) == 0.50


def test_modifier_high_impact_2h_after():
    """2h after high-impact event → 1.0 (outside window)"""
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(-2.0, reference=ref)]
    assert group._compute_position_modifier(ref) == 1.0


def test_modifier_multiple_events_takes_most_restrictive():
    """Multiple events: most restrictive wins (0.0 beats 0.5)"""
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [
        make_calendar_entry(3.0, reference=ref),   # 3h ahead → 0.50
        make_calendar_entry(0.5, reference=ref),   # 30min ahead → 0.0
    ]
    assert group._compute_position_modifier(ref) == 0.0


def test_modifier_exactly_4h_before():
    """Exactly 4h before: 0 < hours_ahead <= 4 → 0.50"""
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(4.0, reference=ref)]
    assert group._compute_position_modifier(ref) == 0.50


def test_modifier_beyond_4h_before():
    """5h before: outside window → 1.0"""
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(5.0, reference=ref)]
    assert group._compute_position_modifier(ref) == 1.0


# ---------------------------------------------------------------------------
# _has_high_impact_event_next_48h
# ---------------------------------------------------------------------------

def test_has_event_48h_true():
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(24.0, reference=ref)]
    assert group._has_high_impact_event_next_48h(ref) is True


def test_has_event_48h_false_past():
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(-1.0, reference=ref)]
    assert group._has_high_impact_event_next_48h(ref) is False


def test_has_event_48h_false_beyond_window():
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(49.0, reference=ref)]
    assert group._has_high_impact_event_next_48h(ref) is False


# ---------------------------------------------------------------------------
# _load_event_calendar
# ---------------------------------------------------------------------------

def test_load_calendar_no_config():
    """No event_calendar_path configured → empty calendar, no crash."""
    group = make_group(config={})

    async def run():
        await group._load_event_calendar()

    asyncio.run(run())
    assert group._event_calendar == []


def test_load_calendar_valid_json(tmp_path):
    """Valid JSON file → calendar loaded."""
    events = [
        {"date": "2025-06-18", "time": "18:00", "event": "FOMC", "impact": "high", "asset": "all"},
        {"date": "2025-07-30", "time": "18:00", "event": "FOMC", "impact": "high", "asset": "all"},
    ]
    cal_file = tmp_path / "calendar.json"
    cal_file.write_text(json.dumps(events))

    group = make_group(config={"event_calendar_path": str(cal_file)})

    async def run():
        await group._load_event_calendar()

    asyncio.run(run())
    assert len(group._event_calendar) == 2
    assert group._event_calendar[0]["event"] == "FOMC"


def test_load_calendar_missing_file(tmp_path):
    """Non-existent path → empty calendar, no crash."""
    group = make_group(config={"event_calendar_path": str(tmp_path / "no_such_file.json")})

    async def run():
        await group._load_event_calendar()

    asyncio.run(run())
    assert group._event_calendar == []


def test_load_calendar_invalid_json(tmp_path):
    """Corrupt JSON → empty calendar, no crash."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json!!!")

    group = make_group(config={"event_calendar_path": str(bad_file)})

    async def run():
        await group._load_event_calendar()

    asyncio.run(run())
    assert group._event_calendar == []


# ---------------------------------------------------------------------------
# _load_sentiment
# ---------------------------------------------------------------------------

def test_load_sentiment_valid(tmp_path):
    sent_file = tmp_path / "sentiment.json"
    sent_file.write_text(json.dumps({"value": 18, "label": "extreme_fear"}))
    group = make_group(config={"sentiment_path": str(sent_file)})
    assert group._load_sentiment() == 18.0


def test_load_sentiment_missing_file(tmp_path):
    group = make_group(config={"sentiment_path": str(tmp_path / "missing.json")})
    assert group._load_sentiment() == 50.0


def test_load_sentiment_no_config():
    """No sentiment_path → tries data/sentiment.json, returns 50 if not found."""
    group = make_group(config={})
    # If data/sentiment.json doesn't exist from project root CWD, returns 50
    result = group._load_sentiment()
    assert isinstance(result, float)


def test_load_sentiment_extreme_fear_value(tmp_path):
    sent_file = tmp_path / "s.json"
    sent_file.write_text(json.dumps({"value": 10}))
    group = make_group(config={"sentiment_path": str(sent_file)})
    assert group._load_sentiment() == 10.0


# ---------------------------------------------------------------------------
# Fear & Greed modifier in _process_bar_close
# ---------------------------------------------------------------------------

def test_fear_greed_extreme_fear_reduces_modifier():
    """F&G < 20 → modifier * 0.70"""
    group = make_group()
    group._event_calendar = []  # no events → base modifier = 1.0
    group._fear_greed_value = 15.0
    ref = datetime(2025, 6, 1, 12, 0)
    modifier = group._compute_position_modifier(ref)  # 1.0
    fg = group._fear_greed_value
    if fg < 20 or fg > 80:
        modifier *= 0.70
    assert abs(modifier - 0.70) < 1e-9


def test_fear_greed_extreme_greed_reduces_modifier():
    """F&G > 80 → modifier * 0.70"""
    group = make_group()
    group._event_calendar = []
    group._fear_greed_value = 85.0
    ref = datetime(2025, 6, 1, 12, 0)
    modifier = group._compute_position_modifier(ref)
    fg = group._fear_greed_value
    if fg < 20 or fg > 80:
        modifier *= 0.70
    assert abs(modifier - 0.70) < 1e-9


def test_fear_greed_neutral_no_change():
    """F&G = 50 → no modifier change"""
    group = make_group()
    group._event_calendar = []
    group._fear_greed_value = 50.0
    ref = datetime(2025, 6, 1, 12, 0)
    modifier = group._compute_position_modifier(ref)
    fg = group._fear_greed_value
    if fg < 20 or fg > 80:
        modifier *= 0.70
    assert abs(modifier - 1.0) < 1e-9


def test_fear_greed_combined_with_event_modifier():
    """F&G extreme AND event nearby → both modifiers apply."""
    group = make_group()
    ref = datetime(2025, 6, 1, 12, 0)
    group._event_calendar = [make_calendar_entry(3.0, reference=ref)]  # 0.50
    group._fear_greed_value = 15.0
    modifier = group._compute_position_modifier(ref)   # 0.50
    fg = group._fear_greed_value
    if fg < 20 or fg > 80:
        modifier *= 0.70
    modifier = max(0.0, min(1.0, modifier))
    assert abs(modifier - 0.35) < 1e-9


# ---------------------------------------------------------------------------
# _process_bar_close — async integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_bar_close_publishes_group_signal_event():
    """_process_bar_close publishes a GroupSignalEvent."""
    bus = EventBus()
    state = make_state()
    group = NewsMacroGroup(state=state, bus=bus, config={})
    group._event_calendar = []
    group._fear_greed_value = 50.0

    published = []
    from core.events import GroupSignalEvent
    async def capture(ev):
        published.append(ev)
    await bus.subscribe(GroupSignalEvent, capture)

    bar = make_bar(ts=datetime(2025, 6, 1, 12, 0))
    event = BarCloseEvent(bar=bar)
    await group._process_bar_close(event)

    assert len(published) == 1
    bundle = published[0].bundle
    assert bundle.metadata["macro_position_modifier"] == 1.0
    assert bundle.metadata["fear_greed_index"] == 50.0
    assert bundle.metadata["btc_macro"] in ("bull", "bear", "ranging", "unknown")


@pytest.mark.asyncio
async def test_process_bar_close_updates_system_state():
    """_process_bar_close updates state.macro_position_modifier."""
    state = make_state()
    group = NewsMacroGroup(state=state, bus=make_bus(), config={})
    group._event_calendar = []
    group._fear_greed_value = 50.0

    bar = make_bar()
    await group._process_bar_close(BarCloseEvent(bar=bar))

    assert state.macro_position_modifier == 1.0
    assert state.fear_greed_index == 50.0


@pytest.mark.asyncio
async def test_process_bar_close_event_blocks_update_state():
    """With event 30min ahead, state.macro_position_modifier → 0.0"""
    state = make_state()
    ref = datetime(2025, 6, 1, 12, 0)
    group = NewsMacroGroup(state=state, bus=make_bus(), config={})
    group._event_calendar = [make_calendar_entry(0.5, reference=ref)]
    group._fear_greed_value = 50.0

    bar = make_bar(ts=ref)
    await group._process_bar_close(BarCloseEvent(bar=bar))

    assert state.macro_position_modifier == 0.0


@pytest.mark.asyncio
async def test_process_bar_close_uses_cached_features_for_macro():
    """FeatureReadyEvent caches features; bar close uses them for btc_macro."""
    state = make_state()
    bus = EventBus()
    group = NewsMacroGroup(state=state, bus=bus, config={})
    group._event_calendar = []
    group._fear_greed_value = 50.0

    # Cache a bullish feature vector
    fv = make_feature_vector(ema20=55000, ema50=52000, ema200=48000)
    group._latest_features["BTCUSDT"] = fv

    published = []
    from core.events import GroupSignalEvent
    async def capture(ev):
        published.append(ev)
    await bus.subscribe(GroupSignalEvent, capture)

    bar = make_bar(ts=datetime(2025, 6, 1, 12, 0))
    await group._process_bar_close(BarCloseEvent(bar=bar))

    assert published[0].bundle.metadata["btc_macro"] == "bull"


@pytest.mark.asyncio
async def test_handle_event_caches_feature_ready():
    """FeatureReadyEvent updates _latest_features cache."""
    state = make_state()
    group = NewsMacroGroup(state=state, bus=make_bus(), config={})
    fv = make_feature_vector(symbol="ETHUSDT")
    event = FeatureReadyEvent(features=fv)
    await group._handle_event(event)
    assert "ETHUSDT" in group._latest_features


# ---------------------------------------------------------------------------
# SystemState.update_macro_state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_state_update_macro_state():
    state = SystemState()
    assert state.macro_position_modifier == 1.0
    assert state.fear_greed_index == 50.0

    await state.update_macro_state(0.5, 18.0)
    assert state.macro_position_modifier == 0.5
    assert state.fear_greed_index == 18.0


@pytest.mark.asyncio
async def test_system_state_update_macro_state_clamps_modifier():
    """Modifier is clamped to [0.0, 1.0]."""
    state = SystemState()
    await state.update_macro_state(1.5, 50.0)
    assert state.macro_position_modifier == 1.0

    await state.update_macro_state(-0.5, 50.0)
    assert state.macro_position_modifier == 0.0


# ---------------------------------------------------------------------------
# RiskLeverageGroup integration
# ---------------------------------------------------------------------------

def test_risk_group_check_event_risk_reads_state_modifier():
    """_check_event_risk returns state.macro_position_modifier as Decimal."""
    from groups.risk_leverage.group import RiskLeverageGroup
    state = make_state()
    state.macro_position_modifier = 0.5
    bus = EventBus()
    group = RiskLeverageGroup(state=state, bus=bus, config={})
    result = group._check_event_risk(MagicMock())
    assert result == Decimal("0.5")


def test_risk_group_check_event_risk_default_full():
    """Default state → full size (1.0)."""
    from groups.risk_leverage.group import RiskLeverageGroup
    state = make_state()
    bus = EventBus()
    group = RiskLeverageGroup(state=state, bus=bus, config={})
    result = group._check_event_risk(MagicMock())
    assert result == Decimal("1.0")


def test_risk_group_check_event_risk_zero_blocks():
    """macro_position_modifier=0.0 → Decimal('0.0')"""
    from groups.risk_leverage.group import RiskLeverageGroup
    state = make_state()
    state.macro_position_modifier = 0.0
    bus = EventBus()
    group = RiskLeverageGroup(state=state, bus=bus, config={})
    result = group._check_event_risk(MagicMock())
    assert result == Decimal("0.0")


# ---------------------------------------------------------------------------
# MDPState macro fields
# ---------------------------------------------------------------------------

def test_mdp_state_has_macro_fields():
    """MDPState includes macro_position_modifier and fear_greed_index."""
    from mdp.state import MDPState
    import inspect
    fields = {f.name for f in MDPState.__dataclass_fields__.values()}
    assert "macro_position_modifier" in fields
    assert "fear_greed_index" in fields


def test_mdp_state_defaults():
    from mdp.state import MDPState
    # Build a minimal MDPState — non-default fields provided, defaults expected on macro
    state = MDPState(
        direction="long", symbol="BTCUSDT", timeframe="1h",
        entry_price=50000.0, stop_price=49000.0, target_price=53000.0,
        r_r_ratio=3.0, composite_score=0.70, setup_quality="B",
        btc_macro="bull", trending=True, volatility_regime="normal",
        adx14=28.0, at_support=True, at_resistance=False,
        approve_count=13, reject_count=5, abstain_count=2,
        avg_score=6.5, weighted_score=6.8, panel_confidence=0.72,
        evaluator_scores={}, evaluator_votes={}, evaluator_confidences={},
        score_std_dev=1.2, bull_bear_split=0.6,
        key_risks=[], key_strengths=[],
        current_equity=100000.0, drawdown_pct=0.02, daily_pnl_pct=0.01,
        open_positions_count=1, total_exposure_pct=0.15,
        recent_win_rate=0.55, current_streak=2, trades_last_24_bars=3,
    )
    assert state.macro_position_modifier == 1.0
    assert state.fear_greed_index == 50.0


def test_mdp_state_to_dict_includes_macro():
    from mdp.state import MDPState
    state = MDPState(
        direction="long", symbol="BTCUSDT", timeframe="1h",
        entry_price=50000.0, stop_price=49000.0, target_price=53000.0,
        r_r_ratio=3.0, composite_score=0.70, setup_quality="B",
        btc_macro="bull", trending=True, volatility_regime="normal",
        adx14=28.0, at_support=True, at_resistance=False,
        approve_count=13, reject_count=5, abstain_count=2,
        avg_score=6.5, weighted_score=6.8, panel_confidence=0.72,
        evaluator_scores={}, evaluator_votes={}, evaluator_confidences={},
        score_std_dev=1.2, bull_bear_split=0.6,
        key_risks=[], key_strengths=[],
        current_equity=100000.0, drawdown_pct=0.02, daily_pnl_pct=0.01,
        open_positions_count=1, total_exposure_pct=0.15,
        recent_win_rate=0.55, current_streak=2, trades_last_24_bars=3,
        macro_position_modifier=0.5, fear_greed_index=18.0,
    )
    d = state.to_dict()
    assert d["macro_position_modifier"] == 0.5
    assert d["fear_greed_index"] == 18.0


def test_mdp_state_to_vector_includes_macro():
    from mdp.state import MDPState
    state = MDPState(
        direction="long", symbol="BTCUSDT", timeframe="1h",
        entry_price=50000.0, stop_price=49000.0, target_price=53000.0,
        r_r_ratio=3.0, composite_score=0.70, setup_quality="B",
        btc_macro="bull", trending=True, volatility_regime="normal",
        adx14=28.0, at_support=True, at_resistance=False,
        approve_count=13, reject_count=5, abstain_count=2,
        avg_score=6.5, weighted_score=6.8, panel_confidence=0.72,
        evaluator_scores={}, evaluator_votes={}, evaluator_confidences={},
        score_std_dev=1.2, bull_bear_split=0.6,
        key_risks=[], key_strengths=[],
        current_equity=100000.0, drawdown_pct=0.02, daily_pnl_pct=0.01,
        open_positions_count=1, total_exposure_pct=0.15,
        recent_win_rate=0.55, current_streak=2, trades_last_24_bars=3,
        macro_position_modifier=0.5, fear_greed_index=18.0,
    )
    vec = state.to_vector()
    # macro_position_modifier=0.5 and fear_greed_index=18 → (18-50)/50=-0.64 should be present
    assert 0.5 in vec
    # Fear greed normalized: (18 - 50) / 50 = -0.64
    assert any(abs(v - (-0.64)) < 1e-9 for v in vec)


# ---------------------------------------------------------------------------
# MDPStateBuilder macro integration
# ---------------------------------------------------------------------------

def _make_mdp_packet_and_panel():
    """Build a minimal BTCSetupPacket + PanelResult for MDPStateBuilder tests."""
    from validation.scenario_loader import scenario_ideal_bull_long
    from traders.panel import PanelResult

    labelled = scenario_ideal_bull_long()
    panel = PanelResult(
        packet_id=labelled.packet.packet_id,
        verdicts=[], approve_count=0, reject_count=0, abstain_count=0,
        avg_score=5.0, weighted_score=5.0, panel_confidence=0.5,
        key_risks=[], key_strengths=[],
    )
    return labelled.packet, panel


def test_state_builder_reads_macro_from_system_state():
    """MDPStateBuilder reads macro fields from SystemState when provided."""
    from mdp.state_builder import MDPStateBuilder

    state = SystemState()
    state.macro_position_modifier = 0.5
    state.fear_greed_index = 18.0

    packet, panel = _make_mdp_packet_and_panel()
    builder = MDPStateBuilder()
    mdp_state = builder.build(packet, panel, system_state=state)

    assert mdp_state.macro_position_modifier == 0.5
    assert mdp_state.fear_greed_index == 18.0


def test_state_builder_macro_defaults_without_system_state():
    """Without SystemState, macro fields default to 1.0 and 50.0."""
    from mdp.state_builder import MDPStateBuilder

    packet, panel = _make_mdp_packet_and_panel()
    builder = MDPStateBuilder()
    mdp_state = builder.build(packet, panel, system_state=None)

    assert mdp_state.macro_position_modifier == 1.0
    assert mdp_state.fear_greed_index == 50.0


# ---------------------------------------------------------------------------
# Data files existence
# ---------------------------------------------------------------------------

def test_event_calendar_json_exists():
    """data/event_calendar.json must exist and be valid JSON."""
    path = Path("data/event_calendar.json")
    if not path.exists():
        # Try relative to project root
        path = Path(__file__).parent.parent.parent / "data" / "event_calendar.json"
    assert path.exists(), "data/event_calendar.json not found"
    events = json.loads(path.read_text())
    assert len(events) > 0
    # All high-impact events have required fields
    for e in events:
        assert "date" in e
        assert "time" in e
        assert "event" in e
        assert "impact" in e


def test_event_calendar_has_fomc_entries():
    """event_calendar.json must include FOMC events."""
    path = Path("data/event_calendar.json")
    if not path.exists():
        path = Path(__file__).parent.parent.parent / "data" / "event_calendar.json"
    events = json.loads(path.read_text())
    fomc_events = [e for e in events if "FOMC" in e.get("event", "")]
    assert len(fomc_events) >= 8, "Expected at least 8 FOMC entries"


def test_sentiment_json_exists():
    """data/sentiment.json must exist and have 'value' key."""
    path = Path("data/sentiment.json")
    if not path.exists():
        path = Path(__file__).parent.parent.parent / "data" / "sentiment.json"
    assert path.exists(), "data/sentiment.json not found"
    data = json.loads(path.read_text())
    assert "value" in data
    assert 0 <= float(data["value"]) <= 100
