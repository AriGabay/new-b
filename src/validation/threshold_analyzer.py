"""
PanelThresholdSensitivityAnalyzer — read-only what-if threshold analysis.

CRITICAL: This module does NOT mutate any production thresholds.
It re-evaluates collected PanelResult data against alternative thresholds
in isolation, clearly labeling all results as sensitivity analysis.

Current production thresholds (TraderEvaluatorPanel):
  APPROVE_THRESHOLD = 12  (12/20 traders must approve)
  MIN_AVG_SCORE     = 5.5

Current FinalDecisionGroup safety rails are applied on top — they are
NOT varied in this analysis (they are hard risk constraints, not quality filters).

Usage:
    analyzer = PanelThresholdSensitivityAnalyzer()
    report = analyzer.analyze(panel_records)
    # report contains what-if enter rates at alternative thresholds
    # All alternative results are labeled: "sensitivity_analysis_only"
    # Do NOT use sensitivity results as edge evidence
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from traders.panel import TraderEvaluatorPanel
from validation.metrics import describe

logger = logging.getLogger(__name__)

# Production thresholds — READ ONLY
_PRODUCTION_APPROVE_THRESHOLD = TraderEvaluatorPanel.APPROVE_THRESHOLD  # 14
_PRODUCTION_MIN_AVG_SCORE = TraderEvaluatorPanel.MIN_AVG_SCORE          # 6.5


@dataclass
class ThresholdScenario:
    approve_threshold: int     # minimum approve_count
    min_avg_score: float       # minimum avg_score
    is_production: bool = False
    label: str = ""


@dataclass
class ThresholdSensitivityRow:
    """Result of applying one threshold combination to the collected panel data."""
    approve_threshold: int
    min_avg_score: float
    enter_count: int
    hold_count: int
    total: int
    enter_rate: float
    is_production_threshold: bool
    note: str = ""


class PanelThresholdSensitivityAnalyzer:
    """
    Re-evaluates panel results at alternative thresholds.

    NOTE ON FINAL DECISION RAILS: Safety rails in FinalDecisionGroup
    (R:R < 1.5, bear+long, high-vol, invalid setup, etc.) are NOT varied
    here. They are hard risk constraints. This analysis only varies the
    panel consensus thresholds (approve_count and avg_score).

    The production FinalDecisionGroup safety rails are still applied to
    determine which 'enter' calls would survive — but because the rail
    logic depends on the full BTCSetupPacket (not stored in PanelResult),
    this analysis uses panel_recommendation alone as the proxy for the
    enter/hold split at each threshold. The actual FinalDecision from the
    batch run is stored separately.
    """

    # Alternative thresholds to test
    THRESHOLD_SCENARIOS = [
        ThresholdScenario(approve_threshold=10, min_avg_score=5.0, label="Lenient_10/5.0"),
        ThresholdScenario(approve_threshold=11, min_avg_score=5.5, label="Relaxed_11/5.5"),
        ThresholdScenario(approve_threshold=12, min_avg_score=6.0, label="Moderate_12/6.0"),
        ThresholdScenario(approve_threshold=13, min_avg_score=6.0, label="Moderate_13/6.0"),
        ThresholdScenario(
            approve_threshold=_PRODUCTION_APPROVE_THRESHOLD,
            min_avg_score=_PRODUCTION_MIN_AVG_SCORE,
            is_production=True,
            label=f"PRODUCTION_{_PRODUCTION_APPROVE_THRESHOLD}/{_PRODUCTION_MIN_AVG_SCORE}",
        ),
        ThresholdScenario(approve_threshold=15, min_avg_score=7.0, label="Strict_15/7.0"),
        ThresholdScenario(approve_threshold=16, min_avg_score=7.0, label="VeryStrict_16/7.0"),
        ThresholdScenario(approve_threshold=18, min_avg_score=7.5, label="Extreme_18/7.5"),
    ]

    def analyze(
        self,
        panel_records: list,  # list[PanelBatchRecord]
    ) -> dict:
        """
        Apply each threshold scenario to the panel results.
        Returns sensitivity report with clear labeling.
        """
        if not panel_records:
            return {
                "validation_source": "sensitivity_analysis_only",
                "note": "No panel records to analyze.",
                "rows": [],
            }

        rows = []
        for scenario in self.THRESHOLD_SCENARIOS:
            enter_count = 0
            hold_count = 0
            for rec in panel_records:
                pr = rec.panel_result
                # Apply this threshold (ignoring FinalDecisionGroup rails for simplicity)
                if (pr.approve_count >= scenario.approve_threshold
                        and pr.avg_score >= scenario.min_avg_score):
                    enter_count += 1
                else:
                    hold_count += 1

            total = len(panel_records)
            enter_rate = enter_count / total if total > 0 else 0.0
            row = ThresholdSensitivityRow(
                approve_threshold=scenario.approve_threshold,
                min_avg_score=scenario.min_avg_score,
                enter_count=enter_count,
                hold_count=hold_count,
                total=total,
                enter_rate=round(enter_rate, 3),
                is_production_threshold=scenario.is_production,
                note=(
                    "← PRODUCTION THRESHOLD (not mutated)" if scenario.is_production
                    else "sensitivity_analysis_only — NOT for edge conclusions"
                ),
            )
            rows.append(row)
            logger.info(
                "Threshold %s (%d/%d): enter=%d/%d (%.0f%%) %s",
                scenario.label,
                scenario.approve_threshold,
                int(scenario.min_avg_score * 10),
                enter_count, total,
                enter_rate * 100,
                "← PRODUCTION" if scenario.is_production else "",
            )

        # Summary: how much does the production threshold differ from alternatives?
        prod_row = next((r for r in rows if r.is_production_threshold), None)
        lenient_row = rows[0] if rows else None
        strictest_row = rows[-1] if rows else None

        return {
            "validation_source": "sensitivity_analysis_only",
            "IMPORTANT": (
                "This analysis does NOT mutate production thresholds. "
                "All rows labeled 'sensitivity_analysis_only' except the production row. "
                "Do NOT use alternative threshold results as edge evidence."
            ),
            "production_threshold": {
                "approve_threshold": _PRODUCTION_APPROVE_THRESHOLD,
                "min_avg_score": _PRODUCTION_MIN_AVG_SCORE,
            },
            "total_panel_evaluations": len(panel_records),
            "rows": [
                {
                    "label": self.THRESHOLD_SCENARIOS[i].label,
                    "approve_threshold": r.approve_threshold,
                    "min_avg_score": r.min_avg_score,
                    "enter_count": r.enter_count,
                    "hold_count": r.hold_count,
                    "enter_rate": r.enter_rate,
                    "is_production": r.is_production_threshold,
                    "note": r.note,
                }
                for i, r in enumerate(rows)
            ],
            "interpretation": self._interpret(prod_row, lenient_row, strictest_row),
        }

    @staticmethod
    def _interpret(
        prod: Optional[ThresholdSensitivityRow],
        lenient: Optional[ThresholdSensitivityRow],
        strictest: Optional[ThresholdSensitivityRow],
    ) -> str:
        if prod is None:
            return "No production data available."
        parts = [
            f"Production threshold ({prod.approve_threshold}/20, "
            f"avg≥{prod.min_avg_score}) produces "
            f"{prod.enter_count}/{prod.total} enters ({prod.enter_rate:.0%})."
        ]
        if lenient is not None and lenient.total > 0:
            increase = lenient.enter_count - prod.enter_count
            parts.append(
                f"Relaxing to {lenient.approve_threshold}/20 + avg≥{lenient.min_avg_score} "
                f"would add {increase} more enters (+{increase/prod.total:.0%} of batch)."
            )
        if strictest is not None and strictest.total > 0:
            decrease = prod.enter_count - strictest.enter_count
            parts.append(
                f"Tightening to {strictest.approve_threshold}/20 + avg≥{strictest.min_avg_score} "
                f"would remove {decrease} enters ({decrease/prod.total:.0%} of batch)."
            )
        if prod.enter_rate < 0.20:
            parts.append(
                "WARNING: Production threshold is highly restrictive (<20% enter rate on this scenario set). "
                "This may be correct risk management, or thresholds may need recalibration "
                "once real trade outcomes are available."
            )
        return " ".join(parts)
