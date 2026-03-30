"""
Tests for the chart pattern plugin architecture (Task 7).

Coverage:
  PatternRegistry:
    - register() decorator populates _by_name and _by_hypothesis
    - get_all_patterns() returns name-keyed dict
    - get_all_by_hypothesis() returns hypothesis-keyed dict
    - get_pattern() matches by name
    - get_pattern() matches by hypothesis ref
    - get_pattern() returns None for unknown
    - autodiscover() imports all concrete pattern modules
    - autodiscover() is idempotent (no double registration)
    - _reset() clears state (used for test isolation)

  BasePatternDetector:
    - is a subclass of PatternStateMachine
    - has name, hypothesis_refs, direction_bias, min_bars_needed class attrs
    - detect() delegates to advance()

  Concrete patterns registered after autodiscover():
    - DoubleBottomMachine registered (H1-003)
    - HeadAndShouldersMachine registered (H1-001 and H1-002)
    - DescendingTriangleMachine registered (H1-004)
    - TripleBottomMachine registered (H1-005)
    - All five hypothesis refs present in registry

  Backward compatibility (state_machine.py re-exports):
    - DoubleBottomMachine importable from state_machine
    - HeadAndShouldersMachine importable from state_machine
    - DescendingTriangleMachine importable from state_machine
    - TripleBottomMachine importable from state_machine
    - PatternState importable from state_machine

  ChartPatternGroup integration:
    - _initialize_machines_for_symbol uses registry when populated
    - _initialize_machines_for_symbol falls back to PATTERN_MACHINES when empty

  MDPState chart pattern fields:
    - active_chart_patterns defaults to None
    - chart_pattern_completion_pct defaults to None
    - chart_pattern_measured_move defaults to None
    - to_dict() includes all three fields

  MDPStateBuilder:
    - build() accepts optional chart_pattern_group param
    - returns None fields when chart_pattern_group=None
    - populates active_chart_patterns from _active_cache
    - populates chart_pattern_completion_pct from forming machines

  SystemConfig:
    - enable_chart_patterns defaults to False
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_registry():
    """Reset registry between tests to ensure isolation."""
    from groups.chart_pattern.registry import PatternRegistry
    PatternRegistry._reset()


def _run_autodiscover():
    from groups.chart_pattern.registry import PatternRegistry
    PatternRegistry.autodiscover()


# ---------------------------------------------------------------------------
# PatternRegistry — register()
# ---------------------------------------------------------------------------

class TestPatternRegistryRegister:

    def setup_method(self):
        _reset_registry()

    def teardown_method(self):
        # Re-run autodiscover so the registry is populated for other tests
        _run_autodiscover()

    def test_register_populates_by_name(self):
        from groups.chart_pattern.registry import PatternRegistry
        from groups.chart_pattern.patterns.base import BasePatternDetector

        @PatternRegistry.register
        class _TestPattern(BasePatternDetector):
            name = "test_pattern"
            hypothesis_refs = ["H9-001"]

        assert "test_pattern" in PatternRegistry.get_all_patterns()

    def test_register_populates_by_hypothesis(self):
        from groups.chart_pattern.registry import PatternRegistry
        from groups.chart_pattern.patterns.base import BasePatternDetector

        @PatternRegistry.register
        class _TestPattern2(BasePatternDetector):
            name = "test_pattern2"
            hypothesis_refs = ["H9-002", "H9-003"]

        by_hyp = PatternRegistry.get_all_by_hypothesis()
        assert "H9-002" in by_hyp
        assert "H9-003" in by_hyp

    def test_register_returns_class_unchanged(self):
        from groups.chart_pattern.registry import PatternRegistry
        from groups.chart_pattern.patterns.base import BasePatternDetector

        @PatternRegistry.register
        class _TestPattern3(BasePatternDetector):
            name = "test_pattern3"
            hypothesis_refs = ["H9-004"]

        assert issubclass(_TestPattern3, BasePatternDetector)

    def test_register_multiple_hypothesis_refs(self):
        from groups.chart_pattern.registry import PatternRegistry
        from groups.chart_pattern.patterns.base import BasePatternDetector

        @PatternRegistry.register
        class _Multi(BasePatternDetector):
            name = "multi_direction"
            hypothesis_refs = ["H9-010", "H9-011"]

        by_hyp = PatternRegistry.get_all_by_hypothesis()
        assert by_hyp["H9-010"] is _Multi
        assert by_hyp["H9-011"] is _Multi


# ---------------------------------------------------------------------------
# PatternRegistry — get_pattern()
# ---------------------------------------------------------------------------

class TestPatternRegistryGetPattern:

    def setup_method(self):
        _reset_registry()
        _run_autodiscover()

    def test_get_pattern_by_name(self):
        from groups.chart_pattern.registry import PatternRegistry
        klass = PatternRegistry.get_pattern("double_bottom")
        assert klass is not None

    def test_get_pattern_by_hypothesis_ref(self):
        from groups.chart_pattern.registry import PatternRegistry
        klass = PatternRegistry.get_pattern("H1-003")
        assert klass is not None

    def test_get_pattern_by_name_and_hypothesis_are_same_class(self):
        from groups.chart_pattern.registry import PatternRegistry
        by_name = PatternRegistry.get_pattern("double_bottom")
        by_hyp = PatternRegistry.get_pattern("H1-003")
        assert by_name is by_hyp

    def test_get_pattern_unknown_returns_none(self):
        from groups.chart_pattern.registry import PatternRegistry
        assert PatternRegistry.get_pattern("nonexistent_pattern") is None
        assert PatternRegistry.get_pattern("H9-999") is None


# ---------------------------------------------------------------------------
# PatternRegistry — autodiscover()
# ---------------------------------------------------------------------------

class TestPatternRegistryAutodiscover:

    def setup_method(self):
        _reset_registry()

    def test_autodiscover_registers_all_five_hypotheses(self):
        from groups.chart_pattern.registry import PatternRegistry
        PatternRegistry.autodiscover()
        by_hyp = PatternRegistry.get_all_by_hypothesis()
        for href in ("H1-001", "H1-002", "H1-003", "H1-004", "H1-005"):
            assert href in by_hyp, f"{href} not found in registry after autodiscover"

    def test_autodiscover_registers_all_pattern_names(self):
        from groups.chart_pattern.registry import PatternRegistry
        PatternRegistry.autodiscover()
        by_name = PatternRegistry.get_all_patterns()
        expected = {"head_and_shoulders", "double_bottom", "descending_triangle", "triple_bottom"}
        assert expected.issubset(set(by_name.keys()))

    def test_autodiscover_is_idempotent(self):
        from groups.chart_pattern.registry import PatternRegistry
        PatternRegistry.autodiscover()
        count_before = len(PatternRegistry.get_all_by_hypothesis())
        PatternRegistry.autodiscover()  # second call
        count_after = len(PatternRegistry.get_all_by_hypothesis())
        assert count_after == count_before

    def test_autodiscover_sets_discovered_flag(self):
        from groups.chart_pattern.registry import PatternRegistry
        assert PatternRegistry._discovered is False
        PatternRegistry.autodiscover()
        assert PatternRegistry._discovered is True


# ---------------------------------------------------------------------------
# BasePatternDetector
# ---------------------------------------------------------------------------

class TestBasePatternDetector:

    def test_is_subclass_of_pattern_state_machine(self):
        from groups.chart_pattern.patterns.base import BasePatternDetector
        from groups.chart_pattern.state_machine import PatternStateMachine
        assert issubclass(BasePatternDetector, PatternStateMachine)

    def test_class_attributes_defined(self):
        from groups.chart_pattern.patterns.base import BasePatternDetector
        assert hasattr(BasePatternDetector, "name")
        assert hasattr(BasePatternDetector, "hypothesis_refs")
        assert hasattr(BasePatternDetector, "direction_bias")
        assert hasattr(BasePatternDetector, "min_bars_needed")

    def test_class_attribute_defaults(self):
        from groups.chart_pattern.patterns.base import BasePatternDetector
        assert BasePatternDetector.name == ""
        assert BasePatternDetector.hypothesis_refs == []
        assert BasePatternDetector.direction_bias == "both"
        assert BasePatternDetector.min_bars_needed == 10

    def test_detect_delegates_to_advance(self):
        """detect() should call advance(), which raises NotImplementedError on base."""
        from groups.chart_pattern.patterns.base import BasePatternDetector
        det = BasePatternDetector(pattern_type="test", symbol="BTCUSDT", timeframe="1h")
        with pytest.raises(NotImplementedError):
            det.detect(object())


# ---------------------------------------------------------------------------
# Concrete pattern classes
# ---------------------------------------------------------------------------

class TestConcretePatternClasses:

    def test_double_bottom_has_correct_metadata(self):
        from groups.chart_pattern.patterns.double_bottom import DoubleBottomMachine
        assert DoubleBottomMachine.name == "double_bottom"
        assert "H1-003" in DoubleBottomMachine.hypothesis_refs
        assert DoubleBottomMachine.direction_bias == "long"

    def test_head_and_shoulders_covers_both_hypotheses(self):
        from groups.chart_pattern.patterns.head_and_shoulders import HeadAndShouldersMachine
        assert "H1-001" in HeadAndShouldersMachine.hypothesis_refs
        assert "H1-002" in HeadAndShouldersMachine.hypothesis_refs
        assert HeadAndShouldersMachine.direction_bias == "both"

    def test_descending_triangle_is_short(self):
        from groups.chart_pattern.patterns.descending_triangle import DescendingTriangleMachine
        assert "H1-004" in DescendingTriangleMachine.hypothesis_refs
        assert DescendingTriangleMachine.direction_bias == "short"

    def test_triple_bottom_is_long(self):
        from groups.chart_pattern.patterns.triple_bottom import TripleBottomMachine
        assert "H1-005" in TripleBottomMachine.hypothesis_refs
        assert TripleBottomMachine.direction_bias == "long"

    def test_double_bottom_is_base_pattern_detector(self):
        from groups.chart_pattern.patterns.double_bottom import DoubleBottomMachine
        from groups.chart_pattern.patterns.base import BasePatternDetector
        assert issubclass(DoubleBottomMachine, BasePatternDetector)


# ---------------------------------------------------------------------------
# Backward compatibility (state_machine.py re-exports)
# ---------------------------------------------------------------------------

class TestStateMAchineBackwardCompat:

    def test_double_bottom_importable_from_state_machine(self):
        from groups.chart_pattern.state_machine import DoubleBottomMachine
        assert DoubleBottomMachine is not None

    def test_head_and_shoulders_importable_from_state_machine(self):
        from groups.chart_pattern.state_machine import HeadAndShouldersMachine
        assert HeadAndShouldersMachine is not None

    def test_descending_triangle_importable_from_state_machine(self):
        from groups.chart_pattern.state_machine import DescendingTriangleMachine
        assert DescendingTriangleMachine is not None

    def test_triple_bottom_importable_from_state_machine(self):
        from groups.chart_pattern.state_machine import TripleBottomMachine
        assert TripleBottomMachine is not None

    def test_pattern_state_importable_from_state_machine(self):
        from groups.chart_pattern.state_machine import PatternState
        assert PatternState.INACTIVE == "INACTIVE"
        assert PatternState.CONFIRMED == "CONFIRMED"

    def test_state_machine_classes_are_same_as_patterns(self):
        """Re-exported classes must be identical to the canonical pattern classes."""
        from groups.chart_pattern.state_machine import DoubleBottomMachine as SM_DB
        from groups.chart_pattern.patterns.double_bottom import DoubleBottomMachine as P_DB
        assert SM_DB is P_DB


# ---------------------------------------------------------------------------
# ChartPatternGroup integration
# ---------------------------------------------------------------------------

class TestChartPatternGroupRegistry:

    def test_initialize_machines_uses_registry_when_populated(self):
        """After autodiscover, _initialize_machines_for_symbol uses registry."""
        from groups.chart_pattern.registry import PatternRegistry
        from groups.chart_pattern.group import ChartPatternGroup
        from core.events import EventBus
        from core.schemas import ModeGate
        from core.state import SystemState

        PatternRegistry.autodiscover()
        state = SystemState(mode=ModeGate.SHADOW)
        bus = EventBus()
        group = ChartPatternGroup(state, bus)
        group._initialize_machines_for_symbol("BTCUSDT", "1h")

        machine_keys = set(group._machines["BTCUSDT"].keys())
        # All five hypothesis refs should be present (from registry)
        assert {"H1-001", "H1-002", "H1-003", "H1-004", "H1-005"}.issubset(machine_keys)

    def test_initialize_machines_fallback_to_pattern_machines(self):
        """When registry is empty, fall back to PATTERN_MACHINES."""
        from groups.chart_pattern.registry import PatternRegistry
        from groups.chart_pattern.group import ChartPatternGroup
        from core.events import EventBus
        from core.schemas import ModeGate
        from core.state import SystemState

        PatternRegistry._reset()  # empty registry
        state = SystemState(mode=ModeGate.SHADOW)
        bus = EventBus()
        group = ChartPatternGroup(state, bus)
        group._initialize_machines_for_symbol("BTCUSDT", "1h")

        machine_keys = set(group._machines["BTCUSDT"].keys())
        assert {"H1-001", "H1-002", "H1-003", "H1-004", "H1-005"}.issubset(machine_keys)

        # Restore for subsequent tests
        PatternRegistry.autodiscover()


# ---------------------------------------------------------------------------
# MDPState chart pattern fields
# ---------------------------------------------------------------------------

class TestMDPStateChartPatternFields:

    def _build_base_mdp(self):
        from mdp.state import MDPState
        return MDPState(
            direction="long", symbol="BTCUSDT", timeframe="1h",
            entry_price=50000.0, stop_price=49000.0, target_price=52000.0,
            r_r_ratio=2.0, composite_score=0.65, setup_quality="B",
            btc_macro="bull", trending=True, volatility_regime="normal", adx14=25.0,
            at_support=True, at_resistance=False,
            approve_count=12, reject_count=5, abstain_count=3,
            avg_score=6.5, weighted_score=6.8, panel_confidence=0.7,
            evaluator_scores={}, evaluator_votes={}, evaluator_confidences={},
            score_std_dev=1.2, bull_bear_split=0.6,
            key_risks=[], key_strengths=[],
            current_equity=100000.0, drawdown_pct=0.0, daily_pnl_pct=0.0,
            open_positions_count=0, total_exposure_pct=0.0,
            recent_win_rate=0.5, current_streak=0, trades_last_24_bars=0,
        )

    def test_active_chart_patterns_defaults_none(self):
        state = self._build_base_mdp()
        assert state.active_chart_patterns is None

    def test_chart_pattern_completion_pct_defaults_none(self):
        state = self._build_base_mdp()
        assert state.chart_pattern_completion_pct is None

    def test_chart_pattern_measured_move_defaults_none(self):
        state = self._build_base_mdp()
        assert state.chart_pattern_measured_move is None

    def test_to_dict_includes_chart_pattern_fields(self):
        state = self._build_base_mdp()
        d = state.to_dict()
        assert "active_chart_patterns" in d
        assert "chart_pattern_completion_pct" in d
        assert "chart_pattern_measured_move" in d

    def test_to_dict_none_values_serialised(self):
        state = self._build_base_mdp()
        d = state.to_dict()
        assert d["active_chart_patterns"] is None
        assert d["chart_pattern_completion_pct"] is None
        assert d["chart_pattern_measured_move"] is None

    def test_to_dict_with_pattern_data(self):
        state = self._build_base_mdp()
        state.active_chart_patterns = ["H1-003"]
        state.chart_pattern_completion_pct = 0.75
        state.chart_pattern_measured_move = 3000.0
        d = state.to_dict()
        assert d["active_chart_patterns"] == ["H1-003"]
        assert d["chart_pattern_completion_pct"] == pytest.approx(0.75)
        assert d["chart_pattern_measured_move"] == pytest.approx(3000.0)


# ---------------------------------------------------------------------------
# MDPStateBuilder — chart_pattern_group parameter
# ---------------------------------------------------------------------------

class TestMDPStateBuilderChartPatternGroup:

    def _make_builder_inputs(self):
        import uuid
        from decimal import Decimal
        from datetime import datetime
        from core.schemas import RegimeContext, Direction
        from traders.panel import PanelResult
        from traders.evaluators import TraderVerdict
        from core.setup_packet import (
            BTCSetupPacket, IndicatorSnapshot, StructuralSnapshot,
            CandlestickSnapshot, ChartPatternSnapshot, SetupProposal, MACDValues,
        )

        packet = BTCSetupPacket(
            packet_id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="1h",
            bar_timestamp=datetime.utcnow(),
            assembled_at=datetime.utcnow(),
            indicators=IndicatorSnapshot(
                close=Decimal("65000"),
                ema20=Decimal("64000"), ema50=Decimal("63000"), ema200=Decimal("60000"),
                ema_alignment="full_bull", rsi14=58.0, prev_rsi14=55.0,
                rsi_direction="rising",
                macd=MACDValues(
                    macd_line=Decimal("100"), signal_line=Decimal("80"),
                    histogram=Decimal("20"), trend="bullish_above",
                ),
                bb_upper=Decimal("67000"), bb_middle=Decimal("64000"),
                bb_lower=Decimal("61000"), bb_width_pct=45.0, bb_position="middle",
                atr14=Decimal("800"), atr14_vs_sma20=1.0,
                volatility_regime="normal", adx14=32.0,
                trend_strength="strong", volume_ratio=1.5, volume_character="above_avg",
            ),
            structure=StructuralSnapshot(
                at_resistance=False, at_support=True,
                nearest_resistance=Decimal("67000"), nearest_support=Decimal("63000"),
                resistance_distance_pct=3.0, support_distance_pct=3.0,
                structure_quality="strong", trend_direction="uptrend",
                higher_highs=True, higher_lows=True,
            ),
            candlestick=CandlestickSnapshot(
                patterns_detected=[], primary_pattern=None,
                pattern_direction=None, pattern_at_structure=False,
            ),
            chart_pattern=ChartPatternSnapshot(
                active_patterns=[], confirmed_patterns=[],
                primary_confirmed=None, pattern_direction=None,
                measured_move=None, conservative_target=None, breakout_level=None,
            ),
            regime=RegimeContext(
                btc_macro="bull", trending=True, volatility_regime="normal",
                adx14=32.0, atr14=Decimal("800"), atr14_vs_sma20=1.0,
            ),
            proposal=SetupProposal(
                direction=Direction.LONG,
                entry_price=Decimal("65000"),
                stop_price=Decimal("63000"),
                target_price=Decimal("71000"),
                r_r_ratio=3.0,
                stop_distance_pct=3.1,
                target_distance_pct=9.2,
                proposed_leverage=10.0,
                proposed_risk_pct=0.01,
                setup_quality="B",
                confirming_signals=[],
                conflicting_signals=[],
                primary_thesis="Test thesis",
            ),
        )
        verdict = TraderVerdict(
            trader_id="Trend", vote="approve", score=7.0, confidence=0.8,
            pro_reason="trend aligned", anti_reason="none",
            execution_concern="none", risk_concern="none",
            explanation="trend-following setup",
        )
        panel = PanelResult(
            packet_id=packet.packet_id,
            verdicts=[verdict],
            approve_count=1, reject_count=0, abstain_count=0,
            avg_score=7.0, weighted_score=7.0,
            panel_recommendation="enter",
            panel_confidence=0.8,
            key_risks=[], key_strengths=[],
        )
        return packet, panel

    def test_build_without_chart_pattern_group_returns_none_fields(self):
        from mdp.state_builder import MDPStateBuilder
        packet, panel = self._make_builder_inputs()
        builder = MDPStateBuilder()
        state = builder.build(packet, panel)
        assert state.active_chart_patterns is None
        assert state.chart_pattern_completion_pct is None
        assert state.chart_pattern_measured_move is None

    def test_build_with_empty_chart_pattern_group(self):
        """When group has no active patterns, fields stay None."""
        from mdp.state_builder import MDPStateBuilder
        from unittest.mock import MagicMock

        packet, panel = self._make_builder_inputs()

        mock_group = MagicMock()
        mock_group._active_cache = {}
        mock_group._machines = {}
        mock_group._signals_cache = {}

        builder = MDPStateBuilder()
        state = builder.build(packet, panel, chart_pattern_group=mock_group)
        assert state.active_chart_patterns is None
        assert state.chart_pattern_completion_pct is None
        assert state.chart_pattern_measured_move is None

    def test_build_with_active_patterns_in_cache(self):
        """When active_cache has patterns, active_chart_patterns is populated."""
        from mdp.state_builder import MDPStateBuilder
        from unittest.mock import MagicMock

        packet, panel = self._make_builder_inputs()
        symbol = packet.symbol

        mock_group = MagicMock()
        mock_group._active_cache = {symbol: ["H1-003"]}
        mock_group._machines = {}
        mock_group._signals_cache = {}

        builder = MDPStateBuilder()
        state = builder.build(packet, panel, chart_pattern_group=mock_group)
        assert state.active_chart_patterns == ["H1-003"]

    def test_build_completion_pct_from_forming_machines(self):
        """chart_pattern_completion_pct is avg bars_in_formation / max_bars."""
        from mdp.state_builder import MDPStateBuilder
        from groups.chart_pattern.state_machine import PatternStateMachine, PatternState
        from unittest.mock import MagicMock

        packet, panel = self._make_builder_inputs()
        symbol = packet.symbol

        machine = PatternStateMachine(
            pattern_type="H1-003", symbol=symbol, timeframe="1h",
        )
        machine.state = PatternState.FORMING
        machine.bars_in_formation = 30  # 30/60 = 0.5
        machine.max_bars = 60

        mock_group = MagicMock()
        mock_group._active_cache = {}
        mock_group._machines = {symbol: {"H1-003": machine}}
        mock_group._signals_cache = {}

        builder = MDPStateBuilder()
        state = builder.build(packet, panel, chart_pattern_group=mock_group)
        assert state.chart_pattern_completion_pct == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# SystemConfig
# ---------------------------------------------------------------------------

class TestSystemConfigEnableChartPatterns:

    def test_enable_chart_patterns_defaults_false(self):
        from config.settings import SystemConfig
        cfg = SystemConfig()
        assert cfg.enable_chart_patterns is False

    def test_enable_chart_patterns_can_be_set_true(self):
        from config.settings import SystemConfig
        cfg = SystemConfig(enable_chart_patterns=True)
        assert cfg.enable_chart_patterns is True

    def test_load_config_returns_false_by_default(self):
        from config.settings import load_config
        cfg = load_config()
        assert cfg.enable_chart_patterns is False
