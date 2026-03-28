"""
OutcomeAttributor and ErrorTaxonomy.

OutcomeAttributor: full pipeline for processing a closed trade.
  1. Validate outcome source is consistent.
  2. Write OutcomeAttribution via DecisionTraceLogger.
  3. Update TraderCalibration for all participating traders.
  4. Update SetupFamilyRecord.
  5. Update SpecialistGroupRecord for all contributing groups.

ErrorTaxonomy: classifies why a trade failed.
  Categories:
    A — entry_timing    : entered too early/late relative to signal
    B — stop_placement  : stop too tight, hit by noise
    C — target_too_far  : target unrealistic for regime
    D — regime_mismatch : trade in wrong regime
    E — signal_quality  : low-quality or conflicting signals
    F — execution       : slippage, order placement
    G — unknown         : insufficient data to classify

Source: /docs/learning_logic.md
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from learning.calibration import TraderCalibrator, PanelCalibrator
from learning.decision_logger import DecisionTraceLogger
from learning.journal_extension import JournalExtension
from learning.outcome_source import OutcomeSource
from learning.tracking import SetupFamilyTracker, SpecialistGroupTracker

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ErrorTaxonomy:
    """
    Classifies trade failures into error categories.
    Returns a category code and description.

    This classification is heuristic and should be reviewed manually
    before drawing conclusions. Min 30 samples per category.
    """

    CATEGORIES = {
        "A": "entry_timing",
        "B": "stop_placement",
        "C": "target_too_far",
        "D": "regime_mismatch",
        "E": "signal_quality",
        "F": "execution",
        "G": "unknown",
    }

    def classify(
        self,
        outcome: str,
        pnl_r: float,
        exit_reason: str,
        bars_held: int,
        composite_score: Optional[float],
        regime: Optional[str],
        direction: Optional[str],
    ) -> tuple[str, str]:
        """
        Returns (category_code, description).
        Only classifies losses (outcome == "loss").
        Wins and breakevens return ("none", "not_a_loss").
        """
        if outcome != "loss":
            return ("none", "not_a_loss")

        # D: regime_mismatch — bear regime + long trade
        if regime == "bear" and direction == "LONG":
            return ("D", "regime_mismatch: long in bear regime")

        # B: stop placement — stopped out very quickly (<=3 bars)
        if exit_reason == "stop_loss" and bars_held <= 3:
            return ("B", "stop_placement: stopped within 3 bars (likely noise)")

        # A: entry timing — stopped out but took many bars
        if exit_reason == "stop_loss" and bars_held > 15:
            return ("A", "entry_timing: slow bleed to stop, possible late entry")

        # E: signal quality — low composite score on entry
        if composite_score is not None and composite_score < 0.55:
            return ("E", f"signal_quality: low composite_score={composite_score:.2f}")

        # C: target — time stop after many bars (position never hit target)
        if exit_reason == "time_stop" and bars_held >= 18:
            return ("C", "target_too_far: time stop triggered, target never reached")

        return ("G", "unknown: insufficient data to classify")


class OutcomeAttributor:
    """
    Full attribution pipeline for closed trades.

    Processes one closed trade through:
      1. Log attribution
      2. Update all calibration records
      3. Update setup family performance
      4. Update specialist group records

    Must be called AFTER the trade is confirmed closed in JournalDB.
    """

    def __init__(
        self,
        extension: JournalExtension,
        outcome_source: OutcomeSource,
    ) -> None:
        self._ext = extension
        self._source = outcome_source
        self._trace_logger = DecisionTraceLogger(extension, outcome_source)
        self._trader_calibrator = TraderCalibrator(extension)
        self._panel_calibrator = PanelCalibrator(extension)
        self._setup_tracker = SetupFamilyTracker(extension)
        self._specialist_tracker = SpecialistGroupTracker(extension)
        self._error_taxonomy = ErrorTaxonomy()

    def process_closed_trade(
        self,
        trade_id: str,
        outcome: str,
        pnl_r: float,
        exit_reason: str,
        bars_held: int,
        setup_family: str,
        packet_id: Optional[str] = None,
        panel_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        trader_reviews: Optional[list] = None,
        group_signals: Optional[list] = None,
        composite_score: Optional[float] = None,
        regime: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> dict:
        """
        Run full attribution pipeline for one closed trade.

        Parameters:
          trade_id       — from JournalDB trades table
          outcome        — "win" / "loss" / "breakeven"
          pnl_r          — final R-multiple
          exit_reason    — "stop_loss" / "target_reached" / "time_stop" / "trailing_stop"
          bars_held      — number of bars position was open
          setup_family   — e.g. "ema_crossover"
          packet_id      — linked setup packet (if available)
          panel_id       — linked panel summary (if available)
          decision_id    — linked final decision (if available)
          trader_reviews — list of dicts with trader_name, vote, score, confidence
          group_signals  — list of dicts with group_id, quality_score
          composite_score — proposal composite score
          regime         — btc_macro regime string
          direction      — "LONG" or "SHORT"

        Returns summary dict.
        """
        # 1. Log attribution
        attribution_id = self._trace_logger.log_outcome_attribution(
            trade_id=trade_id,
            packet_id=packet_id,
            panel_id=panel_id,
            decision_id=decision_id,
            outcome=outcome,
            pnl_r=pnl_r,
            exit_reason=exit_reason,
            bars_held=bars_held,
            setup_family=setup_family,
        )

        # 2. Update trader calibration
        if trader_reviews:
            for review in trader_reviews:
                try:
                    self._trader_calibrator.process_trade_outcome(
                        trade_id=trade_id,
                        outcome=outcome,
                        outcome_source=self._source,
                        trader_name=review.get("trader_name", "unknown"),
                        vote=review.get("vote", "abstain"),
                        score=float(review.get("score", 5.0)),
                        confidence=float(review.get("confidence", 0.5)),
                    )
                except Exception as exc:
                    logger.warning("Calibration update failed for trader: %s", exc)

        # 3. Update setup family
        try:
            self._setup_tracker.process_trade_outcome(
                setup_family=setup_family,
                outcome=outcome,
                pnl_r=pnl_r,
                bars_held=bars_held,
                outcome_source=self._source,
            )
        except Exception as exc:
            logger.warning("Setup family update failed: %s", exc)

        # 4. Update specialist groups
        if group_signals:
            for sig in group_signals:
                try:
                    self._specialist_tracker.process_trade_outcome(
                        group_id=sig.get("group_id", "unknown"),
                        outcome=outcome,
                        signal_quality_score=float(sig.get("quality_score", 0.5)),
                        outcome_source=self._source,
                    )
                except Exception as exc:
                    logger.warning("Specialist group update failed: %s", exc)

        # 5. Error taxonomy
        error_code, error_desc = self._error_taxonomy.classify(
            outcome=outcome,
            pnl_r=pnl_r,
            exit_reason=exit_reason,
            bars_held=bars_held,
            composite_score=composite_score,
            regime=regime,
            direction=direction,
        )

        return {
            "attribution_id": attribution_id,
            "trade_id": trade_id,
            "outcome": outcome,
            "pnl_r": pnl_r,
            "setup_family": setup_family,
            "error_category": error_code,
            "error_description": error_desc,
            "outcome_source": self._source.value,
        }
