"""
PanelBehaviorAnalyzer and PanelBatchRunner.

PanelBatchRunner:
  Runs the real TraderEvaluatorPanel and FinalDecisionGroup against a list of
  BTCSetupPackets WITHOUT forcing any approvals.
  Source: event_driven_runtime_simulation (real components, synthetic scenarios).

PanelBehaviorAnalyzer:
  Accumulates PanelResult + FinalDecision records and computes:
  - approval distribution (approve_count histogram)
  - avg_score distribution
  - enter vs hold rate
  - safety rail trigger frequencies
  - score dispersion per trader
  - per-evaluator vote frequency
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.setup_packet import BTCSetupPacket
from traders.panel import PanelResult, TraderEvaluatorPanel
from decision.final_group import FinalDecision, FinalDecisionGroup
from validation.metrics import describe
from validation.source_enforcer import SourceEnforcer

logger = logging.getLogger(__name__)

VALIDATION_SOURCE = "event_driven_runtime_simulation"


@dataclass
class PanelBatchRecord:
    """One panel evaluation result + final decision."""
    scenario_id: str
    scenario_label: str
    packet_id: str
    panel_result: PanelResult
    final_decision: FinalDecision
    validation_source: str = VALIDATION_SOURCE


class PanelBatchRunner:
    """
    Runs real TraderEvaluatorPanel + FinalDecisionGroup against a list of
    BTCSetupPackets. No approvals are forced.

    Returns a list of PanelBatchRecord for analysis.
    Source: event_driven_runtime_simulation.
    """

    def __init__(self) -> None:
        self._panel = TraderEvaluatorPanel()
        self._decision_group = FinalDecisionGroup()

    def run_batch(
        self,
        labelled_packets: list,  # list[LabelledPacket] from scenario_loader
    ) -> list[PanelBatchRecord]:
        """
        Run panel + decision on each packet. No forcing.
        Returns PanelBatchRecord for each input.
        """
        from validation.scenario_loader import LabelledPacket
        records = []
        for lp in labelled_packets:
            if not isinstance(lp, LabelledPacket):
                logger.warning("PanelBatchRunner: skipping non-LabelledPacket input %s", type(lp))
                continue
            packet = lp.packet
            desc = lp.descriptor
            try:
                panel_result = self._panel.evaluate(packet)
                final_decision = self._decision_group.decide(packet, panel_result)
                records.append(PanelBatchRecord(
                    scenario_id=desc.scenario_id,
                    scenario_label=desc.label,
                    packet_id=packet.packet_id,
                    panel_result=panel_result,
                    final_decision=final_decision,
                    validation_source=VALIDATION_SOURCE,
                ))
                logger.info(
                    "PanelBatch: %-40s approve=%d/20 avg=%.1f → %s (rails=%s)",
                    desc.label[:40],
                    panel_result.approve_count,
                    panel_result.avg_score,
                    final_decision.decision,
                    final_decision.safety_rails_triggered or "none",
                )
            except Exception as exc:
                logger.error("PanelBatchRunner: error on scenario %s: %s", desc.scenario_id, exc)
        return records


class PanelBehaviorAnalyzer:
    """
    Accumulates PanelBatchRecord results and computes aggregate statistics.

    All metrics are gated by sample size. The analyzer never makes
    calibration conclusions from fewer than 30 samples.

    Attributes:
        records: accumulated PanelBatchRecord objects
    """

    MIN_SAMPLES_FOR_CONCLUSIONS = 30

    def __init__(self) -> None:
        self.records: list[PanelBatchRecord] = []

    def add(self, record: PanelBatchRecord) -> None:
        SourceEnforcer.validate_report(
            {"validation_source": record.validation_source},
            VALIDATION_SOURCE,
        )
        self.records.append(record)

    def add_all(self, records: list[PanelBatchRecord]) -> None:
        for r in records:
            self.add(r)

    # -----------------------------------------------------------------------
    # Derived metrics
    # -----------------------------------------------------------------------

    @property
    def n(self) -> int:
        return len(self.records)

    def _approval_counts(self) -> list[int]:
        return [r.panel_result.approve_count for r in self.records]

    def _avg_scores(self) -> list[float]:
        return [r.panel_result.avg_score for r in self.records]

    def _decisions(self) -> list[str]:
        return [r.final_decision.decision for r in self.records]

    def enter_rate(self) -> Optional[float]:
        d = self._decisions()
        if not d:
            return None
        return sum(1 for x in d if x == "enter") / len(d)

    def hold_rate(self) -> Optional[float]:
        r = self.enter_rate()
        return None if r is None else 1.0 - r

    def approval_distribution(self) -> dict:
        """Histogram of approve_count values (0-20)."""
        counts = self._approval_counts()
        hist = {i: 0 for i in range(21)}
        for c in counts:
            hist[c] = hist.get(c, 0) + 1
        return {
            "histogram": hist,
            "stats": describe(counts),
        }

    def score_distribution(self) -> dict:
        return {"stats": describe(self._avg_scores())}

    def safety_rail_frequencies(self) -> dict:
        """Count how often each safety rail fires."""
        rail_counts: dict[str, int] = {}
        no_rails = 0
        for r in self.records:
            rails = r.final_decision.safety_rails_triggered
            if not rails:
                no_rails += 1
            for rail in rails:
                # Normalize rail name to first word/phrase
                key = self._normalize_rail(rail)
                rail_counts[key] = rail_counts.get(key, 0) + 1
        return {
            "rail_counts": rail_counts,
            "no_rails_triggered": no_rails,
            "total_evaluations": self.n,
        }

    @staticmethod
    def _normalize_rail(rail: str) -> str:
        """Map verbose rail string to short category."""
        r = rail.lower()
        if "avg_score" in r:
            return "Rail1_avg_score_below_5"
        if "reject_count" in r:
            return "Rail2_majority_reject"
        if "r:r" in r or "r_r" in r or "rr" in r:
            return "Rail3_rr_below_1.5"
        if "setup_quality" in r or "invalid" in r:
            return "Rail4_invalid_setup_quality"
        if "bear" in r and "regime" in r:
            return "Rail5_bear_regime_long"
        if "long trade in bear" in r:
            return "Rail5_bear_regime_long"
        if "volatility" in r or "high vol" in r:
            return "Rail6_high_vol_insufficient_consensus"
        return f"Other: {rail[:50]}"

    def per_evaluator_vote_summary(self) -> dict:
        """
        For each of the 20 evaluators, count approve/reject/abstain across all records.
        Returns dict keyed by trader_id.
        """
        summary: dict[str, dict[str, int]] = {}
        for record in self.records:
            for verdict in record.panel_result.verdicts:
                tid = verdict.trader_id
                if tid not in summary:
                    summary[tid] = {"approve": 0, "reject": 0, "abstain": 0, "total": 0}
                summary[tid][verdict.vote] = summary[tid].get(verdict.vote, 0) + 1
                summary[tid]["total"] += 1
        # Add rates
        for tid, counts in summary.items():
            total = counts["total"]
            if total > 0:
                counts["approve_rate"] = round(counts["approve"] / total, 3)
                counts["reject_rate"] = round(counts["reject"] / total, 3)
                counts["abstain_rate"] = round(counts["abstain"] / total, 3)
        return summary

    def per_evaluator_score_summary(self) -> dict:
        """Average score per evaluator across all records."""
        score_lists: dict[str, list[float]] = {}
        for record in self.records:
            for verdict in record.panel_result.verdicts:
                tid = verdict.trader_id
                if tid not in score_lists:
                    score_lists[tid] = []
                score_lists[tid].append(verdict.score)
        return {
            tid: describe(scores)
            for tid, scores in score_lists.items()
        }

    def summarize(self) -> dict:
        """Full summary report dict."""
        sample_warning = None
        if self.n < self.MIN_SAMPLES_FOR_CONCLUSIONS:
            sample_warning = (
                f"INSUFFICIENT SAMPLES: {self.n}/{self.MIN_SAMPLES_FOR_CONCLUSIONS} minimum. "
                "Panel behavior analysis is indicative only, not statistically reliable."
            )
        return {
            "validation_source": VALIDATION_SOURCE,
            "total_evaluations": self.n,
            "sample_size_warning": sample_warning,
            "enter_rate": self.enter_rate(),
            "hold_rate": self.hold_rate(),
            "approval_distribution": self.approval_distribution(),
            "score_distribution": self.score_distribution(),
            "safety_rail_frequencies": self.safety_rail_frequencies(),
            "per_evaluator_votes": self.per_evaluator_vote_summary(),
            "per_evaluator_scores": self.per_evaluator_score_summary(),
            "panel_thresholds": {
                "approve_threshold": TraderEvaluatorPanel.APPROVE_THRESHOLD,
                "min_avg_score": TraderEvaluatorPanel.MIN_AVG_SCORE,
                "note": "These are PRODUCTION thresholds. Not mutated by this analysis.",
            },
        }
