"""
FinalDecisionGroup: Layer C — makes the binary enter/hold decision.

Design constraints (from architecture):
  - ONLY reads 20 trader verdicts + hard safety rails.
  - Does NOT create its own market thesis.
  - Does NOT look at raw market data or FeatureVector directly.
  - Decision is deterministic given panel result + safety rails.

Hard safety rails (override panel if any violated):
  1. avg_score < 5.0 → always hold
  2. reject_count > 12 → always hold (more than half reject)
  3. proposal.r_r_ratio < 1.5 → always hold (bad R:R)
  4. proposal.setup_quality == "invalid" → always hold
  5. regime.btc_macro == "bear" AND proposal.direction == "long" → always hold
  6. volatility_regime == "high" AND approve_count < 16 → hold (need stronger consensus in volatile market)

Decision:
  - "enter" only if panel_recommendation == "enter" AND all safety rails pass
  - Otherwise: "hold"

Output: FinalDecision dataclass
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

logger = logging.getLogger(__name__)

# Threshold constant — kept here so FinalDecisionGroup.decide() can reference it
# without importing TraderEvaluatorPanel (avoids circular dependency).
_PANEL_APPROVE_THRESHOLD = 14


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

    # Verdict summary
    approve_count: int = 0
    reject_count: int = 0
    avg_score: float = 0.0
    panel_confidence: float = 0.0

    # Key rationale
    enter_rationale: str = ""
    hold_rationale: str = ""

    decided_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class FinalDecisionGroup:
    """
    Layer C: Final binary decision maker.

    Takes PanelResult and BTCSetupPacket.
    Returns FinalDecision.
    Does NOT publish to EventBus — returns result directly.
    """

    def decide(self, packet: BTCSetupPacket, panel: PanelResult) -> FinalDecision:
        """Make final enter/hold decision."""
        decision = FinalDecision(
            packet_id=packet.packet_id,
            panel_recommendation=panel.panel_recommendation,
            approve_count=panel.approve_count,
            reject_count=panel.reject_count,
            avg_score=panel.avg_score,
            panel_confidence=panel.panel_confidence,
        )

        rails_triggered: list[str] = []
        proposal = packet.proposal
        regime = packet.regime

        # ------------------------------------------------------------------
        # Rail 1: avg_score floor
        # ------------------------------------------------------------------
        if panel.avg_score < 5.0:
            rails_triggered.append(
                f"avg_score {panel.avg_score:.1f} < 5.0"
            )

        # ------------------------------------------------------------------
        # Rail 2: majority reject
        # ------------------------------------------------------------------
        if panel.reject_count > 12:
            rails_triggered.append(
                f"reject_count {panel.reject_count} > 12/20"
            )

        # ------------------------------------------------------------------
        # Rail 3: R:R too low
        # ------------------------------------------------------------------
        if proposal.r_r_ratio < 1.5:
            rails_triggered.append(
                f"R:R {proposal.r_r_ratio:.2f} < 1.5"
            )

        # ------------------------------------------------------------------
        # Rail 4: invalid setup quality
        # ------------------------------------------------------------------
        if proposal.setup_quality == "invalid":
            rails_triggered.append("setup_quality=invalid")

        # ------------------------------------------------------------------
        # Rail 5: bear regime long trade
        # ------------------------------------------------------------------
        direction_value = (
            proposal.direction.value
            if isinstance(proposal.direction, Direction)
            else str(proposal.direction).lower()
        )
        if regime.btc_macro == "bear" and direction_value == "long":
            rails_triggered.append("long trade in bear regime blocked")

        # ------------------------------------------------------------------
        # Rail 6: high volatility requires stronger consensus
        # ------------------------------------------------------------------
        if regime.volatility_regime == "high" and panel.approve_count < 16:
            rails_triggered.append(
                f"high volatility requires 16 approves (got {panel.approve_count})"
            )

        decision.safety_rails_triggered = rails_triggered

        # ------------------------------------------------------------------
        # Final decision
        # ------------------------------------------------------------------
        if rails_triggered:
            decision.decision = "hold"
            decision.hold_rationale = (
                "Safety rails triggered: " + "; ".join(rails_triggered)
            )

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

        logger.info(
            "FinalDecision: %s | approve=%d reject=%d avg=%.1f | rails=%s",
            decision.decision,
            decision.approve_count,
            decision.reject_count,
            decision.avg_score,
            rails_triggered or "none",
        )

        return decision
