"""
JournalExtension: adds 6 learning-layer tables to the existing JournalDB.

New tables:
  setup_packets           — archived BTCSetupPackets at decision time
  trader_reviews          — individual TraderVerdict records
  panel_summaries         — PanelResult summaries
  final_decisions         — FinalDecisionGroup outputs
  outcome_attributions    — closed-trade attribution linking trace → outcome
  calibration_records     — trader calibration running state (JSON blob per trader)

These tables are append-only (same rules as JournalDB). calibration_records
is the exception: it has one row per (trader_name, outcome_source) and is
updated in-place (UPSERT).

Source: /docs/journal_schema.md
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from learning.outcome_source import OutcomeSource
from learning.schemas import (
    OutcomeAttribution,
    SetupFamilyRecord,
    SpecialistGroupRecord,
    StoredFinalDecision,
    StoredPanelSummary,
    StoredSetupPacket,
    StoredTraderReview,
    TraderCalibrationRecord,
)

logger = logging.getLogger(__name__)


class JournalExtension:
    """
    Extends an existing JournalDB SQLite connection with learning-layer tables.

    Usage:
        ext = JournalExtension(conn)  # conn from JournalDB._conn
        ext.initialize()
        ext.insert_setup_packet(...)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def initialize(self) -> None:
        """Create all 6 new tables if not exist."""
        self._create_setup_packets_table()
        self._create_trader_reviews_table()
        self._create_panel_summaries_table()
        self._create_final_decisions_table()
        self._create_outcome_attributions_table()
        self._create_calibration_tables()
        self._conn.commit()
        logger.info("JournalExtension: 6 learning-layer tables initialized.")

    def _create_setup_packets_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS setup_packets (
                packet_id       TEXT PRIMARY KEY,
                symbol          TEXT NOT NULL,
                timeframe       TEXT,
                bar_timestamp   TEXT,
                stored_at       TEXT,
                outcome_source  TEXT NOT NULL,
                packet_json     TEXT NOT NULL,
                trade_id        TEXT
            )
        """)

    def _create_trader_reviews_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trader_reviews (
                review_id           TEXT PRIMARY KEY,
                packet_id           TEXT NOT NULL,
                trader_name         TEXT NOT NULL,
                outcome_source      TEXT NOT NULL,
                vote                TEXT,
                score               REAL,
                confidence          REAL,
                pro_reason          TEXT,
                anti_reason         TEXT,
                execution_concern   TEXT,
                risk_concern        TEXT,
                explanation         TEXT,
                reviewed_at         TEXT,
                trade_id            TEXT
            )
        """)

    def _create_panel_summaries_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS panel_summaries (
                panel_id                TEXT PRIMARY KEY,
                packet_id               TEXT NOT NULL,
                outcome_source          TEXT NOT NULL,
                approve_count           INTEGER,
                reject_count            INTEGER,
                abstain_count           INTEGER,
                avg_score               REAL,
                weighted_score          REAL,
                panel_recommendation    TEXT,
                key_risks               TEXT,
                key_strengths           TEXT,
                evaluated_at            TEXT,
                trade_id                TEXT
            )
        """)

    def _create_final_decisions_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS final_decisions (
                decision_id             TEXT PRIMARY KEY,
                packet_id               TEXT NOT NULL,
                panel_id                TEXT NOT NULL,
                outcome_source          TEXT NOT NULL,
                decision                TEXT,
                safety_rails_triggered  TEXT,
                rationale               TEXT,
                decided_at              TEXT,
                trade_id                TEXT
            )
        """)

    def _create_outcome_attributions_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS outcome_attributions (
                attribution_id  TEXT PRIMARY KEY,
                trade_id        TEXT NOT NULL,
                packet_id       TEXT,
                panel_id        TEXT,
                decision_id     TEXT,
                outcome_source  TEXT NOT NULL,
                outcome         TEXT,
                pnl_r           REAL,
                exit_reason     TEXT,
                bars_held       INTEGER,
                setup_family    TEXT,
                attributed_at   TEXT
            )
        """)

    def _create_calibration_tables(self) -> None:
        """
        Trader calibration, setup family, specialist group, and recommendations.
        These use UPSERT semantics (one row per key).
        """
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trader_calibration (
                trader_name             TEXT NOT NULL,
                outcome_source          TEXT NOT NULL,
                calibration_json        TEXT NOT NULL,
                last_updated            TEXT,
                PRIMARY KEY (trader_name, outcome_source)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS setup_family_records (
                setup_family    TEXT NOT NULL,
                outcome_source  TEXT NOT NULL,
                record_json     TEXT NOT NULL,
                last_updated    TEXT,
                PRIMARY KEY (setup_family, outcome_source)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS specialist_group_records (
                group_id        TEXT NOT NULL,
                outcome_source  TEXT NOT NULL,
                record_json     TEXT NOT NULL,
                last_updated    TEXT,
                PRIMARY KEY (group_id, outcome_source)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS learning_recommendations (
                recommendation_id   TEXT PRIMARY KEY,
                created_at          TEXT,
                outcome_source      TEXT NOT NULL,
                recommendation_type TEXT,
                target              TEXT,
                reason              TEXT,
                evidence            TEXT,
                sample_size         INTEGER,
                confidence          TEXT,
                applied             INTEGER DEFAULT 0,
                applied_at          TEXT
            )
        """)

    # ------------------------------------------------------------------
    # Insert methods
    # ------------------------------------------------------------------

    def insert_setup_packet(self, packet: StoredSetupPacket) -> None:
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO setup_packets
                   (packet_id, symbol, timeframe, bar_timestamp, stored_at,
                    outcome_source, packet_json, trade_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    packet.packet_id,
                    packet.symbol,
                    packet.timeframe,
                    packet.bar_timestamp.isoformat(),
                    packet.stored_at.isoformat(),
                    packet.outcome_source.value,
                    packet.packet_json,
                    packet.trade_id,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_setup_packet failed: %s", exc)

    def insert_trader_review(self, review: StoredTraderReview) -> None:
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO trader_reviews
                   (review_id, packet_id, trader_name, outcome_source,
                    vote, score, confidence, pro_reason, anti_reason,
                    execution_concern, risk_concern, explanation,
                    reviewed_at, trade_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review.review_id,
                    review.packet_id,
                    review.trader_name,
                    review.outcome_source.value,
                    review.vote,
                    review.score,
                    review.confidence,
                    review.pro_reason,
                    review.anti_reason,
                    review.execution_concern,
                    review.risk_concern,
                    review.explanation,
                    review.reviewed_at.isoformat(),
                    review.trade_id,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_trader_review failed: %s", exc)

    def insert_panel_summary(self, summary: StoredPanelSummary) -> None:
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO panel_summaries
                   (panel_id, packet_id, outcome_source, approve_count,
                    reject_count, abstain_count, avg_score, weighted_score,
                    panel_recommendation, key_risks, key_strengths,
                    evaluated_at, trade_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    summary.panel_id,
                    summary.packet_id,
                    summary.outcome_source.value,
                    summary.approve_count,
                    summary.reject_count,
                    summary.abstain_count,
                    summary.avg_score,
                    summary.weighted_score,
                    summary.panel_recommendation,
                    summary.key_risks,
                    summary.key_strengths,
                    summary.evaluated_at.isoformat(),
                    summary.trade_id,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_panel_summary failed: %s", exc)

    def insert_final_decision(self, decision: StoredFinalDecision) -> None:
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO final_decisions
                   (decision_id, packet_id, panel_id, outcome_source,
                    decision, safety_rails_triggered, rationale,
                    decided_at, trade_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision.decision_id,
                    decision.packet_id,
                    decision.panel_id,
                    decision.outcome_source.value,
                    decision.decision,
                    decision.safety_rails_triggered,
                    decision.rationale,
                    decision.decided_at.isoformat(),
                    decision.trade_id,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_final_decision failed: %s", exc)

    def insert_outcome_attribution(self, attr: OutcomeAttribution) -> None:
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO outcome_attributions
                   (attribution_id, trade_id, packet_id, panel_id, decision_id,
                    outcome_source, outcome, pnl_r, exit_reason, bars_held,
                    setup_family, attributed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attr.attribution_id,
                    attr.trade_id,
                    attr.packet_id,
                    attr.panel_id,
                    attr.decision_id,
                    attr.outcome_source.value,
                    attr.outcome,
                    attr.pnl_r,
                    attr.exit_reason,
                    attr.bars_held,
                    attr.setup_family,
                    attr.attributed_at.isoformat(),
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_outcome_attribution failed: %s", exc)

    def upsert_trader_calibration(self, record: TraderCalibrationRecord) -> None:
        try:
            now = datetime.utcnow().isoformat()
            record_json = json.dumps({
                "total_reviews": record.total_reviews,
                "approvals_given": record.approvals_given,
                "approvals_that_won": record.approvals_that_won,
                "rejections_given": record.rejections_given,
                "brier_score_sum": record.brier_score_sum,
                "brier_score_count": record.brier_score_count,
                "high_conf_wrong_count": record.high_conf_wrong_count,
                "win_score_sum": record.win_score_sum,
                "win_score_count": record.win_score_count,
                "loss_score_sum": record.loss_score_sum,
                "loss_score_count": record.loss_score_count,
            })
            self._conn.execute(
                """INSERT INTO trader_calibration
                   (trader_name, outcome_source, calibration_json, last_updated)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(trader_name, outcome_source)
                   DO UPDATE SET calibration_json=excluded.calibration_json,
                                 last_updated=excluded.last_updated""",
                (record.trader_name, record.outcome_source.value, record_json, now),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("upsert_trader_calibration failed: %s", exc)

    def upsert_setup_family_record(self, record: SetupFamilyRecord) -> None:
        try:
            now = datetime.utcnow().isoformat()
            record_json = json.dumps({
                "total_trades": record.total_trades,
                "wins": record.wins,
                "losses": record.losses,
                "breakevens": record.breakevens,
                "total_pnl_r": record.total_pnl_r,
                "bars_held_sum": record.bars_held_sum,
            })
            self._conn.execute(
                """INSERT INTO setup_family_records
                   (setup_family, outcome_source, record_json, last_updated)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(setup_family, outcome_source)
                   DO UPDATE SET record_json=excluded.record_json,
                                 last_updated=excluded.last_updated""",
                (record.setup_family, record.outcome_source.value, record_json, now),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("upsert_setup_family_record failed: %s", exc)

    def upsert_specialist_group_record(self, record: SpecialistGroupRecord) -> None:
        try:
            now = datetime.utcnow().isoformat()
            record_json = json.dumps({
                "signals_contributed": record.signals_contributed,
                "signals_on_winning_trades": record.signals_on_winning_trades,
                "signals_on_losing_trades": record.signals_on_losing_trades,
                "avg_quality_score_wins": record.avg_quality_score_wins,
                "avg_quality_score_losses": record.avg_quality_score_losses,
            })
            self._conn.execute(
                """INSERT INTO specialist_group_records
                   (group_id, outcome_source, record_json, last_updated)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(group_id, outcome_source)
                   DO UPDATE SET record_json=excluded.record_json,
                                 last_updated=excluded.last_updated""",
                (record.group_id, record.outcome_source.value, record_json, now),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("upsert_specialist_group_record failed: %s", exc)

    def insert_learning_recommendation(self, rec) -> None:
        """rec is a LearningRecommendation dataclass."""
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO learning_recommendations
                   (recommendation_id, created_at, outcome_source,
                    recommendation_type, target, reason, evidence,
                    sample_size, confidence, applied, applied_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec.recommendation_id,
                    rec.created_at.isoformat(),
                    rec.outcome_source.value,
                    rec.recommendation_type,
                    rec.target,
                    rec.reason,
                    rec.evidence,
                    rec.sample_size,
                    rec.confidence,
                    int(rec.applied),
                    rec.applied_at.isoformat() if rec.applied_at else None,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_learning_recommendation failed: %s", exc)

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def load_trader_calibration(
        self,
        trader_name: str,
        outcome_source: OutcomeSource,
    ) -> Optional[TraderCalibrationRecord]:
        """Load existing calibration record, or return a fresh one."""
        try:
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT calibration_json FROM trader_calibration "
                "WHERE trader_name=? AND outcome_source=?",
                (trader_name, outcome_source.value),
            )
            row = cursor.fetchone()
            if row is None:
                return TraderCalibrationRecord(
                    trader_name=trader_name,
                    outcome_source=outcome_source,
                )
            data = json.loads(row["calibration_json"])
            rec = TraderCalibrationRecord(
                trader_name=trader_name,
                outcome_source=outcome_source,
            )
            for k, v in data.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)
            return rec
        except Exception as exc:
            logger.error("load_trader_calibration failed: %s", exc)
            return None

    def load_setup_family_record(
        self,
        setup_family: str,
        outcome_source: OutcomeSource,
    ) -> Optional[SetupFamilyRecord]:
        try:
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT record_json FROM setup_family_records "
                "WHERE setup_family=? AND outcome_source=?",
                (setup_family, outcome_source.value),
            )
            row = cursor.fetchone()
            if row is None:
                return SetupFamilyRecord(
                    setup_family=setup_family,
                    outcome_source=outcome_source,
                )
            data = json.loads(row["record_json"])
            rec = SetupFamilyRecord(
                setup_family=setup_family,
                outcome_source=outcome_source,
            )
            for k, v in data.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)
            return rec
        except Exception as exc:
            logger.error("load_setup_family_record failed: %s", exc)
            return None

    def query_trader_reviews_by_packet(self, packet_id: str) -> list[dict]:
        """
        Return trader review rows for a given packet_id.

        Used by the attribution pipeline to fetch trader verdicts when
        processing a closed trade, so TraderCalibrator can be updated.
        """
        if not packet_id:
            return []
        try:
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            cursor.execute(
                """SELECT trader_name, vote, score, confidence
                   FROM trader_reviews WHERE packet_id = ?""",
                (packet_id,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.error("query_trader_reviews_by_packet failed: %s", exc)
            return []

    def query_attributions_for_trader(
        self,
        trader_name: str,
        outcome_source: OutcomeSource,
        n: Optional[int] = None,
    ) -> list[dict]:
        """
        Return outcome attribution rows for trades where this trader
        participated (requires join with trader_reviews).
        """
        try:
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            query = """
                SELECT oa.* FROM outcome_attributions oa
                JOIN trader_reviews tr ON oa.trade_id = tr.trade_id
                WHERE tr.trader_name = ?
                  AND oa.outcome_source = ?
                  AND oa.outcome IS NOT NULL
                ORDER BY oa.attributed_at DESC
            """
            params: list = [trader_name, outcome_source.value]
            if n is not None:
                query += " LIMIT ?"
                params.append(n)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.error("query_attributions_for_trader failed: %s", exc)
            return []

    def query_recent_recommendations(
        self,
        outcome_source: OutcomeSource,
        n: int = 20,
    ) -> list[dict]:
        try:
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            cursor.execute(
                """SELECT * FROM learning_recommendations
                   WHERE outcome_source = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (outcome_source.value, n),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.error("query_recent_recommendations failed: %s", exc)
            return []
