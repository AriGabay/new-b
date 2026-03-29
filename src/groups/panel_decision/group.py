"""
PanelDecisionGroup: Layer B+C bridge (always_on=False).

Responsibilities:
  - Subscribe to CandidateTradeEvent from EntryGroup.
  - Build BTCSetupPacket from proposal + current feature state.
  - Run TraderEvaluatorPanel (20 trader evaluators).
  - Run FinalDecisionGroup (6 safety rails).
  - If decision == "enter": publish PanelApprovedProposalEvent.
  - If decision == "hold": log rejection, do not forward.
  - Log full decision trace via DecisionTraceLogger (if available).

LLM: NOT permitted in this group. TraderEvaluatorPanel and FinalDecisionGroup
     are both deterministic (no LLM calls in Phase 4).
Trigger: CandidateTradeEvent.
Depends on: MarketDataGroup (for FeatureVector cache), TechnicalStructureGroup (optional structural cache).
Always-on: NO.

Source: /docs/runtime_runner_design.md
        /docs/adr/ADR-003-where-llm-reasoning-is-permitted.md
"""
from __future__ import annotations

import logging
from typing import Optional

from dataclasses import replace as dataclass_replace
from decimal import Decimal

from agents.base.group import BaseGroup
from core.events import (
    CandidateTradeEvent,
    EventBus,
    PanelApprovedProposalEvent,
    SystemEvent,
)
from core.registry import GroupID
from core.state import SystemState

logger = logging.getLogger(__name__)


