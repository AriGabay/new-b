"""
ValidationReportBuilder — collects all validation results into one structured report.

Runs the full validation suite and produces a human-readable, machine-parseable
report dict covering:
  1. Panel behavior (real panel + decision, no forced approvals)
  2. Risk gate behavior (rejection codes + pass rate)
  3. Threshold sensitivity (READ-ONLY, no production mutation)
  4. Calibration status (honest: likely all "insufficient samples")
  5. Source separation audit (proves no silent mixing)

Usage:
    builder = ValidationReportBuilder()
    report = await builder.build_full_report()
    print(report["honest_summary"])

CRITICAL: This builder never fabricates data. If metrics are unavailable
(e.g., zero closed trades), it says so explicitly.

Source: event_driven_runtime_simulation for panel/risk runs.
        sensitivity_analysis_only for threshold variations.
        CalibrationReporter reads from event_driven_runtime DB records.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from validation.panel_analyzer import PanelBatchRunner, PanelBehaviorAnalyzer
from validation.risk_analyzer import RiskRuleRunner, RiskGateAnalyzer, make_risk_test_proposals
from validation.threshold_analyzer import PanelThresholdSensitivityAnalyzer
from validation.source_enforcer import SourceEnforcer
from validation.scenario_loader import get_all_standard_scenarios

logger = logging.getLogger(__name__)

VALIDATION_SOURCE = "event_driven_runtime_simulation"


class ValidationReportBuilder:
    """
    Runs the full validation suite and assembles results.

    Can run with or without a JournalExtension (calibration requires one).
    Panel and risk analysis run entirely from in-memory scenario evaluation.

    Args:
        journal_extension: Optional JournalExtension for calibration reporting.
                           If None, calibration section reports "not available."
    """

    def __init__(self, journal_extension=None) -> None:
        self._journal_extension = journal_extension

    def build_panel_report(self) -> dict:
        """
        Run all 10 standard scenarios through the real panel + decision group.
        Returns PanelBehaviorAnalyzer summary.
        """
        logger.info("ValidationReportBuilder: running panel analysis...")
        labelled_packets = get_all_standard_scenarios()
        runner = PanelBatchRunner()
        records = runner.run_batch(labelled_packets)

        analyzer = PanelBehaviorAnalyzer()
        analyzer.add_all(records)
        summary = analyzer.summarize()

        logger.info(
            "Panel report: %d evaluations, enter_rate=%.1f%%",
            summary["total_evaluations"],
            (summary["enter_rate"] or 0) * 100,
        )
        return summary

    def build_risk_report(self) -> dict:
        """
        Run the standard 8-proposal test suite through the real risk rule chain.
        Returns RiskGateAnalyzer summary.
        """
        logger.info("ValidationReportBuilder: running risk gate analysis...")
        proposals = make_risk_test_proposals()
        runner = RiskRuleRunner()
        results = runner.check_batch(proposals)

        analyzer = RiskGateAnalyzer()
        analyzer.add_all(results)
        summary = analyzer.summarize()

        logger.info(
            "Risk report: %d proposals, pass_rate=%.1f%%",
            summary["total_proposals"],
            (summary["pass_rate"] or 0) * 100,
        )
        return summary

    def build_threshold_report(self, panel_records: Optional[list] = None) -> dict:
        """
        Run threshold sensitivity analysis on panel records.

        If panel_records is None, runs the standard 10 scenarios first.
        NEVER mutates production thresholds.
        """
        logger.info("ValidationReportBuilder: running threshold sensitivity analysis...")
        if panel_records is None:
            labelled_packets = get_all_standard_scenarios()
            runner = PanelBatchRunner()
            panel_records = runner.run_batch(labelled_packets)

        analyzer = PanelThresholdSensitivityAnalyzer()
        report = analyzer.analyze(panel_records)

        logger.info(
            "Threshold report: %d panel records evaluated across %d threshold scenarios.",
            len(panel_records),
            len(report.get("rows", [])),
        )
        return report

    def build_calibration_report(self) -> dict:
        """
        Return calibration status from the journal DB.
        Honest: reports "no data" if journal_extension not provided or no closed trades.
        """
        if self._journal_extension is None:
            return {
                "validation_source": VALIDATION_SOURCE,
                "status": "not_available",
                "note": (
                    "No JournalExtension provided to ValidationReportBuilder. "
                    "Calibration reporting requires a live journal DB connection. "
                    "Pass journal_extension= when constructing ValidationReportBuilder."
                ),
            }

        try:
            from validation.calibration_reporter import CalibrationReporter
            from learning.outcome_source import OutcomeSource
            reporter = CalibrationReporter(self._journal_extension)
            report = reporter.full_report(OutcomeSource.EVENT_DRIVEN_RUNTIME)
            logger.info(
                "Calibration report: %s",
                report.get("overall_calibration_status", "unknown"),
            )
            return report
        except Exception as exc:
            logger.error("Calibration report failed: %s", exc)
            return {
                "validation_source": VALIDATION_SOURCE,
                "status": "error",
                "error": str(exc),
            }

    def build_source_audit(
        self,
        panel_summary: dict,
        risk_summary: dict,
        threshold_summary: dict,
        calibration_summary: dict,
    ) -> dict:
        """
        Audit source separation across all sub-reports.
        Returns proof that no sources were mixed.
        """
        sources_seen = set()

        if "validation_source" in panel_summary:
            sources_seen.add(panel_summary["validation_source"])
        if "validation_source" in risk_summary:
            sources_seen.add(risk_summary["validation_source"])
        if "validation_source" in threshold_summary:
            sources_seen.add(threshold_summary["validation_source"])
        if "validation_source" in calibration_summary:
            sources_seen.add(calibration_summary["validation_source"])

        # Threshold uses "sensitivity_analysis_only" which is a separate category
        runtime_sources = sources_seen - {"sensitivity_analysis_only", "not_available", "error"}

        mixing_detected = False
        mixing_detail = ""
        if len(runtime_sources) > 1:
            mixing_detected = True
            mixing_detail = f"Multiple runtime sources detected: {sorted(runtime_sources)}"

        return {
            "sources_in_report": sorted(sources_seen),
            "runtime_sources": sorted(runtime_sources),
            "mixing_detected": mixing_detected,
            "mixing_detail": mixing_detail,
            "audit_passed": not mixing_detected,
            "note": (
                "Source audit checks that panel/risk/calibration sections "
                "all carry the same validation_source tag. Threshold analysis uses "
                "'sensitivity_analysis_only' (not a runtime source — intentional)."
            ),
        }

    def build_full_report(self) -> dict:
        """
        Run the complete validation suite and assemble all results.

        Returns a single dict with sections:
          - metadata
          - panel_behavior
          - risk_gate_behavior
          - threshold_sensitivity
          - trader_calibration
          - source_audit
          - honest_summary

        No fabrication. If data is missing, says so.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info("ValidationReportBuilder: building full report at %s", timestamp)

        # Run all sections
        panel = self.build_panel_report()
        risk = self.build_risk_report()
        threshold = self.build_threshold_report()
        calibration = self.build_calibration_report()
        source_audit = self.build_source_audit(panel, risk, threshold, calibration)

        # Derive honest summary
        honest_summary = self._derive_honest_summary(panel, risk, threshold, calibration)

        report = {
            "metadata": {
                "generated_at": timestamp,
                "validation_framework_version": "phase_5",
                "validation_source": VALIDATION_SOURCE,
                "WARNING": (
                    "This report uses synthetic BTCSetupPacket scenarios through the "
                    "real pipeline. Panel enter/hold rates reflect threshold selectivity "
                    "on these specific scenarios, NOT real market performance. "
                    "No edge conclusions should be drawn from this data."
                ),
            },
            "panel_behavior": panel,
            "risk_gate_behavior": risk,
            "threshold_sensitivity": threshold,
            "trader_calibration": calibration,
            "source_audit": source_audit,
            "honest_summary": honest_summary,
        }

        logger.info(
            "ValidationReportBuilder: full report complete. "
            "panel=%d evals, risk=%d proposals, threshold=%d scenarios, "
            "calibration=%s, source_audit=%s",
            panel.get("total_evaluations", 0),
            risk.get("total_proposals", 0),
            len(threshold.get("rows", [])),
            calibration.get("status", "present"),
            "PASS" if source_audit["audit_passed"] else "FAIL",
        )
        return report

    @staticmethod
    def _derive_honest_summary(
        panel: dict,
        risk: dict,
        threshold: dict,
        calibration: dict,
    ) -> str:
        """
        Write an honest, factual summary of validation results.
        No spin. No false positives. No fabricated confidence.
        """
        lines = []

        # Panel
        n = panel.get("total_evaluations", 0)
        enter_rate = panel.get("enter_rate")
        panel_warning = panel.get("sample_size_warning")
        if panel_warning:
            lines.append(f"PANEL: {panel_warning}")
        else:
            lines.append(
                f"PANEL: {n} scenarios evaluated. "
                f"Enter rate: {enter_rate:.1%}" if enter_rate is not None
                else f"PANEL: {n} scenarios evaluated. Enter rate: N/A"
            )

        # Risk
        total_props = risk.get("total_proposals", 0)
        pass_rate = risk.get("pass_rate")
        rej_codes = risk.get("rejection_code_frequencies", {})
        lines.append(
            f"RISK GATES: {total_props} proposals tested. "
            f"Pass rate: {pass_rate:.1%}" if pass_rate is not None
            else f"RISK GATES: {total_props} proposals. Pass rate: N/A"
        )
        if rej_codes:
            lines.append(f"  Rejection codes: {rej_codes}")

        # Threshold
        prod_row = next(
            (r for r in threshold.get("rows", []) if r.get("is_production")), None
        )
        if prod_row:
            lines.append(
                f"THRESHOLD SENSITIVITY: Production (14/6.5) → "
                f"{prod_row['enter_count']}/{prod_row.get('enter_count', 0) + prod_row.get('hold_count', 0)} "
                f"enter ({prod_row['enter_rate']:.1%}). "
                f"See threshold_sensitivity.rows for full spectrum."
            )

        # Calibration
        cal_status = calibration.get("overall_calibration_status") or calibration.get(
            "note", calibration.get("status", "unknown")
        )
        lines.append(f"CALIBRATION: {cal_status}")

        lines.append(
            "IMPORTANT: These results use synthetic scenarios. "
            "No edge conclusions are valid from this data. "
            "Edge evidence requires event_driven_runtime_replay or live_exchange_fed_paper."
        )

        return "\n".join(lines)


