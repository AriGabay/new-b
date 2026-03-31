"""
Performance, Journal & Learning Group (Group 10 — always_on=True, implementation_priority=3).

Responsibilities:
  - Log ALL system events to SQLite journal (append-only, never deleted).
  - Compute per-hypothesis performance metrics after each trade close.
  - Detect edge decay (recent 50 vs full 200 window comparison).
  - Run HistorianAgent to index trade outcomes for Entry group queries.
  - Run SummarizerAgent (LLM) weekly to produce narrative edge report.
  - Publish JournalEntryEvent for all logged items.
  - Validate hypotheses against OOS criteria when sample size reached.

LLM: PERMITTED for SummarizerAgent (narrative output only; never influences orders).
Always-on: YES — subscribes to all relevant events.
Implementation priority: 3 (required before any meaningful performance analysis).

Phase 2 deliverable:
  SQLite journal, trade outcome logging, basic performance metrics.

Journal tables (see learning_contract.md):
  - trades:        one row per closed trade
  - signals:       one row per signal emitted
  - journal_events: all system events (signals, bars, alerts, risk decisions)

Edge decay rule:
  - Compare win_rate/profit_factor over last 50 trades vs full 200-trade window.
  - If recent_metric < 0.60 × full_window_metric → emit EdgeDecayAlert.
  - Hypothesis status updated to IN_SAMPLE or OOS_PASSED via HypothesisValidator.

Source: /docs/agent_registry/group_registry.md (PERFORMANCE_JOURNAL entry)
        /docs/learning_system/learning_contract.md
        /docs/adr/ADR-003-where-llm-reasoning-is-permitted.md
"""
from __future__ import annotations

import logging
from typing import Optional

from agents.base.group import BaseGroup
from core.events import (
    CandidateTradeEvent,
    EventBus,
    FeatureReadyEvent,
    GroupSignalEvent,
    JournalEntryEvent,
    PositionCloseEvent,
    PositionOpenEvent,
    RiskDecisionEvent,
    SystemAlertEvent,
    SystemEvent,
)
from core.registry import GroupID
from core.state import SystemState

logger = logging.getLogger(__name__)

EDGE_DECAY_THRESHOLD   = 0.60   # Recent metric must be >= 60% of full-window metric
RECENT_WINDOW_TRADES   = 50     # Recent window for decay detection
FULL_WINDOW_TRADES     = 200    # Full window for decay comparison
MIN_TRADES_FOR_DECAY   = 50     # Minimum trades before decay check runs


