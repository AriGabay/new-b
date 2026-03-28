"""
Tests for the Phase 4 learning layer.

Tests cover:
  1. OutcomeSource enum and source mixing guard
  2. JournalExtension table creation and insert/query
  3. DecisionTraceLogger full trace logging
  4. TraderCalibrator min-sample guard, update, and summary
  5. SetupFamilyTracker update and summary
  6. OutcomeAttributor full pipeline
  7. RecommendationEngine (no recs when < 30 samples)
  8. LearningReportGenerator

All tests use in-memory SQLite. No filesystem access required.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pytest

from learning.outcome_source import OutcomeSource, assert_single_source
from learning.journal_extension import JournalExtension
from learning.schemas import (
    StoredSetupPacket,
    StoredTraderReview,
    StoredPanelSummary,
    StoredFinalDecision,
    OutcomeAttribution,
    TraderCalibrationRecord,
    SetupFamilyRecord,
)
from learning.decision_logger import DecisionTraceLogger
from learning.calibration import TraderCalibrator, PanelCalibrator
from learning.tracking import SetupFamilyTracker, SpecialistGroupTracker
from learning.attribution import OutcomeAttributor, ErrorTaxonomy
from learning.recommendation_engine import RecommendationEngine
from learning.reports import LearningReportGenerator


def make_extension() -> JournalExtension:
    """Create in-memory SQLite JournalExtension for testing."""
    conn = sqlite3.connect(":memory:")
    ext = JournalExtension(conn)
    ext.initialize()
    return ext


# ---------------------------------------------------------------------------
# 1. OutcomeSource
# ---------------------------------------------------------------------------

class TestOutcomeSource:
    def test_enum_values(self):
        assert OutcomeSource.EVENT_DRIVEN_RUNTIME.value == "event_driven_runtime"
        assert OutcomeSource.SIMPLIFIED_BACKTEST.value == "simplified_backtest"
        assert OutcomeSource.LIVE_EXCHANGE_FED.value == "live_exchange_fed"

    def test_is_live(self):
        assert OutcomeSource.LIVE_EXCHANGE_FED.is_live()
        assert not OutcomeSource.EVENT_DRIVEN_RUNTIME.is_live()

    def test_is_validated_source(self):
        assert OutcomeSource.EVENT_DRIVEN_RUNTIME.is_validated_source()
        assert OutcomeSource.LIVE_EXCHANGE_FED.is_validated_source()
        assert not OutcomeSource.SIMPLIFIED_BACKTEST.is_validated_source()
        assert not OutcomeSource.SYNTHETIC_DATA.is_validated_source()

    def test_assert_single_source_ok(self):
        src = assert_single_source([
            OutcomeSource.EVENT_DRIVEN_RUNTIME,
            OutcomeSource.EVENT_DRIVEN_RUNTIME,
        ])
        assert src == OutcomeSource.EVENT_DRIVEN_RUNTIME

    def test_assert_single_source_mixing_raises(self):
        with pytest.raises(ValueError, match="mixing"):
            assert_single_source([
                OutcomeSource.EVENT_DRIVEN_RUNTIME,
                OutcomeSource.SIMPLIFIED_BACKTEST,
            ])

    def test_assert_single_source_empty_raises(self):
        with pytest.raises(ValueError):
            assert_single_source([])


# ---------------------------------------------------------------------------
# 2. JournalExtension
# ---------------------------------------------------------------------------

class TestJournalExtension:
    def test_initialize_creates_tables(self):
        ext = make_extension()
        cursor = ext._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        expected = {
            "setup_packets", "trader_reviews", "panel_summaries",
            "final_decisions", "outcome_attributions",
            "trader_calibration", "setup_family_records",
            "specialist_group_records", "learning_recommendations",
        }
        assert expected.issubset(tables)

    def test_insert_setup_packet(self):
        ext = make_extension()
        packet = StoredSetupPacket(
            packet_id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="1h",
            bar_timestamp=datetime.now(timezone.utc),
            stored_at=datetime.now(timezone.utc),
            outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
            packet_json='{"symbol": "BTCUSDT"}',
        )
        ext.insert_setup_packet(packet)
        cursor = ext._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM setup_packets")
        assert cursor.fetchone()[0] == 1

    def test_insert_trader_review(self):
        ext = make_extension()
        review = StoredTraderReview(
            review_id=str(uuid.uuid4()),
            packet_id=str(uuid.uuid4()),
            trader_name="TrendFollowingEvaluator",
            outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
            vote="approve",
            score=7.5,
            confidence=0.8,
            pro_reason="strong trend",
            anti_reason="high ATR",
            execution_concern="none",
            risk_concern="none",
            explanation="looks good",
            reviewed_at=datetime.now(timezone.utc),
        )
        ext.insert_trader_review(review)
        cursor = ext._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trader_reviews")
        assert cursor.fetchone()[0] == 1

    def test_upsert_trader_calibration(self):
        ext = make_extension()
        rec = TraderCalibrationRecord(
            trader_name="MomentumEvaluator",
            outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
            total_reviews=5,
            approvals_given=3,
            approvals_that_won=2,
        )
        ext.upsert_trader_calibration(rec)
        ext.upsert_trader_calibration(rec)  # should not duplicate
        cursor = ext._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trader_calibration")
        assert cursor.fetchone()[0] == 1

    def test_load_trader_calibration_fresh(self):
        ext = make_extension()
        rec = ext.load_trader_calibration("NewTrader", OutcomeSource.EVENT_DRIVEN_RUNTIME)
        assert rec is not None
        assert rec.total_reviews == 0
        assert rec.trader_name == "NewTrader"


# ---------------------------------------------------------------------------
# 3. DecisionTraceLogger
# ---------------------------------------------------------------------------

class TestDecisionTraceLogger:
    def test_log_setup_packet_returns_id(self):
        ext = make_extension()
        logger = DecisionTraceLogger(ext, OutcomeSource.EVENT_DRIVEN_RUNTIME)
        packet_id = logger.log_setup_packet({"symbol": "BTCUSDT", "timeframe": "1h"})
        assert isinstance(packet_id, str)
        assert len(packet_id) > 0

    def test_log_trader_reviews(self):
        ext = make_extension()
        dtl = DecisionTraceLogger(ext, OutcomeSource.EVENT_DRIVEN_RUNTIME)
        packet_id = dtl.log_setup_packet({"symbol": "BTCUSDT"})

        @dataclass
        class FakeVerdict:
            trader_name: str
            vote: str
            score: float
            confidence: float
            pro_reason: str = ""
            anti_reason: str = ""
            execution_concern: str = ""
            risk_concern: str = ""
            explanation: str = ""

        verdicts = [
            FakeVerdict("TrendFollowingEvaluator", "approve", 7.0, 0.8),
            FakeVerdict("MomentumEvaluator", "reject", 4.0, 0.6),
        ]
        dtl.log_trader_reviews(packet_id, verdicts)

        cursor = ext._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trader_reviews WHERE packet_id=?", (packet_id,))
        assert cursor.fetchone()[0] == 2

    def test_full_trace(self):
        ext = make_extension()
        dtl = DecisionTraceLogger(ext, OutcomeSource.EVENT_DRIVEN_RUNTIME)
        packet_id = dtl.log_setup_packet({"symbol": "BTCUSDT"})

        @dataclass
        class FakePanel:
            approve_count: int = 15
            reject_count: int = 5
            abstain_count: int = 0
            avg_score: float = 7.2
            weighted_score: float = 7.1
            panel_recommendation: str = "enter"
            key_risks: list = None
            key_strengths: list = None
            def __post_init__(self):
                self.key_risks = self.key_risks or []
                self.key_strengths = self.key_strengths or []

        @dataclass
        class FakeDecision:
            decision: str = "enter"
            safety_rails_triggered: list = None
            rationale: str = "all rails passed"
            def __post_init__(self):
                self.safety_rails_triggered = self.safety_rails_triggered or []

        panel_id = dtl.log_panel_summary(packet_id, FakePanel())
        decision_id = dtl.log_final_decision(packet_id, panel_id, FakeDecision())
        attribution_id = dtl.log_outcome_attribution(
            trade_id="trade-001",
            packet_id=packet_id,
            panel_id=panel_id,
            decision_id=decision_id,
            outcome="win",
            pnl_r=1.8,
            exit_reason="target_reached",
            bars_held=8,
            setup_family="ema_crossover",
        )

        assert isinstance(panel_id, str)
        assert isinstance(decision_id, str)
        assert isinstance(attribution_id, str)

        cursor = ext._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM outcome_attributions WHERE trade_id='trade-001'")
        assert cursor.fetchone()[0] == 1


# ---------------------------------------------------------------------------
# 4. TraderCalibrator
# ---------------------------------------------------------------------------

class TestTraderCalibrator:
    def test_insufficient_samples_returns_none_metrics(self):
        ext = make_extension()
        cal = TraderCalibrator(ext)
        summary = cal.get_calibration_summary("TestTrader", OutcomeSource.EVENT_DRIVEN_RUNTIME)
        assert summary["has_sufficient_samples"] is False
        assert summary["approval_win_rate"] is None
        assert "Insufficient samples" in summary["note"]

    def test_update_increments_counts(self):
        ext = make_extension()
        cal = TraderCalibrator(ext)
        for i in range(5):
            cal.process_trade_outcome(
                trade_id=f"t{i}",
                outcome="win" if i % 2 == 0 else "loss",
                outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
                trader_name="TestTrader",
                vote="approve",
                score=7.0,
                confidence=0.8,
            )
        rec = ext.load_trader_calibration("TestTrader", OutcomeSource.EVENT_DRIVEN_RUNTIME)
        assert rec.total_reviews == 5
        assert rec.approvals_given == 5

    def test_min_30_samples_gate(self):
        ext = make_extension()
        cal = TraderCalibrator(ext)
        # Add 29 samples — still insufficient
        for i in range(29):
            cal.process_trade_outcome(
                trade_id=f"t{i}",
                outcome="win",
                outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
                trader_name="TestTrader",
                vote="approve",
                score=7.0,
                confidence=0.8,
            )
        summary = cal.get_calibration_summary("TestTrader", OutcomeSource.EVENT_DRIVEN_RUNTIME)
        assert summary["has_sufficient_samples"] is False

        # Add 1 more to reach 30
        cal.process_trade_outcome(
            trade_id="t29",
            outcome="win",
            outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
            trader_name="TestTrader",
            vote="approve",
            score=7.0,
            confidence=0.8,
        )
        summary = cal.get_calibration_summary("TestTrader", OutcomeSource.EVENT_DRIVEN_RUNTIME)
        assert summary["has_sufficient_samples"] is True
        assert summary["approval_win_rate"] is not None


# ---------------------------------------------------------------------------
# 5. SetupFamilyTracker
# ---------------------------------------------------------------------------

class TestSetupFamilyTracker:
    def test_process_and_summarize(self):
        ext = make_extension()
        tracker = SetupFamilyTracker(ext)
        for i in range(10):
            tracker.process_trade_outcome(
                setup_family="ema_crossover",
                outcome="win" if i < 7 else "loss",
                pnl_r=1.5 if i < 7 else -1.0,
                bars_held=8,
                outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
            )
        summary = tracker.get_family_summary("ema_crossover", OutcomeSource.EVENT_DRIVEN_RUNTIME)
        assert summary["total_trades"] == 10
        assert summary["has_sufficient_samples"] is False  # < 30
        assert summary["win_rate"] is None  # insufficient

    def test_win_rate_available_at_30(self):
        ext = make_extension()
        tracker = SetupFamilyTracker(ext)
        for i in range(30):
            tracker.process_trade_outcome(
                setup_family="bb_squeeze",
                outcome="win" if i < 18 else "loss",
                pnl_r=1.0 if i < 18 else -1.0,
                bars_held=10,
                outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
            )
        summary = tracker.get_family_summary("bb_squeeze", OutcomeSource.EVENT_DRIVEN_RUNTIME)
        assert summary["has_sufficient_samples"] is True
        assert abs(summary["win_rate"] - 0.60) < 0.01


# ---------------------------------------------------------------------------
# 6. ErrorTaxonomy
# ---------------------------------------------------------------------------

class TestErrorTaxonomy:
    def test_win_returns_none(self):
        et = ErrorTaxonomy()
        code, desc = et.classify("win", 1.5, "target_reached", 8, 0.7, "bull", "LONG")
        assert code == "none"

    def test_regime_mismatch(self):
        et = ErrorTaxonomy()
        code, desc = et.classify("loss", -1.0, "stop_loss", 5, 0.7, "bear", "LONG")
        assert code == "D"

    def test_stop_placement_fast_exit(self):
        et = ErrorTaxonomy()
        code, desc = et.classify("loss", -1.0, "stop_loss", 2, 0.7, "bull", "LONG")
        assert code == "B"

    def test_signal_quality_low_score(self):
        et = ErrorTaxonomy()
        code, desc = et.classify("loss", -1.0, "stop_loss", 8, 0.52, "bull", "LONG")
        assert code == "E"


# ---------------------------------------------------------------------------
# 7. RecommendationEngine (no recs before 30 samples)
# ---------------------------------------------------------------------------

class TestRecommendationEngine:
    def test_no_recommendations_before_30_samples(self):
        ext = make_extension()
        cal = TraderCalibrator(ext)
        for i in range(20):
            cal.process_trade_outcome(
                trade_id=f"t{i}",
                outcome="loss",
                outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
                trader_name="BadTrader",
                vote="approve",
                score=4.0,
                confidence=0.9,
            )
        engine = RecommendationEngine(ext)
        recs = engine.generate_trader_recommendations(OutcomeSource.EVENT_DRIVEN_RUNTIME)
        # No recs — insufficient samples (20 < 30)
        assert len(recs) == 0

    def test_quarantine_recommendation_after_30_bad_trades(self):
        ext = make_extension()
        cal = TraderCalibrator(ext)
        for i in range(35):
            cal.process_trade_outcome(
                trade_id=f"t{i}",
                outcome="loss",  # always loses
                outcome_source=OutcomeSource.EVENT_DRIVEN_RUNTIME,
                trader_name="TerribleTrader",
                vote="approve",
                score=4.0,
                confidence=0.9,
            )
        engine = RecommendationEngine(ext)
        recs = engine.generate_trader_recommendations(OutcomeSource.EVENT_DRIVEN_RUNTIME)
        quarantine_recs = [r for r in recs if r.recommendation_type == "quarantine"]
        assert len(quarantine_recs) >= 1
        assert quarantine_recs[0].target == "TerribleTrader"
        assert quarantine_recs[0].sample_size >= 30


# ---------------------------------------------------------------------------
# 8. LearningReportGenerator
# ---------------------------------------------------------------------------

class TestLearningReportGenerator:
    def test_report_generates_without_data(self):
        ext = make_extension()
        gen = LearningReportGenerator(ext)
        report = gen.generate_full_report(OutcomeSource.EVENT_DRIVEN_RUNTIME)
        assert report is not None
        text = report.format_text()
        assert "Learning Report" in text
        assert "Trade Performance" in text

    def test_report_to_dict(self):
        ext = make_extension()
        gen = LearningReportGenerator(ext)
        report = gen.generate_full_report(OutcomeSource.EVENT_DRIVEN_RUNTIME)
        d = report.to_dict()
        assert "generated_at" in d
        assert "outcome_source" in d
        assert d["outcome_source"] == "event_driven_runtime"
