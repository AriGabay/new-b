"""
ObservationalReplayHarness — Phase 6.1 evidential pipeline observer.

Instruments the real runtime pipeline to measure:
  A. SIGNAL OCCURRENCE — H3-005 bars, candlestick bars, co-occurrence bars
  B. PROPOSAL FLOW    — proposals generated, score ranges, signal composition
  C. PANEL FLOW       — panel evaluations, approve/reject/abstain distributions
  D. DECISION FLOW    — enters vs holds, final decisions, risk outcomes
  E. POSITION FLOW    — natural opens, natural closes, exit reasons

Design principles:
  - NO forced approvals
  - NO special-casing pass conditions
  - NO control-mode contamination
  - Real runner (BtcBybitPaperRunner, simulation_mode=True)
  - Real panel (TraderEvaluatorPanel, APPROVE_THRESHOLD=14, MIN_AVG_SCORE=6.5)
  - Real final decision layer (FinalDecisionGroup)
  - Real risk layer (9 deterministic rules)
  - Real exit layer (ExitGroup)

The harness subscribes to the EventBus and captures all events.
It provides per-bar metrics and full-pipeline funnel reporting.

Source tag: event_driven_runtime_replay (real pipeline)
Phase: 6.1
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class BarObservation:
    """One bar's observed state across all pipeline stages."""
    bar_index: int
    timestamp: str
    close_price: float
    ema20: float
    ema50: float
    ema200: float
    ema_alignment: str        # full_bull | full_bear | partial_bull | partial_bear | mixed
    adx14: float
    rsi14: float
    volume_ratio: float

    h3005_fired: bool = False
    h3005_direction: Optional[str] = None
    candlestick_signals: list[str] = field(default_factory=list)
    indicator_signals: list[str] = field(default_factory=list)
    structure_signals: list[str] = field(default_factory=list)
    at_resistance: bool = False
    at_support: bool = False

    proposal_fired: bool = False
    proposal_direction: Optional[str] = None
    proposal_composite_score: Optional[float] = None
    proposal_signal_count: Optional[int] = None

    panel_evaluated: bool = False
    panel_approve_count: Optional[int] = None
    panel_avg_score: Optional[float] = None
    panel_decision: Optional[str] = None  # "enter" | "hold"

    final_decision: Optional[str] = None
    risk_approved: Optional[bool] = None
    risk_rejection_code: Optional[str] = None

    position_opened: bool = False
    position_closed: bool = False
    exit_reason: Optional[str] = None
    pnl_r: Optional[float] = None


@dataclass
class FunnelMetrics:
    """Aggregated funnel from bars → position opens."""
    fixture_name: str
    total_bars: int

    # Signal layer
    h3005_bars: int = 0
    h3005_long_bars: int = 0
    h3005_short_bars: int = 0
    candlestick_pattern_bars: int = 0
    h3005_and_candlestick_cooccurrence: int = 0
    at_resistance_bars: int = 0
    at_support_bars: int = 0

    # Proposal layer
    proposals_total: int = 0
    proposals_long: int = 0
    proposals_short: int = 0
    proposal_score_min: Optional[float] = None
    proposal_score_max: Optional[float] = None
    proposal_score_avg: Optional[float] = None

    # Panel layer
    panel_evaluations: int = 0
    panel_enters: int = 0
    panel_holds: int = 0
    panel_avg_score_across_reviews: Optional[float] = None
    panel_approve_count_distribution: dict = field(default_factory=dict)

    # Decision layer
    final_enters: int = 0
    final_holds: int = 0
    risk_approvals: int = 0
    risk_rejections: int = 0
    risk_rejection_codes: dict = field(default_factory=dict)

    # Position layer
    positions_opened: int = 0
    positions_closed: int = 0
    exit_reasons: dict = field(default_factory=dict)
    pnl_r_values: list[float] = field(default_factory=list)

    # Blocking analysis
    first_blocker: Optional[str] = None
    blocker_detail: Optional[str] = None

    def pass_rates(self) -> dict:
        def pct(n, d):
            return round(100 * n / d, 1) if d > 0 else 0.0
        return {
            "h3005_bars_pct": pct(self.h3005_bars, self.total_bars),
            "cooccurrence_pct": pct(self.h3005_and_candlestick_cooccurrence, self.h3005_bars),
            "proposals_per_h3005_pct": pct(self.proposals_total, self.h3005_bars),
            "panel_enter_rate": pct(self.panel_enters, self.panel_evaluations),
            "final_enter_rate": pct(self.final_enters, self.panel_enters) if self.panel_enters else 0.0,
            "risk_approval_rate": pct(self.risk_approvals, self.final_enters) if self.final_enters else 0.0,
            "open_rate": pct(self.positions_opened, self.risk_approvals) if self.risk_approvals else 0.0,
        }

    def determine_blocker(self) -> str:
        """Identify the stage where the funnel first hits zero."""
        if self.h3005_bars == 0:
            return "H3-005_never_fires"
        if self.h3005_and_candlestick_cooccurrence == 0:
            return "no_H3005_candlestick_cooccurrence"
        if self.proposals_total == 0:
            return "proposals_not_generated_despite_cooccurrence"
        if self.panel_evaluations == 0:
            return "proposals_not_reaching_panel"
        if self.panel_enters == 0:
            return "panel_rejects_all_proposals"
        if self.final_enters == 0:
            return "final_decision_holds_all_panel_enters"
        if self.risk_approvals == 0:
            return "risk_rejects_all_final_enters"
        if self.positions_opened == 0:
            return "position_open_blocked_after_risk"
        return "none_positions_opened"