class PerformanceJournalGroup(BaseGroup):
    """
    Append-only event journal and performance analytics.

    Cross-bar state:
    -   _db_conn: sqlite3.Connection  — open DB connection (journal.db)
    -   _trade_counts: dict[hypothesis_id, int]  — trade counts per hypothesis
    -   _last_weekly_summary: datetime  — timestamp of last LLM narrative report
    """

    group_id = GroupID.PERFORMANCE_JOURNAL

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)
        self._db_conn = None
        self._journal_db = None
        self._trade_counts: dict = {}
        self._last_weekly_summary = None
        self._summarizer = None         # SummarizerAgent, injected at startup
        self._outcome_attributor = None  # OutcomeAttributor, injected by runner after setup
        # Exit diagnostics recorder — injected by runner after setup.
        # When wired, records a post-trade snapshot for every closed position
        # and writes results to data/exit_diagnosis.csv at teardown.
        self._exit_diagnostics = None   # Optional[ExitDiagnosticsRecorder]

    async def _setup(self) -> None:
        # Subscribe to all relevant event types
        await self.bus.subscribe(GroupSignalEvent,      self.handle_event)
        await self.bus.subscribe(CandidateTradeEvent,   self.handle_event)
        await self.bus.subscribe(RiskDecisionEvent,     self.handle_event)
        await self.bus.subscribe(PositionOpenEvent,     self.handle_event)
        await self.bus.subscribe(PositionCloseEvent,    self.handle_event)
        await self.bus.subscribe(SystemAlertEvent,      self.handle_event)
        # FeatureReadyEvent subscription drives post-close snapshot filling
        # for the exit diagnostics recorder (only active when recorder is wired).
        await self.bus.subscribe(FeatureReadyEvent,     self.handle_event)
        await self._initialize_db()
        logger.info("PerformanceJournalGroup ready. Journal DB initialized.")

    async def _handle_event(self, event: SystemEvent) -> None:
        """Route events to appropriate journal handlers."""
        if isinstance(event, GroupSignalEvent):
            await self._log_signal_event(event)
        elif isinstance(event, CandidateTradeEvent):
            await self._log_candidate_trade(event)
        elif isinstance(event, RiskDecisionEvent):
            await self._log_risk_decision(event)
        elif isinstance(event, PositionOpenEvent):
            await self._log_position_open(event)
        elif isinstance(event, PositionCloseEvent):
            await self._log_position_close(event)
        elif isinstance(event, SystemAlertEvent):
            await self._log_system_alert(event)
        elif isinstance(event, FeatureReadyEvent):
            self._on_feature_ready(event)

    async def _initialize_db(self) -> None:
        """Initialize JournalDB and create tables."""
        from journal.db import JournalDB
        import os
        db_path = (self.config or {}).get("journal_db_path", "data/journal.db")
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._journal_db = JournalDB(db_path=db_path)
        self._journal_db.initialize()
        logger.info("PerformanceJournalGroup: JournalDB initialized at %s", db_path)

    async def _log_signal_event(self, event: GroupSignalEvent) -> None:
        if self._journal_db is None or not event.bundle:
            return
        try:
            for sig in (event.bundle.signals or []):
                self._journal_db.insert_signal(sig)
        except Exception as exc:
            logger.warning("PerformanceJournalGroup: failed to log signal: %s", exc)

    async def _log_candidate_trade(self, event: CandidateTradeEvent) -> None:
        if self._journal_db is None or not event.proposal:
            return
        try:
            p = event.proposal
            self._journal_db.insert_journal_event(
                event_type="candidate_trade",
                source="entry_group",
                payload={
                    "proposal_id": p.proposal_id,
                    "symbol": p.symbol,
                    "direction": str(p.direction),
                    "composite_score": p.composite_score,
                    "entry_price": str(p.entry_price),
                },
            )
        except Exception as exc:
            logger.warning("PerformanceJournalGroup: failed to log candidate trade: %s", exc)

    async def _log_risk_decision(self, event: RiskDecisionEvent) -> None:
        if self._journal_db is None:
            return
        try:
            if event.approved and event.order:
                payload = {"approved": True, "order_id": event.order.order_id, "symbol": event.order.symbol}
            elif event.rejection:
                payload = {"approved": False, "reason": event.rejection.rejection_reason, "detail": event.rejection.rejection_detail}
            else:
                payload = {"approved": event.approved}
            self._journal_db.insert_journal_event("risk_decision", "risk_leverage_group", payload)
        except Exception as exc:
            logger.warning("PerformanceJournalGroup: failed to log risk decision: %s", exc)

    async def _log_position_open(self, event: PositionOpenEvent) -> None:
        if self._journal_db is None or not event.position:
            return
        try:
            self._journal_db.insert_trade_open(
                position=event.position,
                proposal_id=event.position.order_id,
                composite_score=event.position.composite_score,
            )
            logger.info(
                "PerformanceJournalGroup: trade opened — %s %s @ %s",
                event.position.direction, event.position.symbol, event.position.entry_price,
            )
        except Exception as exc:
            logger.warning("PerformanceJournalGroup: failed to log position open: %s", exc)

    async def _log_position_close(self, event: PositionCloseEvent) -> None:
        if self._journal_db is None or not event.exit_signal or not event.final_position:
            return
        try:
            self._journal_db.update_trade_close(
                exit_signal=event.exit_signal,
                position=event.final_position,
            )
            # Register with exit diagnostics recorder (non-blocking — failures are logged)
            if self._exit_diagnostics is not None:
                self._exit_diagnostics.on_trade_close(
                    position=event.final_position,
                    exit_signal=event.exit_signal,
                )
            # NOTE: state.close_position() is NOT called here.
            # ExitGroup._execute_exit() already calls state.close_position() before
            # publishing PositionCloseEvent. Calling it again here would double-count
            # PnL (equity += pnl twice) and double-increment total_trades.
            # This group's responsibility is journal logging only.
            from utils.bar_duration import format_bars
            tf = getattr(event.final_position, "timeframe", "1h") or "1h"
            logger.info(
                "PerformanceJournalGroup: trade closed — %s PnL=$%.2f (%.2fR) reason=%s held=%s",
                event.final_position.symbol,
                event.exit_signal.pnl_usd,
                event.exit_signal.pnl_r,
                event.exit_signal.exit_reason,
                format_bars(event.exit_signal.bars_held, tf),
            )
        except Exception as exc:
            logger.warning("PerformanceJournalGroup: failed to log position close: %s", exc)

        # Run attribution pipeline if OutcomeAttributor is wired.
        # This updates trader calibration, setup family records, and logs outcome_attributions.
        # Requires packet_id/panel_id/decision_id carried on the Position (set by RiskLeverageGroup
        # from PanelApprovedProposalEvent). If Position was opened without the panel path these
        # will be empty strings and attribution still runs (but without DB links).
        if self._outcome_attributor is not None and event.final_position is not None:
            try:
                pos = event.final_position
                sig = event.exit_signal
                pnl_r = sig.pnl_r if sig else 0.0
                if pnl_r > 0.05:
                    outcome = "win"
                elif pnl_r < -0.05:
                    outcome = "loss"
                else:
                    outcome = "breakeven"
                setup_family = pos.setup_refs[0] if pos.setup_refs else "unknown"
                # Fetch trader reviews from the learning DB so calibration
                # updates can run.  Without this, trader_calibration stays empty
                # because process_closed_trade defaults trader_reviews=None.
                # BUG FIX (Phase 7): this was missing since Phase 4, causing
                # trader_calibration to remain at 0 rows despite 34 attributions.
                trader_reviews = None
                if pos.packet_id and self._outcome_attributor._ext:
                    try:
                        trader_reviews = (
                            self._outcome_attributor._ext
                            .query_trader_reviews_by_packet(pos.packet_id)
                        )
                    except Exception as tr_exc:
                        logger.debug(
                            "PerformanceJournalGroup: trader reviews lookup: %s",
                            tr_exc,
                        )

                direction_str = (
                    pos.direction.value.upper()
                    if hasattr(pos.direction, "value")
                    else str(pos.direction).upper()
                )

                self._outcome_attributor.process_closed_trade(
                    trade_id=pos.position_id,
                    outcome=outcome,
                    pnl_r=pnl_r,
                    exit_reason=sig.exit_reason.value if sig else "unknown",
                    bars_held=sig.bars_held if sig else 0,
                    setup_family=setup_family,
                    packet_id=pos.packet_id,
                    panel_id=pos.panel_id,
                    decision_id=pos.decision_id,
                    composite_score=pos.composite_score,
                    trader_reviews=trader_reviews,
                    direction=direction_str,
                )
            except Exception as exc:
                logger.warning(
                    "PerformanceJournalGroup: outcome attribution failed: %s", exc
                )

    def _on_feature_ready(self, event: FeatureReadyEvent) -> None:
        """Forward bar data to the exit diagnostics recorder (if wired)."""
        if self._exit_diagnostics is not None and event.features is not None:
            self._exit_diagnostics.on_bar(event.features)

    async def _log_system_alert(self, event: SystemAlertEvent) -> None:
        if self._journal_db is None:
            return
        try:
            self._journal_db.insert_journal_event(
                event_type="system_alert",
                source=event.source,
                payload={"alert_code": event.alert_code, "description": event.description},
                severity=event.severity,
            )
        except Exception as exc:
            logger.warning("PerformanceJournalGroup: failed to log alert: %s", exc)

    async def _teardown(self) -> None:
        # Flush and summarise exit diagnostics before closing the DB
        if self._exit_diagnostics is not None:
            try:
                self._exit_diagnostics.flush_pending()
                self._exit_diagnostics.print_summary()
            except Exception as exc:
                logger.warning("PerformanceJournalGroup: exit_diagnostics teardown error: %s", exc)

        if self._journal_db is not None:
            self._journal_db.close()
            self._journal_db = None
            logger.info("PerformanceJournalGroup: JournalDB closed.")

    async def _check_edge_decay(self, hypothesis_id: str) -> None:
        """
        Compare recent 50-trade window vs full 200-trade window.
        If recent win_rate < 0.60 × full_window win_rate → emit EdgeDecayAlert.

        STATUS: DEFERRED — Phase 4+ implementation pending.
        Requires sufficient trade history (min 50 trades) before meaningful comparison.
        Not called automatically; must be wired to a periodic scheduler.
        """
        logger.debug(
            "_check_edge_decay: deferred (Phase 4+ pending) for hypothesis %s",
            hypothesis_id,
        )

    async def _check_hypothesis_validation(self, hypothesis_id: str) -> None:
        """
        Check if hypothesis meets in-sample promotion criteria (Gate 1):
        - Sample size >= 30 trades
        - Profit factor > 1.2
        - Win rate > 45%
        - Max drawdown < 30%
        If met: update HYPOTHESIS_REGISTRY status to IN_SAMPLE.
        OOS gate (Gate 2) is separate — requires human sign-off.

        STATUS: DEFERRED — Phase 4+ implementation pending.
        Requires HYPOTHESIS_REGISTRY implementation and min 30 closed trades.
        """
        logger.debug(
            "_check_hypothesis_validation: deferred (Phase 4+ pending) for hypothesis %s",
            hypothesis_id,
        )

    async def _run_weekly_summary(self) -> None:
        """
        Invoke SummarizerAgent (LLM) to produce narrative edge report.
        Output: advisory text only. Stored in journal. Never influences orders.

        STATUS: DEFERRED — SummarizerAgent not yet implemented.
        """
        logger.debug("_run_weekly_summary: deferred (SummarizerAgent not yet implemented)")

    def query_historical_analogs(
        self,
        hypothesis_id: str,
        direction: str,
        symbol: Optional[str] = None,
    ) -> dict:
        """
        Called by HistorianAgent (via Entry group) to get historical trade stats.
        Returns: {similar_trades_count, win_rate, avg_r_multiple,
                  common_failure_modes, last_10_outcomes}

        STATUS: DEFERRED — HistorianAgent not yet implemented.
        Returns empty dict until wired. EntryGroup._historian is always None
        in current runtime, so this path is never reached.
        """
        logger.debug(
            "query_historical_analogs: deferred (HistorianAgent not yet implemented) "
            "for hypothesis %s direction %s", hypothesis_id, direction,
        )
        return {}