class PanelDecisionGroup(BaseGroup):
    """
    Layer B+C bridge: 20-trader panel + FinalDecisionGroup.

    Wired between EntryGroup and RiskLeverageGroup.
    CandidateTradeEvent → (panel + decision) → PanelApprovedProposalEvent

    Cross-bar state:
    -   _feature_cache: dict[symbol, FeatureVector] — latest features per symbol
    -   _structural_cache: dict[symbol, StructuralLevelBundle] — latest S/R per symbol
    -   _trace_logger: DecisionTraceLogger or None (requires JournalExtension)
    """

    group_id = GroupID.ENTRY   # shares logical location; no dedicated GroupID yet

    def __init__(
        self,
        state: SystemState,
        bus: EventBus,
        config: Optional[dict] = None,
        journal_extension=None,
        outcome_source=None,
    ) -> None:
        super().__init__(state, bus, config)
        # Inject optional feature + structural caches (set by runner after setup)
        self._feature_cache: dict = {}
        self._structural_cache: dict = {}
        self._candlestick_signal_cache: dict = {}   # symbol → list[CandlestickSignal]
        self._chart_pattern_signal_cache: dict = {}   # symbol → list[ChartPatternSignal]
        self._active_chart_pattern_cache: dict = {}   # symbol → list[str]
        self._journal_extension = journal_extension
        self._outcome_source = outcome_source
        self._trace_logger = None
        self._panel = None
        self._decision_group = None

    def set_feature_cache(self, cache: dict) -> None:
        """Inject reference to MarketDataGroup's feature cache dict."""
        self._feature_cache = cache

    def set_structural_cache(self, cache: dict) -> None:
        """Inject reference to TechnicalStructureGroup's structural cache."""
        self._structural_cache = cache

    def set_candlestick_signal_cache(self, cache: dict) -> None:
        """Inject reference to CandlestickGroup's signal cache."""
        self._candlestick_signal_cache = cache

    def set_chart_pattern_signal_cache(self, cache: dict) -> None:
        """Inject reference to ChartPatternGroup's confirmed signal cache."""
        self._chart_pattern_signal_cache = cache

    def set_active_chart_pattern_cache(self, cache: dict) -> None:
        """Inject reference to ChartPatternGroup's active pattern name cache."""
        self._active_chart_pattern_cache = cache

    async def _setup(self) -> None:
        # Lazy import to avoid circular deps
        from traders.panel import TraderEvaluatorPanel
        from decision.final_group import FinalDecisionGroup

        self._panel = TraderEvaluatorPanel()
        self._decision_group = FinalDecisionGroup()

        # Wire trace logger if journal extension provided
        if self._journal_extension is not None and self._outcome_source is not None:
            from learning.decision_logger import DecisionTraceLogger
            self._trace_logger = DecisionTraceLogger(
                self._journal_extension, self._outcome_source
            )

        await self.bus.subscribe(CandidateTradeEvent, self.handle_event)
        logger.info(
            "PanelDecisionGroup ready: 20-trader panel + FinalDecisionGroup wired. "
            "TraceLogger=%s",
            "active" if self._trace_logger else "not wired",
        )

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, CandidateTradeEvent) and event.proposal:
            await self._evaluate_proposal(event.proposal)

    async def _evaluate_proposal(self, proposal) -> None:
        """
        Full Layer B+C evaluation pipeline:
        1. Build BTCSetupPacket from proposal + runtime state.
        2. Run TraderEvaluatorPanel (20 traders).
        3. Run FinalDecisionGroup (6 safety rails).
        4. Log trace if DecisionTraceLogger available.
        5. Publish PanelApprovedProposalEvent if decision == "enter".
        """
        from runtime.setup_packet_builder import build_btc_setup_packet

        symbol = proposal.symbol

        # 1. Get latest FeatureVector for this symbol
        fv = self._feature_cache.get(symbol)
        if fv is None:
            # Try (symbol, "1h") key format (MarketDataGroup style)
            fv = self._feature_cache.get((symbol, "1h"))
        if fv is None:
            logger.warning(
                "PanelDecisionGroup: no FeatureVector for %s — cannot build BTCSetupPacket. "
                "Proposal skipped.", symbol,
            )
            return

        structural_bundle = self._structural_cache.get(symbol)
        candlestick_signals = self._candlestick_signal_cache.get(symbol, [])
        chart_pattern_signals = self._chart_pattern_signal_cache.get(symbol, [])
        active_chart_patterns = self._active_chart_pattern_cache.get(symbol, [])

        # 2. Build BTCSetupPacket
        try:
            packet = build_btc_setup_packet(
                proposal=proposal,
                fv=fv,
                structural_bundle=structural_bundle,
                candlestick_signals=candlestick_signals,
                chart_pattern_signals=chart_pattern_signals,
                active_chart_patterns=active_chart_patterns,
            )
        except Exception as exc:
            logger.error(
                "PanelDecisionGroup: BTCSetupPacket build failed for %s: %s", symbol, exc,
            )
            return

        # 3. Run TraderEvaluatorPanel
        try:
            panel_result = self._panel.evaluate(packet)
        except Exception as exc:
            logger.error(
                "PanelDecisionGroup: TraderEvaluatorPanel.evaluate() failed: %s", exc,
            )
            return

        # 4. Run FinalDecisionGroup
        try:
            final_decision = self._decision_group.decide(packet, panel_result)
        except Exception as exc:
            logger.error(
                "PanelDecisionGroup: FinalDecisionGroup.decide() failed: %s", exc,
            )
            return

        # 5. Log trace
        packet_id = ""
        panel_id = ""
        decision_id = ""
        if self._trace_logger is not None:
            try:
                packet_id = self._trace_logger.log_setup_packet(packet)
                self._trace_logger.log_trader_reviews(
                    packet_id, panel_result.verdicts
                )
                panel_id = self._trace_logger.log_panel_summary(packet_id, panel_result)
                decision_id = self._trace_logger.log_final_decision(
                    packet_id, panel_id, final_decision
                )
            except Exception as exc:
                logger.warning("PanelDecisionGroup: trace logging failed: %s", exc)

        logger.info(
            "PanelDecisionGroup: %s %s | approve=%d/20 avg=%.1f | decision=%s | rails=%s",
            proposal.direction, symbol,
            panel_result.approve_count,
            panel_result.avg_score,
            final_decision.decision,
            [r for r in getattr(final_decision, "safety_rails_triggered", [])],
        )

        # 6. Forward only if approved
        if final_decision.decision == "enter":
            # Enrich CandidateTradeProposal with computed raw_target.
            # build_setup_proposal() computes target_price from ATR when raw_target == 0.
            # Risk Rule 9 in RiskLeverageGroup requires raw_target > 0 or it rejects with
            # INCOMPLETE_TRADE_PLAN. If the proposal already has a raw_target, preserve it.
            enriched_proposal = proposal
            if (
                packet.proposal.target_price > Decimal("0")
                and proposal.raw_target == Decimal("0")
            ):
                enriched_proposal = dataclass_replace(
                    proposal, raw_target=packet.proposal.target_price
                )
            await self.bus.publish(
                PanelApprovedProposalEvent(
                    source="panel_decision_group",
                    proposal=enriched_proposal,
                    panel_approve_count=panel_result.approve_count,
                    panel_avg_score=panel_result.avg_score,
                    panel_decision="enter",
                    packet_id=packet_id,
                    panel_id=panel_id,
                    decision_id=decision_id,
                )
            )
        else:
            logger.info(
                "PanelDecisionGroup: proposal %s %s HELD by Layer C "
                "(approve=%d/20 avg=%.1f safety_rails=%s)",
                proposal.direction, symbol,
                panel_result.approve_count,
                panel_result.avg_score,
                getattr(final_decision, "safety_rails_triggered", []),
            )
