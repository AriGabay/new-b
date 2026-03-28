"""
RecommendationEngine: generates actionable recommendations based on calibration data.

STRICT RULES:
  1. Never recommend policy changes without sufficient evidence (min 30 samples).
  2. Always report sample size alongside any recommendation.
  3. Segment recommendations by OutcomeSource — never mix.
  4. Recommendations are advisory only. No automatic policy changes.
  5. Quarantine means "flag for review" — NOT automatic disabling.

Recommendation types:
  reweight   — adjust trader's influence weight (advisory)
  quarantine — flag trader/setup for human review
  caution    — flag for extra scrutiny, not disabling
  none       — no action recommended

Source: /docs/learning_logic.md
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from learning.calibration import TraderCalibrator
from learning.journal_extension import JournalExtension
from learning.outcome_source import OutcomeSource
from learning.schemas import LearningRecommendation
from learning.tracking import SetupFamilyTracker

logger = logging.getLogger(__name__)

MIN_SAMPLES = 30
POOR_WIN_RATE_THRESHOLD   = 0.40   # below this → caution
VERY_POOR_WIN_RATE        = 0.30   # below this → quarantine
GOOD_WIN_RATE_THRESHOLD   = 0.60   # above this → reweight up
POOR_BRIER_THRESHOLD      = 0.30   # above this → caution (random = 0.25)


class RecommendationEngine:
    """
    Analyzes calibration data and emits recommendations.

    Does NOT modify any weights or thresholds automatically.
    Returns LearningRecommendation objects that can be reviewed
    and applied manually.
    """

    def __init__(self, extension: JournalExtension) -> None:
        self._ext = extension
        self._calibrator = TraderCalibrator(extension)
        self._setup_tracker = SetupFamilyTracker(extension)

    def generate_trader_recommendations(
        self,
        outcome_source: OutcomeSource,
    ) -> list[LearningRecommendation]:
        """
        Scan all trader calibration records and generate recommendations.
        Only generates recommendations for traders with >= 30 samples.
        """
        recs = []
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            cursor.execute(
                "SELECT trader_name FROM trader_calibration WHERE outcome_source=?",
                (outcome_source.value,),
            )
            traders = [row["trader_name"] for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("RecommendationEngine: failed to load traders: %s", exc)
            return []

        for trader_name in traders:
            summary = self._calibrator.get_calibration_summary(trader_name, outcome_source)

            if not summary.get("has_sufficient_samples", False):
                continue  # Not enough data

            total = summary.get("total_reviews", 0)
            win_rate = summary.get("approval_win_rate")
            brier = summary.get("brier_score")
            overconfident = summary.get("is_overconfident", False)

            rec_type = "none"
            reason = ""
            evidence = ""
            confidence = "low"

            if win_rate is not None and win_rate < VERY_POOR_WIN_RATE:
                rec_type = "quarantine"
                reason = f"Approval win rate {win_rate:.1%} is very poor (threshold {VERY_POOR_WIN_RATE:.0%})"
                evidence = f"Based on {total} samples. All trades approved by this trader."
                confidence = "medium"

            elif win_rate is not None and win_rate < POOR_WIN_RATE_THRESHOLD:
                rec_type = "caution"
                reason = f"Approval win rate {win_rate:.1%} is below caution threshold {POOR_WIN_RATE_THRESHOLD:.0%}"
                evidence = f"Based on {total} samples."
                confidence = "low"

            elif win_rate is not None and win_rate >= GOOD_WIN_RATE_THRESHOLD:
                rec_type = "reweight"
                reason = f"Approval win rate {win_rate:.1%} is strong (threshold {GOOD_WIN_RATE_THRESHOLD:.0%})"
                evidence = f"Based on {total} samples. Consider increasing influence weight."
                confidence = "medium" if total >= 60 else "low"

            if overconfident and rec_type == "none":
                rec_type = "caution"
                reason = "Systematic overconfidence detected (high confidence + wrong outcome > 30%)"
                evidence = f"Based on {total} samples."
                confidence = "medium"

            if rec_type != "none":
                recs.append(LearningRecommendation(
                    recommendation_id=str(uuid.uuid4()),
                    created_at=datetime.now(timezone.utc),
                    outcome_source=outcome_source,
                    recommendation_type=rec_type,
                    target=trader_name,
                    reason=reason,
                    evidence=evidence,
                    sample_size=total,
                    confidence=confidence,
                ))
                self._ext.insert_learning_recommendation(recs[-1])

        return recs

    def generate_setup_family_recommendations(
        self,
        outcome_source: OutcomeSource,
    ) -> list[LearningRecommendation]:
        """
        Scan all setup family records and flag underperforming families.
        """
        recs = []
        families = self._setup_tracker.get_all_families(outcome_source)

        for summary in families:
            if not summary.get("has_sufficient_samples", False):
                continue

            family = summary["setup_family"]
            total = summary["total_trades"]
            win_rate = summary.get("win_rate")
            avg_pnl_r = summary.get("avg_pnl_r")

            if win_rate is None:
                continue

            rec_type = "none"
            reason = ""
            evidence = ""

            if win_rate < VERY_POOR_WIN_RATE and avg_pnl_r is not None and avg_pnl_r < -0.5:
                rec_type = "quarantine"
                reason = f"Setup family '{family}' has very poor win rate {win_rate:.1%} and avg_pnl_r {avg_pnl_r:.2f}R"
                evidence = f"Based on {total} trades."
                confidence = "medium"

            elif win_rate < POOR_WIN_RATE_THRESHOLD:
                rec_type = "caution"
                reason = f"Setup family '{family}' win rate {win_rate:.1%} below {POOR_WIN_RATE_THRESHOLD:.0%}"
                evidence = f"Based on {total} trades."
                confidence = "low"

            if rec_type != "none":
                recs.append(LearningRecommendation(
                    recommendation_id=str(uuid.uuid4()),
                    created_at=datetime.now(timezone.utc),
                    outcome_source=outcome_source,
                    recommendation_type=rec_type,
                    target=family,
                    reason=reason,
                    evidence=evidence,
                    sample_size=total,
                    confidence=confidence,
                ))
                self._ext.insert_learning_recommendation(recs[-1])

        return recs

    def generate_all_recommendations(
        self,
        outcome_source: OutcomeSource,
    ) -> dict:
        """Run all recommendation generators. Returns summary dict."""
        trader_recs = self.generate_trader_recommendations(outcome_source)
        setup_recs = self.generate_setup_family_recommendations(outcome_source)

        all_recs = trader_recs + setup_recs
        return {
            "outcome_source": outcome_source.value,
            "trader_recommendations": len(trader_recs),
            "setup_family_recommendations": len(setup_recs),
            "total": len(all_recs),
            "recommendations": [
                {
                    "type": r.recommendation_type,
                    "target": r.target,
                    "reason": r.reason,
                    "sample_size": r.sample_size,
                    "confidence": r.confidence,
                }
                for r in all_recs
            ],
        }
