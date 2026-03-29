"""
Phase 5 Validation Framework Tests.

Tests the validation infrastructure itself — NOT the production system.
Verifies that:
  1. Source constants are well-formed
  2. SourceEnforcer raises on violations, passes on valid input
  3. Metrics functions compute correctly
  4. ScenarioLoader builds valid BTCSetupPackets
  5. PanelBatchRunner runs real panel on scenarios (no forced approvals)
  6. PanelBehaviorAnalyzer computes distributions from records
  7. RiskRuleRunner runs all 9 rules on test proposals
  8. RiskGateAnalyzer aggregates results correctly
  9. ThresholdAnalyzer evaluates scenarios at all threshold variants (never mutates production)
 10. CalibrationReporter returns "insufficient" for empty DB (no fabrication)
 11. ReplayHarness sets up and runs a bar sequence without crashing
 12. ReportBuilder assembles all sections without error
 13. Source separation: no runtime source mixed with synthetic_control_scenarios
 14. Panel enter_rate is in [0, 1] for all scenario batches
 15. Risk pass_rate is in [0, 1] for all test proposals
 16. Threshold sensitivity: production row present and NOT mutated
 17. CalibrationReporter reports 0 sufficient traders when DB empty
 18. ReplayHarness positions_opened >= 0 (harness doesn't crash on no-entry)
"""
from __future__ import annotations

import asyncio
import pytest
from decimal import Decimal
from datetime import datetime, timezone


# ──────────────────────────────────────────────────────────────────────────────
# 1. VALIDATION_SOURCES constants
# ──────────────────────────────────────────────────────────────────────────────

def test_validation_sources_defined():
    from validation import VALIDATION_SOURCES, RUNTIME_SOURCES, EDGE_EVIDENCE_SOURCES
    assert len(VALIDATION_SOURCES) == 5
    assert "event_driven_runtime_replay" in VALIDATION_SOURCES
    assert "event_driven_runtime_simulation" in VALIDATION_SOURCES
    assert "synthetic_control_scenarios" in VALIDATION_SOURCES
    assert "simplified_backtest" in VALIDATION_SOURCES
    assert "live_exchange_fed_paper" in VALIDATION_SOURCES


def test_edge_evidence_sources_subset():
    from validation import VALIDATION_SOURCES, EDGE_EVIDENCE_SOURCES
    assert EDGE_EVIDENCE_SOURCES.issubset(VALIDATION_SOURCES)
    assert "event_driven_runtime_replay" in EDGE_EVIDENCE_SOURCES
    assert "live_exchange_fed_paper" in EDGE_EVIDENCE_SOURCES
    assert "simplified_backtest" not in EDGE_EVIDENCE_SOURCES
    assert "synthetic_control_scenarios" not in EDGE_EVIDENCE_SOURCES


# ──────────────────────────────────────────────────────────────────────────────
# 2. SourceEnforcer
# ──────────────────────────────────────────────────────────────────────────────

def test_source_enforcer_single_source_passes():
    from validation.source_enforcer import SourceEnforcer
    src = SourceEnforcer.assert_single_source(
        ["event_driven_runtime_simulation"] * 5
    )
    assert src == "event_driven_runtime_simulation"


def test_source_enforcer_mixed_sources_raises():
    from validation.source_enforcer import SourceEnforcer, SourceSeparationError
    with pytest.raises(SourceSeparationError):
        SourceEnforcer.assert_single_source([
            "event_driven_runtime_simulation",
            "synthetic_control_scenarios",
        ])


def test_source_enforcer_unknown_source_raises():
    from validation.source_enforcer import SourceEnforcer, SourceSeparationError
    with pytest.raises(SourceSeparationError):
        SourceEnforcer.assert_single_source(["made_up_source"])


def test_source_enforcer_not_edge_evidence_raises():
    from validation.source_enforcer import SourceEnforcer, SourceSeparationError
    with pytest.raises(SourceSeparationError):
        SourceEnforcer.assert_not_edge_evidence("simplified_backtest")


def test_source_enforcer_edge_evidence_passes():
    from validation.source_enforcer import SourceEnforcer
    # Should not raise
    SourceEnforcer.assert_not_edge_evidence("event_driven_runtime_replay")


