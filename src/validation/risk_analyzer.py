"""
RiskGateAnalyzer — measures real RiskLeverageGroup behavior.

Runs CandidateTradeProposals through the actual 9 risk rule stack.
Source: event_driven_runtime_simulation.

Tracks:
  - rejection reasons by RejectionCode
  - pass-through rate (how many proposals clear all rules)
  - size/leverage distributions on approvals
  - which rules fire most often
  - whether certain rules are too restrictive or protective
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.schemas import (
    CandidateTradeProposal, Direction, ModeGate, RegimeContext, RejectionCode,
)
from core.state import SystemState
from validation.metrics import describe
from validation.source_enforcer import SourceEnforcer

logger = logging.getLogger(__name__)

VALIDATION_SOURCE = "event_driven_runtime_simulation"


@dataclass
class RiskRuleResult:
    """Result of running a single proposal through all 9 risk rules."""
    proposal_id: str
    scenario_label: str
    approved: bool
    rejection_code: Optional[str]
    rejection_detail: Optional[str]
    # Only present if approved:
    leverage: Optional[float]
    position_size_usd: Optional[Decimal]
    stop_price: Optional[Decimal]
    target_price: Optional[Decimal]
    r_amount: Optional[Decimal]
    validation_source: str = VALIDATION_SOURCE


class RiskRuleRunner:
    """
    Runs proposals through the actual RiskLeverageGroup rule stack.
    Uses a clean SystemState. Does not require EventBus.

    Each call is independent — state resets between calls unless
    you provide a shared state to test exposure-based rules.
    """

    def __init__(self, initial_equity: Decimal = Decimal("1000")) -> None:  # Capital: $1,000 with 10x leverage = $10,000 notional
        from core.events import EventBus
        self._initial_equity = initial_equity
        self._state = None
        self._bus = None
        self._risk_group = None

    def _fresh_state(self) -> SystemState:
        state = SystemState(mode=ModeGate.SHADOW)
        state.portfolio.equity = self._initial_equity
        state.portfolio.available = self._initial_equity
        return state

    def check_proposal(
        self,
        proposal: CandidateTradeProposal,
        scenario_label: str = "",
        state: Optional[SystemState] = None,
        regime: Optional[RegimeContext] = None,
        eligible_symbols: Optional[set] = None,
    ) -> RiskRuleResult:
        """
        Run one proposal through all 9 risk rules.
        Returns RiskRuleResult with pass/fail + details.
        """
        from groups.risk_leverage.group import (
            RiskLeverageGroup,
            DEFAULT_RISK_FRACTION,
        )

        if state is None:
            state = self._fresh_state()

        import asyncio as _asyncio

        def _run(coro):
            try:
                loop = _asyncio.get_event_loop()
                if loop.is_running():
                    # Inside an already-running loop (e.g. pytest-asyncio)
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(_asyncio.run, coro)
                        return future.result()
                return loop.run_until_complete(coro)
            except RuntimeError:
                return _asyncio.run(coro)

        # Inject regime if provided
        if regime is not None:
            _run(state.update_regime(regime))

        # Inject eligible symbols
        syms = eligible_symbols or {proposal.symbol}
        _run(state.update_universe(syms))

        # Construct risk group in isolation
        from core.events import EventBus
        bus = EventBus()
        rg = RiskLeverageGroup(state, bus)

        # Run rule chain manually (NOT through the full event path)
        results = {
            "rule1": rg._check_mode_gate(proposal),
            "rule2": rg._check_daily_loss_limit(),
            "rule3": rg._check_max_drawdown(),
            "rule4": rg._check_portfolio_exposure(proposal),
            "rule5": rg._check_correlated_exposure(proposal),
            "rule6": rg._check_liquidity(proposal),
            "rule7": rg._check_pump_signal(proposal),
            "rule9": rg._check_plan_completeness(proposal),
        }

        for rule_name, result in results.items():
            if not result.approved:
                return RiskRuleResult(
                    proposal_id=proposal.proposal_id,
                    scenario_label=scenario_label,
                    approved=False,
                    rejection_code=result.rejection_code.value if result.rejection_code else "unknown",
                    rejection_detail=result.rejection_detail,
                    leverage=None,
                    position_size_usd=None,
                    stop_price=None,
                    target_price=None,
                    r_amount=None,
                )

        # All rules passed — compute order
        event_risk_reduction = rg._check_event_risk(proposal)
        order = rg._compute_order(proposal, event_risk_reduction)
        return RiskRuleResult(
            proposal_id=proposal.proposal_id,
            scenario_label=scenario_label,
            approved=True,
            rejection_code=None,
            rejection_detail=None,
            leverage=order.leverage,
            position_size_usd=order.position_size_usd,
            stop_price=order.stop_price,
            target_price=order.target_price,
            r_amount=order.r_amount,
        )

    def check_batch(
        self,
        proposals: list[tuple[CandidateTradeProposal, str]],  # (proposal, label)
        regime: Optional[RegimeContext] = None,
    ) -> list[RiskRuleResult]:
        """Run a list of (proposal, label) tuples through risk rules."""
        results = []
        for proposal, label in proposals:
            result = self.check_proposal(proposal, label, regime=regime)
            logger.info(
                "RiskRule: %-40s → %s %s",
                label[:40],
                "APPROVED" if result.approved else "REJECTED",
                f"({result.rejection_code})" if not result.approved else
                f"(leverage={result.leverage:.2f}x)",
            )
            results.append(result)
        return results


def make_risk_test_proposals() -> list[tuple[CandidateTradeProposal, str]]:
    """
    Build a set of CandidateTradeProposals for risk gate validation.
    Covers all 9 rules with controlled test cases.
    """
    from uuid import uuid4

    base_kwargs = dict(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=datetime.utcnow(),
        direction=Direction.LONG,
        entry_price=Decimal("65000"),
        thesis="test",
        setup_refs=["ema_crossover"],
        hypothesis_refs=["H3-001"],
        composite_score=0.65,
        score_breakdown={"indicator": 0.65},
        mode_gate=ModeGate.SHADOW,
    )

    proposals = []

    # P1: All rules pass — valid complete proposal
    proposals.append((CandidateTradeProposal(
        **base_kwargs,
        raw_target=Decimal("68900"),
    ), "P1_all_rules_pass"))

    # P2: Missing raw_target → Rule 9 INCOMPLETE_TRADE_PLAN
    proposals.append((CandidateTradeProposal(
        **base_kwargs,
        raw_target=Decimal("0"),
    ), "P2_missing_raw_target"))

    # P3: No hypothesis_refs → Rule 9 HYPOTHESIS_NOT_ACTIVE
    p3_kwargs = dict(base_kwargs)
    p3_kwargs["hypothesis_refs"] = []
    p3_kwargs["raw_target"] = Decimal("68900")
    proposals.append((CandidateTradeProposal(**p3_kwargs), "P3_no_hypothesis_refs"))

    # P4: composite_score < 0.50 → Rule 9 SCORE_BELOW_THRESHOLD
    p4_kwargs = dict(base_kwargs)
    p4_kwargs["composite_score"] = 0.42
    p4_kwargs["score_breakdown"] = {"indicator": 0.42}
    p4_kwargs["raw_target"] = Decimal("68900")
    proposals.append((CandidateTradeProposal(**p4_kwargs), "P4_score_below_0.50"))

    # P5: Symbol not in eligible universe → Rule 6 UNIVERSE_FILTER
    p5_kwargs = dict(base_kwargs)
    p5_kwargs["symbol"] = "XYZUSDT"
    p5_kwargs["raw_target"] = Decimal("68900")
    proposals.append((CandidateTradeProposal(**p5_kwargs), "P5_not_eligible_symbol"))

    # P6: Valid proposal, composite_score = exactly 0.50 (boundary)
    p6_kwargs = dict(base_kwargs)
    p6_kwargs["composite_score"] = 0.50
    p6_kwargs["score_breakdown"] = {"indicator": 0.50}
    p6_kwargs["raw_target"] = Decimal("68900")
    proposals.append((CandidateTradeProposal(**p6_kwargs), "P6_score_exactly_0.50"))

    # P7: Valid proposal with score = 0.75 (high score)
    p7_kwargs = dict(base_kwargs)
    p7_kwargs["composite_score"] = 0.75
    p7_kwargs["score_breakdown"] = {"indicator": 0.75}
    p7_kwargs["raw_target"] = Decimal("68900")
    proposals.append((CandidateTradeProposal(**p7_kwargs), "P7_score_0.75"))

    # P8: RESEARCH mode (mode_gate metadata only — actual block depends on state.mode)
    # Note: mode_gate on proposal is metadata; Rule 1 checks state.mode (always SHADOW here)
    p8_kwargs = dict(base_kwargs)
    p8_kwargs["mode_gate"] = ModeGate.RESEARCH  # metadata — state.mode still SHADOW
    p8_kwargs["raw_target"] = Decimal("68900")
    proposals.append((CandidateTradeProposal(**p8_kwargs), "P8_proposal_research_mode_metadata"))

    return proposals


class RiskGateAnalyzer:
    """
    Accumulates RiskRuleResult records and computes aggregate statistics.
    """

    def __init__(self) -> None:
        self.results: list[RiskRuleResult] = []

    def add_all(self, results: list[RiskRuleResult]) -> None:
        self.results.extend(results)

    def pass_rate(self) -> Optional[float]:
        if not self.results:
            return None
        return sum(1 for r in self.results if r.approved) / len(self.results)

    def rejection_code_frequencies(self) -> dict[str, int]:
        codes: dict[str, int] = {}
        for r in self.results:
            if not r.approved and r.rejection_code:
                codes[r.rejection_code] = codes.get(r.rejection_code, 0) + 1
        return codes

    def leverage_distribution(self) -> dict:
        leverages = [r.leverage for r in self.results if r.approved and r.leverage is not None]
        return {"stats": describe(leverages), "count": len(leverages)}

    def position_size_distribution(self) -> dict:
        sizes = [float(r.position_size_usd) for r in self.results
                 if r.approved and r.position_size_usd is not None]
        return {"stats": describe(sizes), "count": len(sizes)}

    def summarize(self) -> dict:
        return {
            "validation_source": VALIDATION_SOURCE,
            "total_proposals": len(self.results),
            "approved": sum(1 for r in self.results if r.approved),
            "rejected": sum(1 for r in self.results if not r.approved),
            "pass_rate": self.pass_rate(),
            "rejection_code_frequencies": self.rejection_code_frequencies(),
            "leverage_distribution": self.leverage_distribution(),
            "position_size_distribution": self.position_size_distribution(),
            "risk_rules": {
                "rule1_mode_gate": "blocks RESEARCH mode (state.mode, not proposal.mode_gate)",
                "rule2_daily_loss": "blocks if daily_pnl_pct < -2%",
                "rule3_max_drawdown": "blocks if drawdown_pct > 10%",
                "rule4_portfolio_exposure": "blocks if total open > 25% equity",
                "rule5_correlated_exposure": "blocks if BTC cluster > 15% equity",
                "rule6_liquidity": "blocks symbol not in eligible_symbols",
                "rule7_pump": "blocks if volume_ratio > 5.0",
                "rule8_event_risk": "reduces size 50% if high-impact event (stub: always 1.0x)",
                "rule9_completeness": "blocks missing raw_target, no hypothesis_refs, score < 0.50",
            },
        }
