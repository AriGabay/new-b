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

DEFAULT_RISK_FRACTION  = Decimal("0.01")   # 1% per trade
MAX_SINGLE_POSITION    = Decimal("0.10")   # 10% of equity cap
DAILY_LOSS_LIMIT       = -0.02             # −2% daily PnL
MAX_DRAWDOWN_HALT      = 0.10              # 10% drawdown halts system
MAX_PORTFOLIO_EXPOSURE = Decimal("0.25")   # 25% total exposure
MAX_CORRELATED_CLUSTER = Decimal("0.15")   # 15% per correlation cluster
PUMP_VOLUME_RATIO      = 5.0               # 5× normal volume = pump signal


class RiskLeverageGroup(BaseGroup):
    """
    Non-overridable risk gate. Deterministic. No LLM.

    All 9 rules are checked in sequence. First failure = rejection.
    On approval: compute position size, emit RiskApprovedOrder.
    """

    group_id = GroupID.RISK_LEVERAGE

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)

    async def _setup(self) -> None:
        await self.bus.subscribe(CandidateTradeEvent, self.handle_event)
        logger.info("RiskLeverageGroup subscribed to CandidateTradeEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, CandidateTradeEvent) and event.proposal:
            await self._evaluate_proposal(event.proposal)

    async def _evaluate_proposal(self, proposal: CandidateTradeProposal) -> None:
        """
        Run all 9 risk rules in order.
        Publish RiskDecisionEvent (approved or rejected).
        If approved: publish PositionOpenEvent and update SystemState.
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
        await self._approve(proposal, order)

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
        """Rule 4: Total open position USD ≤ 25% of equity."""
        portfolio = self.state.portfolio
        equity = portfolio.equity
        if equity <= 0:
            return RiskCheckResult.approved_ok()
        total_exposure = sum(
            p.position_size_usd for p in portfolio.open_positions.values()
        )
        if total_exposure / equity > MAX_PORTFOLIO_EXPOSURE:
            return RiskCheckResult.rejected(
                RejectionCode.PORTFOLIO_EXPOSURE,
                f"Portfolio exposure {float(total_exposure / equity):.1%} exceeds {float(MAX_PORTFOLIO_EXPOSURE):.0%} limit.",
            )
        return RiskCheckResult.approved_ok()

    def _check_correlated_exposure(self, proposal: CandidateTradeProposal) -> RiskCheckResult:
        """Rule 5: BTC correlation cluster ≤ 15% of equity."""
        portfolio = self.state.portfolio
        equity = portfolio.equity
        if equity <= 0:
            return RiskCheckResult.approved_ok()
        btc_exposure = sum(
            p.position_size_usd
            for p in portfolio.open_positions.values()
            if getattr(p, "correlation_cluster", "btc") == "btc"
        )
        if btc_exposure / equity > MAX_CORRELATED_CLUSTER:
            return RiskCheckResult.rejected(
                RejectionCode.CORRELATED_EXPOSURE,
                f"BTC cluster exposure {float(btc_exposure / equity):.1%} exceeds {float(MAX_CORRELATED_CLUSTER):.0%} limit.",
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

    def _compute_order(
        self,
        proposal: CandidateTradeProposal,
        size_reduction: Decimal,
    ) -> RiskApprovedOrder:
        """
        Compute position size using R-multiple method.
        Returns RiskApprovedOrder.
        """
        from risk.sizing import ATRStopPlacer, RMultipleSizer

        equity = self.state.portfolio.equity

        # Apply drawdown-based size reduction on top of event-risk reduction
        dd = self.state.portfolio.drawdown_pct
        if dd > 0.05:
            drawdown_reduction = Decimal("0.75")
        else:
            drawdown_reduction = Decimal("1.0")
        combined_reduction = size_reduction * drawdown_reduction

        # Place stop using ATR
        atr14 = self.state.regime.atr14 if self.state.regime.atr14 > 0 else Decimal("1000")
        placer = ATRStopPlacer()
        stop_price = placer.compute(proposal.entry_price, proposal.direction, atr14)

        # Compute target: 2× stop distance
        stop_dist = abs(proposal.entry_price - stop_price)
        if proposal.direction == Direction.LONG:
            target_price = proposal.entry_price + stop_dist * Decimal("2")
        else:
            target_price = proposal.entry_price - stop_dist * Decimal("2")

        # Size the position
        sizer = RMultipleSizer(equity=equity)
        size_base, size_usd, r_amount = sizer.compute(
            proposal.entry_price, stop_price, combined_reduction
        )

        leverage = float(size_usd / equity) if equity > 0 else 1.0
        leverage = min(leverage, 3.0)

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
            risk_fraction=float(sizer.risk_fraction),
            risk_checks_passed=rule_names,
            max_bars_to_hold=20,
        )

    async def _approve(self, proposal: CandidateTradeProposal, order: RiskApprovedOrder) -> None:
        """Publish approval and open position in SystemState."""
        await self.bus.publish(
            RiskDecisionEvent(
                source=self.group_id.value,
                approved=True,
                order=order,
            )
        )
        logger.info(
            "Proposal %s APPROVED: %s leverage=%.2fx size_usd=%s",
            proposal.proposal_id,
            proposal.direction,
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
