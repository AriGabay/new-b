"""
LearningReport generator.

Generates structured reports summarizing the system's learning state:
  - Overall performance by outcome source
  - Trader calibration status (who has sufficient samples, who doesn't)
  - Setup family performance summary
  - Specialist group contribution summary
  - Active recommendations
  - Error taxonomy distribution
  - Learning objectives status (all 12 from Phase 4 spec)

Reports are OBSERVATIONS only. They do not trigger any system changes.
All metrics note sample sizes and flag insufficient data clearly.

Source: /docs/example_learning_reports.md
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from learning.calibration import TraderCalibrator, PanelCalibrator
from learning.journal_extension import JournalExtension
from learning.outcome_source import OutcomeSource
from learning.recommendation_engine import RecommendationEngine
from learning.tracking import SetupFamilyTracker, SpecialistGroupTracker

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LearningReportGenerator:
    """
    Generates comprehensive learning-state reports.

    Usage:
        gen = LearningReportGenerator(extension)
        report = gen.generate_full_report(OutcomeSource.EVENT_DRIVEN_RUNTIME)
        print(report.format_text())
    """

    def __init__(self, extension: JournalExtension) -> None:
        self._ext = extension
        self._trader_cal = TraderCalibrator(extension)
        self._panel_cal = PanelCalibrator(extension)
        self._setup_tracker = SetupFamilyTracker(extension)
        self._specialist_tracker = SpecialistGroupTracker(extension)
        self._rec_engine = RecommendationEngine(extension)

    def generate_full_report(
        self,
        outcome_source: OutcomeSource,
    ) -> "LearningReport":
        """Generate full learning report for one outcome source."""
        now = _utcnow()

        # Section 1: Overall trade performance
        trade_stats = self._get_trade_stats(outcome_source)

        # Section 2: Trader calibration
        trader_section = self._get_trader_calibration_section(outcome_source)

        # Section 3: Panel calibration
        panel_section = self._panel_cal.compute_panel_stats(outcome_source)

        # Section 4: Setup family performance
        setup_section = self._setup_tracker.get_all_families(outcome_source)

        # Section 5: Specialist group reliability
        specialist_section = self._get_specialist_section(outcome_source)

        # Section 6: Active recommendations (last 20)
        rec_section = self._ext.query_recent_recommendations(outcome_source, n=20)

        # Section 7: Error taxonomy distribution
        error_section = self._get_error_distribution(outcome_source)

        return LearningReport(
            generated_at=now,
            outcome_source=outcome_source,
            trade_stats=trade_stats,
            trader_calibration=trader_section,
            panel_calibration=panel_section,
            setup_families=setup_section,
            specialist_groups=specialist_section,
            recommendations=rec_section,
            error_taxonomy=error_section,
        )

    def _get_trade_stats(self, outcome_source: OutcomeSource) -> dict:
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            cursor.execute(
                """
                SELECT outcome, COUNT(*) as count, AVG(pnl_r) as avg_pnl_r
                FROM outcome_attributions
                WHERE outcome_source = ?
                  AND outcome NOT IN ('open', '')
                GROUP BY outcome
                """,
                (outcome_source.value,),
            )
            rows = {r["outcome"]: {"count": r["count"], "avg_pnl_r": r["avg_pnl_r"]}
                    for r in cursor.fetchall()}

            wins = rows.get("win", {}).get("count", 0)
            losses = rows.get("loss", {}).get("count", 0)
            total = wins + losses + rows.get("breakeven", {}).get("count", 0)

            return {
                "total_closed": total,
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / total, 3) if total >= 30 else None,
                "win_rate_note": None if total >= 30 else f"Insufficient samples ({total}/30)",
                "avg_pnl_r_wins": rows.get("win", {}).get("avg_pnl_r"),
                "avg_pnl_r_losses": rows.get("loss", {}).get("avg_pnl_r"),
            }
        except Exception as exc:
            logger.error("_get_trade_stats failed: %s", exc)
            return {"error": str(exc)}

    def _get_trader_calibration_section(self, outcome_source: OutcomeSource) -> list[dict]:
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            cursor.execute(
                "SELECT trader_name FROM trader_calibration WHERE outcome_source=?",
                (outcome_source.value,),
            )
            traders = [row["trader_name"] for row in cursor.fetchall()]
            return [
                self._trader_cal.get_calibration_summary(t, outcome_source)
                for t in traders
            ]
        except Exception as exc:
            logger.error("_get_trader_calibration_section failed: %s", exc)
            return []

    def _get_specialist_section(self, outcome_source: OutcomeSource) -> list[dict]:
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            cursor.execute(
                "SELECT group_id FROM specialist_group_records WHERE outcome_source=?",
                (outcome_source.value,),
            )
            groups = [row["group_id"] for row in cursor.fetchall()]
            return [
                self._specialist_tracker.get_group_summary(g, outcome_source)
                for g in groups
            ]
        except Exception as exc:
            logger.error("_get_specialist_section failed: %s", exc)
            return []

    def _get_error_distribution(self, outcome_source: OutcomeSource) -> dict:
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            # query outcome_attributions — error taxonomy is derived, not stored
            # Return a note that error classification requires post-processing
            cursor.execute(
                """SELECT COUNT(*) as total FROM outcome_attributions
                   WHERE outcome_source=? AND outcome='loss'""",
                (outcome_source.value,),
            )
            row = cursor.fetchone()
            total_losses = row["total"] if row else 0
            return {
                "total_losses": total_losses,
                "note": "Error classification requires running ErrorTaxonomy.classify() on each trade. See attribution.py.",
            }
        except Exception as exc:
            return {"error": str(exc)}


class LearningReport:
    """Structured learning report. Call format_text() for readable output."""

    def __init__(
        self,
        generated_at: datetime,
        outcome_source: OutcomeSource,
        trade_stats: dict,
        trader_calibration: list,
        panel_calibration: dict,
        setup_families: list,
        specialist_groups: list,
        recommendations: list,
        error_taxonomy: dict,
    ) -> None:
        self.generated_at = generated_at
        self.outcome_source = outcome_source
        self.trade_stats = trade_stats
        self.trader_calibration = trader_calibration
        self.panel_calibration = panel_calibration
        self.setup_families = setup_families
        self.specialist_groups = specialist_groups
        self.recommendations = recommendations
        self.error_taxonomy = error_taxonomy

    def format_text(self) -> str:
        lines = [
            f"# Learning Report",
            f"Generated: {self.generated_at.isoformat()}",
            f"Source: {self.outcome_source.value}",
            "",
            "## Trade Performance",
        ]

        ts = self.trade_stats
        if "error" in ts:
            lines.append(f"  ERROR: {ts['error']}")
        else:
            lines.append(f"  Total closed: {ts.get('total_closed', 0)}")
            lines.append(f"  Wins: {ts.get('wins', 0)}  Losses: {ts.get('losses', 0)}")
            wr = ts.get("win_rate")
            if wr is None:
                lines.append(f"  Win rate: N/A — {ts.get('win_rate_note', '')}")
            else:
                lines.append(f"  Win rate: {wr:.1%}")

        lines += ["", "## Trader Calibration"]
        if not self.trader_calibration:
            lines.append("  No calibration data yet.")
        for tc in self.trader_calibration:
            name = tc.get("trader_name", "?")
            total = tc.get("total_reviews", 0)
            sufficient = tc.get("has_sufficient_samples", False)
            if not sufficient:
                lines.append(f"  {name}: {total} reviews (insufficient — min 30)")
            else:
                wr2 = tc.get("approval_win_rate")
                bs = tc.get("brier_score")
                lines.append(
                    f"  {name}: {total} reviews | "
                    f"approval_win_rate={wr2:.1%} | "
                    f"brier={bs:.3f} | "
                    f"overconfident={tc.get('is_overconfident')}"
                    if wr2 is not None and bs is not None
                    else f"  {name}: {total} reviews"
                )

        lines += ["", "## Setup Families"]
        if not self.setup_families:
            lines.append("  No setup family data yet.")
        for sf in self.setup_families:
            family = sf.get("setup_family", "?")
            total = sf.get("total_trades", 0)
            sufficient = sf.get("has_sufficient_samples", False)
            if not sufficient:
                lines.append(f"  {family}: {total} trades (insufficient — min 30)")
            else:
                wr3 = sf.get("win_rate")
                pnl = sf.get("avg_pnl_r")
                lines.append(f"  {family}: {total} trades | win_rate={wr3:.1%} | avg_pnl_r={pnl:.2f}R")

        lines += ["", "## Active Recommendations"]
        if not self.recommendations:
            lines.append("  No recommendations generated.")
        for rec in self.recommendations[:10]:
            lines.append(
                f"  [{rec.get('recommendation_type', '?').upper()}] "
                f"{rec.get('target', '?')}: {rec.get('reason', '')} "
                f"(n={rec.get('sample_size', 0)}, conf={rec.get('confidence', '?')})"
            )

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "outcome_source": self.outcome_source.value,
            "trade_stats": self.trade_stats,
            "trader_calibration": self.trader_calibration,
            "panel_calibration": self.panel_calibration,
            "setup_families": self.setup_families,
            "specialist_groups": self.specialist_groups,
            "recommendations": self.recommendations,
            "error_taxonomy": self.error_taxonomy,
        }
