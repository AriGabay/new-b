"""
TraderEvaluatorPanel: runs all 20 trader evaluators against a BTCSetupPacket.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.setup_packet import BTCSetupPacket
from traders.evaluators import (
    TraderVerdict,
    TrendFollowingEvaluator,
    MomentumEvaluator,
    MeanReversionEvaluator,
    BreakoutEvaluator,
    StructureEvaluator,
    CandlestickEvaluator,
    RiskParityEvaluator,
    VolatilityEvaluator,
    VolumeProfileEvaluator,
    MacroRegimeEvaluator,
    ContraryEvaluator,
    ProfitTargetEvaluator,
    EntryTimingEvaluator,
    ConfluenceEvaluator,
    DrawdownRiskEvaluator,
    LeverageSpecialistEvaluator,
    PatternCompletionEvaluator,
    WickAnalysisEvaluator,
    MarketContextEvaluator,
    ExecutionQualityEvaluator,
)

logger = logging.getLogger(__name__)


@dataclass
class PanelResult:
    """Aggregated result from all 20 trader evaluations."""

    packet_id: str
    verdicts: list[TraderVerdict] = field(default_factory=list)

    # Aggregated stats
    approve_count: int = 0
    reject_count: int = 0
    abstain_count: int = 0
    avg_score: float = 0.0
    weighted_score: float = 0.0  # weighted by confidence

    # Outcome
    panel_recommendation: str = "hold"  # "enter" | "hold" | "reduce"
    panel_confidence: float = 0.0
    key_risks: list[str] = field(default_factory=list)
    key_strengths: list[str] = field(default_factory=list)


class TraderEvaluatorPanel:
    """
    Orchestrates all 20 trader evaluators.

    Decision threshold: >= 11/20 approve AND avg_score >= 5.8 → "enter"
    Soft threshold: 8-10 approve → "hold"
    Hard reject: < 8 approve → "hold" (force no trade)
    """

    APPROVE_THRESHOLD = 15   # need 15/20 to enter (optimized in Phase 5)
    MIN_AVG_SCORE = 5.8      # need avg score >= 5.8
    AVG_SCORE_THRESHOLD = 5.8  # alias for MIN_AVG_SCORE (Phase 6.4 test compatibility)

    def __init__(self) -> None:
        self._evaluators = [
            TrendFollowingEvaluator(),
            MomentumEvaluator(),
            MeanReversionEvaluator(),
            BreakoutEvaluator(),
            StructureEvaluator(),
            CandlestickEvaluator(),
            RiskParityEvaluator(),
            VolatilityEvaluator(),
            VolumeProfileEvaluator(),
            MacroRegimeEvaluator(),
            ContraryEvaluator(),
            ProfitTargetEvaluator(),
            EntryTimingEvaluator(),
            ConfluenceEvaluator(),
            DrawdownRiskEvaluator(),
            LeverageSpecialistEvaluator(),
            PatternCompletionEvaluator(),
            WickAnalysisEvaluator(),
            MarketContextEvaluator(),
            ExecutionQualityEvaluator(),
        ]

    def evaluate(self, packet: BTCSetupPacket) -> PanelResult:
        """Run all 20 evaluators and aggregate results."""
        result = PanelResult(packet_id=packet.packet_id)

        for evaluator in self._evaluators:
            try:
                verdict = evaluator.evaluate(packet)
                result.verdicts.append(verdict)
                if verdict.vote == "approve":
                    result.approve_count += 1
                elif verdict.vote == "reject":
                    result.reject_count += 1
                else:
                    result.abstain_count += 1
            except Exception:
                logger.exception("Evaluator %s failed", evaluator.trader_id)

        if result.verdicts:
            result.avg_score = sum(v.score for v in result.verdicts) / len(result.verdicts)

            # Weighted score by confidence
            total_confidence = sum(v.confidence for v in result.verdicts)
            if total_confidence > 0:
                result.weighted_score = (
                    sum(v.score * v.confidence for v in result.verdicts) / total_confidence
                )

            # Collect key risks (from rejecters) and strengths (from approvers)
            result.key_risks = [
                v.risk_concern
                for v in result.verdicts
                if v.vote == "reject" and v.risk_concern != "none"
            ][:5]
            result.key_strengths = [
                v.pro_reason
                for v in result.verdicts
                if v.vote == "approve"
            ][:5]

        # Panel decision
        if (
            result.approve_count >= self.APPROVE_THRESHOLD
            and result.avg_score >= self.MIN_AVG_SCORE
        ):
            result.panel_recommendation = "enter"
            result.panel_confidence = result.approve_count / 20.0
        elif result.approve_count >= 10:
            result.panel_recommendation = "hold"
            result.panel_confidence = result.approve_count / 20.0
        else:
            result.panel_recommendation = "hold"
            result.panel_confidence = result.reject_count / 20.0

        logger.info(
            "Panel: %d approve, %d reject, %d abstain | avg=%.1f | → %s",
            result.approve_count,
            result.reject_count,
            result.abstain_count,
            result.avg_score,
            result.panel_recommendation,
        )
        return result
