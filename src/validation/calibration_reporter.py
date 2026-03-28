"""
CalibrationReporter — wraps TraderCalibrator and PanelCalibrator for validation.

CRITICAL RULES:
  1. No conclusions before MIN_SAMPLES = 30. Returns explicit "insufficient" notice.
  2. All results segmented by OutcomeSource. Never mix.
  3. Reports are READ-ONLY — never mutates calibration records.
  4. Honest about current state: with zero closed trades, all metrics are None.

This reporter is used in validation runs to describe what calibration data
exists (or doesn't yet exist) in the journal DB.

Source: This reporter reads from the DB written by event_driven_runtime runs.
"""
from __future__ import annotations

import logging
from typing import Optional

from learning.calibration import TraderCalibrator, PanelCalibrator, MIN_SAMPLES
from learning.journal_extension import JournalExtension
from learning.outcome_source import OutcomeSource

logger = logging.getLogger(__name__)

VALIDATION_SOURCE = "event_driven_runtime_simulation"

# Canonical 20 trader evaluator names — must match TraderEvaluatorPanel internals
KNOWN_TRADER_NAMES = [
    "TrendFollower",
    "MeanReversionTrader",
    "BreakoutSpecialist",
    "ValueInvestor",
    "MomentumTrader",
    "RiskArbTrader",
    "SwingTrader",
    "ScalpingTrader",
    "MacroTrader",
    "QuantTrader",
    "SentimentTrader",
    "TechnicalAnalyst",
    "FundamentalAnalyst",
    "PatternRecognizer",
    "VolumeAnalyst",
    "OrderFlowTrader",
    "RegimeSwitcher",
    "VolatilityTrader",
    "ContraryEvaluator",
    "CycleTrader",
]


