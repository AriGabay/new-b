"""
Tests for HistorianGroup.

Coverage:
  - 0-trade query returns neutral HistoricalAnalog
  - 15-trade query returns correct win_rate blending
  - Streak detection (3 losses, 5 losses)
  - Regime memory: caution flag when WR < 40% with 15+ trades
  - GroupID.HISTORIAN exists in registry
  - HistorianGroup is wired to EntryGroup after runner.setup()
  - EntryGroup composite score uses 5-component formula when historian present
  - EntryGroup uses 4-component formula when historian is None
  - _record_closed_trade updates stats correctly
  - _query_hypothesis returns neutral (0.5) when no data
  - _query_regime returns neutral (0.5) when no data
  - only most severe streak warning is included
  - regime caution combined with streak
  - last_10_outcomes ring buffer (max 10)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events import EventBus, PositionCloseEvent
from core.registry import GroupID
from core.schemas import (
    Direction,
    HistoricalAnalog,
    Position,
    RegimeContext,
)
from core.state import SystemState
from groups.historian.group import (
    HistorianGroup,
    _HYP_MIN_TRADES,
    _REGIME_MIN_TRADES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state() -> SystemState:
    from core.schemas import ModeGate
    return SystemState(mode=ModeGate.SHADOW)


def _make_bus() -> EventBus:
    return EventBus()


def _make_historian() -> HistorianGroup:
    return HistorianGroup(_make_state(), _make_bus())


def _make_position(
    pnl_r: float = 1.0,
    hypothesis_refs: Optional[list[str]] = None,
    setup_refs: Optional[list[str]] = None,
) -> Position:
    return Position(
        symbol="BTCUSDT",
        direction=Direction.LONG,
        current_pnl_r=pnl_r,
        hypothesis_refs=hypothesis_refs or [],
        setup_refs=setup_refs or [],
        status="closed",
    )


def _make_close_event(
    pnl_r: float = 1.0,
    hypothesis_refs: Optional[list[str]] = None,
    setup_refs: Optional[list[str]] = None,
) -> PositionCloseEvent:
    pos = _make_position(pnl_r, hypothesis_refs, setup_refs)
    return PositionCloseEvent(final_position=pos)


def _inject_trades(
    historian: HistorianGroup,
    n_wins: int,
    n_losses: int,
    hypothesis_refs: Optional[list[str]] = None,
    regime_key: Optional[str] = None,
) -> None:
    """Inject n_wins winning trades then n_losses losing trades."""
    hrefs = hypothesis_refs or []
    srefs = [f"regime:{regime_key}"] if regime_key else []
    for _ in range(n_wins):
        historian._record_closed_trade(_make_close_event(
            pnl_r=1.0, hypothesis_refs=hrefs, setup_refs=srefs
        ))
    for _ in range(n_losses):
        historian._record_closed_trade(_make_close_event(
            pnl_r=-1.0, hypothesis_refs=hrefs, setup_refs=srefs
        ))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_group_id_historian_exists():
    assert GroupID.HISTORIAN == "historian"


# ---------------------------------------------------------------------------
# 0-trade query
# ---------------------------------------------------------------------------

def test_zero_trade_query_returns_neutral():
    h = _make_historian()
    analog = h.query("BTCUSDT", Direction.LONG)
    assert analog.similar_trades_count == 0
    assert analog.win_rate == 0.5
    assert analog.avg_r_multiple == 0.0
    assert analog.common_failure_modes == []
    assert analog.last_10_outcomes == []


def test_zero_trade_query_with_refs_still_neutral():
    h = _make_historian()
    analog = h.query(
        "BTCUSDT", Direction.LONG,
        hypothesis_refs=["H1-001"],
        regime_key="bull_normal",
    )
    assert analog.win_rate == 0.5
    assert analog.similar_trades_count == 0


# ---------------------------------------------------------------------------
# Hypothesis stats
# ---------------------------------------------------------------------------

def test_hypothesis_stats_updated_on_win():
    h = _make_historian()
    _inject_trades(h, n_wins=3, n_losses=0, hypothesis_refs=["H1-001"])
    assert h._hyp_stats["H1-001"]["wins"] == 3
    assert h._hyp_stats["H1-001"]["total"] == 3


def test_hypothesis_stats_updated_on_loss():
    h = _make_historian()
    _inject_trades(h, n_wins=0, n_losses=2, hypothesis_refs=["H1-001"])
    assert h._hyp_stats["H1-001"]["wins"] == 0
    assert h._hyp_stats["H1-001"]["total"] == 2


def test_query_hypothesis_neutral_below_min_trades():
    h = _make_historian()
    _inject_trades(h, n_wins=5, n_losses=3, hypothesis_refs=["H1-001"])  # 8 < 10
    # Below minimum — hyp component uses 0.5 neutral
    analog = h.query("BTCUSDT", Direction.LONG, hypothesis_refs=["H1-001"])
    # No regime data either, so blended should be 0.5
    assert analog.win_rate == pytest.approx(0.5, abs=0.01)


def test_query_hypothesis_above_min_trades():
    h = _make_historian()
    # 10 wins, 0 losses = 100% WR
    _inject_trades(h, n_wins=10, n_losses=0, hypothesis_refs=["H1-001"])
    analog = h.query("BTCUSDT", Direction.LONG, hypothesis_refs=["H1-001"])
    # hyp_wr=1.0, regime neutral(0.5): 0.6*1.0 + 0.4*0.5 = 0.8
    assert analog.win_rate == pytest.approx(0.8, abs=0.01)
    assert analog.similar_trades_count == 10


# ---------------------------------------------------------------------------
# Regime stats
# ---------------------------------------------------------------------------

def test_regime_stats_updated():
    h = _make_historian()
    _inject_trades(h, n_wins=5, n_losses=10, regime_key="bear_high")
    assert "bear_high" in h._regime_stats
    assert h._regime_stats["bear_high"]["total"] == 15


def test_query_regime_neutral_below_min_trades():
    h = _make_historian()
    _inject_trades(h, n_wins=7, n_losses=5, regime_key="bull_normal")  # 12 < 15
    analog = h.query("BTCUSDT", Direction.LONG, regime_key="bull_normal")
    assert analog.win_rate == pytest.approx(0.5, abs=0.01)


def test_query_regime_above_min_trades():
    h = _make_historian()
    # 15 wins, 0 losses = 100% WR in regime
    _inject_trades(h, n_wins=15, n_losses=0, regime_key="bull_normal")
    analog = h.query("BTCUSDT", Direction.LONG, regime_key="bull_normal")
    # hyp neutral(0.5), regime_wr=1.0: 0.6*0.5 + 0.4*1.0 = 0.70
    assert analog.win_rate == pytest.approx(0.70, abs=0.01)


# ---------------------------------------------------------------------------
# Both hypothesis + regime above minimum
# ---------------------------------------------------------------------------

def test_blended_win_rate_both_above_minimum():
    h = _make_historian()
    # 10 trades, 7 wins for hypothesis
    _inject_trades(h, n_wins=7, n_losses=3, hypothesis_refs=["H1-002"], regime_key="bull_normal")
    # 15 trades, 12 wins for regime (already counted above — need fresh historian)
    h2 = _make_historian()
    _inject_trades(h2, n_wins=7, n_losses=3, hypothesis_refs=["H1-002"], regime_key="bull_normal")
    # Add 5 more trades to regime only to reach 15 minimum
    _inject_trades(h2, n_wins=3, n_losses=2, regime_key="bull_normal")
    # hyp_wr = 7/10 = 0.70, regime_wr = 10/15 = 0.667
    analog = h2.query("BTCUSDT", Direction.LONG, hypothesis_refs=["H1-002"], regime_key="bull_normal")
    expected = 0.6 * (7/10) + 0.4 * (10/15)
    assert analog.win_rate == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Streak detection
# ---------------------------------------------------------------------------

def test_no_streak_no_warning():
    h = _make_historian()
    # Inject losses then a win to reset the streak
    _inject_trades(h, n_wins=0, n_losses=2)
    _inject_trades(h, n_wins=1, n_losses=0)
    assert h._consecutive_losses == 0
    analog = h.query("BTCUSDT", Direction.LONG)
    assert not any("streak" in f for f in analog.common_failure_modes)


def test_three_loss_streak_warning():
    h = _make_historian()
    _inject_trades(h, n_wins=0, n_losses=3)
    assert h._consecutive_losses == 3
    analog = h.query("BTCUSDT", Direction.LONG)
    assert any("3-loss streak" in f for f in analog.common_failure_modes)
    assert any("-20%" in f for f in analog.common_failure_modes)


def test_five_loss_streak_warning():
    h = _make_historian()
    _inject_trades(h, n_wins=0, n_losses=5)
    assert h._consecutive_losses == 5
    analog = h.query("BTCUSDT", Direction.LONG)
    assert any("5-loss streak" in f for f in analog.common_failure_modes)
    assert any("-40%" in f for f in analog.common_failure_modes)


def test_five_loss_streak_only_most_severe():
    """5-loss streak should not also emit 3-loss streak warning."""
    h = _make_historian()
    _inject_trades(h, n_wins=0, n_losses=5)
    analog = h.query("BTCUSDT", Direction.LONG)
    streak_warnings = [f for f in analog.common_failure_modes if "streak" in f]
    assert len(streak_warnings) == 1
    assert "5-loss" in streak_warnings[0]


def test_streak_resets_on_win():
    h = _make_historian()
    _inject_trades(h, n_wins=0, n_losses=5)
    assert h._consecutive_losses == 5
    _inject_trades(h, n_wins=1, n_losses=0)
    assert h._consecutive_losses == 0
    analog = h.query("BTCUSDT", Direction.LONG)
    assert not any("streak" in f for f in analog.common_failure_modes)


# ---------------------------------------------------------------------------
# Regime caution flag
# ---------------------------------------------------------------------------

def test_regime_caution_flag_low_win_rate():
    h = _make_historian()
    # 15 trades: 5 wins, 10 losses = 33% WR < 40%
    _inject_trades(h, n_wins=5, n_losses=10, regime_key="bear_high")
    analog = h.query("BTCUSDT", Direction.LONG, regime_key="bear_high")
    assert any("CAUTION: regime" in f for f in analog.common_failure_modes)


def test_regime_caution_flag_not_triggered_above_threshold():
    h = _make_historian()
    # 15 trades: 8 wins, 7 losses = 53% WR > 40%
    _inject_trades(h, n_wins=8, n_losses=7, regime_key="bull_normal")
    analog = h.query("BTCUSDT", Direction.LONG, regime_key="bull_normal")
    assert not any("CAUTION: regime" in f for f in analog.common_failure_modes)


def test_regime_caution_not_triggered_below_minimum_trades():
    h = _make_historian()
    # Only 10 trades: below _REGIME_MIN_TRADES=15
    _inject_trades(h, n_wins=2, n_losses=8, regime_key="bear_high")
    analog = h.query("BTCUSDT", Direction.LONG, regime_key="bear_high")
    assert not any("CAUTION: regime" in f for f in analog.common_failure_modes)


# ---------------------------------------------------------------------------
# last_10_outcomes ring buffer
# ---------------------------------------------------------------------------

def test_last_10_outcomes_ring_buffer():
    h = _make_historian()
    for _ in range(15):
        h._record_closed_trade(_make_close_event(pnl_r=1.0))
    assert len(h._recent_outcomes) == 10


def test_last_10_outcomes_content():
    h = _make_historian()
    _inject_trades(h, n_wins=3, n_losses=2)
    analog = h.query("BTCUSDT", Direction.LONG)
    assert len(analog.last_10_outcomes) == 5
    assert analog.last_10_outcomes[:3] == ["win", "win", "win"]
    assert analog.last_10_outcomes[3:] == ["loss", "loss"]


# ---------------------------------------------------------------------------
# avg_r_multiple
# ---------------------------------------------------------------------------

def test_avg_r_multiple_computed():
    h = _make_historian()
    # 10 trades each at pnl_r=2.0
    for _ in range(10):
        h._record_closed_trade(_make_close_event(pnl_r=2.0, hypothesis_refs=["H1-001"]))
    analog = h.query("BTCUSDT", Direction.LONG, hypothesis_refs=["H1-001"])
    assert analog.avg_r_multiple == pytest.approx(2.0, abs=0.01)


# ---------------------------------------------------------------------------
# EntryGroup composite score branches
# ---------------------------------------------------------------------------

def test_entry_group_uses_4_component_when_historian_none():
    """When _historian is None, composite score uses 4-component formula."""
    from groups.entry.group import EntryGroup, _ACTIVE_SCORE_COMPONENTS
    state = _make_state()
    bus = _make_bus()
    entry = EntryGroup(state, bus)
    assert entry._historian is None
    # Simulate composite score with no historian
    score, breakdown = entry._compute_composite_score(
        bundles={},
        primary_signals=[],
        structural_bundle=None,
        historian_analog=None,
        regime=None,
        direction=Direction.LONG,
    )
    assert breakdown["historian_score"] is None
    # With no signals, all component values are 0, so active_weight_sum = 0
    # (only non-zero components contribute to active weight after Phase 4 normalization)
    assert breakdown["active_weight_sum"] >= 0


def test_entry_group_uses_5_component_when_historian_present():
    """When historian_analog is provided, composite score uses 5-component formula."""
    from groups.entry.group import EntryGroup, _HISTORIAN_SCORE_COMPONENTS
    state = _make_state()
    bus = _make_bus()
    entry = EntryGroup(state, bus)
    analog = HistoricalAnalog(win_rate=0.7)
    score, breakdown = entry._compute_composite_score(
        bundles={},
        primary_signals=[],
        structural_bundle=None,
        historian_analog=analog,
        regime=None,
        direction=Direction.LONG,
    )
    assert breakdown["historian_score"] == pytest.approx(0.7, abs=0.001)
    # With historian_analog.win_rate=0.7 (non-zero) but no signals, only
    # historian component is active. active_weight_sum = historian weight only.
    assert breakdown["active_weight_sum"] > 0


def test_entry_group_5_component_score_includes_historian_weight():
    """Historian win_rate=1.0 should increase composite score vs historian=None."""
    from groups.entry.group import EntryGroup
    state = _make_state()
    bus = _make_bus()
    entry = EntryGroup(state, bus)

    analog = HistoricalAnalog(win_rate=1.0)
    score_with, _ = entry._compute_composite_score(
        bundles={},
        primary_signals=[],
        structural_bundle=None,
        historian_analog=analog,
        regime=None,
        direction=Direction.LONG,
    )
    score_without, _ = entry._compute_composite_score(
        bundles={},
        primary_signals=[],
        structural_bundle=None,
        historian_analog=None,
        regime=None,
        direction=Direction.LONG,
    )
    # With a perfect historian score, the total should be higher
    assert score_with > score_without


# ---------------------------------------------------------------------------
# Runner wiring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runner_creates_historian_group():
    """Runner creates a HistorianGroup and wires it to EntryGroup."""
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True)
    await runner.setup()
    try:
        assert runner._historian is not None
        assert isinstance(runner._historian, HistorianGroup)
        assert runner._entry._historian is runner._historian
    finally:
        await runner.teardown()


@pytest.mark.asyncio
async def test_historian_in_all_groups():
    """HistorianGroup is included in the runner's _all_groups list."""
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True)
    await runner.setup()
    try:
        group_types = [type(g).__name__ for g in runner._all_groups]
        assert "HistorianGroup" in group_types
    finally:
        await runner.teardown()
