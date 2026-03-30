"""
MDPStateBuilder: assembles MDPState from runtime data.

Inputs:
  - BTCSetupPacket (proposal + indicators + structure + regime)
  - PanelResult    (20 evaluator verdicts + aggregated stats)
  - SystemState    (portfolio equity, drawdown, positions) — optional

Missing/optional fields default to neutral values so this builder works
in test contexts where SystemState is not provided.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

from core.setup_packet import BTCSetupPacket
from traders.panel import PanelResult

logger = logging.getLogger(__name__)

# Evaluator IDs classified as trend-following in nature.
# Used to compute bull_bear_split (fraction of trend-following approvers).
_TREND_FOLLOWING_IDS = frozenset([
    "TrendFollowing",
    "Momentum",
    "Breakout",
    "MacroRegime",
    "EntryTiming",
    "Confluence",
    "MarketContext",
])

# Default equity baseline for normalisation when SystemState is unavailable
_DEFAULT_EQUITY = 100_000.0


class MDPStateBuilder:
    """
    Assembles MDPState from BTCSetupPacket + PanelResult + SystemState.

    Usage:
        builder = MDPStateBuilder()
        state = builder.build(packet, panel, system_state)
    """

    def build(
        self,
        packet: BTCSetupPacket,
        panel: PanelResult,
        system_state=None,          # Optional[SystemState] — avoid import cycle
        chart_pattern_group=None,   # Optional[ChartPatternGroup] — avoid import cycle
    ) -> "MDPState":
        """Extract all relevant features into MDPState."""
        from mdp.state import MDPState

        proposal = packet.proposal
        regime = packet.regime
        structure = packet.structure

        # ------------------------------------------------------------------
        # Direction
        # ------------------------------------------------------------------
        from core.schemas import Direction
        direction_val = proposal.direction
        if isinstance(direction_val, Direction):
            direction_str = direction_val.value
        else:
            direction_str = str(direction_val).lower()

        # ------------------------------------------------------------------
        # Individual evaluator data
        # ------------------------------------------------------------------
        evaluator_scores: dict[str, float] = {}
        evaluator_votes: dict[str, str] = {}
        evaluator_confidences: dict[str, float] = {}
        evaluator_metadata: dict[str, dict] = {}

        for verdict in panel.verdicts:
            evaluator_scores[verdict.trader_id] = verdict.score
            evaluator_votes[verdict.trader_id] = verdict.vote
            evaluator_confidences[verdict.trader_id] = verdict.confidence
            if verdict.metadata:
                evaluator_metadata[verdict.trader_id] = verdict.metadata

        # ------------------------------------------------------------------
        # Score standard deviation (disagreement metric)
        # ------------------------------------------------------------------
        scores = [v.score for v in panel.verdicts]
        if len(scores) >= 2:
            mean = panel.avg_score
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)
            score_std_dev = math.sqrt(variance)
        else:
            score_std_dev = 0.0

        # ------------------------------------------------------------------
        # Bull/bear split among approvers
        # fraction of approving evaluators that are "trend-following"
        # ------------------------------------------------------------------
        approving_verdicts = [v for v in panel.verdicts if v.vote == "approve"]
        if approving_verdicts:
            trend_approve = sum(
                1 for v in approving_verdicts
                if v.trader_id in _TREND_FOLLOWING_IDS
            )
            bull_bear_split = trend_approve / len(approving_verdicts)
        else:
            bull_bear_split = 0.5  # neutral when no approvers

        # ------------------------------------------------------------------
        # Account state from SystemState (or defaults)
        # ------------------------------------------------------------------
        if system_state is not None:
            portfolio = system_state.portfolio
            current_equity = float(portfolio.equity)
            drawdown_pct = portfolio.drawdown_pct
            daily_pnl_pct = portfolio.daily_pnl_pct
            open_positions_count = len(portfolio.open_positions)

            # Total exposure: sum of open position notional / equity
            if current_equity > 0 and portfolio.open_positions:
                total_notional = sum(
                    float(p.position_size_usd)
                    for p in portfolio.open_positions.values()
                )
                total_exposure_pct = total_notional / current_equity
            else:
                total_exposure_pct = 0.0

            # current_streak: negative = consecutive losses, positive = win streak
            # PortfolioState tracks consecutive_losses; win streaks not tracked.
            consecutive_losses = portfolio.consecutive_losses
            current_streak = -consecutive_losses if consecutive_losses > 0 else 0

            # recent_win_rate: rolling last-20-trades win rate (PortfolioState property)
            recent_win_rate = portfolio.recent_win_rate

            # trades_last_24_bars: count of trades closed in last 24h (PortfolioState property)
            trades_last_24_bars = portfolio.trades_last_24_bars
        else:
            current_equity = _DEFAULT_EQUITY
            drawdown_pct = 0.0
            daily_pnl_pct = 0.0
            open_positions_count = 0
            total_exposure_pct = 0.0
            current_streak = 0
            recent_win_rate = 0.5
            trades_last_24_bars = 0

        # ------------------------------------------------------------------
        # Macro state (populated by NewsMacroGroup; defaults when unavailable)
        # ------------------------------------------------------------------
        macro_position_modifier = getattr(system_state, "macro_position_modifier", 1.0) \
            if system_state is not None else 1.0
        fear_greed_index = getattr(system_state, "fear_greed_index", 50.0) \
            if system_state is not None else 50.0

        # ------------------------------------------------------------------
        # Chart pattern state (from ChartPatternGroup cache; optional)
        # ------------------------------------------------------------------
        active_chart_patterns = None
        chart_pattern_completion_pct = None
        chart_pattern_measured_move = None

        if chart_pattern_group is not None:
            symbol = packet.symbol
            # Active patterns: hypothesis refs currently in a non-terminal state
            active = list(chart_pattern_group._active_cache.get(symbol, []))
            if active:
                active_chart_patterns = active

            # Completion pct: average bars_in_formation / max_bars across active machines
            from groups.chart_pattern.state_machine import PatternState as _PS
            machines = chart_pattern_group._machines.get(symbol, {})
            completion_pcts = []
            for machine in machines.values():
                if machine.state not in (
                    _PS.INACTIVE, _PS.CONFIRMED, _PS.FAILED, _PS.EXPIRED
                ):
                    pct = (
                        machine.bars_in_formation / machine.max_bars
                        if machine.max_bars > 0 else 0.0
                    )
                    completion_pcts.append(min(1.0, pct))
            if completion_pcts:
                chart_pattern_completion_pct = sum(completion_pcts) / len(completion_pcts)

            # Measured move: average across confirmed signals in this bar's cache
            signals = chart_pattern_group._signals_cache.get(symbol, [])
            moves = [
                float(s.measured_move)
                for s in signals
                if getattr(s, "measured_move", None) and float(s.measured_move) > 0
            ]
            if moves:
                chart_pattern_measured_move = sum(moves) / len(moves)

        return MDPState(
            # Proposal
            direction=direction_str,
            symbol=packet.symbol,
            timeframe=packet.timeframe,
            entry_price=float(proposal.entry_price),
            stop_price=float(proposal.stop_price),
            target_price=float(proposal.target_price),
            r_r_ratio=proposal.r_r_ratio,
            composite_score=getattr(proposal, "composite_score", 0.0),
            setup_quality=proposal.setup_quality,
            # Regime
            btc_macro=regime.btc_macro,
            trending=regime.trending,
            volatility_regime=regime.volatility_regime,
            adx14=regime.adx14,
            # Structure
            at_support=structure.at_support,
            at_resistance=structure.at_resistance,
            # Panel
            approve_count=panel.approve_count,
            reject_count=panel.reject_count,
            abstain_count=panel.abstain_count,
            avg_score=panel.avg_score,
            weighted_score=panel.weighted_score,
            panel_confidence=panel.panel_confidence,
            evaluator_scores=evaluator_scores,
            evaluator_votes=evaluator_votes,
            evaluator_confidences=evaluator_confidences,
            evaluator_metadata=evaluator_metadata,
            score_std_dev=score_std_dev,
            bull_bear_split=bull_bear_split,
            key_risks=list(panel.key_risks),
            key_strengths=list(panel.key_strengths),
            # Account
            current_equity=current_equity,
            drawdown_pct=drawdown_pct,
            daily_pnl_pct=daily_pnl_pct,
            open_positions_count=open_positions_count,
            total_exposure_pct=total_exposure_pct,
            recent_win_rate=recent_win_rate,
            current_streak=current_streak,
            trades_last_24_bars=trades_last_24_bars,
            macro_position_modifier=macro_position_modifier,
            fear_greed_index=fear_greed_index,
            active_chart_patterns=active_chart_patterns,
            chart_pattern_completion_pct=chart_pattern_completion_pct,
            chart_pattern_measured_move=chart_pattern_measured_move,
        )
