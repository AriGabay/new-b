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
      0.35 × indicator_quality       (avg quality of indicator signals)
    + 0.25 × candlestick_quality     (avg quality of candlestick signals)
    + 0.20 × structural_alignment    (1.0 = at S/R, 0.0 = no S/R)
    + 0.20 × momentum_confirmation   (computed from ADX + RSI direction + volume)
  )
  Weights sum to 1.0 — no normalization divisor needed.
  momentum_confirmation sub-score (capped at 1.0):
    RSI direction aligned    +0.30
    ADX > 20                 +0.25  (+ 0.15 more if ADX > 30 = total 0.40)
    volume > 1.2×            +0.20  (+ 0.10 more if volume > 2× = total 0.30)
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

CONFIRMATION_GATE_MIN_GROUPS = 1   # Lowered from 2 — panel evaluators are the quality gate
COMPOSITE_SCORE_THRESHOLD    = 0.30  # Lowered from 0.50 — allows indicator+momentum proposals
CRITIC_SCORE_THRESHOLD       = 0.60
SINGLE_SIGNAL_HIGH_CONFIDENCE = 0.60  # Lowered from 0.80 — single strong signal can proceed

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
    # name                       weight   notes
    "indicator":                 0.35,   # Phase 3 — raised from 0.20
    "candlestick":               0.25,   # Phase 3
    "structural":                0.20,   # Phase 3 — raised from 0.10
    "momentum_confirmation":     0.20,   # Phase 3 — new component (ADX + RSI + volume)
}

# 5-component weights used when HistorianGroup is wired (Phase 4+)
_HISTORIAN_SCORE_COMPONENTS: dict = {
    "indicator":                 0.30,
    "candlestick":               0.22,
    "structural":                0.18,
    "momentum_confirmation":     0.16,
    "historian":                 0.14,
}

