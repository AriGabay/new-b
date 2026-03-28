"""
SetupFamilyTracker and SpecialistGroupTracker.

Both trackers update running performance records keyed by
(setup_family/group_id, outcome_source). All conclusions gated at 30 samples.

Source: /docs/specialist_group_reliability_framework.md
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from learning.journal_extension import JournalExtension
from learning.outcome_source import OutcomeSource
from learning.schemas import SetupFamilyRecord, SpecialistGroupRecord

logger = logging.getLogger(__name__)

MIN_SAMPLES = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SetupFamilyTracker:
    """
    Tracks per-setup-family trade performance.

    Setup families are defined by the signals that triggered the trade:
      ema_crossover, bb_squeeze, rsi_divergence, support_bounce, etc.
      The setup_family string is set at trade-open time and stored in
      outcome_attributions.setup_family.

    All win-rate / avg_pnl_r metrics require 30+ samples.
    """

    def __init__(self, extension: JournalExtension) -> None:
        self._ext = extension

    def process_trade_outcome(
        self,
        setup_family: str,
        outcome: str,        # win / loss / breakeven
        pnl_r: float,
        bars_held: int,
        outcome_source: OutcomeSource,
    ) -> SetupFamilyRecord:
        """Update family record after one trade closes. Returns updated record."""
        rec = self._ext.load_setup_family_record(setup_family, outcome_source)
        if rec is None:
            rec = SetupFamilyRecord(
                setup_family=setup_family,
                outcome_source=outcome_source,
            )

        rec.total_trades += 1
        if outcome == "win":
            rec.wins += 1
        elif outcome == "loss":
            rec.losses += 1
        else:
            rec.breakevens += 1

        rec.total_pnl_r += pnl_r
        rec.bars_held_sum += bars_held
        rec.avg_bars_held = rec.bars_held_sum / rec.total_trades
        rec.last_updated = _utcnow()

        self._ext.upsert_setup_family_record(rec)
        return rec

    def get_family_summary(
        self,
        setup_family: str,
        outcome_source: OutcomeSource,
    ) -> dict:
        rec = self._ext.load_setup_family_record(setup_family, outcome_source)
        if rec is None:
            return {"setup_family": setup_family, "error": "not found"}
        return {
            "setup_family": setup_family,
            "outcome_source": outcome_source.value,
            "total_trades": rec.total_trades,
            "has_sufficient_samples": rec.has_sufficient_samples,
            "win_rate": rec.win_rate,
            "avg_pnl_r": rec.avg_pnl_r,
            "avg_bars_held": round(rec.avg_bars_held, 1) if rec.total_trades > 0 else None,
            "note": (
                None if rec.has_sufficient_samples
                else f"Insufficient samples ({rec.total_trades}/{MIN_SAMPLES}). No conclusions."
            ),
        }

    def get_all_families(self, outcome_source: OutcomeSource) -> list[dict]:
        """Return summaries for all setup families for the given source."""
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            cursor.execute(
                "SELECT setup_family FROM setup_family_records WHERE outcome_source=?",
                (outcome_source.value,),
            )
            families = [row["setup_family"] for row in cursor.fetchall()]
            return [self.get_family_summary(f, outcome_source) for f in families]
        except Exception as exc:
            logger.error("get_all_families failed: %s", exc)
            return []


class SpecialistGroupTracker:
    """
    Tracks per-specialist-group signal contribution to outcomes.

    For each group (indicators, candlestick, chart_pattern, etc.):
      - How many of its signals were on winning trades vs losing trades?
      - Average signal quality score for wins vs losses?

    These metrics require 30+ samples before conclusions.
    """

    def __init__(self, extension: JournalExtension) -> None:
        self._ext = extension

    def process_trade_outcome(
        self,
        group_id: str,
        outcome: str,
        signal_quality_score: float,
        outcome_source: OutcomeSource,
    ) -> SpecialistGroupRecord:
        """Update group record after one signal's trade closes."""
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            cursor.execute(
                "SELECT record_json FROM specialist_group_records "
                "WHERE group_id=? AND outcome_source=?",
                (group_id, outcome_source.value),
            )
            row = cursor.fetchone()
        except Exception as exc:
            logger.error("SpecialistGroupTracker read failed: %s", exc)
            row = None

        import json
        if row is None:
            rec = SpecialistGroupRecord(
                group_id=group_id,
                outcome_source=outcome_source,
            )
        else:
            data = json.loads(row["record_json"])
            rec = SpecialistGroupRecord(
                group_id=group_id,
                outcome_source=outcome_source,
            )
            for k, v in data.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)

        rec.signals_contributed += 1
        is_win = outcome == "win"

        if is_win:
            rec.signals_on_winning_trades += 1
            # Running average quality on wins
            n = rec.signals_on_winning_trades
            rec.avg_quality_score_wins = (
                (rec.avg_quality_score_wins * (n - 1) + signal_quality_score) / n
            )
        else:
            rec.signals_on_losing_trades += 1
            n = rec.signals_on_losing_trades
            rec.avg_quality_score_losses = (
                (rec.avg_quality_score_losses * (n - 1) + signal_quality_score) / n
            )

        rec.last_updated = _utcnow()
        self._ext.upsert_specialist_group_record(rec)
        return rec

    def get_group_summary(
        self,
        group_id: str,
        outcome_source: OutcomeSource,
    ) -> dict:
        import json
        try:
            self._ext._conn.row_factory = __import__("sqlite3").Row
            cursor = self._ext._conn.cursor()
            cursor.execute(
                "SELECT record_json FROM specialist_group_records "
                "WHERE group_id=? AND outcome_source=?",
                (group_id, outcome_source.value),
            )
            row = cursor.fetchone()
        except Exception as exc:
            return {"group_id": group_id, "error": str(exc)}

        if row is None:
            return {"group_id": group_id, "total": 0}

        data = json.loads(row["record_json"])
        rec = SpecialistGroupRecord(group_id=group_id, outcome_source=outcome_source)
        for k, v in data.items():
            if hasattr(rec, k):
                setattr(rec, k, v)

        return {
            "group_id": group_id,
            "outcome_source": outcome_source.value,
            "signals_contributed": rec.signals_contributed,
            "has_sufficient_samples": rec.has_sufficient_samples,
            "win_contribution_rate": rec.win_contribution_rate,
            "avg_quality_score_wins": round(rec.avg_quality_score_wins, 3),
            "avg_quality_score_losses": round(rec.avg_quality_score_losses, 3),
        }
