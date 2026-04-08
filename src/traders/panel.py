"""
TraderEvaluatorPanel: runs all 22 trader evaluators against a BTCSetupPacket.
"""
from __future__ import annotations

import logging
import os
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
    OrderFlowEvaluator,
    MLSignalEvaluator,
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
    Orchestrates all 22 trader evaluators.

    Decision threshold: >= 15/22 approve AND avg_score >= 5.8 → "enter"
    Regime-adaptive: bull/trending = 14, ranging/bear = 15
    Soft threshold: 10-13 approve → "hold"
    Hard reject: < 10 approve → "hold" (force no trade)

    Evaluator #22 (MLSignalEvaluator) abstains until 100 labelled outcomes
    are available in the learning DB, so the threshold is unaffected early on.
    """

    APPROVE_THRESHOLD = 15   # default fallback
    MIN_AVG_SCORE = 5.8      # need avg score >= 5.8
    AVG_SCORE_THRESHOLD = 5.8  # alias for MIN_AVG_SCORE (test compatibility)
    _PANEL_SIZE = 22         # total number of evaluators
    _REGIME_THRESHOLDS = {"bull": 14, "trending": 14, "ranging": 15, "bear": 15}

    def __init__(self) -> None:
        self._weights: dict[str, float] = self._load_weights()
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
            OrderFlowEvaluator(),    # #21 — order flow / institutional signals
            MLSignalEvaluator(),     # #22 — LightGBM win-probability predictor
        ]

    @staticmethod
    def _load_weights() -> dict[str, float]:
        """
        Load evaluator weights from data/evaluator_weights.json.
        Returns empty dict if file doesn't exist (fallback: equal weighting).
        Called once at panel construction.
        """
        try:
            from learning.weight_updater import EvaluatorWeightUpdater
            updater = EvaluatorWeightUpdater()
            weights = updater.load_weights()
            if weights:
                logger.info(
                    "TraderEvaluatorPanel: loaded %d evaluator weights from JSON.", len(weights)
                )
            return weights
        except Exception as exc:
            logger.debug("TraderEvaluatorPanel: could not load weights: %s", exc)
            return {}

    def reload_weights(self) -> None:
        """Reload evaluator weights from disk (call after learn_and_test.py runs)."""
        self._weights = self._load_weights()

    def evaluate(self, packet: BTCSetupPacket) -> PanelResult:
        """Run all 21 evaluators and aggregate results with Sharpe-based weighting."""
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

            # Weighted score: confidence × Sharpe-weight (learned) per evaluator
            # Falls back to confidence-only weighting when no weights loaded
            total_weight = 0.0
            weighted_sum = 0.0
            for v in result.verdicts:
                sharpe_weight = self._weights.get(v.trader_id, 1.0)
                w = v.confidence * sharpe_weight
                weighted_sum += v.score * w
                total_weight += w
            if total_weight > 0:
                result.weighted_score = weighted_sum / total_weight

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

        # Panel decision (regime-adaptive threshold)
        regime_str = getattr(getattr(packet, "regime", None), "btc_macro", "ranging")
        approve_threshold = self._REGIME_THRESHOLDS.get(regime_str, self.APPROVE_THRESHOLD)
        logger.info("Panel threshold: %d (regime=%s)", approve_threshold, regime_str)
        n_evaluators = len(self._evaluators)
        if (
            result.approve_count >= approve_threshold
            and result.avg_score >= self.MIN_AVG_SCORE
        ):
            result.panel_recommendation = "enter"
            result.panel_confidence = result.approve_count / n_evaluators
        elif result.approve_count >= 10:
            result.panel_recommendation = "hold"
            result.panel_confidence = result.approve_count / n_evaluators
        else:
            result.panel_recommendation = "hold"
            result.panel_confidence = result.reject_count / n_evaluators

        logger.info(
            "Panel (%d evaluators): %d approve, %d reject, %d abstain | avg=%.1f | → %s",
            n_evaluators,
            result.approve_count,
            result.reject_count,
            result.abstain_count,
            result.avg_score,
            result.panel_recommendation,
        )
        return result