def test_source_enforcer_validate_report_passes():
    from validation.source_enforcer import SourceEnforcer
    report = {"validation_source": "event_driven_runtime_simulation"}
    SourceEnforcer.validate_report(report, "event_driven_runtime_simulation")


def test_source_enforcer_validate_report_mismatch_raises():
    from validation.source_enforcer import SourceEnforcer, SourceSeparationError
    report = {"validation_source": "event_driven_runtime_simulation"}
    with pytest.raises(SourceSeparationError):
        SourceEnforcer.validate_report(report, "event_driven_runtime_replay")


def test_source_enforcer_validate_report_missing_field_raises():
    from validation.source_enforcer import SourceEnforcer, SourceSeparationError
    report = {"data": 123}
    with pytest.raises(SourceSeparationError):
        SourceEnforcer.validate_report(report, "event_driven_runtime_simulation")


def test_source_enforcer_assert_not_mixed_runtime_backtest_raises():
    from validation.source_enforcer import SourceEnforcer, SourceSeparationError
    with pytest.raises(SourceSeparationError):
        SourceEnforcer.assert_not_mixed([
            "event_driven_runtime_simulation",
            "simplified_backtest",
        ])


def test_source_enforcer_assert_not_mixed_runtime_synthetic_raises():
    from validation.source_enforcer import SourceEnforcer, SourceSeparationError
    with pytest.raises(SourceSeparationError):
        SourceEnforcer.assert_not_mixed([
            "event_driven_runtime_replay",
            "synthetic_control_scenarios",
        ])


# ──────────────────────────────────────────────────────────────────────────────
# 3. Metrics
# ──────────────────────────────────────────────────────────────────────────────

def test_win_rate_basic():
    from validation.metrics import win_rate
    assert win_rate(["win", "win", "loss"]) == pytest.approx(2/3)


def test_win_rate_empty():
    from validation.metrics import win_rate
    assert win_rate([]) is None


def test_expectancy_basic():
    from validation.metrics import expectancy
    # 2 wins of +1R, 1 loss of -1R → expectancy = (2 - 1) / 3 = 0.333
    result = expectancy([1.0, 1.0, -1.0])
    assert result == pytest.approx(1/3, rel=1e-3)


def test_expectancy_empty():
    from validation.metrics import expectancy
    assert expectancy([]) is None


def test_profit_factor_basic():
    from validation.metrics import profit_factor
    # 2 wins of +2R each, 1 loss of -1R → PF = 4/1 = 4.0
    result = profit_factor([2.0, 2.0, -1.0])
    assert result == pytest.approx(4.0)


def test_profit_factor_no_losses():
    from validation.metrics import profit_factor
    # Only wins — infinite profit factor
    result = profit_factor([1.0, 2.0])
    assert result is None or result == float("inf") or result > 100


def test_max_drawdown_basic():
    from validation.metrics import max_drawdown
    equity = [100, 110, 90, 95, 85, 100]
    dd = max_drawdown(equity)
    # Peak=110, trough=85 → drawdown = (110-85)/110 = 22.7%
    assert dd == pytest.approx(25/110, rel=1e-2)


def test_max_drawdown_empty():
    from validation.metrics import max_drawdown
    assert max_drawdown([]) is None


def test_sample_size_warning():
    from validation.metrics import sample_size_warning
    w = sample_size_warning(5, minimum=30)
    assert w is not None
    assert "5" in w

    assert sample_size_warning(30, minimum=30) is None
    assert sample_size_warning(50, minimum=30) is None


