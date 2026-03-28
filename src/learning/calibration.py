"""
TraderCalibrator and PanelCalibrator.

CRITICAL RULES:
  1. Minimum 30 samples before ANY conclusions are drawn.
  2. All metrics must be segmented by OutcomeSource. Never mix.
  3. No policy changes without explicit evidence + sample size reported.
  4. Brier score formula: (forecast_prob - outcome_binary)^2
     where forecast_prob = confidence * (1 if vote==approve else 0)
     and outcome_binary = 1 if outcome=="win" else 0

Source: /docs/trader_calibration_framework.md
        /docs/panel_consensus_framework.md
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from learning.journal_extension import JournalExtension
from learning.outcome_source import OutcomeSource, assert_single_source
from learning.schemas import TraderCalibrationRecord

logger = logging.getLogger(__name__)

MIN_SAMPLES = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TraderCalibrator:
    """
    Tracks and updates calibration records for individual trader evaluators.

    Calibration tracks:
      - Approval win rate: of all "approve" votes, what fraction led to wins?
      - Brier score: probability calibration quality
      - Score discriminability: do high scores predict wins better than low scores?
      - Overconfidence: high confidence + wrong outcome rate > 30%

    All conclusions gated at MIN_SAMPLES = 30.
    """

    def __init__(self, extension: JournalExtension) -> None:
        self._ext = extension

    def process_trade_outcome(
        self,
        trade_id: str,
        outcome: str,        # "win" / "loss" / "breakeven"
        outcome_source: OutcomeSource,
        trader_name: str,
        vote: str,           # "approve" / "reject" / "abstain"
        score: float,        # 1–10
        confidence: float,   # 0.0–1.0
    ) -> TraderCalibrationRecord:
        """
        Update calibration record for one trader after one trade closes.
        Returns updated record (also persisted to DB).
        """
        rec = self._ext.load_trader_calibration(trader_name, outcome_source)
        if rec is None:
            rec = TraderCalibrationRecord(
                trader_name=trader_name,
                outcome_source=outcome_source,
            )

        is_win = outcome == "win"
        outcome_binary = 1.0 if is_win else 0.0

        rec.total_reviews += 1

        if vote == "approve":
            rec.approvals_given += 1
            if is_win:
                rec.approvals_that_won += 1
        elif vote == "reject":
            rec.rejections_given += 1

        # Brier score: (forecast - outcome)^2
        # Forecast = confidence * (1 if approve else 0)
        forecast_prob = confidence if vote == "approve" else 0.0
        brier_component = (forecast_prob - outcome_binary) ** 2
        rec.brier_score_sum += brier_component
        rec.brier_score_count += 1

        # Overconfidence detection: high confidence + wrong
        if confidence >= 0.75 and not is_win and vote == "approve":
            rec.high_conf_wrong_count += 1
        if confidence >= 0.75 and is_win and vote == "reject":
            rec.high_conf_wrong_count += 1

        # Score tracking by outcome
        if is_win:
            rec.win_score_sum += score
            rec.win_score_count += 1
        else:
            rec.loss_score_sum += score
            rec.loss_score_count += 1

        rec.last_updated = _utcnow()
        self._ext.upsert_trader_calibration(rec)
        return rec

    def get_calibration_summary(
        self,
        trader_name: str,
        outcome_source: OutcomeSource,
    ) -> dict:
        """
        Return human-readable calibration summary.
        All metrics show None if insufficient samples.
        """
        rec = self._ext.load_trader_calibration(trader_name, outcome_source)
        if rec is None:
            return {"trader_name": trader_name, "error": "not found"}

        avg_win_score = (
            rec.win_score_sum / rec.win_score_count
            if rec.win_score_count > 0 else None
        )
        avg_loss_score = (
            rec.loss_score_sum / rec.loss_score_count
            if rec.loss_score_count > 0 else None
        )

        return {
            "trader_name": trader_name,
            "outcome_source": outcome_source.value,
            "total_reviews": rec.total_reviews,
            "has_sufficient_samples": rec.has_sufficient_samples,
            "approval_win_rate": rec.approval_win_rate,
            "brier_score": rec.brier_score,
            "is_overconfident": rec.is_overconfident if rec.has_sufficient_samples else None,
            "avg_score_on_wins": avg_win_score,
            "avg_score_on_losses": avg_loss_score,
            "score_discriminability": (
                round(avg_win_score - avg_loss_score, 3)
                if avg_win_score is not None and avg_loss_score is not None
                else None
            ),
            "note": (
                None if rec.has_sufficient_samples
                else f"Insufficient samples ({rec.total_reviews}/{MIN_SAMPLES} minimum). No conclusions."
            ),
        }


class PanelCalibrator:
    """
    Tracks panel-level consensus quality.

    Tracks:
      - Approval-rate accuracy: when panel says "enter", what % are wins?
      - Disagreement as failure predictor: high reject_count → more losses?
      - avg_score discrimination: does higher avg_score predict wins?

    Min 30 samples before conclusions.
    """

    def __init__(self, extension: JournalExtension) -> None:
        self._ext = extension

    def compute_panel_stats(
        self,
        outcome_source: OutcomeSource,
    ) -> dict:
        """
        Compute panel-level statistics from stored panel_summaries + outcome_attributions.
        Returns dict with metrics. All gated at MIN_SAMPLES.
        """
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            cursor.execute(
                """
                SELECT ps.approve_count, ps.reject_count, ps.avg_score,
                       ps.panel_recommendation,
                       oa.outcome, oa.pnl_r
                FROM panel_summaries ps
                JOIN outcome_attributions oa ON ps.trade_id = oa.trade_id
                WHERE ps.outcome_source = ?
                  AND oa.outcome IS NOT NULL
                  AND oa.outcome != 'open'
                """,
                (outcome_source.value,),
            )
            rows = cursor.fetchall()
        except Exception as exc:
            logger.error("PanelCalibrator.compute_panel_stats failed: %s", exc)
            return {"error": str(exc)}

        if len(rows) < MIN_SAMPLES:
            return {
                "outcome_source": outcome_source.value,
                "sample_size": len(rows),
                "has_sufficient_samples": False,
                "note": f"Insufficient samples ({len(rows)}/{MIN_SAMPLES} minimum). No conclusions.",
            }

        enter_rows = [r for r in rows if r["panel_recommendation"] == "enter"]
        enter_wins = [r for r in enter_rows if r["outcome"] == "win"]
        enter_win_rate = len(enter_wins) / len(enter_rows) if enter_rows else None

        avg_score_wins = [r["avg_score"] for r in rows if r["outcome"] == "win"]
        avg_score_losses = [r["avg_score"] for r in rows if r["outcome"] == "loss"]

        def mean(lst: list) -> Optional[float]:
            return sum(lst) / len(lst) if lst else None

        high_disagree = [r for r in rows if r["reject_count"] >= 8]
        high_disagree_losses = [r for r in high_disagree if r["outcome"] == "loss"]
        disagree_loss_rate = (
            len(high_disagree_losses) / len(high_disagree)
            if high_disagree else None
        )

        return {
            "outcome_source": outcome_source.value,
            "sample_size": len(rows),
            "has_sufficient_samples": True,
            "enter_recommendations": len(enter_rows),
            "enter_win_rate": round(enter_win_rate, 3) if enter_win_rate is not None else None,
            "avg_score_on_wins": round(mean(avg_score_wins), 3) if mean(avg_score_wins) else None,
            "avg_score_on_losses": round(mean(avg_score_losses), 3) if mean(avg_score_losses) else None,
            "high_disagreement_count": len(high_disagree),
            "high_disagreement_loss_rate": round(disagree_loss_rate, 3) if disagree_loss_rate else None,
        }
