"""
Entry Group (Group 7 — always_on=False, implementation_priority=4).

Responsibilities:
  - Collect GroupSignalBundles from Indicators, Candlestick, Chart Pattern,
    Technical Structure, News/Macro groups.
  - Apply confirmation gate: require >= 2 independent group signals agreeing
    on direction before proposing a trade.
  - Resolve direction conflicts via ConflictAgent (highest score wins; tie → skip).
  - Compute composite_score from signal quality scores.
  - Invoke HistorianAgent to retrieve historical analogs.
  - Invoke CriticAgent ONLY if composite_score >= 0.60 (ADR-003).
  - Build CandidateTradeProposal and publish CandidateTradeEvent.
  - Do NOT apply risk rules (that is Risk & Leverage Group's job).

LLM: PERMITTED for CriticAgent only (advisory; composite_score >= 0.60 gate).
Trigger: GroupSignalEvent (from any of the 5 upstream groups).
Depends on: INDICATORS, CANDLESTICK, CHART_PATTERN, TECHNICAL_STRUCTURE, NEWS_MACRO.
Always-on: NO.

Confirmation gate rules:
  - Wait for BOTH indicators AND candlestick bundles before evaluating.
    This ensures candlestick quality is always available for composite score
    and prevents proposals from firing before bar-level price action is known.
  - Minimum 2 signals with same-direction across all collected bundles.
  - At least 1 must be a candlestick or chart_pattern signal (enforced in code).
    Pure indicator-only proposals are suppressed: they consistently produce
    ema_alignment="mixed" or "partial" at transition bars, which the panel
    evaluators score as reject-zone.
  - Structural level required if any signal has requires_structural_level=True.
  - Regime filter: if btc_macro == 'bear', block long proposals (size_reduction applies).

Composite score formula:
  raw_score = (
      0.35 × chart_pattern_quality (0.0 if excluded — Phase 3)
    + 0.25 × candlestick_quality   (0.0 if no pattern detected)
    + 0.20 × indicator_quality     (0.0 if no indicator signal)
    + 0.10 × structural_alignment  (1.0 = at S/R, 0.0 = no S/R)
    + 0.10 × historian_win_rate    (0.0 if excluded — Phase 3)
  )
  composite_score = raw_score / ACTIVE_COMPOSITE_WEIGHT_SUM
    where ACTIVE_COMPOSITE_WEIGHT_SUM = sum of weights for ACTIVE groups only.
    Phase 3: 0.25 + 0.20 + 0.10 = 0.55 → ceiling = 0.4875 / 0.55 = 0.8864.
    Phase 4+: all groups active → ACTIVE_COMPOSITE_WEIGHT_SUM = 1.00 (identity).
  Threshold to pass confirmation gate: composite_score >= 0.50.
  Threshold to invoke CriticAgent: composite_score >= 0.60.

Source: /docs/agent_registry/group_registry.md (ENTRY entry)
        /docs/decision_flow/master_decision_flow.md (Stage 4)
        /docs/adr/ADR-003-where-llm-reasoning-is-permitted.md
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from agents.base.group import BaseGroup
from core.events import (
    CandidateTradeEvent,
    EventBus,
    GroupSignalEvent,
    SystemEvent,
)
from core.registry import GroupID
from core.schemas import (
    CandidateTradeProposal,
    CriticReport,
    Direction,
    GroupSignalBundle,
    HistoricalAnalog,
    ModeGate,
    RegimeContext,
)
from core.state import SystemState

logger = logging.getLogger(__name__)

CONFIRMATION_GATE_MIN_GROUPS = 2
COMPOSITE_SCORE_THRESHOLD    = 0.50
CRITIC_SCORE_THRESHOLD       = 0.60

# ---------------------------------------------------------------------------
# Active score component weights (Phase 3)
#
# The composite_score formula has 5 components totalling 1.00 when all
# groups are wired.  In Phase 3, ChartPatternGroup and HistorianAgent are
# excluded (raise NotImplementedError / hardcoded None).  If the raw
# weighted sum is divided by 1.00 those two absent components drag the
# ceiling down to 0.4875 — permanently below the 0.50 threshold.
#
# The fix: divide the raw weighted sum by the SUM OF ACTIVE WEIGHTS only.
# This makes composite_score express "fraction of achievable quality"
# rather than "fraction of hypothetical 5-group maximum".
#
# Phase 3 active groups:  indicator(0.20) + candlestick(0.25) + structural(0.10) = 0.55
# Ceiling:  0.4875 / 0.55 = 0.8864  (above 0.50 threshold — entries can fire)
#
# When Phase 4 adds ChartPatternGroup (0.35) and HistorianAgent (0.10):
#   ACTIVE_COMPOSITE_WEIGHT_SUM becomes 1.00 → normalization is identity.
# ---------------------------------------------------------------------------

_ACTIVE_SCORE_COMPONENTS: dict = {
    # name              weight   active since
    "indicator":        0.20,   # Phase 3
    "candlestick":      0.25,   # Phase 3
    "structural":       0.10,   # Phase 3
    # "chart_pattern":  0.35,   # Excluded: ChartPatternGroup does NOT publish GroupSignalEvent.
    #                            # Chart pattern data reaches PanelDecisionGroup exclusively
    #                            # via _signals_cache cache wiring (runner._wire_caches).
    #                            # Intentionally kept out of EntryGroup scoring to preserve
    #                            # existing regression fixtures. See ChartPatternGroup NOTE.
    # "historian":      0.10,   # Phase 4+ (HistorianAgent not yet wired)
}

ACTIVE_COMPOSITE_WEIGHT_SUM: float = sum(_ACTIVE_SCORE_COMPONENTS.values())  # 0.55 in Phase 3


class EntryGroup(BaseGroup):
    """
    Signal aggregator and trade proposal generator.

    Cross-bar state:
    -   _pending_bundles: dict[symbol, dict[group_id, GroupSignalBundle]]
        Bundles are accumulated within one bar-close cycle and cleared after proposal.
    -   _historian: HistorianAgent instance (queries journal DB).
    -   _critic: CriticAgent instance (optional LLM call).
    -   _evaluating: set of symbols currently being evaluated (prevents double-trigger).
    """

    group_id = GroupID.ENTRY

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)
        self._pending_bundles: dict[str, dict] = defaultdict(dict)
        self._evaluating: set = set()
        # Agents injected at startup (concrete implementations wired in runner)
        self._historian = None
        self._critic = None

    async def _setup(self) -> None:
        await self.bus.subscribe(GroupSignalEvent, self.handle_event)
        logger.info("EntryGroup subscribed to GroupSignalEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, GroupSignalEvent) and event.bundle:
            await self._collect_bundle(event.bundle)

    async def _collect_bundle(self, bundle: GroupSignalBundle) -> None:
        """
        Accumulate incoming signal bundles.

        Stores bundle keyed by group_id. Triggers evaluation once we have
        at least one indicators bundle (minimum viable input). The _evaluating
        set prevents re-entrant evaluation for the same symbol.
        """
        symbol = bundle.symbol
        self._pending_bundles[symbol][str(bundle.group_id)] = bundle

        bundles = self._pending_bundles[symbol]

        # Trigger when we have BOTH an indicators bundle AND a candlestick bundle.
        #
        # Previously the gate fired on indicators alone.  This caused proposals
        # to be evaluated before CandlestickGroup had published its bundle for
        # the same bar, producing proposals with candlestick_quality=0.0 and
        # ema_alignment="mixed" (crossover-transition bars).  Those proposals
        # could never satisfy the panel's avg_score >= 6.5 requirement.
        #
        # CandlestickGroup always publishes a bundle every bar (even with 0
        # signals — see CandlestickGroup._process_features line 169 comment).
        # Waiting for it is therefore safe: no proposals are silently dropped.
        #
        # The key may come in as "indicators"/"GroupID.INDICATORS" or
        # "candlestick"/"GroupID.CANDLESTICK" depending on how the upstream
        # group serialises its group_id.
        has_indicators = any(
            "indicators" in k.lower() for k in bundles
        )
        has_candlestick = any(
            "candlestick" in k.lower() for k in bundles
        )

        if has_indicators and has_candlestick and symbol not in self._evaluating:
            self._evaluating.add(symbol)
            try:
                await self._evaluate_trade_opportunity(symbol)
            finally:
                self._evaluating.discard(symbol)

    async def _evaluate_trade_opportunity(self, symbol: str) -> None:
        """
        Full entry pipeline for one symbol:
        1. Collect all bundles → flatten signals.
        2. Apply confirmation gate (>= 2 signals agreeing on direction).
        3. Regime filter (block LONG in bear macro).
        4. Compute composite score.
        5. Invoke HistorianAgent (Phase 3: skipped — returns 0.0 win_rate).
        6. Invoke CriticAgent if score >= CRITIC_SCORE_THRESHOLD (Phase 3: skipped).
        7. Build CandidateTradeProposal.
        8. Publish CandidateTradeEvent.
        9. Clear pending bundles for this symbol.
        """
        bundles = self._pending_bundles.get(symbol, {})
        if not bundles:
            return

        # Clear for next bar before any early returns so state stays clean.
        self._pending_bundles[symbol] = {}

        now = datetime.now(timezone.utc)

        # ------------------------------------------------------------------
        # 1. Flatten signals from all collected bundles
        # ------------------------------------------------------------------
        all_signals = []
        for b in bundles.values():
            all_signals.extend(b.signals)

        # ------------------------------------------------------------------
        # 2. Extract regime (use first bundle that carries one; fall back safe)
        # ------------------------------------------------------------------
        regime: Optional[RegimeContext] = None
        for b in bundles.values():
            if b.regime is not None:
                regime = b.regime
                break

        if regime is None:
            regime = RegimeContext(
                btc_macro="ranging",
                trending=False,
                volatility_regime="normal",
                adx14=20.0,
                atr14=Decimal("1000"),
                atr14_vs_sma20=1.0,
            )

        # ------------------------------------------------------------------
        # 3. Extract structural bundle
        # ------------------------------------------------------------------
        structural_bundle = None
        for b in bundles.values():
            if b.structural is not None:
                structural_bundle = b.structural
                break

        # ------------------------------------------------------------------
        # 4. Direction counting — confirmation gate
        # ------------------------------------------------------------------
        long_signals = [
            s for s in all_signals
            if hasattr(s, "direction") and str(s.direction).upper() in (
                "LONG", "DIRECTION.LONG", "long"
            )
        ]
        short_signals = [
            s for s in all_signals
            if hasattr(s, "direction") and str(s.direction).upper() in (
                "SHORT", "DIRECTION.SHORT", "short"
            )
        ]

        if len(long_signals) < CONFIRMATION_GATE_MIN_GROUPS and \
                len(short_signals) < CONFIRMATION_GATE_MIN_GROUPS:
            logger.debug(
                "EntryGroup: confirmation gate not met for %s (L=%d S=%d)",
                symbol, len(long_signals), len(short_signals),
            )
            return

        # Choose the majority direction; ties go to LONG (conservative bias in
        # bull markets is more appropriate than arbitrary SHORT bias).
        if len(long_signals) >= len(short_signals):
            direction = Direction.LONG
            primary_signals = long_signals
        else:
            direction = Direction.SHORT
            primary_signals = short_signals

        # ------------------------------------------------------------------
        # 5a. Bar-level confirmation gate: require candlestick or chart_pattern
        # ------------------------------------------------------------------
        # The panel's Candlestick evaluator scores 4.0 (abstain/reject) when no
        # pattern is present.  WickAnalysis and MarketContext also score poorly
        # without candlestick context.  Proposals that are pure indicator signals
        # carry ema_alignment="mixed" or "partial" (crossover-transition bars) and
        # are structurally unable to reach the panel's avg_score >= 6.5 threshold.
        #
        # Enforcing bar-level confirmation here means the composite score will
        # always include non-zero candlestick_quality, and the setup packet will
        # carry a real pattern for the panel evaluators to score.
        has_bar_level_confirmation = any(
            getattr(s, "signal_type", "") in ("candlestick", "chart_pattern")
            for s in primary_signals
        )
        if not has_bar_level_confirmation:
            logger.debug(
                "EntryGroup: no candlestick/chart_pattern confirmation for %s "
                "(%s) — indicator-only proposals suppressed (panel incompatible).",
                symbol, direction.value,
            )
            return

        # ------------------------------------------------------------------
        # 5b. Regime filter: block LONGs in confirmed bear macro
        # ------------------------------------------------------------------
        if regime.btc_macro == "bear" and direction == Direction.LONG:
            logger.info(
                "EntryGroup: LONG blocked by bear regime for %s", symbol
            )
            return

        # ------------------------------------------------------------------
        # 6. Composite score computation (now includes candlestick_quality > 0)
        # ------------------------------------------------------------------
        composite_score, score_breakdown = self._compute_composite_score(
            bundles=bundles,
            primary_signals=primary_signals,
            structural_bundle=structural_bundle,
            historian_analog=None,  # Phase 3: no historian
        )

        if composite_score < COMPOSITE_SCORE_THRESHOLD:
            logger.debug(
                "EntryGroup: score %.2f below %.2f threshold for %s",
                composite_score, COMPOSITE_SCORE_THRESHOLD, symbol,
            )
            return

        # ------------------------------------------------------------------
        # 7. Historian / Critic (Phase 3: skipped — agents not wired)
        # ------------------------------------------------------------------
        historian_analog: Optional[HistoricalAnalog] = None
        critic_report: Optional[CriticReport] = None

        if self._historian is not None:
            try:
                historian_analog = await self._historian.query(symbol, direction)
            except Exception as exc:
                logger.warning("EntryGroup: historian query failed: %s", exc)

        if self._critic is not None and composite_score >= CRITIC_SCORE_THRESHOLD:
            try:
                critic_report = await self._critic.evaluate(symbol, direction, composite_score)
            except Exception as exc:
                logger.warning("EntryGroup: critic evaluation failed: %s", exc)

        # ------------------------------------------------------------------
        # 8. Build and publish CandidateTradeProposal
        # ------------------------------------------------------------------
        proposal = self._build_proposal(
            symbol=symbol,
            bundles=bundles,
            primary_signals=primary_signals,
            direction=direction,
            composite_score=composite_score,
            score_breakdown=score_breakdown,
            historian_analog=historian_analog,
            critic_report=critic_report,
            regime=regime,
            now=now,
        )

        if proposal is None:
            return  # entry price unavailable — logged in _build_proposal

        await self.bus.publish(CandidateTradeEvent(proposal=proposal))
        logger.info(
            "EntryGroup: published CandidateTradeProposal %s %s score=%.2f",
            direction, symbol, composite_score,
        )

    def _compute_composite_score(
        self,
        bundles: dict,
        primary_signals: list,
        structural_bundle,
        historian_analog: Optional[HistoricalAnalog],
    ) -> tuple[float, dict]:
        """
        Returns (composite_score, score_breakdown).

        Weights per spec:
          chart_pattern_quality : 0.35
          candlestick_quality   : 0.25
          indicator_quality     : 0.20
          structural_alignment  : 0.10
          historian_win_rate    : 0.10
        """
        indicator_signals = [
            s for s in primary_signals
            if getattr(s, "signal_type", "") == "indicator"
        ]
        candlestick_signals = [
            s for s in primary_signals
            if getattr(s, "signal_type", "") == "candlestick"
        ]
        chart_signals = [
            s for s in primary_signals
            if getattr(s, "signal_type", "") == "chart_pattern"
        ]

        def avg_quality(sigs: list) -> float:
            if not sigs:
                return 0.0
            return sum(s.quality_score for s in sigs) / len(sigs)

        indicator_quality = avg_quality(indicator_signals)
        candlestick_quality = avg_quality(candlestick_signals)
        chart_pattern_quality = avg_quality(chart_signals)

        structural_alignment = (
            1.0
            if (
                structural_bundle is not None
                and (
                    getattr(structural_bundle, "at_resistance", False)
                    or getattr(structural_bundle, "at_support", False)
                )
            )
            else 0.0
        )

        historian_win_rate = (
            historian_analog.win_rate if historian_analog is not None else 0.0
        )

        raw_score = (
            0.35 * chart_pattern_quality
            + 0.25 * candlestick_quality
            + 0.20 * indicator_quality
            + 0.10 * structural_alignment
            + 0.10 * historian_win_rate
        )

        # Normalize by the sum of ACTIVE component weights so excluded groups
        # do not depress the ceiling below the threshold.  See module-level
        # ACTIVE_COMPOSITE_WEIGHT_SUM for the active component set.
        composite_score = (
            raw_score / ACTIVE_COMPOSITE_WEIGHT_SUM
            if ACTIVE_COMPOSITE_WEIGHT_SUM > 0
            else 0.0
        )

        score_breakdown = {
            "chart_pattern_quality": chart_pattern_quality,
            "candlestick_quality": candlestick_quality,
            "indicator_quality": indicator_quality,
            "structural_alignment": structural_alignment,
            "historian_win_rate": historian_win_rate,
            "raw_score": round(raw_score, 6),
            "active_weight_sum": ACTIVE_COMPOSITE_WEIGHT_SUM,
            "normalized_composite_score": round(composite_score, 6),
        }

        return composite_score, score_breakdown

    def _build_proposal(
        self,
        symbol: str,
        bundles: dict,
        primary_signals: list,
        direction: Direction,
        composite_score: float,
        score_breakdown: dict,
        historian_analog: Optional[HistoricalAnalog],
        critic_report: Optional[CriticReport],
        regime: RegimeContext,
        now: datetime,
    ) -> Optional[CandidateTradeProposal]:
        """Assemble CandidateTradeProposal from aggregated signal data."""

        # Source 1: SystemState.last_close_by_symbol (set by MarketDataGroup on each bar)
        entry_price = self.state.last_close_by_symbol.get(symbol, Decimal("0"))

        # Source 2: signal metadata fallback (carries 'close' if upstream group adds it)
        if entry_price == Decimal("0"):
            for s in primary_signals:
                if hasattr(s, "metadata") and "close" in s.metadata:
                    try:
                        entry_price = Decimal(str(s.metadata["close"]))
                        break
                    except Exception:
                        pass

        # Fail loudly: a proposal without entry price is invalid
        if entry_price == Decimal("0"):
            logger.warning(
                "EntryGroup: entry_price unavailable for %s — proposal aborted. "
                "Ensure MarketDataGroup.fetch_and_process() runs before EntryGroup "
                "receives bundles (state.last_close_by_symbol not populated).",
                symbol,
            )
            return None

        hypothesis_refs = list(
            {s.hypothesis_ref for s in primary_signals if s.hypothesis_ref}
        )
        setup_refs = list(
            {getattr(s, "signal_type", "") for s in primary_signals}
        )
        setup_refs = [r for r in setup_refs if r]  # drop empty strings

        direction_str = "LONG" if direction == Direction.LONG else "SHORT"
        thesis = (
            f"{direction_str} on {symbol}: "
            f"{len(primary_signals)} confirming signals "
            f"(score={composite_score:.2f})"
        )

        return CandidateTradeProposal(
            symbol=symbol,
            timeframe="1h",
            timestamp=now,
            direction=direction,
            entry_price=entry_price,
            thesis=thesis,
            setup_refs=setup_refs,
            hypothesis_refs=hypothesis_refs,
            composite_score=composite_score,
            score_breakdown=score_breakdown,
            historian_analog=historian_analog,
            critic_report=critic_report,
            regime_context=regime,
            mode_gate=ModeGate.SHADOW,  # Phase 4+: paper trading (shadow) mode
        )