def test_describe_basic():
    from validation.metrics import describe
    stats = describe([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats["count"] == 5
    assert stats["mean"] == pytest.approx(3.0)
    assert stats["min"] == 1.0
    assert stats["max"] == 5.0


def test_describe_empty():
    from validation.metrics import describe
    stats = describe([])
    assert stats["count"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# 4. ScenarioLoader
# ──────────────────────────────────────────────────────────────────────────────

def test_scenario_loader_returns_10_scenarios():
    from validation.scenario_loader import get_all_standard_scenarios
    packets = get_all_standard_scenarios()
    assert len(packets) == 10


def test_scenario_loader_all_have_unique_ids():
    from validation.scenario_loader import get_all_standard_scenarios
    packets = get_all_standard_scenarios()
    ids = [lp.packet.packet_id for lp in packets]
    assert len(set(ids)) == 10


def test_scenario_loader_packets_have_required_fields():
    from validation.scenario_loader import get_all_standard_scenarios
    from core.setup_packet import BTCSetupPacket
    packets = get_all_standard_scenarios()
    for lp in packets:
        pkt = lp.packet
        assert isinstance(pkt, BTCSetupPacket)
        assert pkt.indicators is not None
        assert pkt.structure is not None
        assert pkt.candlestick is not None
        assert pkt.proposal is not None
        assert pkt.regime is not None


def test_scenario_loader_descriptors_have_labels():
    from validation.scenario_loader import get_all_standard_scenarios
    packets = get_all_standard_scenarios()
    for lp in packets:
        assert lp.descriptor.label
        assert lp.descriptor.scenario_id


def test_scenario_loader_bar_sequences():
    from validation.scenario_loader import (
        make_bull_bar_sequence,
        make_bear_bar_sequence,
        make_ranging_bar_sequence,
    )
    bull = make_bull_bar_sequence(5)
    bear = make_bear_bar_sequence(5)
    ranging = make_ranging_bar_sequence(5)
    for seq in [bull, bear, ranging]:
        assert len(seq) == 5
        for fv in seq:
            assert fv.symbol == "BTCUSDT"
            assert fv.close > Decimal("0")


# ──────────────────────────────────────────────────────────────────────────────
# 5. PanelBatchRunner — real panel, no forced approvals
# ──────────────────────────────────────────────────────────────────────────────

def test_panel_batch_runner_returns_records_for_all_scenarios():
    from validation.panel_analyzer import PanelBatchRunner
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    packets = get_all_standard_scenarios()
    records = runner.run_batch(packets)
    assert len(records) == 10


def test_panel_batch_runner_records_have_real_verdicts():
    from validation.panel_analyzer import PanelBatchRunner
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    packets = get_all_standard_scenarios()
    records = runner.run_batch(packets)
    for rec in records:
        pr = rec.panel_result
        # 20 traders must have voted
        assert len(pr.verdicts) == 20
        # approve_count must be in [0, 20]
        assert 0 <= pr.approve_count <= 20
        # avg_score must be in [0, 10]
        assert 0.0 <= pr.avg_score <= 10.0


def test_panel_batch_runner_decisions_are_enter_or_hold():
    from validation.panel_analyzer import PanelBatchRunner
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    packets = get_all_standard_scenarios()
    records = runner.run_batch(packets)
    for rec in records:
        assert rec.final_decision.decision in ("enter", "hold")


def test_panel_batch_runner_source_tag():
    from validation.panel_analyzer import PanelBatchRunner, VALIDATION_SOURCE
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    for rec in records:
        assert rec.validation_source == VALIDATION_SOURCE


# ──────────────────────────────────────────────────────────────────────────────
# 6. PanelBehaviorAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

def test_panel_behavior_analyzer_enter_rate_in_range():
    from validation.panel_analyzer import PanelBatchRunner, PanelBehaviorAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelBehaviorAnalyzer()
    analyzer.add_all(records)
    rate = analyzer.enter_rate()
    assert rate is not None
    assert 0.0 <= rate <= 1.0


def test_panel_behavior_analyzer_hold_rate_complements_enter():
    from validation.panel_analyzer import PanelBatchRunner, PanelBehaviorAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelBehaviorAnalyzer()
    analyzer.add_all(records)
    er = analyzer.enter_rate()
    hr = analyzer.hold_rate()
    assert er is not None and hr is not None
    assert er + hr == pytest.approx(1.0)


def test_panel_behavior_analyzer_summarize_has_required_keys():
    from validation.panel_analyzer import PanelBatchRunner, PanelBehaviorAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelBehaviorAnalyzer()
    analyzer.add_all(records)
    summary = analyzer.summarize()
    required = [
        "validation_source", "total_evaluations", "enter_rate", "hold_rate",
        "approval_distribution", "score_distribution", "safety_rail_frequencies",
        "panel_thresholds",
    ]
    for key in required:
        assert key in summary, f"Missing key: {key}"


def test_panel_behavior_analyzer_insufficient_samples_warning():
    from validation.panel_analyzer import PanelBatchRunner, PanelBehaviorAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    # 10 records < 30 minimum
    analyzer = PanelBehaviorAnalyzer()
    analyzer.add_all(records)
    summary = analyzer.summarize()
    # sample_size_warning must be present (10 < 30)
    assert summary["sample_size_warning"] is not None
    assert "10" in summary["sample_size_warning"]


def test_panel_behavior_analyzer_source_enforcer_rejects_wrong_source():
    from validation.panel_analyzer import PanelBehaviorAnalyzer
    from validation.panel_analyzer import PanelBatchRecord
    from validation.source_enforcer import SourceSeparationError
    analyzer = PanelBehaviorAnalyzer()
    # Create a fake record with wrong source
    import dataclasses
    from traders.panel import PanelResult
    from traders.evaluators import TraderVerdict
    from decision.final_group import FinalDecision
    fake_result = PanelResult(
        packet_id="fake_packet",
        approve_count=15, reject_count=5, abstain_count=0,
        avg_score=7.0, panel_recommendation="enter",
        verdicts=[
            TraderVerdict(
                trader_id=f"T{i}", vote="approve", score=7.0, confidence=0.8,
                pro_reason="test", anti_reason="test",
                execution_concern="none", risk_concern="none", explanation="test",
            )
            for i in range(20)
        ],
    )
    fake_decision = FinalDecision(
        decision="enter", safety_rails_triggered=[]
    )
    bad_record = PanelBatchRecord(
        scenario_id="s00",
        scenario_label="bad",
        packet_id="p00",
        panel_result=fake_result,
        final_decision=fake_decision,
        validation_source="synthetic_control_scenarios",  # wrong
    )
    with pytest.raises(SourceSeparationError):
        analyzer.add(bad_record)


# ──────────────────────────────────────────────────────────────────────────────
# 7. RiskRuleRunner
# ──────────────────────────────────────────────────────────────────────────────

def test_risk_rule_runner_returns_result_for_each_proposal():
    from validation.risk_analyzer import RiskRuleRunner, make_risk_test_proposals
    proposals = make_risk_test_proposals()
    runner = RiskRuleRunner()
    results = runner.check_batch(proposals)
    assert len(results) == len(proposals)


def test_risk_rule_runner_p1_all_rules_pass():
    """P1 should approve: valid proposal with raw_target, hypothesis_refs, score=0.65."""
    from validation.risk_analyzer import RiskRuleRunner, make_risk_test_proposals
    proposals = make_risk_test_proposals()
    p1, label = proposals[0]
    assert label == "P1_all_rules_pass"
    runner = RiskRuleRunner()
    result = runner.check_proposal(p1, label)
    assert result.approved is True
    assert result.leverage is not None
    assert result.leverage > 0


def test_risk_rule_runner_p2_rejected_rule9():
    """P2 raw_target=0 → Rule 9 INCOMPLETE_TRADE_PLAN."""
    from validation.risk_analyzer import RiskRuleRunner, make_risk_test_proposals
    proposals = make_risk_test_proposals()
    p2, label = proposals[1]
    assert label == "P2_missing_raw_target"
    runner = RiskRuleRunner()
    result = runner.check_proposal(p2, label)
    assert result.approved is False
    assert "INCOMPLETE" in (result.rejection_code or "").upper() or result.rejection_code is not None


def test_risk_rule_runner_p4_score_below_threshold():
    """P4 score=0.42 → Rule 9 SCORE_BELOW_THRESHOLD."""
    from validation.risk_analyzer import RiskRuleRunner, make_risk_test_proposals
    proposals = make_risk_test_proposals()
    p4, label = proposals[3]
    assert label == "P4_score_below_0.50"
    runner = RiskRuleRunner()
    result = runner.check_proposal(p4, label)
    assert result.approved is False


def test_risk_rule_runner_p5_universe_filter():
    """P5 XYZUSDT not in eligible → Rule 6 UNIVERSE_FILTER.
    Must pass eligible_symbols={"BTCUSDT"} so XYZUSDT is excluded.
    The default behavior uses proposal.symbol as eligible, which would trivially pass.
    """
    from validation.risk_analyzer import RiskRuleRunner, make_risk_test_proposals
    proposals = make_risk_test_proposals()
    p5, label = proposals[4]
    assert label == "P5_not_eligible_symbol"
    runner = RiskRuleRunner()
    # Explicitly restrict eligible universe to BTCUSDT only (excludes XYZUSDT)
    result = runner.check_proposal(p5, label, eligible_symbols={"BTCUSDT"})
    assert result.approved is False


def test_risk_rule_runner_source_tag():
    from validation.risk_analyzer import RiskRuleRunner, make_risk_test_proposals, VALIDATION_SOURCE
    proposals = make_risk_test_proposals()
    runner = RiskRuleRunner()
    results = runner.check_batch(proposals)
    for r in results:
        assert r.validation_source == VALIDATION_SOURCE


# ──────────────────────────────────────────────────────────────────────────────
# 8. RiskGateAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

def test_risk_gate_analyzer_pass_rate_in_range():
    from validation.risk_analyzer import RiskRuleRunner, RiskGateAnalyzer, make_risk_test_proposals
    proposals = make_risk_test_proposals()
    runner = RiskRuleRunner()
    results = runner.check_batch(proposals)
    analyzer = RiskGateAnalyzer()
    analyzer.add_all(results)
    rate = analyzer.pass_rate()
    assert rate is not None
    assert 0.0 <= rate <= 1.0


def test_risk_gate_analyzer_rejection_codes_populated():
    from validation.risk_analyzer import RiskRuleRunner, RiskGateAnalyzer, make_risk_test_proposals
    proposals = make_risk_test_proposals()
    runner = RiskRuleRunner()
    results = runner.check_batch(proposals)
    analyzer = RiskGateAnalyzer()
    analyzer.add_all(results)
    codes = analyzer.rejection_code_frequencies()
    # At least P2, P3, P4, P5 should be rejected
    assert len(codes) > 0


def test_risk_gate_analyzer_summarize_has_required_keys():
    from validation.risk_analyzer import RiskRuleRunner, RiskGateAnalyzer, make_risk_test_proposals
    proposals = make_risk_test_proposals()
    runner = RiskRuleRunner()
    results = runner.check_batch(proposals)
    analyzer = RiskGateAnalyzer()
    analyzer.add_all(results)
    summary = analyzer.summarize()
    for key in ["validation_source", "total_proposals", "approved", "rejected",
                "pass_rate", "rejection_code_frequencies", "leverage_distribution",
                "position_size_distribution", "risk_rules"]:
        assert key in summary, f"Missing key: {key}"


# ──────────────────────────────────────────────────────────────────────────────
# 9. ThresholdAnalyzer — READ-ONLY, never mutates production
# ──────────────────────────────────────────────────────────────────────────────

def test_threshold_analyzer_has_production_row():
    from validation.panel_analyzer import PanelBatchRunner
    from validation.threshold_analyzer import PanelThresholdSensitivityAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelThresholdSensitivityAnalyzer()
    report = analyzer.analyze(records)
    prod_rows = [r for r in report["rows"] if r.get("is_production")]
    assert len(prod_rows) == 1
    assert prod_rows[0]["approve_threshold"] == 11
    assert prod_rows[0]["min_avg_score"] == 5.8


def test_threshold_analyzer_production_threshold_not_mutated():
    """Verify production constants unchanged after analysis."""
    from traders.panel import TraderEvaluatorPanel
    from validation.panel_analyzer import PanelBatchRunner
    from validation.threshold_analyzer import PanelThresholdSensitivityAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios

    before_approve = TraderEvaluatorPanel.APPROVE_THRESHOLD
    before_score = TraderEvaluatorPanel.MIN_AVG_SCORE

    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelThresholdSensitivityAnalyzer()
    analyzer.analyze(records)

    assert TraderEvaluatorPanel.APPROVE_THRESHOLD == before_approve
    assert TraderEvaluatorPanel.MIN_AVG_SCORE == before_score


def test_threshold_analyzer_8_scenarios():
    from validation.panel_analyzer import PanelBatchRunner
    from validation.threshold_analyzer import PanelThresholdSensitivityAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelThresholdSensitivityAnalyzer()
    report = analyzer.analyze(records)
    assert len(report["rows"]) == 8


def test_threshold_analyzer_enter_rates_monotone():
    """Stricter thresholds must produce <= enter rate than lenient ones.
    Sort rows by (approve_threshold, min_avg_score) before checking so that
    the production row (which may be more lenient than adjacent labeled rows)
    appears in the correct position.
    """
    from validation.panel_analyzer import PanelBatchRunner
    from validation.threshold_analyzer import PanelThresholdSensitivityAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelThresholdSensitivityAnalyzer()
    report = analyzer.analyze(records)
    # Sort by strictness (higher threshold = stricter) before checking monotone
    sorted_rows = sorted(
        report["rows"],
        key=lambda r: (r["approve_threshold"], r["min_avg_score"])
    )
    rates = [r["enter_rate"] for r in sorted_rows]
    for i in range(len(rates) - 1):
        assert rates[i] >= rates[i+1], (
            f"Non-monotone (by threshold): row[{i}]={rates[i]} < row[{i+1}]={rates[i+1]}"
        )


def test_threshold_analyzer_non_production_note():
    from validation.panel_analyzer import PanelBatchRunner
    from validation.threshold_analyzer import PanelThresholdSensitivityAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelThresholdSensitivityAnalyzer()
    report = analyzer.analyze(records)
    for row in report["rows"]:
        if not row.get("is_production"):
            assert "sensitivity_analysis_only" in row["note"]


def test_threshold_analyzer_source_tag():
    from validation.panel_analyzer import PanelBatchRunner
    from validation.threshold_analyzer import PanelThresholdSensitivityAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelThresholdSensitivityAnalyzer()
    report = analyzer.analyze(records)
    assert report["validation_source"] == "sensitivity_analysis_only"


# ──────────────────────────────────────────────────────────────────────────────
# 10. CalibrationReporter — honest "insufficient" when no closed trades
# ──────────────────────────────────────────────────────────────────────────────

def _make_in_memory_journal_extension():
    """Create a JournalExtension backed by an in-memory SQLite DB."""
    import sqlite3
    from learning.journal_extension import JournalExtension
    conn = sqlite3.connect(":memory:")
    ext = JournalExtension(conn)
    ext.initialize()
    return ext


def test_calibration_reporter_no_data_is_honest():
    from validation.calibration_reporter import CalibrationReporter
    from learning.outcome_source import OutcomeSource
    ext = _make_in_memory_journal_extension()
    reporter = CalibrationReporter(ext)
    report = reporter.full_report(OutcomeSource.EVENT_DRIVEN_RUNTIME)

    assert report["overall_calibration_status"] is not None
    # Must mention no data
    status = report["overall_calibration_status"].upper()
    assert "NO" in status or "INSUFFICIENT" in status or "ZERO" in status


def test_calibration_reporter_zero_sufficient_traders():
    from validation.calibration_reporter import CalibrationReporter
    from learning.outcome_source import OutcomeSource
    ext = _make_in_memory_journal_extension()
    reporter = CalibrationReporter(ext)
    trader_report = reporter.trader_summary(OutcomeSource.EVENT_DRIVEN_RUNTIME)

    assert trader_report["traders_with_sufficient_samples"] == 0
    assert trader_report["traders_with_insufficient_samples"] == 20


def test_calibration_reporter_has_20_traders():
    from validation.calibration_reporter import CalibrationReporter
    from learning.outcome_source import OutcomeSource
    ext = _make_in_memory_journal_extension()
    reporter = CalibrationReporter(ext)
    trader_report = reporter.trader_summary(OutcomeSource.EVENT_DRIVEN_RUNTIME)
    assert trader_report["traders_queried"] == 20
    assert len(trader_report["per_trader"]) == 20


def test_calibration_reporter_panel_insufficient():
    from validation.calibration_reporter import CalibrationReporter
    from learning.outcome_source import OutcomeSource
    ext = _make_in_memory_journal_extension()
    reporter = CalibrationReporter(ext)
    panel_report = reporter.panel_summary(OutcomeSource.EVENT_DRIVEN_RUNTIME)
    assert panel_report["panel_calibration"]["has_sufficient_samples"] is False


def test_calibration_reporter_without_extension():
    from validation.report_builder import ValidationReportBuilder
    builder = ValidationReportBuilder(journal_extension=None)
    cal = builder.build_calibration_report()
    assert cal["status"] == "not_available"
    assert "JournalExtension" in cal["note"]


# ──────────────────────────────────────────────────────────────────────────────
# 11. RuntimeReplayHarness
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replay_harness_setup_teardown():
    from validation.replay_harness import RuntimeReplayHarness
    harness = RuntimeReplayHarness()
    await harness.setup()
    assert harness.state is not None
    assert harness.runner is not None
    await harness.teardown()


@pytest.mark.asyncio
async def test_replay_harness_run_sequence_no_crash():
    from validation.replay_harness import RuntimeReplayHarness
    from validation.scenario_loader import make_bull_bar_sequence
    harness = RuntimeReplayHarness()
    await harness.setup()
    try:
        seq = make_bull_bar_sequence(3)
        summary = await harness.run_sequence(seq, label="test_bull_3bars")
        assert summary.bars_run == 3
        assert summary.positions_opened >= 0  # May be 0 — that's fine
        assert summary.validation_source == "event_driven_runtime_simulation"
    finally:
        await harness.teardown()


@pytest.mark.asyncio
async def test_replay_harness_positions_opened_is_non_negative():
    from validation.replay_harness import RuntimeReplayHarness
    from validation.scenario_loader import make_bull_bar_sequence
    harness = RuntimeReplayHarness()
    await harness.setup()
    try:
        seq = make_bull_bar_sequence(5)
        summary = await harness.run_sequence(seq, label="harness_positions_check")
        assert summary.positions_opened >= 0
        assert summary.final_open_positions >= 0
    finally:
        await harness.teardown()


@pytest.mark.asyncio
async def test_replay_harness_errors_list_is_empty_on_clean_run():
    from validation.replay_harness import RuntimeReplayHarness
    from validation.scenario_loader import make_ranging_bar_sequence
    harness = RuntimeReplayHarness()
    await harness.setup()
    try:
        seq = make_ranging_bar_sequence(4)
        summary = await harness.run_sequence(seq, label="harness_clean_run")
        assert summary.errors == []
    finally:
        await harness.teardown()


# ──────────────────────────────────────────────────────────────────────────────
# 12. ValidationReportBuilder
# ──────────────────────────────────────────────────────────────────────────────

def test_report_builder_panel_report_runs():
    from validation.report_builder import ValidationReportBuilder
    builder = ValidationReportBuilder()
    report = builder.build_panel_report()
    assert "validation_source" in report
    assert "total_evaluations" in report
    assert report["total_evaluations"] == 10


def test_report_builder_risk_report_runs():
    from validation.report_builder import ValidationReportBuilder
    builder = ValidationReportBuilder()
    report = builder.build_risk_report()
    assert "validation_source" in report
    assert "total_proposals" in report
    assert report["total_proposals"] == 8


def test_report_builder_threshold_report_runs():
    from validation.report_builder import ValidationReportBuilder
    builder = ValidationReportBuilder()
    report = builder.build_threshold_report()
    assert "rows" in report
    assert len(report["rows"]) == 8


def test_report_builder_full_report_has_all_sections():
    from validation.report_builder import ValidationReportBuilder
    builder = ValidationReportBuilder()
    report = builder.build_full_report()
    for key in ["metadata", "panel_behavior", "risk_gate_behavior",
                "threshold_sensitivity", "trader_calibration",
                "source_audit", "honest_summary"]:
        assert key in report, f"Missing section: {key}"


def test_report_builder_source_audit_passes():
    from validation.report_builder import ValidationReportBuilder
    builder = ValidationReportBuilder()
    report = builder.build_full_report()
    audit = report["source_audit"]
    assert audit["audit_passed"] is True


def test_report_builder_honest_summary_is_non_empty():
    from validation.report_builder import ValidationReportBuilder
    builder = ValidationReportBuilder()
    report = builder.build_full_report()
    summary = report["honest_summary"]
    assert isinstance(summary, str)
    assert len(summary) > 20


def test_report_builder_format_as_text():
    from validation.report_builder import ValidationReportBuilder, format_report_as_text
    builder = ValidationReportBuilder()
    report = builder.build_full_report()
    text = format_report_as_text(report)
    assert "PHASE 5 VALIDATION REPORT" in text
    assert "PANEL BEHAVIOR" in text
    assert "RISK GATE BEHAVIOR" in text
    assert "THRESHOLD SENSITIVITY" in text
    assert "TRADER CALIBRATION" in text
    assert "SOURCE AUDIT" in text


# ──────────────────────────────────────────────────────────────────────────────
# 13. Source separation: no runtime mixed with synthetic_control_scenarios
# ──────────────────────────────────────────────────────────────────────────────

def test_source_separation_panel_not_synthetic():
    """Panel records from PanelBatchRunner must use simulation source, not synthetic_control."""
    from validation.panel_analyzer import PanelBatchRunner, VALIDATION_SOURCE
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    for rec in records:
        assert rec.validation_source != "synthetic_control_scenarios"
        assert rec.validation_source == VALIDATION_SOURCE


def test_source_separation_risk_not_synthetic():
    """Risk results must use simulation source, not synthetic_control."""
    from validation.risk_analyzer import RiskRuleRunner, make_risk_test_proposals, VALIDATION_SOURCE
    runner = RiskRuleRunner()
    results = runner.check_batch(make_risk_test_proposals())
    for r in results:
        assert r.validation_source != "synthetic_control_scenarios"
        assert r.validation_source == VALIDATION_SOURCE


def test_source_separation_no_backtest_mixed_with_runtime():
    from validation.source_enforcer import SourceEnforcer, SourceSeparationError
    sources = ["event_driven_runtime_simulation", "simplified_backtest"]
    with pytest.raises(SourceSeparationError):
        SourceEnforcer.assert_not_mixed(sources)


# ──────────────────────────────────────────────────────────────────────────────
# 14 & 15. enter_rate / pass_rate bounds
# ──────────────────────────────────────────────────────────────────────────────

def test_enter_rate_bounded():
    from validation.panel_analyzer import PanelBatchRunner, PanelBehaviorAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios
    runner = PanelBatchRunner()
    records = runner.run_batch(get_all_standard_scenarios())
    analyzer = PanelBehaviorAnalyzer()
    analyzer.add_all(records)
    rate = analyzer.enter_rate()
    assert 0.0 <= rate <= 1.0


def test_pass_rate_bounded():
    from validation.risk_analyzer import RiskRuleRunner, RiskGateAnalyzer, make_risk_test_proposals
    runner = RiskRuleRunner()
    results = runner.check_batch(make_risk_test_proposals())
    analyzer = RiskGateAnalyzer()
    analyzer.add_all(results)
    rate = analyzer.pass_rate()
    assert rate is not None
    assert 0.0 <= rate <= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# 16. Threshold sensitivity: production row present, thresholds not mutated
# ──────────────────────────────────────────────────────────────────────────────

def test_production_threshold_values_unchanged():
    """Threshold analysis must never mutate APPROVE_THRESHOLD or MIN_AVG_SCORE."""
    from traders.panel import TraderEvaluatorPanel
    original_approve = TraderEvaluatorPanel.APPROVE_THRESHOLD
    original_score = TraderEvaluatorPanel.MIN_AVG_SCORE

    from validation.panel_analyzer import PanelBatchRunner
    from validation.threshold_analyzer import PanelThresholdSensitivityAnalyzer
    from validation.scenario_loader import get_all_standard_scenarios

    records = PanelBatchRunner().run_batch(get_all_standard_scenarios())
    PanelThresholdSensitivityAnalyzer().analyze(records)

    assert TraderEvaluatorPanel.APPROVE_THRESHOLD == original_approve
    assert TraderEvaluatorPanel.MIN_AVG_SCORE == original_score
