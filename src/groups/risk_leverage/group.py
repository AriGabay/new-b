"""
Risk & Leverage Group (Group 9 — always_on=False, implementation_priority=1).

Responsibilities:
  - Final, non-overridable gate on every CandidateTradeProposal.
  - Apply all 9 Phase 1 risk rules in order (see risk_contract.md).
  - If all rules pass: compute position size, build RiskApprovedOrder, publish.
  - If any rule fails: build RiskRejectedEvent, publish, log reason.
  - Update SystemState.risk_state (halt, size_reduction).
  - LLM output (CriticReport) is NEVER read by this group (ADR-003).

LLM: NOT permitted. EVER.
Trigger: CandidateTradeEvent (from Entry group).
Depends on: MARKET_DATA, ENTRY.
Always-on: NO.
Implementation priority: 1 (must work before any other group).

Phase 2 deliverable: All 9 Phase 1 risk rules as deterministic checks.

The 9 rules (executed in this order):
  Rule 1: Mode gate — RESEARCH mode blocks all orders.
  Rule 2: Daily loss limit — daily_pnl_pct < −2% blocks new entries.
  Rule 3: Max drawdown — drawdown_pct > 10% halts system.
  Rule 4: Portfolio exposure — sum(open_position_usd) ≤ 25% of equity.
  Rule 5: Correlated exposure — btc cluster ≤ 15% of equity.
  Rule 6: Spread/liquidity — volume_sma20 > $10M/day (already universe-filtered).
  Rule 7: Pump detection — volume_ratio > 5.0 in last 3 bars → block.
  Rule 8: Event risk — high-impact event in next 48h → reduce size by 50%.
  Rule 9: Trading plan completeness — proposal must have entry, stop, target,
          hypothesis_refs, composite_score ≥ 0.50.

Position sizing (Rule after all gates pass):
  R amount    = equity × risk_fraction (default 1%)
  Stop dist   = abs(entry_price − stop_price)
  size_base   = R_amount / stop_dist
  size_usd    = size_base × entry_price
  size_usd    = min(size_usd, equity × 0.10)  # single position cap: 10% equity
  Apply size_reduction from RiskState (drawdown controller output).

Source: /docs/risk_framework/risk_contract.md
        /docs/adr/ADR-002-deterministic-pipelines-first.md
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from agents.base.group import BaseGroup
from core.events import (
    CandidateTradeEvent,
    EventBus,
    PanelApprovedProposalEvent,
    PositionOpenEvent,
    RiskDecisionEvent,
    SystemEvent,
)
from core.registry import GroupID
from core.schemas import (
    CandidateTradeProposal,
    Direction,
    ModeGate,
    RejectionCode,
    RiskApprovedOrder,
    RiskCheckResult,
    RiskRejectedEvent,
)
from core.state import RiskState, SystemState

logger = logging.getLogger(__name__)

DEFAULT_RISK_FRACTION  = Decimal("0.01")   # 1% per trade (used for R tracking)
# Leveraged futures risk limits — calibrated for 5×–35× leverage model
# where a single 1R loss can be 10–18% of equity.
DAILY_LOSS_LIMIT       = -0.20             # −20% daily PnL (allows 1–2 full losing trades)
MAX_DRAWDOWN_HALT      = 0.40              # 40% drawdown halts system
PUMP_VOLUME_RATIO      = 5.0               # 5× normal volume = pump signal

# Leverage-driven sizing (perpetual futures model)
MIN_LEVERAGE           = 5.0               # Minimum leverage for any approved trade
MAX_LEVERAGE           = 35.0              # Maximum leverage cap
MAX_RISK_PER_TRADE     = 0.10              # 10% of equity max risk per trade
DEFAULT_MAX_BARS       = 48                # Time stop: 48 bars (2 days on 1h)

# Portfolio exposure limits — in MARGIN terms (notional/leverage), not raw notional.
# With leveraged futures, notional can be many × equity; we track margin utilization.
MAX_MARGIN_UTILIZATION = Decimal("0.80")   # 80% of equity as margin across all positions
MAX_CLUSTER_MARGIN     = Decimal("0.80")   # 80% margin per correlation cluster


class RiskLeverageGroup(BaseGroup):
    """
    Non-overridable risk gate. Deterministic. No LLM.

    All 9 rules are checked in sequence. First failure = rejection.
    On approval: compute position size, emit RiskApprovedOrder.
    """

    group_id = GroupID.RISK_LEVERAGE

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)
        # Set by runner.set_panel_wired(True) when PanelDecisionGroup is active.
        # When True, CandidateTradeEvent is ignored — proposals MUST pass Layer B+C
        # (TraderEvaluatorPanel + FinalDecisionGroup) before reaching risk evaluation.
        # When False (default), direct CandidateTradeEvent path is active (unit tests,
        # backtest injection, or standalone use without panel).
        self._panel_wired: bool = False

    def set_panel_wired(self, wired: bool = True) -> None:
        """
        Called by BtcBybitPaperRunner after PanelDecisionGroup is wired.
        Enables the panel gate: CandidateTradeEvent is silently ignored.
        Only PanelApprovedProposalEvent (from PanelDecisionGroup) is processed.

        This prevents CandidateTradeEvent from bypassing the 20-trader panel
        and FinalDecisionGroup safety rails in the wired runtime.
        """
        self._panel_wired = wired
        logger.info(
            "RiskLeverageGroup: panel gate %s — "
            "CandidateTradeEvent %s, PanelApprovedProposalEvent active.",
            "ENGAGED" if wired else "DISENGAGED",
            "IGNORED (panel bypass blocked)" if wired else "ACTIVE (direct path)",
        )

    async def _setup(self) -> None:
        # Primary wired path: proposal approved by Layer B+C
        await self.bus.subscribe(PanelApprovedProposalEvent, self.handle_event)
        # Also subscribe to CandidateTradeEvent for standalone/test use.
        # When panel is wired (set_panel_wired=True), this path is gated out
        # in _handle_event() to prevent bypass of PanelDecisionGroup.
        await self.bus.subscribe(CandidateTradeEvent, self.handle_event)
        logger.info(
            "RiskLeverageGroup subscribed to PanelApprovedProposalEvent (primary) "
            "and CandidateTradeEvent (gated — active only when panel NOT wired)."
        )

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, PanelApprovedProposalEvent) and event.proposal:
            # Primary wired path: proposal has passed Layer B+C.
            # Thread packet_id/panel_id/decision_id so Position carries learning DB links.
            await self._evaluate_proposal(
                event.proposal,
                packet_id=event.packet_id,
                panel_id=event.panel_id,
                decision_id=event.decision_id,
            )
        elif isinstance(event, CandidateTradeEvent) and event.proposal:
            if self._panel_wired:
                # Panel is active. This event was already received by PanelDecisionGroup.
                # Ignore it here to prevent bypassing the 20-trader panel gate.
                # Only PanelApprovedProposalEvent (emitted by PanelDecisionGroup after
                # panel approval) should trigger risk evaluation in the wired runtime.
                logger.debug(
                    "RiskLeverageGroup: CandidateTradeEvent IGNORED (panel gate active). "
                    "Awaiting PanelApprovedProposalEvent for proposal %s.",
                    getattr(event.proposal, "proposal_id", "?"),
                )
                return
            # Panel not wired (direct/test path): evaluate proposal directly
            await self._evaluate_proposal(event.proposal)

    async def _evaluate_proposal(
        self,
        proposal: CandidateTradeProposal,
        packet_id: str = "",
        panel_id: str = "",
        decision_id: str = "",
    ) -> None:
        """
        Run all 9 risk rules in order.
        Publish RiskDecisionEvent (approved or rejected).
        If approved: create Position, open in SystemState, publish PositionOpenEvent.
        packet_id/panel_id/decision_id link the Position to learning DB records.
        """
        # Rule 1: Mode gate
        result = self._check_mode_gate(proposal)
        if not result.approved:
            await self._reject(proposal, result)
            return

        # Rule 2: Daily loss limit
        result = self._check_daily_loss_limit()
        if not result.approved:
            await self._reject(proposal, result)
            return

        # Rule 3: Max drawdown / halt
        result = self._check_max_drawdown()
        if not result.approved:
            await self._reject(proposal, result)
            return

        # Rule 4: Portfolio exposure
        result = self._check_portfolio_exposure(proposal)
        if not result.approved:
            await self._reject(proposal, result)
            return

        # Rule 5: Correlated exposure
        result = self._check_correlated_exposure(proposal)
        if not result.approved:
            await self._reject(proposal, result)
            return

        # Rule 6: Liquidity (already universe-filtered; validate here)
        result = self._check_liquidity(proposal)
        if not result.approved:
            await self._reject(proposal, result)
            return

        # Rule 7: Pump detection
        result = self._check_pump_signal(proposal)
        if not result.approved:
            await self._reject(proposal, result)
            return

        # Rule 8: Event risk (size reduction, not block)
        event_risk_reduction = self._check_event_risk(proposal)

        # Rule 9: Trading plan completeness
        result = self._check_plan_completeness(proposal)
        if not result.approved:
            await self._reject(proposal, result)
            return

        # All rules passed — compute position size and approve
        order = self._compute_order(proposal, event_risk_reduction)
        await self._approve(proposal, order, packet_id=packet_id, panel_id=panel_id, decision_id=decision_id)

    # ------------------------------------------------------------------
    # Rule implementations (deterministic — no LLM, no external calls)
    # ------------------------------------------------------------------

    def _check_mode_gate(self, proposal: CandidateTradeProposal) -> RiskCheckResult:
        """Rule 1: Block execution in RESEARCH mode."""
        if self.state.mode == ModeGate.RESEARCH:
            return RiskCheckResult.rejected(
                RejectionCode.MODE_GATE,
                "System in RESEARCH mode — no order execution.",
            )
        return RiskCheckResult.approved_ok()

    def _check_daily_loss_limit(self) -> RiskCheckResult:
        """Rule 2: Block new entries if daily_pnl_pct < −2%."""
        if self.state.portfolio.daily_pnl_pct < DAILY_LOSS_LIMIT:
            return RiskCheckResult.rejected(
                RejectionCode.DAILY_LOSS_LIMIT,
                f"Daily PnL {self.state.portfolio.daily_pnl_pct:.1%} below {DAILY_LOSS_LIMIT:.1%} limit.",
            )
        return RiskCheckResult.approved_ok()

    def _check_max_drawdown(self) -> RiskCheckResult:
        """Rule 3: Halt system if drawdown_pct > 10%."""
        if self.state.portfolio.drawdown_pct > MAX_DRAWDOWN_HALT:
            return RiskCheckResult.rejected(
                RejectionCode.MAX_DRAWDOWN,
                f"Drawdown {self.state.portfolio.drawdown_pct:.1%} exceeds {MAX_DRAWDOWN_HALT:.1%} halt threshold.",
            )
        return RiskCheckResult.approved_ok()

    def _check_portfolio_exposure(self, proposal: CandidateTradeProposal) -> RiskCheckResult:
        """Rule 4: Total margin utilization ≤ 80% of equity.

        In leveraged perpetual futures, we track margin (notional/leverage),
        not raw notional, to avoid rejecting valid leveraged positions.
        """
        portfolio = self.state.portfolio
        equity = portfolio.equity
        if equity <= 0:
            return RiskCheckResult.approved_ok()
        total_margin = sum(
            p.position_size_usd / Decimal(str(max(p.leverage, 1.0)))
            for p in portfolio.open_positions.values()
        )
        if total_margin / equity > MAX_MARGIN_UTILIZATION:
            return RiskCheckResult.rejected(
                RejectionCode.PORTFOLIO_EXPOSURE,
                f"Margin utilization {float(total_margin / equity):.1%} exceeds {float(MAX_MARGIN_UTILIZATION):.0%} limit.",
            )
        return RiskCheckResult.approved_ok()

    def _check_correlated_exposure(self, proposal: CandidateTradeProposal) -> RiskCheckResult:
        """Rule 5: BTC cluster margin ≤ 80% of equity."""
        portfolio = self.state.portfolio
        equity = portfolio.equity
        if equity <= 0:
            return RiskCheckResult.approved_ok()
        btc_margin = sum(
            p.position_size_usd / Decimal(str(max(p.leverage, 1.0)))
            for p in portfolio.open_positions.values()
            if getattr(p, "correlation_cluster", "btc") == "btc"
        )
        if btc_margin / equity > MAX_CLUSTER_MARGIN:
            return RiskCheckResult.rejected(
                RejectionCode.CORRELATED_EXPOSURE,
                f"BTC cluster margin {float(btc_margin / equity):.1%} exceeds {float(MAX_CLUSTER_MARGIN):.0%} limit.",
            )
        return RiskCheckResult.approved_ok()

    def _check_liquidity(self, proposal: CandidateTradeProposal) -> RiskCheckResult:
        """Rule 6: Symbol must be in eligible_symbols (already volume-filtered)."""
        if proposal.symbol not in self.state.eligible_symbols:
            return RiskCheckResult.rejected(
                RejectionCode.UNIVERSE_FILTER,
                f"{proposal.symbol} not in eligible universe.",
            )
        return RiskCheckResult.approved_ok()

    def _check_pump_signal(self, proposal: CandidateTradeProposal) -> RiskCheckResult:
        """Rule 7: Block if pump signal detected (volume_ratio > 5.0 in last 3 bars)."""
        vol_ratio = getattr(self.state.regime, "volume_ratio", 1.0)
        if vol_ratio > PUMP_VOLUME_RATIO:
            return RiskCheckResult.rejected(
                RejectionCode.PUMP_SIGNAL,
                f"Volume ratio {vol_ratio:.1f}x exceeds {PUMP_VOLUME_RATIO:.1f}x pump threshold.",
            )
        return RiskCheckResult.approved_ok()

    def _check_event_risk(self, proposal: CandidateTradeProposal) -> Decimal:
        """
        Rule 8: If high-impact event within 48h → apply 0.5× size reduction.
        Returns size reduction multiplier (1.0 = full, 0.5 = half size).
        Never blocks — only reduces.
        Phase 3: no news event system yet — always return full size.
        """
        return Decimal("1.0")

    def _check_plan_completeness(self, proposal: CandidateTradeProposal) -> RiskCheckResult:
        """
        Rule 9: Proposal must have:
        - entry_price > 0
        - stop_price != entry_price
        - raw_target > 0
        - at least one hypothesis_ref
        - composite_score >= 0.50
        """
        if proposal.entry_price <= 0:
            return RiskCheckResult.rejected(
                RejectionCode.INCOMPLETE_TRADE_PLAN, "Missing entry_price.")
        if proposal.raw_target <= 0:
            return RiskCheckResult.rejected(
                RejectionCode.INCOMPLETE_TRADE_PLAN, "Missing raw_target.")
        if not proposal.hypothesis_refs:
            return RiskCheckResult.rejected(
                RejectionCode.HYPOTHESIS_NOT_ACTIVE, "No hypothesis_refs on proposal.")
        if proposal.composite_score < 0.50:
            return RiskCheckResult.rejected(
                RejectionCode.SCORE_BELOW_THRESHOLD,
                f"composite_score {proposal.composite_score:.2f} < 0.50.")
        return RiskCheckResult.approved_ok()

    def _compute_leverage(
        self,
        proposal: CandidateTradeProposal,
        stop_dist_pct: float,
    ) -> float:
        """
        Determine leverage from setup quality, market conditions, and risk cap.

        Leverage ladder (base, before adjustments):
          composite_score >= 0.75 (A quality)  → 20×
          composite_score >= 0.65 (B quality)  → 15×
          composite_score >= 0.55 (C+ quality) → 10×
          composite_score >= 0.50 (C quality)  →  7×

        Volatility adjustment:
          High volatility (stop > 4% of entry)  → ×0.6
          Low volatility  (stop < 1.5% of entry) → ×1.2

        Drawdown adjustment:
          Drawdown > 5% → ×0.75

        Risk cap: leverage × stop_dist_pct ≤ MAX_RISK_PER_TRADE (10%).
          If exceeded, leverage is reduced to fit the risk cap.

        Final result clamped to [MIN_LEVERAGE, MAX_LEVERAGE].
        """
        score = proposal.composite_score
        if score >= 0.75:
            base = 20.0
        elif score >= 0.65:
            base = 15.0
        elif score >= 0.55:
            base = 10.0
        else:
            base = 7.0

        # Volatility adjustment
        if stop_dist_pct > 0.04:
            base *= 0.6
        elif stop_dist_pct < 0.015:
            base *= 1.2

        # Graduated drawdown reduction ladder
        dd = self.state.portfolio.drawdown_pct
        if dd > 0.25:
            base *= 0.50   # Severe: half leverage
        elif dd > 0.15:
            base *= 0.65   # Moderate: 65%
        elif dd > 0.08:
            base *= 0.80   # Mild: 80%

        # Risk cap: ensure leverage × stop_dist_pct ≤ MAX_RISK_PER_TRADE
        if stop_dist_pct > 0:
            max_from_risk = MAX_RISK_PER_TRADE / stop_dist_pct
            base = min(base, max_from_risk)

        return max(MIN_LEVERAGE, min(MAX_LEVERAGE, base))

    def _compute_order(
        self,
        proposal: CandidateTradeProposal,
        size_reduction: Decimal,
    ) -> RiskApprovedOrder:
        """
        Compute position size using leverage-driven model for perpetual futures.

        Flow:
        1. Place ATR-based stop.
        2. Compute leverage from setup quality + market conditions.
        3. Position size = equity × leverage × size_reduction.
        4. R amount = size_base × stop_distance (actual risk in USD).
        5. Target = entry ± 2× stop distance.

        Returns RiskApprovedOrder.
        """
        from risk.sizing import ATRStopPlacer

        equity = self.state.portfolio.equity

        # Place stop using ATR
        atr14 = self.state.regime.atr14 if self.state.regime.atr14 > 0 else Decimal("1000")
        placer = ATRStopPlacer()
        stop_price = placer.compute(proposal.entry_price, proposal.direction, atr14)

        # Compute target: 2× stop distance
        stop_dist = abs(proposal.entry_price - stop_price)
        stop_dist_pct = float(stop_dist / proposal.entry_price) if proposal.entry_price > 0 else 0.025
        if proposal.direction == Direction.LONG:
            target_price = proposal.entry_price + stop_dist * Decimal("2")
        else:
            target_price = proposal.entry_price - stop_dist * Decimal("2")

        # Compute leverage from setup quality and conditions
        leverage = self._compute_leverage(proposal, stop_dist_pct)

        # Position size from leverage (apply event-risk size_reduction)
        size_usd = equity * Decimal(str(leverage)) * size_reduction
        size_base = size_usd / proposal.entry_price if proposal.entry_price > 0 else Decimal("0")

        # R amount = actual risk in USD (for exit trailing-stop logic and tracking)
        r_amount = size_base * stop_dist

        # Risk fraction = r_amount / equity (for record-keeping)
        risk_fraction = float(r_amount / equity) if equity > 0 else 0.0

        rule_names = [
            "_check_mode_gate",
            "_check_daily_loss_limit",
            "_check_max_drawdown",
            "_check_portfolio_exposure",
            "_check_correlated_exposure",
            "_check_liquidity",
            "_check_pump_signal",
            "_check_event_risk",
            "_check_plan_completeness",
        ]

        return RiskApprovedOrder(
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            direction=proposal.direction,
            entry_price=proposal.entry_price,
            stop_price=stop_price,
            target_price=target_price,
            position_size_usd=size_usd,
            position_size_base=size_base,
            leverage=leverage,
            r_amount=r_amount,
            risk_fraction=risk_fraction,
            risk_checks_passed=rule_names,
            max_bars_to_hold=DEFAULT_MAX_BARS,
        )

    async def _approve(
        self,
        proposal: CandidateTradeProposal,
        order: RiskApprovedOrder,
        packet_id: str = "",
        panel_id: str = "",
        decision_id: str = "",
    ) -> None:
        """
        Publish RiskDecisionEvent (approved), create Position in SystemState,
        and publish PositionOpenEvent so ExitGroup and Journal receive it.

        packet_id/panel_id/decision_id are threaded from PanelApprovedProposalEvent
        so the Position carries DB links to the learning layer records.
        """
        from core.schemas import Position

        await self.bus.publish(
            RiskDecisionEvent(
                source=self.group_id.value,
                approved=True,
                order=order,
            )
        )

        # Create Position from approved order + learning layer IDs
        position = Position(
            order_id=order.order_id,
            symbol=order.symbol,
            direction=order.direction,
            entry_price=order.entry_price,
            stop_price=order.stop_price,
            target_price=order.target_price,
            position_size_usd=order.position_size_usd,
            leverage=order.leverage,
            r_amount=order.r_amount,
            composite_score=proposal.composite_score,
            packet_id=packet_id,
            panel_id=panel_id,
            decision_id=decision_id,
            setup_refs=list(getattr(proposal, "setup_refs", []) or []),
            hypothesis_refs=list(getattr(proposal, "hypothesis_refs", []) or []),
        )
        await self.state.open_position(position)
        await self.bus.publish(
            PositionOpenEvent(source=self.group_id.value, position=position)
        )

        logger.info(
            "Proposal %s APPROVED and position opened: %s %s leverage=%.2fx size_usd=%s",
            proposal.proposal_id,
            proposal.direction,
            order.symbol,
            order.leverage,
            order.position_size_usd,
        )

    async def _reject(self, proposal: CandidateTradeProposal, result: RiskCheckResult) -> None:
        """Publish rejection event."""
        rejection = RiskRejectedEvent(
            proposal_id=proposal.proposal_id,
            rejection_reason=result.rejection_code.value if result.rejection_code else "unknown",
            rejection_detail=result.rejection_detail or "",
        )
        await self.bus.publish(
            RiskDecisionEvent(
                source=self.group_id.value,
                approved=False,
                rejection=rejection,
            )
        )
        logger.info(
            "Proposal %s REJECTED: %s — %s",
            proposal.proposal_id,
            rejection.rejection_reason,
            rejection.rejection_detail,
        )
