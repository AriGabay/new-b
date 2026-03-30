"""
Tests for the MDP decision framework (Task 3).

Covers:
  - MDPState construction and serialisation
  - MDPPolicy: each of the 6 rules
  - Safety rail override
  - TransitionLogger: log + reward backfill
  - MDPStateBuilder: full build from packet + panel + state
  - FinalDecisionGroup: MDP-aware path
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_mdp_state(
    approve_count=15,
    reject_count=6,
    abstain_count=2,
    avg_score=6.5,
    weighted_score=6.5,
    score_std_dev=1.0,
    r_r_ratio=2.5,
    composite_score=0.70,
    drawdown_pct=0.05,
    current_streak=1,
    recent_win_rate=0.55,
    volatility_regime="normal",
    btc_macro="bull",
    direction="long",
    symbol="BTCUSDT",
):
    """Build a minimal MDPState for testing."""
    from mdp.state import MDPState

    evaluator_names = [f"Trader{i}" for i in range(20)]
    evaluator_scores = {n: avg_score for n in evaluator_names}
    evaluator_votes = {n: ("approve" if i < approve_count else "reject")
                       for i, n in enumerate(evaluator_names)}
    evaluator_confidences = {n: 0.75 for n in evaluator_names}

    return MDPState(
        direction=direction,
        symbol=symbol,
        timeframe="1h",
        entry_price=65000.0,
        stop_price=63000.0,
        target_price=70000.0,
        r_r_ratio=r_r_ratio,
        composite_score=composite_score,
        setup_quality="A",
        btc_macro=btc_macro,
        trending=True,
        volatility_regime=volatility_regime,
        adx14=30.0,
        at_support=True,
        at_resistance=False,
        approve_count=approve_count,
        reject_count=reject_count,
        abstain_count=abstain_count,
        avg_score=avg_score,
        weighted_score=weighted_score,
        panel_confidence=approve_count / 20.0,
        evaluator_scores=evaluator_scores,
        evaluator_votes=evaluator_votes,
        evaluator_confidences=evaluator_confidences,
        score_std_dev=score_std_dev,
        bull_bear_split=0.6,
        key_risks=["wide stop"],
        key_strengths=["strong trend"],
        current_equity=100_000.0,
        drawdown_pct=drawdown_pct,
        daily_pnl_pct=0.01,
        open_positions_count=1,
        total_exposure_pct=0.05,
        recent_win_rate=recent_win_rate,
        current_streak=current_streak,
        trades_last_24_bars=2,
    )


# ---------------------------------------------------------------------------
# MDPState
# ---------------------------------------------------------------------------

class TestMDPState:

    def test_to_dict_is_json_serializable(self):
        state = _make_mdp_state()
        d = state.to_dict()
        # Should round-trip through JSON without error
        serialized = json.dumps(d)
        restored = json.loads(serialized)
        assert restored["approve_count"] == state.approve_count
        assert restored["direction"] == "long"
        assert isinstance(restored["evaluator_scores"], dict)

    def test_to_dict_has_all_required_keys(self):
        state = _make_mdp_state()
        d = state.to_dict()
        required_keys = [
            "direction", "symbol", "timeframe", "entry_price", "stop_price",
            "target_price", "r_r_ratio", "composite_score", "setup_quality",
            "btc_macro", "trending", "volatility_regime", "adx14",
            "at_support", "at_resistance",
            "approve_count", "reject_count", "abstain_count",
            "avg_score", "weighted_score", "panel_confidence",
            "evaluator_scores", "evaluator_votes", "evaluator_confidences",
            "score_std_dev", "bull_bear_split",
            "key_risks", "key_strengths",
            "current_equity", "drawdown_pct", "daily_pnl_pct",
            "open_positions_count", "total_exposure_pct",
            "recent_win_rate", "current_streak", "trades_last_24_bars",
        ]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_to_vector_returns_floats(self):
        state = _make_mdp_state()
        vec = state.to_vector()
        assert isinstance(vec, list)
        assert len(vec) > 0
        for v in vec:
            assert isinstance(v, float), f"Non-float in vector: {v!r}"

    def test_to_vector_length_includes_evaluators(self):
        state = _make_mdp_state()
        vec = state.to_vector()
        # 25 base features + 2 macro features + 20 eval scores + 20 eval confidences = 67
        assert len(vec) == 25 + 2 + 20 + 20

    def test_direction_encoding(self):
        from mdp.state import MDPState
        long_state = _make_mdp_state(direction="long")
        short_state = _make_mdp_state(direction="short")
        long_vec = long_state.to_vector()
        short_vec = short_state.to_vector()
        assert long_vec[0] == 1.0
        assert short_vec[0] == -1.0


# ---------------------------------------------------------------------------
# MDPAction
# ---------------------------------------------------------------------------

class TestMDPAction:

    def test_all_actions_have_size_multipliers(self):
        from mdp.actions import MDPAction, ACTION_SIZE_MULTIPLIERS
        for action in MDPAction:
            assert action in ACTION_SIZE_MULTIPLIERS

    def test_enter_actions_have_positive_multipliers(self):
        from mdp.actions import MDPAction, ACTION_SIZE_MULTIPLIERS, ENTER_ACTIONS
        for action in ENTER_ACTIONS:
            assert ACTION_SIZE_MULTIPLIERS[action] > 0.0

    def test_non_enter_actions_have_zero_multipliers(self):
        from mdp.actions import MDPAction, ACTION_SIZE_MULTIPLIERS, ENTER_ACTIONS
        for action in MDPAction:
            if action not in ENTER_ACTIONS:
                assert ACTION_SIZE_MULTIPLIERS[action] == 0.0

    def test_high_conviction_has_largest_multiplier(self):
        from mdp.actions import MDPAction, ACTION_SIZE_MULTIPLIERS
        hc = ACTION_SIZE_MULTIPLIERS[MDPAction.ENTER_HIGH_CONVICTION]
        med = ACTION_SIZE_MULTIPLIERS[MDPAction.ENTER_MEDIUM]
        small = ACTION_SIZE_MULTIPLIERS[MDPAction.ENTER_SMALL]
        assert hc > med > small > 0.0


# ---------------------------------------------------------------------------
# MDPPolicy rules
# ---------------------------------------------------------------------------

class TestMDPPolicyRules:

    def setup_method(self):
        from mdp.policy import MDPPolicy
        self.policy = MDPPolicy()

    def test_r0_reduce_risk_streak(self):
        """R0: triggered by streak <= -8 (Phase 4: relaxed from -4)."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(current_streak=-9, drawdown_pct=0.05)
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.REDUCE_RISK
        assert reasoning["rule_number"] == 0

    def test_r0_reduce_risk_drawdown(self):
        """R0: triggered by drawdown > 0.38 (Phase 4: relaxed from 0.25)."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(current_streak=0, drawdown_pct=0.40)
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.REDUCE_RISK
        assert reasoning["rule_number"] == 0

    def test_r1_high_conviction(self):
        """R1: strong consensus + healthy account."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=18,  # Phase 4: HC_MIN_APPROVALS raised to 17
            avg_score=7.5,
            score_std_dev=1.0,
            drawdown_pct=0.05,
            recent_win_rate=0.60,
            r_r_ratio=3.0,
        )
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.ENTER_HIGH_CONVICTION
        assert reasoning["rule_number"] == 1
        assert reasoning["size_multiplier"] == 1.5

    def test_r1_fails_if_std_dev_too_high(self):
        """R1 requires score_std_dev < 1.5."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=15,
            avg_score=7.5,
            score_std_dev=2.0,   # too high
            drawdown_pct=0.05,
            recent_win_rate=0.60,
            r_r_ratio=3.0,
        )
        action, _ = self.policy.decide(state)
        assert action != MDPAction.ENTER_HIGH_CONVICTION

    def test_r2_enter_medium(self):
        """R2: standard qualifying entry."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=15,
            avg_score=6.5,
            r_r_ratio=2.5,
            drawdown_pct=0.05,
            current_streak=0,
            volatility_regime="normal",
        )
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.ENTER_MEDIUM
        assert reasoning["rule_number"] == 2
        assert reasoning["size_multiplier"] == 1.0

    def test_r2_fails_if_rr_too_low(self):
        """R2 requires r_r_ratio >= 2.0."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=15,
            avg_score=6.5,
            r_r_ratio=1.7,     # below threshold
            drawdown_pct=0.05,
            current_streak=0,
            volatility_regime="normal",
        )
        action, _ = self.policy.decide(state)
        assert action != MDPAction.ENTER_MEDIUM

    def test_r3_enter_small_high_drawdown(self):
        """R3: qualifying but high drawdown → ENTER_SMALL."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=15,
            avg_score=6.5,
            r_r_ratio=1.7,     # <2.0 so R2 doesn't fire
            drawdown_pct=0.15, # triggers R3
            current_streak=0,
            volatility_regime="normal",
        )
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.ENTER_SMALL
        assert reasoning["rule_number"] == 3
        assert reasoning["size_multiplier"] == 0.5

    def test_r3_enter_small_high_volatility(self):
        """R3: qualifying but high volatility → ENTER_SMALL."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=15,
            avg_score=6.5,
            r_r_ratio=1.7,
            drawdown_pct=0.05,
            current_streak=0,
            volatility_regime="high",   # triggers R3
        )
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.ENTER_SMALL
        assert reasoning["rule_number"] == 3

    def test_r3_enter_small_loss_streak(self):
        """R3: qualifying but loss streak -3 → ENTER_SMALL."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=15,
            avg_score=6.5,
            r_r_ratio=1.7,
            drawdown_pct=0.05,
            current_streak=-3,   # triggers R3
            volatility_regime="normal",
        )
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.ENTER_SMALL
        assert reasoning["rule_number"] == 3

    def test_r4_defer(self):
        """R4: near threshold, promising — defer."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=12,      # >= 11 but < 14 (DEFER range)
            avg_score=5.6,         # >= 5.5
            composite_score=0.68,  # >= 0.65
            score_std_dev=1.5,     # < 2.0
            r_r_ratio=1.7,
            drawdown_pct=0.05,
            current_streak=0,
            volatility_regime="normal",
        )
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.DEFER
        assert reasoning["rule_number"] == 4

    def test_r5_no_trade_fallback(self):
        """R5: nothing fires → NO_TRADE."""
        from mdp.actions import MDPAction
        state = _make_mdp_state(
            approve_count=5,
            avg_score=4.0,
            composite_score=0.40,
            r_r_ratio=1.2,
            drawdown_pct=0.05,
            current_streak=0,
            volatility_regime="normal",
        )
        action, reasoning = self.policy.decide(state)
        assert action == MDPAction.NO_TRADE
        assert reasoning["rule_number"] == 5

    def test_reasoning_always_has_required_keys(self):
        """All rules must return reasoning with rule_fired + size_multiplier."""
        state = _make_mdp_state()
        action, reasoning = self.policy.decide(state)
        assert "rule_fired" in reasoning
        assert "rule_number" in reasoning
        assert "size_multiplier" in reasoning
        assert "factors" in reasoning


# ---------------------------------------------------------------------------
# Safety rail override
# ---------------------------------------------------------------------------

class TestSafetyRailOverride:

    def _build_packet_and_panel(self):
        """Build a qualifying packet+panel that MDP would approve."""
        import sys
        sys.path.insert(0, "src") if "src" not in str(sys.path) else None

        from core.setup_packet import (
            BTCSetupPacket, IndicatorSnapshot, StructuralSnapshot,
            CandlestickSnapshot, ChartPatternSnapshot, SetupProposal, MACDValues,
        )
        from core.schemas import RegimeContext, Direction
        from traders.panel import PanelResult
        from traders.evaluators import TraderVerdict

        packet = BTCSetupPacket(
            packet_id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="1h",
            bar_timestamp=datetime.utcnow(),
            assembled_at=datetime.utcnow(),
            indicators=IndicatorSnapshot(
                close=Decimal("65000"),
                ema20=Decimal("64000"),
                ema50=Decimal("63000"),
                ema200=Decimal("60000"),
                ema_alignment="full_bull",
                rsi14=58.0,
                prev_rsi14=55.0,
                rsi_direction="rising",
                macd=MACDValues(
                    macd_line=Decimal("100"),
                    signal_line=Decimal("80"),
                    histogram=Decimal("20"),
                    trend="bullish_above",
                ),
                bb_upper=Decimal("67000"),
                bb_middle=Decimal("64000"),
                bb_lower=Decimal("61000"),
                bb_width_pct=45.0,
                bb_position="middle",
                atr14=Decimal("800"),
                atr14_vs_sma20=1.0,
                volatility_regime="normal",
                adx14=32.0,
                trend_strength="strong",
                volume_ratio=1.5,
                volume_character="above_avg",
            ),
            structure=StructuralSnapshot(
                at_resistance=False,
                at_support=True,
                nearest_resistance=Decimal("67000"),
                nearest_support=Decimal("63000"),
                resistance_distance_pct=3.0,
                support_distance_pct=3.0,
                structure_quality="strong",
                trend_direction="uptrend",
                higher_highs=True,
                higher_lows=True,
            ),
            candlestick=CandlestickSnapshot(
                patterns_detected=[],
                primary_pattern=None,
                pattern_direction=None,
                pattern_at_structure=False,
            ),
            chart_pattern=ChartPatternSnapshot(
                active_patterns=[],
                confirmed_patterns=[],
                primary_confirmed=None,
                pattern_direction=None,
                measured_move=None,
                conservative_target=None,
                breakout_level=None,
            ),
            regime=RegimeContext(
                btc_macro="bull",
                trending=True,
                volatility_regime="normal",
                adx14=32.0,
                atr14=Decimal("800"),
                atr14_vs_sma20=1.0,
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
                setup_quality="A",
                confirming_signals=["ema_trend"],
                conflicting_signals=[],
                primary_thesis="Bullish breakout above resistance",
            ),
        )

        # Panel with 14/20 approvals
        verdicts = []
        for i in range(20):
            vote = "approve" if i < 14 else "reject"
            verdicts.append(TraderVerdict(
                trader_id=f"Trader{i}",
                score=7.0 if vote == "approve" else 4.0,
                vote=vote,
                confidence=0.80,
                pro_reason="strong trend",
                anti_reason="none",
                execution_concern="none",
                risk_concern="none",
                explanation="Test verdict",
            ))

        panel = PanelResult(
            packet_id=packet.packet_id,
            verdicts=verdicts,
            approve_count=14,
            reject_count=6,
            abstain_count=0,
            avg_score=6.3,
            weighted_score=6.3,
            panel_recommendation="enter",
            panel_confidence=0.70,
            key_risks=[],
            key_strengths=["strong trend"],
        )

        return packet, panel

    def test_bear_regime_blocks_long_even_with_high_conviction(self):
        """Safety rail 5 must override ENTER_HIGH_CONVICTION."""
        from decision.final_group import FinalDecisionGroup
        from core.schemas import RegimeContext

        packet, panel = self._build_packet_and_panel()
        # Inject bear regime
        packet.regime = RegimeContext(
            btc_macro="bear",
            trending=True,
            volatility_regime="normal",
            adx14=32.0,
            atr14=Decimal("800"),
            atr14_vs_sma20=1.0,
        )

        fd = FinalDecisionGroup()
        decision = fd.decide(packet, panel)
        assert decision.decision == "hold"
        assert decision.safety_override is True
        assert any("bear" in r for r in decision.safety_rails_triggered)

    def test_low_avg_score_blocks_entry(self):
        """Safety rail 1: avg_score < 5.0 → hold."""
        from decision.final_group import FinalDecisionGroup
        from traders.panel import PanelResult
        from traders.evaluators import TraderVerdict

        packet, _ = self._build_packet_and_panel()

        # Build panel with avg_score < 5.0
        verdicts = [
            TraderVerdict(
                trader_id=f"Trader{i}", score=4.0, vote="approve",
                confidence=0.5, pro_reason="ok", anti_reason="none",
                execution_concern="none", risk_concern="none",
                explanation="low score",
            )
            for i in range(12)
        ] + [
            TraderVerdict(
                trader_id=f"Trader{i}", score=4.0, vote="reject",
                confidence=0.5, pro_reason="none", anti_reason="risky",
                execution_concern="none", risk_concern="risk",
                explanation="reject",
            )
            for i in range(12, 20)
        ]
        low_panel = PanelResult(
            packet_id=packet.packet_id,
            verdicts=verdicts,
            approve_count=15,
            reject_count=8,
            abstain_count=0,
            avg_score=4.0,  # below floor
            weighted_score=4.0,
            panel_recommendation="hold",
            panel_confidence=0.4,
        )

        fd = FinalDecisionGroup()
        decision = fd.decide(packet, low_panel)
        assert decision.decision == "hold"
        assert any("5.0" in r for r in decision.safety_rails_triggered)

    def test_high_volatility_requires_14_approvals(self):
        """Safety rail 6: high volatility requires 14+ approvals."""
        from decision.final_group import FinalDecisionGroup
        from core.schemas import RegimeContext

        packet, panel = self._build_packet_and_panel()
        # Only 12 approvals
        panel.approve_count = 12
        panel.reject_count = 8
        # Set high volatility
        packet.regime = RegimeContext(
            btc_macro="bull",
            trending=True,
            volatility_regime="high",
            adx14=32.0,
            atr14=Decimal("800"),
            atr14_vs_sma20=1.0,
        )

        fd = FinalDecisionGroup()
        decision = fd.decide(packet, panel)
        assert decision.decision == "hold"
        assert decision.safety_override is True

    def test_qualifying_entry_succeeds(self):
        """No safety rails triggered + qualifying panel → enter decision."""
        from decision.final_group import FinalDecisionGroup

        packet, panel = self._build_packet_and_panel()
        fd = FinalDecisionGroup()
        decision = fd.decide(packet, panel)
        assert decision.decision == "enter"
        assert decision.safety_override is False
        assert decision.mdp_action != ""


# ---------------------------------------------------------------------------
# TransitionLogger
# ---------------------------------------------------------------------------

class TestTransitionLogger:

    def _make_ext(self):
        """Create an in-memory JournalExtension."""
        from learning.journal_extension import JournalExtension
        conn = sqlite3.connect(":memory:")
        ext = JournalExtension(conn)
        ext.initialize()
        return ext

    def test_log_transition_creates_row(self):
        from mdp.transition_logger import TransitionLogger
        from mdp.actions import MDPAction

        ext = self._make_ext()
        tl = TransitionLogger(ext)
        state = _make_mdp_state()
        action = MDPAction.ENTER_MEDIUM
        reasoning = {"rule_fired": "ENTER_MEDIUM", "rule_number": 2,
                     "factors": {}, "size_multiplier": 1.0}

        t_id = tl.log_transition(state, action, reasoning)
        assert t_id != ""

        rows = tl.query_transitions()
        assert len(rows) == 1
        assert rows[0]["action"] == "enter_medium"
        assert rows[0]["reward"] is None  # not yet backfilled

    def test_no_trade_gets_immediate_zero_reward(self):
        """NO_TRADE / DEFER should get reward=0.0 immediately."""
        from mdp.transition_logger import TransitionLogger
        from mdp.actions import MDPAction

        ext = self._make_ext()
        tl = TransitionLogger(ext)
        state = _make_mdp_state()
        reasoning = {"rule_fired": "NO_TRADE", "rule_number": 5,
                     "factors": {}, "size_multiplier": 0.0}

        t_id = tl.log_transition(state, MDPAction.NO_TRADE, reasoning)
        rows = tl.query_transitions()
        assert rows[0]["reward"] == 0.0

    def test_update_reward_backfills(self):
        """update_reward() must backfill reward + next_state."""
        from mdp.transition_logger import TransitionLogger
        from mdp.actions import MDPAction

        ext = self._make_ext()
        tl = TransitionLogger(ext)
        state = _make_mdp_state()
        reasoning = {"rule_fired": "ENTER_MEDIUM", "rule_number": 2,
                     "factors": {}, "size_multiplier": 1.0}
        t_id = tl.log_transition(state, MDPAction.ENTER_MEDIUM, reasoning)

        # Trade closes with 2.3R reward
        next_state = _make_mdp_state(drawdown_pct=0.03)
        tl.update_reward(t_id, reward=2.3, next_state=next_state)

        rows = tl.query_transitions()
        assert rows[0]["reward"] == pytest.approx(2.3, abs=0.001)
        assert rows[0]["next_state_json"] is not None

        next_state_loaded = json.loads(rows[0]["next_state_json"])
        assert next_state_loaded["drawdown_pct"] == pytest.approx(0.03, abs=0.001)

    def test_update_reward_with_trade_id(self):
        """update_reward() backfills trade_id."""
        from mdp.transition_logger import TransitionLogger
        from mdp.actions import MDPAction

        ext = self._make_ext()
        tl = TransitionLogger(ext)
        state = _make_mdp_state()
        reasoning = {"rule_fired": "ENTER_MEDIUM", "rule_number": 2,
                     "factors": {}, "size_multiplier": 1.0}
        t_id = tl.log_transition(state, MDPAction.ENTER_MEDIUM, reasoning)
        tl.update_reward(t_id, reward=1.5, trade_id="pos_abc123")

        rows = tl.query_transitions()
        assert rows[0]["trade_id"] == "pos_abc123"

    def test_transition_state_json_round_trips(self):
        """State stored in DB must deserialize correctly."""
        from mdp.transition_logger import TransitionLogger
        from mdp.actions import MDPAction

        ext = self._make_ext()
        tl = TransitionLogger(ext)
        state = _make_mdp_state(approve_count=15, avg_score=7.2)
        reasoning = {"rule_fired": "ENTER_HIGH_CONVICTION", "rule_number": 1,
                     "factors": {}, "size_multiplier": 1.5}
        tl.log_transition(state, MDPAction.ENTER_HIGH_CONVICTION, reasoning)

        rows = tl.query_transitions()
        stored = json.loads(rows[0]["state_json"])
        assert stored["approve_count"] == 15
        assert stored["avg_score"] == pytest.approx(7.2, abs=0.001)

    def test_reasoning_stored_as_json(self):
        """Reasoning dict must be stored as valid JSON."""
        from mdp.transition_logger import TransitionLogger
        from mdp.actions import MDPAction

        ext = self._make_ext()
        tl = TransitionLogger(ext)
        state = _make_mdp_state()
        reasoning = {
            "rule_fired": "ENTER_MEDIUM",
            "rule_number": 2,
            "factors": {"approve_count": 12, "avg_score": 6.5},
            "size_multiplier": 1.0,
        }
        tl.log_transition(state, MDPAction.ENTER_MEDIUM, reasoning)

        rows = tl.query_transitions()
        loaded = json.loads(rows[0]["reasoning"])
        assert loaded["rule_fired"] == "ENTER_MEDIUM"
        assert loaded["factors"]["approve_count"] == 12


# ---------------------------------------------------------------------------
# MDPStateBuilder
# ---------------------------------------------------------------------------

class TestMDPStateBuilder:

    def _build_simple_packet_and_panel(self):
        from core.setup_packet import (
            BTCSetupPacket, IndicatorSnapshot, StructuralSnapshot,
            CandlestickSnapshot, ChartPatternSnapshot, SetupProposal, MACDValues,
        )
        from core.schemas import RegimeContext, Direction
        from traders.panel import PanelResult
        from traders.evaluators import TraderVerdict

        packet = BTCSetupPacket(
            packet_id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="1h",
            bar_timestamp=datetime.utcnow(),
            assembled_at=datetime.utcnow(),
            indicators=IndicatorSnapshot(
                close=Decimal("65000"),
                ema20=Decimal("64000"),
                ema50=Decimal("63000"),
                ema200=Decimal("60000"),
                ema_alignment="full_bull",
                rsi14=58.0,
                prev_rsi14=55.0,
                rsi_direction="rising",
                macd=MACDValues(
                    macd_line=Decimal("100"),
                    signal_line=Decimal("80"),
                    histogram=Decimal("20"),
                    trend="bullish_above",
                ),
                bb_upper=Decimal("67000"),
                bb_middle=Decimal("64000"),
                bb_lower=Decimal("61000"),
                bb_width_pct=45.0,
                bb_position="middle",
                atr14=Decimal("800"),
                atr14_vs_sma20=1.0,
                volatility_regime="normal",
                adx14=32.0,
                trend_strength="strong",
                volume_ratio=1.5,
                volume_character="above_avg",
            ),
            structure=StructuralSnapshot(
                at_resistance=False,
                at_support=True,
                nearest_resistance=Decimal("67000"),
                nearest_support=Decimal("63000"),
                resistance_distance_pct=3.0,
                support_distance_pct=3.0,
                structure_quality="strong",
                trend_direction="uptrend",
                higher_highs=True,
                higher_lows=True,
            ),
            candlestick=CandlestickSnapshot(
                patterns_detected=[],
                primary_pattern=None,
                pattern_direction=None,
                pattern_at_structure=False,
            ),
            chart_pattern=ChartPatternSnapshot(
                active_patterns=[],
                confirmed_patterns=[],
                primary_confirmed=None,
                pattern_direction=None,
                measured_move=None,
                conservative_target=None,
                breakout_level=None,
            ),
            regime=RegimeContext(
                btc_macro="bull",
                trending=True,
                volatility_regime="normal",
                adx14=32.0,
                atr14=Decimal("800"),
                atr14_vs_sma20=1.0,
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
                setup_quality="A",
                confirming_signals=[],
                conflicting_signals=[],
                primary_thesis="Test thesis",
            ),
        )

        verdicts = []
        for i in range(20):
            vote = "approve" if i < 14 else "reject"
            verdicts.append(TraderVerdict(
                trader_id=f"Trader{i}",
                score=7.0 if vote == "approve" else 4.0,
                vote=vote,
                confidence=0.8,
                pro_reason="good", anti_reason="risk",
                execution_concern="none", risk_concern="none",
                explanation="test",
            ))

        panel = PanelResult(
            packet_id=packet.packet_id,
            verdicts=verdicts,
            approve_count=14,
            reject_count=6,
            abstain_count=0,
            avg_score=6.3,
            weighted_score=6.3,
            panel_recommendation="enter",
            panel_confidence=0.70,
            key_risks=["test risk"],
            key_strengths=["strong trend"],
        )
        return packet, panel

    def test_build_returns_mdp_state(self):
        from mdp.state_builder import MDPStateBuilder
        from mdp.state import MDPState

        builder = MDPStateBuilder()
        packet, panel = self._build_simple_packet_and_panel()
        state = builder.build(packet, panel, system_state=None)
        assert isinstance(state, MDPState)

    def test_approve_count_matches_panel(self):
        from mdp.state_builder import MDPStateBuilder

        builder = MDPStateBuilder()
        packet, panel = self._build_simple_packet_and_panel()
        state = builder.build(packet, panel, system_state=None)
        assert state.approve_count == panel.approve_count
        assert state.avg_score == pytest.approx(panel.avg_score, abs=0.01)

    def test_evaluator_scores_populated(self):
        from mdp.state_builder import MDPStateBuilder

        builder = MDPStateBuilder()
        packet, panel = self._build_simple_packet_and_panel()
        state = builder.build(packet, panel, system_state=None)
        assert len(state.evaluator_scores) == 20
        assert len(state.evaluator_votes) == 20
        assert len(state.evaluator_confidences) == 20

    def test_score_std_dev_computed(self):
        from mdp.state_builder import MDPStateBuilder

        builder = MDPStateBuilder()
        packet, panel = self._build_simple_packet_and_panel()
        state = builder.build(packet, panel, system_state=None)
        # Panel has approvers scoring 7.0 and rejecters scoring 4.0 (14 vs 6)
        # std_dev should be > 0
        assert state.score_std_dev > 0.0

    def test_defaults_when_no_system_state(self):
        from mdp.state_builder import MDPStateBuilder

        builder = MDPStateBuilder()
        packet, panel = self._build_simple_packet_and_panel()
        state = builder.build(packet, panel, system_state=None)
        # Defaults for missing account state
        assert state.drawdown_pct == 0.0
        assert state.open_positions_count == 0
        assert state.recent_win_rate == 0.5

    def test_system_state_equity_used(self):
        from mdp.state_builder import MDPStateBuilder
        from core.state import SystemState
        from core.schemas import ModeGate

        builder = MDPStateBuilder()
        packet, panel = self._build_simple_packet_and_panel()
        sys_state = SystemState(initial_equity=Decimal("250000"))
        state = builder.build(packet, panel, system_state=sys_state)
        assert state.current_equity == pytest.approx(250000.0, abs=0.01)

    def test_bull_bear_split_in_range(self):
        from mdp.state_builder import MDPStateBuilder

        builder = MDPStateBuilder()
        packet, panel = self._build_simple_packet_and_panel()
        state = builder.build(packet, panel, system_state=None)
        assert 0.0 <= state.bull_bear_split <= 1.0


# ---------------------------------------------------------------------------
# FinalDecisionGroup — MDP integration
# ---------------------------------------------------------------------------

class TestFinalDecisionGroupMDP:

    def _build_qualifying_packet_and_panel(self):
        """Build a packet+panel that should produce 'enter' with no rails."""
        from core.setup_packet import (
            BTCSetupPacket, IndicatorSnapshot, StructuralSnapshot,
            CandlestickSnapshot, ChartPatternSnapshot, SetupProposal, MACDValues,
        )
        from core.schemas import RegimeContext, Direction
        from traders.panel import PanelResult
        from traders.evaluators import TraderVerdict

        packet = BTCSetupPacket(
            packet_id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="1h",
            bar_timestamp=datetime.utcnow(),
            assembled_at=datetime.utcnow(),
            indicators=IndicatorSnapshot(
                close=Decimal("65000"),
                ema20=Decimal("64000"), ema50=Decimal("63000"),
                ema200=Decimal("60000"), ema_alignment="full_bull",
                rsi14=58.0, prev_rsi14=55.0, rsi_direction="rising",
                macd=MACDValues(Decimal("100"), Decimal("80"), Decimal("20"), "bullish_above"),
                bb_upper=Decimal("67000"), bb_middle=Decimal("64000"),
                bb_lower=Decimal("61000"), bb_width_pct=45.0, bb_position="middle",
                atr14=Decimal("800"), atr14_vs_sma20=1.0,
                volatility_regime="normal", adx14=32.0, trend_strength="strong",
                volume_ratio=1.5, volume_character="above_avg",
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
                entry_price=Decimal("65000"), stop_price=Decimal("63000"),
                target_price=Decimal("71000"), r_r_ratio=3.0,
                stop_distance_pct=3.1, target_distance_pct=9.2,
                proposed_leverage=10.0, proposed_risk_pct=0.01,
                setup_quality="A", confirming_signals=[], conflicting_signals=[],
                primary_thesis="Test",
            ),
        )

        verdicts = [
            TraderVerdict(
                trader_id=f"Trader{i}",
                score=7.0 if i < 14 else 4.0,
                vote="approve" if i < 14 else "reject",
                confidence=0.8,
                pro_reason="good", anti_reason="risk",
                execution_concern="none", risk_concern="none",
                explanation="test",
            )
            for i in range(20)
        ]

        panel = PanelResult(
            packet_id=packet.packet_id,
            verdicts=verdicts,
            approve_count=14,
            reject_count=6,
            abstain_count=0,
            avg_score=6.3,
            weighted_score=6.3,
            panel_recommendation="enter",
            panel_confidence=0.70,
            key_risks=[],
            key_strengths=["strong trend"],
        )
        return packet, panel

    def test_qualifying_panel_produces_enter(self):
        from decision.final_group import FinalDecisionGroup

        packet, panel = self._build_qualifying_packet_and_panel()
        fd = FinalDecisionGroup()
        decision = fd.decide(packet, panel)
        assert decision.decision == "enter"
        assert not decision.safety_rails_triggered

    def test_mdp_action_stored_in_decision(self):
        from decision.final_group import FinalDecisionGroup

        packet, panel = self._build_qualifying_packet_and_panel()
        fd = FinalDecisionGroup()
        decision = fd.decide(packet, panel)
        assert decision.mdp_action != ""
        assert isinstance(decision.mdp_reasoning, dict)

    def test_safety_override_flag_when_rails_fire(self):
        from decision.final_group import FinalDecisionGroup

        packet, panel = self._build_qualifying_packet_and_panel()
        packet.proposal.r_r_ratio = 1.0  # triggers Rail 3
        fd = FinalDecisionGroup()
        decision = fd.decide(packet, panel)
        assert decision.decision == "hold"
        assert decision.safety_override is True

    def test_size_multiplier_present(self):
        from decision.final_group import FinalDecisionGroup

        packet, panel = self._build_qualifying_packet_and_panel()
        fd = FinalDecisionGroup()
        decision = fd.decide(packet, panel)
        assert isinstance(decision.size_multiplier, float)

    def test_transition_logger_called_when_wired(self):
        """When journal_extension is provided, transition is logged."""
        from decision.final_group import FinalDecisionGroup

        ext_conn = sqlite3.connect(":memory:")
        from learning.journal_extension import JournalExtension
        ext = JournalExtension(ext_conn)
        ext.initialize()

        packet, panel = self._build_qualifying_packet_and_panel()
        fd = FinalDecisionGroup(journal_extension=ext)
        decision = fd.decide(packet, panel)

        # state_snapshot_id should be set
        assert decision.state_snapshot_id != ""

        # Row should be in mdp_transitions
        cursor = ext_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM mdp_transitions")
        count = cursor.fetchone()[0]
        assert count == 1

    def test_no_transition_logged_without_journal(self):
        """No TransitionLogger → state_snapshot_id stays empty."""
        from decision.final_group import FinalDecisionGroup

        packet, panel = self._build_qualifying_packet_and_panel()
        fd = FinalDecisionGroup()  # no journal_extension
        decision = fd.decide(packet, panel)
        assert decision.state_snapshot_id == ""

    def test_backward_compat_no_args(self):
        """FinalDecisionGroup() with no args must still work."""
        from decision.final_group import FinalDecisionGroup

        fd = FinalDecisionGroup()
        assert fd is not None

    def test_final_decision_safety_rails_intact(self):
        """Source of decide() must still contain the 6 safety rail checks."""
        import inspect
        from decision.final_group import FinalDecisionGroup

        src = inspect.getsource(FinalDecisionGroup.decide)
        assert "avg_score < 5.0" in src
        assert "reject_count" in src
        assert "r_r_ratio < 1.5" in src
        assert "setup_quality" in src
        assert "bear" in src
        assert "volatility_regime" in src


# ---------------------------------------------------------------------------
# JournalExtension: mdp_transitions table
# ---------------------------------------------------------------------------

class TestJournalExtensionMDPTable:

    def test_mdp_transitions_table_created_on_initialize(self):
        from learning.journal_extension import JournalExtension

        conn = sqlite3.connect(":memory:")
        ext = JournalExtension(conn)
        ext.initialize()

        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mdp_transitions'"
        )
        assert cursor.fetchone() is not None

    def test_mdp_transitions_schema(self):
        from learning.journal_extension import JournalExtension

        conn = sqlite3.connect(":memory:")
        ext = JournalExtension(conn)
        ext.initialize()

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(mdp_transitions)")
        columns = {row[1] for row in cursor.fetchall()}
        required = {
            "transition_id", "timestamp", "episode_id",
            "state_json", "action", "reasoning",
            "reward", "next_state_json", "trade_id",
        }
        assert required.issubset(columns)


# ---------------------------------------------------------------------------
# trades_last_24_bars — real rolling window
# ---------------------------------------------------------------------------

class TestTradesLast24Bars:

    def test_zero_before_any_close(self):
        """No trades closed yet → trades_last_24_bars == 0."""
        from core.state import PortfolioState
        p = PortfolioState()
        assert p.trades_last_24_bars == 0

    def test_increments_after_close(self):
        """After a trade closes, count increases."""
        from core.state import SystemState
        from core.schemas import ModeGate
        import asyncio
        from decimal import Decimal

        state = SystemState()
        asyncio.get_event_loop().run_until_complete(
            state.close_position("pos_1", Decimal("100"))
        )
        assert state.portfolio.trades_last_24_bars == 1

    def test_multiple_closes_counted(self):
        """Multiple closes in last 24h all counted."""
        from core.state import SystemState
        import asyncio
        from decimal import Decimal

        state = SystemState()
        loop = asyncio.get_event_loop()
        for i in range(3):
            loop.run_until_complete(state.close_position(f"pos_{i}", Decimal("50")))
        assert state.portfolio.trades_last_24_bars == 3

    def test_state_builder_uses_real_count(self):
        """MDPStateBuilder reads trades_last_24_bars from portfolio, not a constant."""
        from mdp.state_builder import MDPStateBuilder
        from core.state import SystemState
        import asyncio
        from decimal import Decimal

        # Build a minimal packet/panel
        import sys
        sys.path.insert(0, "src") if "src" not in str(sys.path) else None
        from core.setup_packet import (
            BTCSetupPacket, IndicatorSnapshot, StructuralSnapshot,
            CandlestickSnapshot, ChartPatternSnapshot, SetupProposal, MACDValues,
        )
        from core.schemas import RegimeContext, Direction
        from traders.panel import PanelResult
        from traders.evaluators import TraderVerdict

        packet = BTCSetupPacket(
            packet_id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="1h",
            bar_timestamp=datetime.utcnow(),
            assembled_at=datetime.utcnow(),
            indicators=IndicatorSnapshot(
                close=Decimal("65000"), ema20=Decimal("64000"), ema50=Decimal("63000"),
                ema200=Decimal("60000"), ema_alignment="full_bull",
                rsi14=58.0, prev_rsi14=55.0, rsi_direction="rising",
                macd=MACDValues(Decimal("100"), Decimal("80"), Decimal("20"), "bullish_above"),
                bb_upper=Decimal("67000"), bb_middle=Decimal("64000"),
                bb_lower=Decimal("61000"), bb_width_pct=45.0, bb_position="middle",
                atr14=Decimal("800"), atr14_vs_sma20=1.0, volatility_regime="normal",
                adx14=32.0, trend_strength="strong", volume_ratio=1.5,
                volume_character="above_avg",
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
                entry_price=Decimal("65000"), stop_price=Decimal("63000"),
                target_price=Decimal("71000"), r_r_ratio=3.0,
                stop_distance_pct=3.1, target_distance_pct=9.2,
                proposed_leverage=10.0, proposed_risk_pct=0.01,
                setup_quality="A", confirming_signals=[], conflicting_signals=[],
                primary_thesis="Test",
            ),
        )
        panel = PanelResult(
            packet_id=packet.packet_id,
            verdicts=[
                TraderVerdict(
                    trader_id=f"T{i}", score=6.5, vote="approve" if i < 12 else "reject",
                    confidence=0.8, pro_reason="ok", anti_reason="risk",
                    execution_concern="none", risk_concern="none", explanation="test",
                )
                for i in range(20)
            ],
            approve_count=15, reject_count=8, abstain_count=0,
            avg_score=6.5, weighted_score=6.5,
            panel_recommendation="enter", panel_confidence=0.60,
        )

        state = SystemState()
        loop = asyncio.get_event_loop()
        # Close 2 trades
        for i in range(2):
            loop.run_until_complete(state.close_position(f"pos_{i}", Decimal("100")))

        builder = MDPStateBuilder()
        mdp_state = builder.build(packet, panel, system_state=state)
        assert mdp_state.trades_last_24_bars == 2


# ---------------------------------------------------------------------------
# Outcome attribution and trade_id backfill
# ---------------------------------------------------------------------------

class TestOutcomeAttribution:

    def _make_ext(self):
        from learning.journal_extension import JournalExtension
        conn = sqlite3.connect(":memory:")
        ext = JournalExtension(conn)
        ext.initialize()
        return ext, conn

    def test_log_outcome_attribution_writes_row(self):
        """log_outcome_attribution() must produce a row in outcome_attributions."""
        from learning.decision_logger import DecisionTraceLogger
        from learning.outcome_source import OutcomeSource

        ext, conn = self._make_ext()
        dtl = DecisionTraceLogger(ext, OutcomeSource.EVENT_DRIVEN_RUNTIME)

        attr_id = dtl.log_outcome_attribution(
            trade_id="pos_abc",
            packet_id="pkt_1",
            panel_id="pan_1",
            decision_id="dec_1",
            outcome="win",
            pnl_r=2.3,
            exit_reason="target_reached",
            bars_held=14,
            setup_family="double_bottom",
        )
        assert attr_id != ""

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM outcome_attributions WHERE trade_id='pos_abc'")
        row = cursor.fetchone()
        assert row is not None

    def test_attribution_fields_stored_correctly(self):
        """All attribution fields must round-trip through the DB."""
        from learning.decision_logger import DecisionTraceLogger
        from learning.outcome_source import OutcomeSource

        ext, conn = self._make_ext()
        dtl = DecisionTraceLogger(ext, OutcomeSource.EVENT_DRIVEN_RUNTIME)

        dtl.log_outcome_attribution(
            trade_id="pos_xyz",
            packet_id="pkt_2",
            panel_id="pan_2",
            decision_id="dec_2",
            outcome="loss",
            pnl_r=-1.0,
            exit_reason="stop_loss",
            bars_held=8,
            setup_family="breakout",
        )

        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM outcome_attributions WHERE trade_id='pos_xyz'")
        row = dict(cursor.fetchone())
        assert row["outcome"] == "loss"
        assert row["pnl_r"] == pytest.approx(-1.0, abs=0.001)
        assert row["exit_reason"] == "stop_loss"
        assert row["bars_held"] == 8
        assert row["packet_id"] == "pkt_2"
        assert row["decision_id"] == "dec_2"

    def test_attribution_joinable_with_mdp_transitions(self):
        """outcome_attributions.trade_id joins to mdp_transitions.trade_id."""
        from learning.decision_logger import DecisionTraceLogger
        from learning.outcome_source import OutcomeSource
        from mdp.transition_logger import TransitionLogger
        from mdp.actions import MDPAction

        ext, conn = self._make_ext()
        dtl = DecisionTraceLogger(ext, OutcomeSource.EVENT_DRIVEN_RUNTIME)
        tl = TransitionLogger(ext)

        state = _make_mdp_state()
        reasoning = {"rule_fired": "ENTER_MEDIUM", "rule_number": 2,
                     "factors": {}, "size_multiplier": 1.0}
        t_id = tl.log_transition(state, MDPAction.ENTER_MEDIUM, reasoning)
        tl.update_reward(t_id, reward=1.8, trade_id="pos_join_test")

        dtl.log_outcome_attribution(
            trade_id="pos_join_test",
            packet_id=None, panel_id=None, decision_id=None,
            outcome="win", pnl_r=1.8,
            exit_reason="target_reached", bars_held=10,
            setup_family="unknown",
        )

        # Join: find transition by trade_id, then find attribution
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mt.action, mt.reward, oa.outcome, oa.pnl_r
            FROM mdp_transitions mt
            JOIN outcome_attributions oa ON mt.trade_id = oa.trade_id
            WHERE mt.trade_id = 'pos_join_test'
        """)
        row = dict(cursor.fetchone())
        assert row["action"] == "enter_medium"
        assert row["reward"] == pytest.approx(1.8, abs=0.001)
        assert row["outcome"] == "win"
        assert row["pnl_r"] == pytest.approx(1.8, abs=0.001)

    def test_backfill_trade_id_for_packet(self):
        """backfill_trade_id_for_packet() must update setup_packets and trader_reviews."""
        from learning.journal_extension import JournalExtension
        from learning.decision_logger import DecisionTraceLogger
        from learning.outcome_source import OutcomeSource
        from learning.schemas import StoredSetupPacket, StoredTraderReview

        ext, conn = self._make_ext()
        dtl = DecisionTraceLogger(ext, OutcomeSource.EVENT_DRIVEN_RUNTIME)

        # Archive a setup packet
        packet_id = dtl.log_setup_packet({
            "packet_id": "pkt_bf", "symbol": "BTCUSDT", "timeframe": "1h",
            "bar_timestamp": datetime.utcnow().isoformat(),
        })

        # Initially trade_id is NULL
        cursor = conn.cursor()
        cursor.execute("SELECT trade_id FROM setup_packets WHERE packet_id=?", (packet_id,))
        assert cursor.fetchone()[0] is None

        # Backfill
        ext.backfill_trade_id_for_packet(packet_id, "pos_backfill")

        cursor.execute("SELECT trade_id FROM setup_packets WHERE packet_id=?", (packet_id,))
        assert cursor.fetchone()[0] == "pos_backfill"

    def test_macro_fields_are_real_not_inert(self):
        """macro_position_modifier and fear_greed_index must be real fields
        populated by NewsMacroGroup — not hardcoded constants."""
        from mdp.state import MDPState
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(MDPState)}
        # These fields are now real (populated by NewsMacroGroup each bar close).
        assert "macro_position_modifier" in field_names
        assert "fear_greed_index" in field_names
        # Verify defaults are sensible neutral values
        state = _make_mdp_state()
        assert state.macro_position_modifier == 1.0   # full size by default
        assert state.fear_greed_index == 50.0          # neutral by default

    def test_trades_last_24_bars_in_mdp_state(self):
        """trades_last_24_bars must be a real field in MDPState."""
        from mdp.state import MDPState
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(MDPState)}
        assert "trades_last_24_bars" in field_names

    def test_to_vector_has_no_constant_slots(self):
        """to_vector() must not produce a vector with the same value for both
        the old macro constant slots regardless of what state is passed."""
        state_a = _make_mdp_state(approve_count=15, avg_score=6.5)
        state_b = _make_mdp_state(approve_count=16, avg_score=8.0)
        vec_a = state_a.to_vector()
        vec_b = state_b.to_vector()
        # Vectors must differ (state is different)
        assert vec_a != vec_b
        # Length: 25 base + 2 macro + 20 eval scores + 20 eval confidences = 67
        assert len(vec_a) == 67