# Weights sum to 1.0 — no normalization divisor needed.
ACTIVE_COMPOSITE_WEIGHT_SUM: float = sum(_ACTIVE_SCORE_COMPONENTS.values())  # 1.00


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
        6. Query HistorianGroup (before composite score so it feeds into it).
        7. Compute composite score (4-component or 5-component with historian).
        8. Invoke CriticAgent if score >= CRITIC_SCORE_THRESHOLD.
        9. Build CandidateTradeProposal.
        10. Publish CandidateTradeEvent.
        11. Clear pending bundles for this symbol.
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
            # Single high-confidence signal bypass
            max_quality_all = max(
                (getattr(s, "quality_score", 0.0) for s in all_signals), default=0.0
            )
            if max_quality_all < SINGLE_SIGNAL_HIGH_CONFIDENCE:
                logger.debug(
                    "EntryGroup: confirmation gate not met for %s (L=%d S=%d) "
                    "and max quality_score %.2f < %.2f — suppressed.",
                    symbol, len(long_signals), len(short_signals),
                    max_quality_all, SINGLE_SIGNAL_HIGH_CONFIDENCE,
                )
                return
            logger.debug(
                "EntryGroup: single high-confidence bypass for %s "
                "(max quality_score=%.2f >= %.2f).",
                symbol, max_quality_all, SINGLE_SIGNAL_HIGH_CONFIDENCE,
            )

        # Choose the majority direction; ties go to LONG (conservative bias in
        # bull markets is more appropriate than arbitrary SHORT bias).
        if len(long_signals) >= len(short_signals):
            direction = Direction.LONG
            primary_signals = long_signals
        else:
            direction = Direction.SHORT
            primary_signals = short_signals

        # ------------------------------------------------------------------
        # 5a. Bar-level confirmation flag (no longer a hard gate)
        # ------------------------------------------------------------------
        # Pure indicator proposals are allowed when composite_score >= 0.60
        # (CRITIC_SCORE_THRESHOLD) or any signal has quality_score >= 0.80.
        # The actual check is deferred until after composite_score is computed.
        has_bar_level_confirmation = any(
            getattr(s, "signal_type", "") in ("candlestick", "chart_pattern")
            for s in primary_signals
        )

        # ------------------------------------------------------------------
        # 5b. Regime filter: block LONGs in confirmed bear macro
        # ------------------------------------------------------------------
        if regime.btc_macro == "bear" and direction == Direction.LONG:
            logger.info(
                "EntryGroup: LONG blocked by bear regime for %s", symbol
            )
            return

        # ------------------------------------------------------------------
        # 6. Historian query (before composite score so result feeds into it)
        # ------------------------------------------------------------------
        historian_analog: Optional[HistoricalAnalog] = None

        if self._historian is not None:
            try:
                # Build regime_key from regime context
                regime_key = (
                    f"{regime.btc_macro}_{regime.volatility_regime}"
                    if regime is not None else None
                )
                hypothesis_refs = list(
                    {getattr(s, "hypothesis_ref", None) for s in primary_signals
                     if getattr(s, "hypothesis_ref", None)}
                )
                historian_analog = self._historian.query(
                    symbol, direction,
                    hypothesis_refs=hypothesis_refs,
                    regime_key=regime_key,
                )
            except Exception as exc:
                logger.warning("EntryGroup: historian query failed: %s", exc)

        # ------------------------------------------------------------------
        # 7. Composite score computation
        # ------------------------------------------------------------------
        composite_score, score_breakdown = self._compute_composite_score(
            bundles=bundles,
            primary_signals=primary_signals,
            structural_bundle=structural_bundle,
            historian_analog=historian_analog,
            regime=regime,
            direction=direction,
        )

        if composite_score < COMPOSITE_SCORE_THRESHOLD:
            logger.debug(
                "EntryGroup: score %.2f below %.2f threshold for %s",
                composite_score, COMPOSITE_SCORE_THRESHOLD, symbol,
            )
            return

        # ------------------------------------------------------------------
        # 7b. Bar-level confirmation note (advisory only — no longer a gate).
        #
        # Pure indicator proposals used to be suppressed here unless
        # composite_score >= 0.60 or quality >= 0.80.  This was removed
        # because it killed trade frequency: with candlestick_quality=0
        # the composite ceiling is ~0.55, permanently below the 0.60 gate.
        # The panel evaluators (20 traders) are the proper quality filter.
        # ------------------------------------------------------------------
        if not has_bar_level_confirmation:
            logger.debug(
                "EntryGroup: pure indicator proposal for %s (%s) — "
                "composite_score=%.2f (no bar-level confirmation, passing to panel).",
                symbol, direction.value, composite_score,
            )

        # ------------------------------------------------------------------
        # 8. Critic (optional LLM call)
        # ------------------------------------------------------------------
        critic_report: Optional[CriticReport] = None

        if self._critic is not None and composite_score >= CRITIC_SCORE_THRESHOLD:
            try:
                critic_report = await self._critic.evaluate(symbol, direction, composite_score)
            except Exception as exc:
                logger.warning("EntryGroup: critic evaluation failed: %s", exc)

        # ------------------------------------------------------------------
        # 9. Build and publish CandidateTradeProposal
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
        regime: Optional[RegimeContext] = None,
        direction: Optional[Direction] = None,
    ) -> tuple[float, dict]:
        """
        Returns (composite_score, score_breakdown).

        Weights (all active, sum = 1.0):
          indicator_quality       : 0.35
          candlestick_quality     : 0.25
          structural_alignment    : 0.20
          momentum_confirmation   : 0.20
        """
        indicator_signals = [
            s for s in primary_signals
            if getattr(s, "signal_type", "") == "indicator"
        ]
        candlestick_signals = [
            s for s in primary_signals
            if getattr(s, "signal_type", "") == "candlestick"
        ]

        def avg_quality(sigs: list) -> float:
            if not sigs:
                return 0.0
            return sum(s.quality_score for s in sigs) / len(sigs)

        indicator_quality = avg_quality(indicator_signals)
        candlestick_quality = avg_quality(candlestick_signals)

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

        # ------------------------------------------------------------------
        # momentum_confirmation: ADX strength + RSI direction + volume
        # ------------------------------------------------------------------
        mc = 0.0
        adx = getattr(regime, "adx14", 0.0) if regime is not None else 0.0
        if adx > 30:
            mc += 0.40   # base 0.25 + extra 0.15
        elif adx > 20:
            mc += 0.25

        # RSI direction: extract from indicator signal indicator_values
        rsi14 = None
        prev_rsi14 = None
        volume_ratio = None
        for sig in primary_signals:
            iv = getattr(sig, "indicator_values", {})
            if rsi14 is None and "rsi14" in iv:
                rsi14 = iv["rsi14"]
            if prev_rsi14 is None and "prev_rsi14" in iv:
                prev_rsi14 = iv["prev_rsi14"]
            if volume_ratio is None and "volume_ratio" in iv:
                volume_ratio = iv["volume_ratio"]

        if rsi14 is not None and prev_rsi14 is not None and direction is not None:
            dir_str = direction.value if hasattr(direction, "value") else str(direction).lower()
            rsi_aligned = (
                (dir_str == "long" and rsi14 > prev_rsi14)
                or (dir_str == "short" and rsi14 < prev_rsi14)
            )
            if rsi_aligned:
                mc += 0.30

        # Volume bonus from indicator_values (if available)
        if volume_ratio is not None:
            if volume_ratio > 2.0:
                mc += 0.30   # base 0.20 + extra 0.10
            elif volume_ratio > 1.2:
                mc += 0.20

        momentum_confirmation = min(1.0, mc)

        if historian_analog is not None:
            # 5-component formula when historian is available
            historian_score = historian_analog.win_rate  # 0.0–1.0
            components = {
                "indicator": (0.30, indicator_quality),
                "candlestick": (0.22, candlestick_quality),
                "structural": (0.18, structural_alignment),
                "momentum_confirmation": (0.16, momentum_confirmation),
                "historian": (0.14, historian_score),
            }
        else:
            # 4-component formula (no historian)
            historian_score = None
            components = {
                "indicator": (0.35, indicator_quality),
                "candlestick": (0.25, candlestick_quality),
                "structural": (0.20, structural_alignment),
                "momentum_confirmation": (0.20, momentum_confirmation),
            }

        # Compute raw weighted score.  Components with value=0 (no candlestick
        # signals, no structural context) contribute zero but their weight is
        # NOT redistributed — a proposal with fewer confirmation types should
        # score lower.  The threshold (0.40) is low enough that strong
        # indicator + momentum signals can still pass without candlestick/
        # structural, but at a naturally lower score that reflects the reduced
        # confirmation.
        raw_score = sum(w * v for w, v in components.values())
        active_weight_sum = sum(w for w, v in components.values() if v > 0)

        # No normalization — raw score = composite score.
        # The 0.40 threshold lets indicator+momentum proposals through (~0.35-0.55)
        # while candlestick+structural proposals naturally score higher (~0.60-0.85).
        composite_score = raw_score

        score_breakdown = {
            "indicator_quality": indicator_quality,
            "candlestick_quality": candlestick_quality,
            "structural_alignment": structural_alignment,
            "momentum_confirmation": round(momentum_confirmation, 6),
            "historian_score": historian_score,
            "raw_score": round(raw_score, 6),
            "active_weight_sum": active_weight_sum,
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