def format_report_as_text(report: dict) -> str:
    """
    Format the full validation report as human-readable text.
    Suitable for writing to a docs file or printing to console.
    """
    lines = []
    lines.append("=" * 72)
    lines.append("PHASE 5 VALIDATION REPORT")
    lines.append(f"Generated: {report.get('metadata', {}).get('generated_at', 'unknown')}")
    lines.append("=" * 72)

    lines.append("")
    lines.append("HONEST SUMMARY")
    lines.append("-" * 40)
    lines.append(report.get("honest_summary", "No summary available."))

    lines.append("")
    lines.append("PANEL BEHAVIOR")
    lines.append("-" * 40)
    panel = report.get("panel_behavior", {})
    lines.append(f"Total evaluations: {panel.get('total_evaluations', 0)}")
    lines.append(f"Enter rate:        {panel.get('enter_rate', 'N/A')}")
    lines.append(f"Hold rate:         {panel.get('hold_rate', 'N/A')}")
    if panel.get("sample_size_warning"):
        lines.append(f"WARNING: {panel['sample_size_warning']}")
    rail_freqs = panel.get("safety_rail_frequencies", {})
    if rail_freqs.get("rail_counts"):
        lines.append(f"Safety rails: {rail_freqs['rail_counts']}")

    lines.append("")
    lines.append("RISK GATE BEHAVIOR")
    lines.append("-" * 40)
    risk = report.get("risk_gate_behavior", {})
    lines.append(f"Total proposals: {risk.get('total_proposals', 0)}")
    lines.append(f"Approved:        {risk.get('approved', 0)}")
    lines.append(f"Rejected:        {risk.get('rejected', 0)}")
    lines.append(f"Pass rate:       {risk.get('pass_rate', 'N/A')}")
    rej_codes = risk.get("rejection_code_frequencies", {})
    if rej_codes:
        lines.append(f"Rejection codes: {rej_codes}")
    lev = risk.get("leverage_distribution", {}).get("stats", {})
    if lev:
        lines.append(f"Leverage stats: mean={lev.get('mean', 'N/A')}, "
                     f"min={lev.get('min', 'N/A')}, max={lev.get('max', 'N/A')}")

    lines.append("")
    lines.append("THRESHOLD SENSITIVITY (READ-ONLY — production NOT mutated)")
    lines.append("-" * 40)
    thresh = report.get("threshold_sensitivity", {})
    for row in thresh.get("rows", []):
        prod_marker = " ← PRODUCTION" if row.get("is_production") else ""
        lines.append(
            f"  {row.get('label', '?'):<30} "
            f"enter={row.get('enter_count', 0)}/{thresh.get('total_panel_evaluations', 0)} "
            f"({row.get('enter_rate', 0):.1%}){prod_marker}"
        )

    lines.append("")
    lines.append("TRADER CALIBRATION")
    lines.append("-" * 40)
    cal = report.get("trader_calibration", {})
    if cal.get("status") == "not_available":
        lines.append(f"NOT AVAILABLE: {cal.get('note', '')}")
    else:
        lines.append(cal.get("overall_calibration_status", "Unknown status."))
        trader_cal = cal.get("trader_calibration", {})
        lines.append(
            f"  Traders with sufficient samples: "
            f"{trader_cal.get('traders_with_sufficient_samples', 0)}/20"
        )

    lines.append("")
    lines.append("SOURCE AUDIT")
    lines.append("-" * 40)
    audit = report.get("source_audit", {})
    result = "PASS" if audit.get("audit_passed") else "FAIL"
    lines.append(f"Result: {result}")
    lines.append(f"Sources: {audit.get('sources_in_report', [])}")
    if audit.get("mixing_detail"):
        lines.append(f"MIXING DETECTED: {audit['mixing_detail']}")

    lines.append("")
    lines.append("=" * 72)
    lines.append("END OF REPORT")
    lines.append("=" * 72)

    return "\n".join(lines)