@dataclass
class ObservationalReport:
    """Complete Phase 6.1 observational report for one fixture run."""
    fixture_name: str
    fixture_description: str
    run_timestamp: str
    bars_processed: int
    funnel: FunnelMetrics
    bar_observations: list[BarObservation]
    h3005_bar_details: list[dict]
    proposal_details: list[dict]
    panel_decision_details: list[dict]
    position_details: list[dict]
    errors: list[str]
    conclusion: str
    next_blocker: Optional[str]


# ─── Harness ──────────────────────────────────────────────────────────────────

class ObservationalReplayHarness:
    """
    Instruments the real BtcBybitPaperRunner pipeline.

    Usage:
        harness = ObservationalReplayHarness()
        await harness.setup()
        report = await harness.run_fixture(fixture)
        await harness.teardown()
    """

    def __init__(self, journal_db_path: str = ":memory:") -> None:
        self._runner = None
        self._journal_db_path = journal_db_path
        self._bar_index = 0
        self._current_bar_obs: Optional[BarObservation] = None
        self._bar_observations: list[BarObservation] = []
        self._proposals: list[dict] = []
        self._panel_decisions: list[dict] = []
        self._position_events: list[dict] = []
        self._errors: list[str] = []

        # Per-bar accumulation maps (reset each bar)
        self._bar_h3005: dict = {}          # symbol → {fired, direction}
        self._bar_candlestick: dict = {}    # symbol → list[subtype]
        self._bar_indicators: dict = {}     # symbol → list[subtype]
        self._bar_structure: dict = {}      # symbol → {at_resistance, at_support}

    async def setup(self) -> None:
        from runtime.runner import BtcBybitPaperRunner
        self._runner = BtcBybitPaperRunner(
            simulation_mode=True,
            journal_db_path=self._journal_db_path,
        )
        await self._runner.setup()
        await self._subscribe_observers()
        logger.info("ObservationalReplayHarness: setup complete (real pipeline, no forcing).")

    async def _subscribe_observers(self) -> None:
        """Subscribe to all relevant events for instrumentation."""
        from core.events import (
            GroupSignalEvent, CandidateTradeEvent, PanelApprovedProposalEvent,
            RiskDecisionEvent, PositionOpenEvent, PositionCloseEvent,
        )
        bus = self._runner.bus
        await bus.subscribe(GroupSignalEvent, self._on_group_signal)
        await bus.subscribe(CandidateTradeEvent, self._on_candidate_trade)
        await bus.subscribe(PanelApprovedProposalEvent, self._on_panel_approved)
        await bus.subscribe(RiskDecisionEvent, self._on_risk_decision)
        await bus.subscribe(PositionOpenEvent, self._on_position_open)
        await bus.subscribe(PositionCloseEvent, self._on_position_close)

    async def _on_group_signal(self, event) -> None:
        bundle = getattr(event, "bundle", None)
        if bundle is None:
            return
        symbol = getattr(bundle, "symbol", "")
        group_id = str(getattr(bundle, "group_id", "")).lower()
        signals = getattr(bundle, "signals", [])

        for sig in signals:
            hyp = getattr(sig, "hypothesis_ref", "")
            subtype = getattr(sig, "signal_subtype", "")
            direction = str(getattr(sig, "direction", ""))

            if hyp == "H3-005":
                self._bar_h3005[symbol] = {"fired": True, "direction": direction}
                if self._current_bar_obs and self._current_bar_obs:
                    self._current_bar_obs.h3005_fired = True
                    self._current_bar_obs.h3005_direction = direction

            if "candlestick" in group_id:
                if symbol not in self._bar_candlestick:
                    self._bar_candlestick[symbol] = []
                self._bar_candlestick[symbol].append(subtype)
                if self._current_bar_obs:
                    if subtype not in self._current_bar_obs.candlestick_signals:
                        self._current_bar_obs.candlestick_signals.append(subtype)

            if "indicators" in group_id:
                if symbol not in self._bar_indicators:
                    self._bar_indicators[symbol] = []
                self._bar_indicators[symbol].append(subtype)
                if self._current_bar_obs:
                    if subtype not in self._current_bar_obs.indicator_signals:
                        self._current_bar_obs.indicator_signals.append(subtype)

            if "technical" in group_id or "structure" in group_id:
                if symbol not in self._bar_structure:
                    self._bar_structure[symbol] = {}
                structural = getattr(bundle, "structural", None)
                if structural:
                    self._bar_structure[symbol]["at_resistance"] = getattr(structural, "at_resistance", False)
                    self._bar_structure[symbol]["at_support"] = getattr(structural, "at_support", False)
                    if self._current_bar_obs:
                        self._current_bar_obs.at_resistance = getattr(structural, "at_resistance", False)
                        self._current_bar_obs.at_support = getattr(structural, "at_support", False)

    async def _on_candidate_trade(self, event) -> None:
        proposal = getattr(event, "proposal", None)
        if proposal is None:
            return
        direction = str(getattr(proposal, "direction", ""))
        comp_score = getattr(proposal, "composite_score", None)
        signals = getattr(proposal, "contributing_signals", []) or []
        d = {
            "bar_index": self._bar_index,
            "direction": direction,
            "composite_score": float(comp_score) if comp_score else None,
            "signal_count": len(signals),
            "proposal_id": getattr(proposal, "proposal_id", ""),
        }
        self._proposals.append(d)
        if self._current_bar_obs:
            self._current_bar_obs.proposal_fired = True
            self._current_bar_obs.proposal_direction = direction
            self._current_bar_obs.proposal_composite_score = d["composite_score"]
            self._current_bar_obs.proposal_signal_count = d["signal_count"]
        logger.info(
            "ObsReplay: CandidateTradeEvent bar=%d direction=%s composite=%.4f signals=%d",
            self._bar_index, direction, d["composite_score"] or 0, d["signal_count"],
        )

    async def _on_panel_approved(self, event) -> None:
        d = {
            "bar_index": self._bar_index,
            "panel_approve_count": getattr(event, "panel_approve_count", 0),
            "panel_avg_score": getattr(event, "panel_avg_score", 0.0),
            "panel_decision": getattr(event, "panel_decision", "enter"),
            "packet_id": getattr(event, "packet_id", ""),
        }
        self._panel_decisions.append(d)
        if self._current_bar_obs:
            self._current_bar_obs.panel_evaluated = True
            self._current_bar_obs.panel_approve_count = d["panel_approve_count"]
            self._current_bar_obs.panel_avg_score = d["panel_avg_score"]
            self._current_bar_obs.panel_decision = d["panel_decision"]
            self._current_bar_obs.final_decision = "enter"
        logger.info(
            "ObsReplay: PanelApproved bar=%d approvals=%d avg=%.2f",
            self._bar_index, d["panel_approve_count"], d["panel_avg_score"],
        )

    async def _on_risk_decision(self, event) -> None:
        approved = getattr(event, "approved", False)
        rejection = getattr(event, "rejection", None)
        rej_code = None
        if rejection:
            rej_code = str(getattr(rejection, "rejection_code", ""))
        if self._current_bar_obs:
            self._current_bar_obs.risk_approved = approved
            self._current_bar_obs.risk_rejection_code = rej_code
        logger.info(
            "ObsReplay: RiskDecision bar=%d approved=%s code=%s",
            self._bar_index, approved, rej_code,
        )

    async def _on_position_open(self, event) -> None:
        pos = getattr(event, "position", None)
        if pos is None:
            return
        d = {
            "bar_index": self._bar_index,
            "symbol": getattr(pos, "symbol", ""),
            "direction": str(getattr(pos, "direction", "")),
            "entry_price": float(getattr(pos, "entry_price", 0)),
            "stop_price": float(getattr(pos, "stop_price", 0)),
            "target_price": float(getattr(pos, "target_price", 0)),
            "position_size_usd": float(getattr(pos, "position_size_usd", 0)),
            "position_id": getattr(pos, "position_id", ""),
        }
        self._position_events.append({"type": "open", **d})
        if self._current_bar_obs:
            self._current_bar_obs.position_opened = True
        logger.info(
            "ObsReplay: PositionOpen bar=%d %s @ %.0f stop=%.0f target=%.0f",
            self._bar_index, d["direction"], d["entry_price"],
            d["stop_price"], d["target_price"],
        )

    async def _on_position_close(self, event) -> None:
        sig = getattr(event, "exit_signal", None)
        pos = getattr(event, "final_position", None)
        if sig is None:
            return
        exit_reason = str(getattr(sig, "exit_reason", ""))
        pnl_r = getattr(sig, "pnl_r", None)
        d = {
            "bar_index": self._bar_index,
            "exit_reason": exit_reason,
            "pnl_r": float(pnl_r) if pnl_r is not None else None,
            "exit_price": float(getattr(sig, "exit_price", 0)),
            "bars_held": getattr(sig, "bars_held", 0),
        }
        self._position_events.append({"type": "close", **d})
        if self._current_bar_obs:
            self._current_bar_obs.position_closed = True
            self._current_bar_obs.exit_reason = exit_reason
            self._current_bar_obs.pnl_r = d["pnl_r"]
        logger.info(
            "ObsReplay: PositionClose bar=%d reason=%s pnl_r=%s",
            self._bar_index, exit_reason, pnl_r,
        )

    async def teardown(self) -> None:
        if self._runner:
            await self._runner.teardown()
            self._runner = None

    async def run_fixture(self, fixture) -> ObservationalReport:
        """
        Run a fixture through the real pipeline and return an ObservationalReport.
        NO forced approvals. NO special-casing. Pure observation.
        """
        self._bar_index = 0
        self._bar_observations = []
        self._proposals = []
        self._panel_decisions = []
        self._position_events = []
        self._errors = []

        fvs = fixture.feature_vectors
        logger.info(
            "ObservationalReplayHarness: running fixture '%s' (%d bars).",
            fixture.name, len(fvs),
        )

        for i, fv in enumerate(fvs):
            self._bar_index = i

            # Build bar observation from feature vector
            ema20 = float(fv.ema20)
            ema50 = float(fv.ema50)
            ema200 = float(fv.ema200)

            if ema20 > ema50 > ema200:
                alignment = "full_bull"
            elif ema20 < ema50 < ema200:
                alignment = "full_bear"
            elif ema20 > ema50:
                alignment = "partial_bull"
            elif ema20 < ema50:
                alignment = "partial_bear"
            else:
                alignment = "mixed"

            obs = BarObservation(
                bar_index=i,
                timestamp=fv.timestamp.isoformat() if hasattr(fv.timestamp, "isoformat") else str(fv.timestamp),
                close_price=float(fv.close),
                ema20=ema20,
                ema50=ema50,
                ema200=ema200,
                ema_alignment=alignment,
                adx14=float(fv.adx14),
                rsi14=float(fv.rsi14),
                volume_ratio=float(fv.volume_ratio),
            )
            self._current_bar_obs = obs

            # Reset per-bar accumulators
            symbol = fv.symbol
            self._bar_h3005.clear()
            self._bar_candlestick.clear()
            self._bar_indicators.clear()
            self._bar_structure.clear()

            # Feed through the real pipeline
            try:
                await self._runner.simulate_bar(fv)
                # Small yield to allow async event propagation
                await asyncio.sleep(0)
            except Exception as e:
                self._errors.append(f"bar {i}: {e}")
                logger.error("ObsReplay bar %d error: %s", i, e)

            self._bar_observations.append(obs)
            self._current_bar_obs = None

        return self._build_report(fixture)

    def _build_report(self, fixture) -> ObservationalReport:
        """Aggregate observations into a complete report."""
        total = len(self._bar_observations)
        funnel = FunnelMetrics(fixture_name=fixture.name, total_bars=total)

        h3005_bars = []
        proposal_details = []
        proposal_scores = []
        panel_score_sum = 0.0
        panel_score_count = 0

        for obs in self._bar_observations:
            if obs.h3005_fired:
                funnel.h3005_bars += 1
                if obs.h3005_direction == "Direction.LONG" or obs.h3005_direction == "LONG":
                    funnel.h3005_long_bars += 1
                else:
                    funnel.h3005_short_bars += 1
                h3005_bars.append({
                    "bar_index": obs.bar_index,
                    "direction": obs.h3005_direction,
                    "close": obs.close_price,
                    "ema20": obs.ema20,
                    "ema50": obs.ema50,
                    "adx14": obs.adx14,
                    "rsi14": obs.rsi14,
                    "volume_ratio": obs.volume_ratio,
                    "candlestick_signals": obs.candlestick_signals,
                    "at_resistance": obs.at_resistance,
                    "at_support": obs.at_support,
                    "proposal_fired": obs.proposal_fired,
                    "ema_alignment": obs.ema_alignment,
                })

            if obs.candlestick_signals:
                funnel.candlestick_pattern_bars += 1

            if obs.h3005_fired and obs.candlestick_signals:
                funnel.h3005_and_candlestick_cooccurrence += 1

            if obs.at_resistance:
                funnel.at_resistance_bars += 1
            if obs.at_support:
                funnel.at_support_bars += 1

            if obs.proposal_fired:
                funnel.proposals_total += 1
                d = (obs.proposal_direction or "").upper()
                if "LONG" in d:
                    funnel.proposals_long += 1
                elif "SHORT" in d:
                    funnel.proposals_short += 1
                if obs.proposal_composite_score is not None:
                    proposal_scores.append(obs.proposal_composite_score)
                proposal_details.append({
                    "bar_index": obs.bar_index,
                    "direction": obs.proposal_direction,
                    "composite_score": obs.proposal_composite_score,
                    "signal_count": obs.proposal_signal_count,
                    "h3005_present": obs.h3005_fired,
                    "candlestick_present": bool(obs.candlestick_signals),
                    "panel_evaluate": obs.panel_evaluated,
                    "panel_decision": obs.panel_decision,
                    "panel_approvals": obs.panel_approve_count,
                    "panel_avg": obs.panel_avg_score,
                    "risk_approved": obs.risk_approved,
                    "position_opened": obs.position_opened,
                })

            if obs.panel_evaluated:
                funnel.panel_evaluations += 1
                if obs.panel_decision == "enter":
                    funnel.panel_enters += 1
                else:
                    funnel.panel_holds += 1
                if obs.panel_avg_score is not None:
                    panel_score_sum += obs.panel_avg_score
                    panel_score_count += 1
                if obs.panel_approve_count is not None:
                    key = str(obs.panel_approve_count)
                    funnel.panel_approve_count_distribution[key] = (
                        funnel.panel_approve_count_distribution.get(key, 0) + 1
                    )

            if obs.final_decision == "enter":
                funnel.final_enters += 1

            if obs.risk_approved is True:
                funnel.risk_approvals += 1
            elif obs.risk_approved is False:
                funnel.risk_rejections += 1
                if obs.risk_rejection_code:
                    funnel.risk_rejection_codes[obs.risk_rejection_code] = (
                        funnel.risk_rejection_codes.get(obs.risk_rejection_code, 0) + 1
                    )

            if obs.position_opened:
                funnel.positions_opened += 1
            if obs.position_closed:
                funnel.positions_closed += 1
                if obs.exit_reason:
                    funnel.exit_reasons[obs.exit_reason] = (
                        funnel.exit_reasons.get(obs.exit_reason, 0) + 1
                    )
                if obs.pnl_r is not None:
                    funnel.pnl_r_values.append(obs.pnl_r)

        # Score stats
        if proposal_scores:
            funnel.proposal_score_min = round(min(proposal_scores), 4)
            funnel.proposal_score_max = round(max(proposal_scores), 4)
            funnel.proposal_score_avg = round(sum(proposal_scores) / len(proposal_scores), 4)

        if panel_score_count > 0:
            funnel.panel_avg_score_across_reviews = round(panel_score_sum / panel_score_count, 2)

        funnel.first_blocker = funnel.determine_blocker()

        # Panel decision details
        panel_decision_details = self._panel_decisions.copy()

        # Position details
        position_details = self._position_events.copy()

        # Build conclusion
        conclusion = self._build_conclusion(funnel)
        next_blocker = funnel.first_blocker if funnel.positions_opened == 0 else None

        return ObservationalReport(
            fixture_name=fixture.name,
            fixture_description=fixture.description,
            run_timestamp=datetime.utcnow().isoformat() + "Z",
            bars_processed=total,
            funnel=funnel,
            bar_observations=self._bar_observations,
            h3005_bar_details=h3005_bars,
            proposal_details=proposal_details,
            panel_decision_details=panel_decision_details,
            position_details=position_details,
            errors=self._errors,
            conclusion=conclusion,
            next_blocker=next_blocker,
        )

    def _build_conclusion(self, f: FunnelMetrics) -> str:
        if f.positions_opened > 0:
            return (
                f"NATURAL POSITIONS OPENED: {f.positions_opened} open, {f.positions_closed} closed. "
                f"Pipeline fully viable for this fixture. "
                f"Panel approvals: {f.panel_enters}/{f.panel_evaluations}. "
                f"Risk approvals: {f.risk_approvals}."
            )
        blocker = f.first_blocker
        if blocker == "H3-005_never_fires":
            return (
                "ZERO NATURAL OPENS. BLOCKER: H3-005 never fires in this fixture. "
                "No bars satisfy full EMA alignment + price-near-EMA20 + ADX>=25 + volume>=1.0 + RSI 35-65. "
                "Fixture does not cover established-trend pullback conditions."
            )
        if blocker == "no_H3005_candlestick_cooccurrence":
            return (
                f"ZERO NATURAL OPENS. BLOCKER: H3-005 fired on {f.h3005_bars} bars "
                f"but no candlestick pattern appeared on the same bars. "
                f"Candlestick patterns were seen on {f.candlestick_pattern_bars} bars total. "
                "The candlestick gate prevents pure indicator proposals from reaching the panel."
            )
        if blocker == "proposals_not_generated_despite_cooccurrence":
            return (
                f"ZERO NATURAL OPENS. BLOCKER: H3-005 + candlestick co-occurred "
                f"{f.h3005_and_candlestick_cooccurrence} times but 0 proposals generated. "
                "Likely cause: composite_score < 0.50 threshold or direction conflict suppressed proposal."
            )
        if blocker == "panel_rejects_all_proposals":
            return (
                f"ZERO NATURAL OPENS. BLOCKER: Panel evaluated {f.panel_evaluations} proposal(s). "
                f"All held. Panel avg_score = {f.panel_avg_score_across_reviews or '?'}. "
                "Panel threshold not met (require 14/20 approve + avg>=6.5). "
                "Signal quality insufficient for current panel policy."
            )
        if blocker == "risk_rejects_all_final_enters":
            return (
                f"ZERO NATURAL OPENS. BLOCKER: Risk gate rejected {f.risk_rejections} proposal(s). "
                f"Codes: {f.risk_rejection_codes}."
            )
        if blocker == "none_positions_opened":
            return (
                f"ZERO NATURAL OPENS despite {f.risk_approvals} risk approvals. "
                "Unexpected: investigate position open chain."
            )
        return f"ZERO NATURAL OPENS. Blocker: {blocker}."
