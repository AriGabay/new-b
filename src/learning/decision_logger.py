"""
DecisionTraceLogger: logs the full decision trace for each setup evaluation.

For each setup that reaches the panel:
  1. Archive BTCSetupPacket → setup_packets table
  2. Archive each TraderVerdict → trader_reviews table
  3. Archive PanelResult → panel_summaries table
  4. Archive FinalDecision → final_decisions table

On trade close:
  5. Write OutcomeAttribution linking trace → outcome

Every record is tagged with OutcomeSource. Records from different sources
are NEVER mixed in calibration metrics.

Source: /docs/learning_logic.md
"""
from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from learning.journal_extension import JournalExtension
from learning.outcome_source import OutcomeSource
from learning.schemas import (
    OutcomeAttribution,
    StoredFinalDecision,
    StoredPanelSummary,
    StoredSetupPacket,
    StoredTraderReview,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DecisionTraceLogger:
    """
    Logs full decision traces to the learning-layer journal tables.

    Usage:
        dtl = DecisionTraceLogger(journal_extension, outcome_source)
        packet_id = dtl.log_setup_packet(btc_setup_packet)
        dtl.log_trader_reviews(packet_id, trader_verdicts)
        panel_id = dtl.log_panel_summary(packet_id, panel_result)
        decision_id = dtl.log_final_decision(packet_id, panel_id, final_decision)

        # When trade closes:
        dtl.log_outcome_attribution(trade_id, packet_id, panel_id, decision_id,
                                    outcome, pnl_r, exit_reason, bars_held, setup_family)
    """

    def __init__(
        self,
        extension: JournalExtension,
        outcome_source: OutcomeSource,
    ) -> None:
        self._ext = extension
        self._source = outcome_source

    def log_setup_packet(self, packet) -> str:
        """
        Archive a BTCSetupPacket. Returns packet_id.
        packet: BTCSetupPacket instance (or any dataclass/dict with symbol, timeframe)
        """
        packet_id = str(uuid.uuid4())
        try:
            # Serialize — handle dataclass or dict
            if dataclasses.is_dataclass(packet) and not isinstance(packet, type):
                packet_dict = dataclasses.asdict(packet)
            elif isinstance(packet, dict):
                packet_dict = packet
            else:
                packet_dict = {"raw": str(packet)}
            packet_json = json.dumps(packet_dict, default=str)
        except Exception as exc:
            logger.warning("DecisionTraceLogger: could not serialize packet: %s", exc)
            packet_json = json.dumps({"serialization_error": str(exc)})

        symbol = getattr(packet, "symbol", "") if not isinstance(packet, dict) else packet.get("symbol", "")
        timeframe = getattr(packet, "timeframe", "1h") if not isinstance(packet, dict) else packet.get("timeframe", "1h")
        bar_ts = getattr(packet, "bar_timestamp", _utcnow())
        if isinstance(bar_ts, str):
            try:
                bar_ts = datetime.fromisoformat(bar_ts)
            except Exception:
                bar_ts = _utcnow()

        stored = StoredSetupPacket(
            packet_id=packet_id,
            symbol=symbol,
            timeframe=timeframe,
            bar_timestamp=bar_ts,
            stored_at=_utcnow(),
            outcome_source=self._source,
            packet_json=packet_json,
        )
        self._ext.insert_setup_packet(stored)
        logger.debug("DecisionTraceLogger: archived setup packet %s", packet_id)
        return packet_id

    def log_trader_reviews(
        self,
        packet_id: str,
        trader_verdicts: list,
    ) -> None:
        """
        Archive a list of TraderVerdict objects.
        Each verdict must have: trader_name, vote, score, confidence,
        pro_reason, anti_reason, execution_concern, risk_concern, explanation.
        """
        for verdict in trader_verdicts:
            review = StoredTraderReview(
                review_id=str(uuid.uuid4()),
                packet_id=packet_id,
                trader_name=getattr(verdict, "trader_id", None) or getattr(verdict, "trader_name", "unknown"),
                outcome_source=self._source,
                vote=str(getattr(verdict, "vote", "")),
                score=float(getattr(verdict, "score", 0.0)),
                confidence=float(getattr(verdict, "confidence", 0.0)),
                pro_reason=getattr(verdict, "pro_reason", ""),
                anti_reason=getattr(verdict, "anti_reason", ""),
                execution_concern=getattr(verdict, "execution_concern", ""),
                risk_concern=getattr(verdict, "risk_concern", ""),
                explanation=getattr(verdict, "explanation", ""),
                reviewed_at=_utcnow(),
            )
            self._ext.insert_trader_review(review)
        logger.debug(
            "DecisionTraceLogger: archived %d trader reviews for packet %s",
            len(trader_verdicts), packet_id,
        )

    def log_panel_summary(
        self,
        packet_id: str,
        panel_result,
    ) -> str:
        """
        Archive PanelResult. Returns panel_id.
        panel_result must have: approve_count, reject_count, abstain_count,
        avg_score, weighted_score, panel_recommendation, key_risks, key_strengths.
        """
        panel_id = str(uuid.uuid4())
        summary = StoredPanelSummary(
            panel_id=panel_id,
            packet_id=packet_id,
            outcome_source=self._source,
            approve_count=int(getattr(panel_result, "approve_count", 0)),
            reject_count=int(getattr(panel_result, "reject_count", 0)),
            abstain_count=int(getattr(panel_result, "abstain_count", 0)),
            avg_score=float(getattr(panel_result, "avg_score", 0.0)),
            weighted_score=float(getattr(panel_result, "weighted_score", 0.0)),
            panel_recommendation=str(getattr(panel_result, "panel_recommendation", "hold")),
            key_risks=json.dumps(getattr(panel_result, "key_risks", []), default=str),
            key_strengths=json.dumps(getattr(panel_result, "key_strengths", []), default=str),
            evaluated_at=_utcnow(),
        )
        self._ext.insert_panel_summary(summary)
        logger.debug("DecisionTraceLogger: archived panel summary %s", panel_id)
        return panel_id

    def log_final_decision(
        self,
        packet_id: str,
        panel_id: str,
        final_decision,
    ) -> str:
        """
        Archive FinalDecision. Returns decision_id.
        final_decision must have: decision, safety_rails_triggered, rationale.
        """
        decision_id = str(uuid.uuid4())
        rails = getattr(final_decision, "safety_rails_triggered", [])
        stored = StoredFinalDecision(
            decision_id=decision_id,
            packet_id=packet_id,
            panel_id=panel_id,
            outcome_source=self._source,
            decision=str(getattr(final_decision, "decision", "hold")),
            safety_rails_triggered=json.dumps(rails, default=str),
            rationale=str(getattr(final_decision, "rationale", "")),
            decided_at=_utcnow(),
        )
        self._ext.insert_final_decision(stored)
        logger.debug("DecisionTraceLogger: archived final decision %s", decision_id)
        return decision_id

    def log_outcome_attribution(
        self,
        trade_id: str,
        packet_id: Optional[str],
        panel_id: Optional[str],
        decision_id: Optional[str],
        outcome: str,
        pnl_r: float,
        exit_reason: str,
        bars_held: int,
        setup_family: str,
    ) -> str:
        """
        Link closed trade to its decision trace.
        Called by PerformanceJournalGroup when trade closes.
        Returns attribution_id.
        """
        attribution_id = str(uuid.uuid4())
        attr = OutcomeAttribution(
            attribution_id=attribution_id,
            trade_id=trade_id,
            packet_id=packet_id or "",
            panel_id=panel_id or "",
            decision_id=decision_id or "",
            outcome_source=self._source,
            outcome=outcome,
            pnl_r=pnl_r,
            exit_reason=exit_reason,
            bars_held=bars_held,
            setup_family=setup_family,
            attributed_at=_utcnow(),
        )
        self._ext.insert_outcome_attribution(attr)
        logger.info(
            "DecisionTraceLogger: attributed trade %s → %s (pnl_r=%.2f, source=%s)",
            trade_id, outcome, pnl_r, self._source.value,
        )
        return attribution_id
