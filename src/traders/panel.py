"""
TraderEvaluatorPanel: runs all 20 trader evaluators against a BTCSetupPacket.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.setup_packet import BTCSetupPacket
from traders.panel_constants import (
    PANEL_APPROVE_THRESHOLD,
    PANEL_MIN_AVG_SCORE,
    PANEL_REGIME_THRESHOLDS,
    PANEL_SYMBOL_THRESHOLD_OFFSET,
)
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

    Decision threshold: >= 12/20 approve AND avg_score >= 5.5 → "enter"
    Soft threshold: 8-10 approve → "hold"
    Hard reject: < 8 approve → "hold" (force no trade)
    """

    # Sweep-optimal: T=15 across all regimes (optimization_result.json)
    # T=14 was below breakeven — do not lower below 15
    APPROVE_THRESHOLD = PANEL_APPROVE_THRESHOLD          # default fallback
    MIN_AVG_SCORE = PANEL_MIN_AVG_SCORE                  # need avg score >= threshold
    AVG_SCORE_THRESHOLD = PANEL_MIN_AVG_SCORE            # alias (Phase 6.4 test compatibility)
    _REGIME_THRESHOLDS = PANEL_REGIME_THRESHOLDS         # per-regime approval counts
    # Task 11H: non-BTC symbols require tighter consensus (panel calibrated on BTC)
    _SYMBOL_THRESHOLD_OFFSET: dict = PANEL_SYMBOL_THRESHOLD_OFFSET

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

        # Panel decision (regime-adaptive threshold + symbol offset)
        regime_str = getattr(getattr(packet, "regime", None), "btc_macro", "ranging")
        symbol_str = getattr(packet, "symbol", "BTCUSDT")
        sym_offset = self._SYMBOL_THRESHOLD_OFFSET.get(symbol_str, 0)
        approve_threshold = (
            self._REGIME_THRESHOLDS.get(regime_str, self.APPROVE_THRESHOLD) + sym_offset
        )
        logger.info(
            "Panel threshold: %d (regime=%s symbol=%s offset=%d)",
            approve_threshold, regime_str, symbol_str, sym_offset,
        )
        if (
            result.approve_count >= approve_threshold
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