class CalibrationReporter:
    """
    Read-only reporter for trader and panel calibration state.

    Wraps TraderCalibrator.get_calibration_summary() and
    PanelCalibrator.compute_panel_stats() with:
      - MIN_SAMPLES gating (no conclusions before 30 samples)
      - explicit "insufficient samples" messaging
      - source separation enforcement

    With zero closed trades (current system state), all outcome-dependent
    metrics will be None. This is correct and expected behaviour.
    """

    def __init__(self, extension: JournalExtension) -> None:
        self._ext = extension
        self._trader_calibrator = TraderCalibrator(extension)
        self._panel_calibrator = PanelCalibrator(extension)

    def trader_summary(
        self,
        outcome_source: OutcomeSource = OutcomeSource.EVENT_DRIVEN_RUNTIME,
        trader_names: Optional[list[str]] = None,
    ) -> dict:
        """
        Return calibration summary for each trader evaluator.

        Args:
            outcome_source: Which source to query. Defaults to EVENT_DRIVEN_RUNTIME.
            trader_names: Explicit list of names to query. Defaults to all 20.

        Returns dict with:
          - per_trader: dict keyed by trader_name
          - traders_with_sufficient_samples: count
          - traders_with_insufficient_samples: count
          - honest_status: human-readable current state

        NOTE: With zero closed trades, all traders will have 0 reviews and
        no metrics. This is reported honestly, not fabricated.
        """
        names = trader_names or KNOWN_TRADER_NAMES
        per_trader = {}
        sufficient_count = 0
        insufficient_count = 0

        for name in names:
            summary = self._trader_calibrator.get_calibration_summary(name, outcome_source)
            if summary.get("error"):
                per_trader[name] = {
                    "status": "no_data",
                    "total_reviews": 0,
                    "has_sufficient_samples": False,
                    "note": f"No calibration record found for {name}. Zero closed trades.",
                }
                insufficient_count += 1
            else:
                per_trader[name] = summary
                if summary.get("has_sufficient_samples"):
                    sufficient_count += 1
                else:
                    insufficient_count += 1

        total = len(names)
        if sufficient_count == 0:
            honest_status = (
                f"INSUFFICIENT DATA: 0/{total} traders have ≥{MIN_SAMPLES} reviews. "
                "This is expected — no closed trades have been recorded yet. "
                "Trader calibration requires real trade outcomes to be meaningful."
            )
        elif sufficient_count < total:
            honest_status = (
                f"PARTIAL DATA: {sufficient_count}/{total} traders have sufficient samples. "
                f"{insufficient_count} traders still need more outcomes."
            )
        else:
            honest_status = (
                f"SUFFICIENT DATA: All {total} traders have ≥{MIN_SAMPLES} reviews. "
                "Calibration metrics are statistically valid."
            )

        return {
            "validation_source": VALIDATION_SOURCE,
            "outcome_source": outcome_source.value,
            "min_samples_required": MIN_SAMPLES,
            "traders_queried": total,
            "traders_with_sufficient_samples": sufficient_count,
            "traders_with_insufficient_samples": insufficient_count,
            "honest_status": honest_status,
            "per_trader": per_trader,
        }

    def panel_summary(
        self,
        outcome_source: OutcomeSource = OutcomeSource.EVENT_DRIVEN_RUNTIME,
    ) -> dict:
        """
        Return panel-level calibration statistics.

        Queries the DB for panel_summaries joined with outcome_attributions.
        Returns honest "insufficient" report if < 30 closed trades exist.
        """
        stats = self._panel_calibrator.compute_panel_stats(outcome_source)

        # Wrap in validation metadata
        return {
            "validation_source": VALIDATION_SOURCE,
            "outcome_source": outcome_source.value,
            "min_samples_required": MIN_SAMPLES,
            "panel_calibration": stats,
            "honest_status": (
                stats.get("note", "Sufficient samples — panel calibration is valid.")
                if not stats.get("has_sufficient_samples", False)
                else (
                    f"Panel calibration computed from {stats.get('sample_size', 0)} closed trades."
                )
            ),
        }

    def full_report(
        self,
        outcome_source: OutcomeSource = OutcomeSource.EVENT_DRIVEN_RUNTIME,
    ) -> dict:
        """
        Combined trader + panel calibration report.

        Returns dict with honest assessment of current calibration state.
        All results labelled with validation_source and outcome_source.
        """
        trader = self.trader_summary(outcome_source)
        panel = self.panel_summary(outcome_source)

        # Determine overall calibration readiness
        has_trader_data = trader["traders_with_sufficient_samples"] > 0
        has_panel_data = panel["panel_calibration"].get("has_sufficient_samples", False)

        if not has_trader_data and not has_panel_data:
            overall_status = (
                "NO CALIBRATION DATA AVAILABLE. "
                "Zero closed trades recorded under this outcome_source. "
                "This is the expected state before the system has run in production. "
                "Run the paper trading loop and wait for positions to close "
                f"before expecting calibration metrics (minimum {MIN_SAMPLES} closed trades)."
            )
        elif has_panel_data and not has_trader_data:
            overall_status = (
                "Panel-level calibration available. "
                "Individual trader calibration still insufficient."
            )
        elif has_trader_data and not has_panel_data:
            overall_status = (
                "Some trader calibration available. "
                "Panel-level statistics still insufficient."
            )
        else:
            overall_status = "Full calibration data available."

        return {
            "validation_source": VALIDATION_SOURCE,
            "outcome_source": outcome_source.value,
            "overall_calibration_status": overall_status,
            "trader_calibration": trader,
            "panel_calibration": panel,
        }

    @staticmethod
    def _rank_traders_by_skill(trader_report: dict) -> list[dict]:
        """
        Rank traders by approval_win_rate (descending).
        Only includes traders with sufficient samples.
        Returns empty list if no sufficient data.
        """
        ranked = []
        for name, data in trader_report.get("per_trader", {}).items():
            if not data.get("has_sufficient_samples"):
                continue
            rate = data.get("approval_win_rate")
            if rate is not None:
                ranked.append({"trader_name": name, "approval_win_rate": rate})
        ranked.sort(key=lambda x: x["approval_win_rate"], reverse=True)
        return ranked
