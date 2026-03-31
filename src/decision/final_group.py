"""
FinalDecisionGroup: Layer C — MDP-aware enter/hold decision.

Architecture:
  1. Build MDPState from packet + panel + SystemState (rich context vector)
  2. Run MDPPolicy.decide(state) → action + reasoning
  3. Apply 6 hard safety rails (ALWAYS run, ALWAYS override any MDP action)
  4. Convert action → FinalDecision
  5. Log (state, action, reasoning) via TransitionLogger

Design constraints (unchanged from original):
  - ONLY reads 20 trader verdicts + hard safety rails.
  - Does NOT create its own market thesis.
  - Does NOT look at raw market data or FeatureVector directly.

Hard safety rails (non-overridable — override MDP if any triggered):
  1. avg_score < 5.0 → always hold
  2. reject_count > 12 → always hold (more than half reject)
  3. proposal.r_r_ratio < 1.5 → always hold (bad R:R)
  4. proposal.setup_quality == "invalid" → always hold
  5. regime.btc_macro == "bear" AND proposal.direction == "long" → always hold
  6. volatility_regime == "high" AND approve_count < 14 → hold

MDP actions → decision mapping:
  ENTER_SMALL / ENTER_MEDIUM / ENTER_HIGH_CONVICTION → "enter" (full/scaled size)
  REDUCE_RISK → "enter" at 50% position size (drawdown/streak protection mode)
  NO_TRADE / DEFER → "hold"

FinalDecisionGroup is callable with no constructor args (system_state and
journal_extension are optional) for full backward compatibility with tests.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.setup_packet import BTCSetupPacket
from core.schemas import Direction
from traders.panel import PanelResult
from traders.panel_constants import (
    PANEL_APPROVE_THRESHOLD,
    PANEL_REGIME_THRESHOLDS,
    PANEL_SYMBOL_THRESHOLD_OFFSET,
)

logger = logging.getLogger(__name__)

# Panel approval threshold constant (default fallback, referenced by hold-rationale text)
_PANEL_APPROVE_THRESHOLD = PANEL_APPROVE_THRESHOLD      # from panel_constants

# Phase 11B: regime-adaptive base thresholds
_REGIME_BASE_THRESHOLDS = PANEL_REGIME_THRESHOLDS       # from panel_constants

# Restored to sweep-optimal value (approve=15, Rail6=16)
# See analysis/optimization_result.json — 68.2% WR, PF 1.85
# Rail 6 absolute threshold = regime_base (15) + this offset (1) = 16.
# Formula: _r6_thresh = _base_thresh + _RAIL6_HIGH_VOL_OFFSET + sym_offset
_RAIL6_HIGH_VOL_OFFSET = 1

# Task 11H: non-BTC symbols require tighter consensus (panel calibrated on BTC)
_SYMBOL_THRESHOLD_OFFSET: dict[str, int] = PANEL_SYMBOL_THRESHOLD_OFFSET  # from panel_constants


@dataclass
class SafetyRailResult:
    passed: bool
    rail_id: str
    reason: str


@dataclass
class FinalDecision:
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    packet_id: str = ""
    decision: str = "hold"  # "enter" | "hold"

    # What drove the decision
    panel_recommendation: str = "hold"
    safety_rails_triggered: list[str] = field(default_factory=list)

    # Trade details (only meaningful if decision == "enter")
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    r_r_ratio: Optional[float] = None
    size_multiplier: float = 1.0   # from MDPAction; 0.5 / 1.0 / 1.5

    # Verdict summary
    approve_count: int = 0
    reject_count: int = 0
    avg_score: float = 0.0
    panel_confidence: float = 0.0

    # Key rationale
    enter_rationale: str = ""
    hold_rationale: str = ""

    # MDP metadata
    mdp_action: str = ""           # MDPAction.value chosen by policy
    mdp_reasoning: dict = field(default_factory=dict)  # policy reasoning
    safety_override: bool = False  # True if safety rails overrode MDP action
    state_snapshot_id: str = ""    # transition_id in mdp_transitions table

    decided_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class FinalDecisionGroup:
    """
    Layer C: MDP-aware final decision maker.

    Takes BTCSetupPacket and PanelResult.
    Returns FinalDecision.
    Does NOT publish to EventBus — returns result directly.

    Optional wiring (all default to None for backward compatibility):
      system_state:       SystemState — provides account context for MDPState
      journal_extension:  JournalExtension — enables TransitionLogger
    """

    def __init__(
        self,
        system_state=None,       # Optional[SystemState]
        journal_extension=None,  # Optional[JournalExtension]
    ) -> None:
        self._system_state = system_state

        # Lazy-init MDP components to avoid circular imports at module load
        self._policy = None
        self._state_builder = None
        self._transition_logger = None
        self._journal_extension = journal_extension

    def _ensure_mdp_ready(self) -> None:
        """Lazy-initialize MDP components on first use."""
        if self._policy is None:
            from mdp.policy import MDPPolicy
            from mdp.state_builder import MDPStateBuilder
            self._policy = MDPPolicy()
            self._state_builder = MDPStateBuilder()

        if self._transition_logger is None and self._journal_extension is not None:
            from mdp.transition_logger import TransitionLogger
            self._transition_logger = TransitionLogger(self._journal_extension)

    def decide(self, packet: BTCSetupPacket, panel: PanelResult) -> FinalDecision:
        """
        MDP-aware enter/hold decision.

        Flow:
          1. Build MDPState (rich context vector)
          2. Run MDPPolicy → action + reasoning
          3. Apply 6 hard safety rails inline (avg_score < 5.0, reject_count, ...)
          4. Safety rails override any MDP action if triggered
          5. Convert action → FinalDecision
          6. Log transition (state, action, reasoning)
        """
        self._ensure_mdp_ready()

        # ------------------------------------------------------------------
        # 1. Build MDP state
        # ------------------------------------------------------------------
        try:
            mdp_state = self._state_builder.build(packet, panel, self._system_state)
        except Exception as exc:
            logger.error("FinalDecisionGroup: MDPStateBuilder.build failed: %s", exc)
            # Fall back to legacy path on state-build failure
            return self._legacy_decide(packet, panel)

        # ------------------------------------------------------------------
        # 2. Policy decision
        # ------------------------------------------------------------------
        try:
            action, reasoning = self._policy.decide(mdp_state)
        except Exception as exc:
            logger.error("FinalDecisionGroup: MDPPolicy.decide failed: %s", exc)
            return self._legacy_decide(packet, panel)

        # ------------------------------------------------------------------
        # 3. Hard safety rails — inline, ALWAYS run, ALWAYS override MDP
        # ------------------------------------------------------------------
        rails_triggered: list[str] = []
        proposal = packet.proposal
        regime = packet.regime

        # Rail 1: avg_score floor
        if panel.avg_score < 5.0:
            rails_triggered.append(f"avg_score {panel.avg_score:.1f} < 5.0")

        # Rail 2: majority reject
        if panel.reject_count > 12:
            rails_triggered.append(f"reject_count {panel.reject_count} > 12/20")

        # Rail 3: R:R too low
        if proposal.r_r_ratio < 1.5:
            rails_triggered.append(f"R:R {proposal.r_r_ratio:.2f} < 1.5")

        # Rail 4: invalid setup quality
        if proposal.setup_quality == "invalid":
            rails_triggered.append("setup_quality=invalid")

        # Rail 5: bear regime long trade
        direction_value = (
            proposal.direction.value
            if isinstance(proposal.direction, Direction)
            else str(proposal.direction).lower()
        )
        if regime.btc_macro == "bear" and direction_value == "long":
            rails_triggered.append("long trade in bear regime blocked")

        # Rail 6: high volatility requires stronger consensus (regime-adaptive + symbol offset)
        _sym_offset = _SYMBOL_THRESHOLD_OFFSET.get(getattr(proposal, "symbol", "BTCUSDT"), 0)
        _base_thresh = _REGIME_BASE_THRESHOLDS.get(regime.btc_macro, _PANEL_APPROVE_THRESHOLD)
        _r6_thresh = min(20, _base_thresh + _RAIL6_HIGH_VOL_OFFSET + _sym_offset)
        if regime.volatility_regime == "high" and panel.approve_count < _r6_thresh:
            rails_triggered.append(
                f"high volatility requires {_r6_thresh} approves (got {panel.approve_count})"
            )

        # ------------------------------------------------------------------
        # 4. Override action if safety rails fired
        # ------------------------------------------------------------------
        from mdp.actions import MDPAction, ACTION_SIZE_MULTIPLIERS, ENTER_ACTIONS
        safety_override = bool(rails_triggered)
        if safety_override:
            reasoning["safety_override"] = rails_triggered
            action = MDPAction.NO_TRADE

        # ------------------------------------------------------------------
        # 5. Build FinalDecision
        # ------------------------------------------------------------------
        decision = FinalDecision(
            packet_id=packet.packet_id,
            panel_recommendation=panel.panel_recommendation,
            approve_count=panel.approve_count,
            reject_count=panel.reject_count,
            avg_score=panel.avg_score,
            panel_confidence=panel.panel_confidence,
            safety_rails_triggered=rails_triggered,
            mdp_action=action.value,
            mdp_reasoning=reasoning,
            safety_override=safety_override,
            size_multiplier=ACTION_SIZE_MULTIPLIERS.get(action, 0.0),
        )

        if action in ENTER_ACTIONS or action == MDPAction.REDUCE_RISK:
            decision.decision = "enter"
            decision.direction = direction_value
            decision.entry_price = float(proposal.entry_price)
            decision.stop_price = float(proposal.stop_price)
            decision.target_price = float(proposal.target_price)
            decision.r_r_ratio = proposal.r_r_ratio
            decision.enter_rationale = (
                f"MDP {action.value}: {panel.approve_count}/20 approve, "
                f"avg_score={panel.avg_score:.1f}. "
                f"Strengths: {'; '.join(panel.key_strengths[:3])}"
            )
            if action == MDPAction.REDUCE_RISK:
                logger.info(
                    "REDUCE_RISK: entering at 50%% position size "
                    "(streak=%d, drawdown=%.1f%%)",
                    mdp_state.current_streak,
                    mdp_state.drawdown_pct * 100,
                )
        else:
            decision.decision = "hold"
            if safety_override:
                decision.hold_rationale = (
                    "Safety rails triggered: " + "; ".join(rails_triggered)
                )
            elif action == MDPAction.DEFER:
                decision.hold_rationale = (
                    f"MDP DEFER: {panel.approve_count}/20 approve "
                    f"(near threshold — re-evaluate next bar)"
                )
            else:
                decision.hold_rationale = (
                    f"MDP NO_TRADE: {panel.approve_count}/20 approve "
                    f"(need {_PANEL_APPROVE_THRESHOLD}), avg_score={panel.avg_score:.1f}"
                )

        # ------------------------------------------------------------------
        # 6. Log transition
        # ------------------------------------------------------------------
        if self._transition_logger is not None:
            try:
                t_id = self._transition_logger.log_transition(
                    state=mdp_state,
                    action=action,
                    reasoning=reasoning,
                    trade_id=None,  # backfilled when position opens
                )
                decision.state_snapshot_id = t_id
            except Exception as exc:
                logger.warning(
                    "FinalDecisionGroup: transition logging failed: %s", exc
                )

        logger.info(
            "FinalDecision [MDP %s%s]: %s | approve=%d reject=%d avg=%.1f | rails=%s",
            action.value,
            " OVERRIDDEN" if safety_override else "",
            decision.decision,
            decision.approve_count,
            decision.reject_count,
            decision.avg_score,
            rails_triggered or "none",
        )

        return decision

    def _legacy_decide(self, packet: BTCSetupPacket, panel: PanelResult) -> FinalDecision:
        """
        Fallback: original threshold-based decision (pre-MDP).
        Used only when MDP components fail to initialize or raise.
        Preserves full original behavior for robustness.
        """
        decision = FinalDecision(
            packet_id=packet.packet_id,
            panel_recommendation=panel.panel_recommendation,
            approve_count=panel.approve_count,
            reject_count=panel.reject_count,
            avg_score=panel.avg_score,
            panel_confidence=panel.panel_confidence,
            mdp_action="no_trade",
            mdp_reasoning={"rule_fired": "legacy_fallback"},
        )

        rails_triggered: list[str] = []
        proposal = packet.proposal
        regime = packet.regime

        if panel.avg_score < 5.0:
            rails_triggered.append(f"avg_score {panel.avg_score:.1f} < 5.0")
        if panel.reject_count > 12:
            rails_triggered.append(f"reject_count {panel.reject_count} > 12/20")
        if proposal.r_r_ratio < 1.5:
            rails_triggered.append(f"R:R {proposal.r_r_ratio:.2f} < 1.5")
        if proposal.setup_quality == "invalid":
            rails_triggered.append("setup_quality=invalid")
        direction_value = (
            proposal.direction.value
            if isinstance(proposal.direction, Direction)
            else str(proposal.direction).lower()
        )
        if regime.btc_macro == "bear" and direction_value == "long":
            rails_triggered.append("long trade in bear regime blocked")
        _sym_offset = _SYMBOL_THRESHOLD_OFFSET.get(getattr(proposal, "symbol", "BTCUSDT"), 0)
        _base_thresh = _REGIME_BASE_THRESHOLDS.get(regime.btc_macro, _PANEL_APPROVE_THRESHOLD)
        _r6_thresh = min(20, _base_thresh + _RAIL6_HIGH_VOL_OFFSET + _sym_offset)
        if regime.volatility_regime == "high" and panel.approve_count < _r6_thresh:
            rails_triggered.append(
                f"high volatility requires {_r6_thresh} approves (got {panel.approve_count})"
            )

        decision.safety_rails_triggered = rails_triggered

        if rails_triggered:
            decision.decision = "hold"
            decision.hold_rationale = "Safety rails triggered: " + "; ".join(rails_triggered)
        elif panel.panel_recommendation == "enter":
            decision.decision = "enter"
            decision.direction = direction_value
            decision.entry_price = float(proposal.entry_price)
            decision.stop_price = float(proposal.stop_price)
            decision.target_price = float(proposal.target_price)
            decision.r_r_ratio = proposal.r_r_ratio
            decision.enter_rationale = (
                f"{panel.approve_count}/20 approve, avg_score={panel.avg_score:.1f}. "
                f"Strengths: {'; '.join(panel.key_strengths[:3])}"
            )
        else:
            decision.decision = "hold"
            decision.hold_rationale = (
                f"Insufficient consensus: {panel.approve_count}/20 approve "
                f"(need {_PANEL_APPROVE_THRESHOLD}), avg_score={panel.avg_score:.1f}"
            )

        return decision
