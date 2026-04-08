"""
20 Trader Evaluator classes for BTC/Bybit setup evaluation.

Each evaluator receives a BTCSetupPacket and returns a TraderVerdict.
Every evaluator uses a distinct analytical lens.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.setup_packet import BTCSetupPacket

from core.schemas import Direction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class TraderVerdict:
    trader_id: str           # e.g. "TrendFollowing"
    score: float             # 1.0 to 10.0
    vote: str                # "approve" | "reject" | "abstain"
    confidence: float        # 0.0 to 1.0
    pro_reason: str          # one sentence why this trade is good
    anti_reason: str         # one sentence why this trade is risky
    execution_concern: str   # e.g. "entry timing off" or "none"
    risk_concern: str        # e.g. "wide stop" or "none"
    explanation: str         # 2-3 sentence explanation of verdict
    metadata: dict = field(default_factory=dict)  # evaluator-specific detected signals


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseTraderEvaluator:
    trader_id: str = "base"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        raise NotImplementedError

    def _make_verdict(
        self,
        score: float,
        vote: str,
        confidence: float,
        pro: str,
        anti: str,
        exec_concern: str,
        risk_concern: str,
        explanation: str,
        metadata: Optional[dict] = None,
    ) -> TraderVerdict:
        return TraderVerdict(
            trader_id=self.trader_id,
            score=max(1.0, min(10.0, score)),
            vote=vote,
            confidence=confidence,
            pro_reason=pro,
            anti_reason=anti,
            execution_concern=exec_concern,
            risk_concern=risk_concern,
            explanation=explanation,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------
    # Helpers shared by multiple evaluators
    # ------------------------------------------------------------------

    @staticmethod
    def _direction_str(packet: "BTCSetupPacket") -> str:
        """Return 'long' or 'short' as a plain string."""
        d = packet.proposal.direction
        if isinstance(d, Direction):
            return d.value
        return str(d).lower()

    @staticmethod
    def _vote_from_score(score: float, approve_threshold: float = 6.0, reject_threshold: float = 4.0) -> str:
        if score >= approve_threshold:
            return "approve"
        if score <= reject_threshold:
            return "reject"
        return "abstain"


# ---------------------------------------------------------------------------
# 1. TrendFollowingEvaluator
# ---------------------------------------------------------------------------

class TrendFollowingEvaluator(BaseTraderEvaluator):
    """Evaluates alignment with the prevailing price trend."""

    trader_id = "TrendFollowing"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        struct = packet.structure
        direction = self._direction_str(packet)

        score = 5.0
        ema_aligned = (
            (direction == "long" and ind.ema_alignment in ("full_bull", "partial_bull"))
            or (direction == "short" and ind.ema_alignment in ("full_bear", "partial_bear"))
        )

        # EMA alignment: full alignment = strong bonus, counter-trend = heavy penalty
        if direction == "long":
            if ind.ema_alignment == "full_bull":
                score += 2.5   # 8-9 territory with other bonuses
            elif ind.ema_alignment == "partial_bull":
                score += 1.5
            elif ind.ema_alignment in ("full_bear", "partial_bear"):
                score -= 2.5   # 2-3 territory — counter-trend
            else:
                score -= 1.5   # mixed/unknown
        else:  # short
            if ind.ema_alignment == "full_bear":
                score += 2.5
            elif ind.ema_alignment == "partial_bear":
                score += 1.5
            elif ind.ema_alignment in ("full_bull", "partial_bull"):
                score -= 2.5
            else:
                score -= 1.5

        # ADX regime awareness: tiered bonus
        if ind.adx14 > 30:
            score += 2.0   # strong trend — big bonus for trend-followers
        elif ind.adx14 > 25:
            score += 1.5
        elif ind.adx14 < 15:
            score -= 0.5   # choppy market — slight penalty

        # Counter-trend in strong trend: extra penalty to reach 2-3 range
        if not ema_aligned and ind.adx14 > 30:
            score -= 0.5

        # Structural trend match
        if direction == "long" and struct.trend_direction == "uptrend":
            score += 1.0
        elif direction == "short" and struct.trend_direction == "downtrend":
            score += 1.0
        else:
            score -= 0.5

        # Higher highs / higher lows confirm uptrend for longs
        if direction == "long" and struct.higher_highs and struct.higher_lows:
            score += 0.5
        elif direction == "short" and not struct.higher_highs and not struct.higher_lows:
            score += 0.5

        vote = self._vote_from_score(score)
        confidence = min(0.95, 0.5 + (score - 5.0) * 0.08)

        meta = {
            "ema_alignment": ind.ema_alignment,
            "adx14": ind.adx14,
            "trend_direction": struct.trend_direction,
            "higher_highs": struct.higher_highs,
            "higher_lows": struct.higher_lows,
            "ema_aligned": ema_aligned,
        }

        pro = (
            f"EMA alignment is {ind.ema_alignment} and ADX {ind.adx14:.1f} confirms "
            f"trend strength for a {direction} trade."
        )
        anti = (
            f"Trend-following entries can chase price; structure trend is "
            f"{struct.trend_direction} which may diverge from proposal."
        )
        exec_concern = "entry may be late in trend" if ind.adx14 > 40 else "none"
        risk_concern = "counter-trend trade risk" if not ema_aligned else "none"
        explanation = (
            f"EMA alignment ({ind.ema_alignment}) {'supports' if ema_aligned else 'opposes'} the "
            f"{direction} direction. ADX at {ind.adx14:.1f} indicates "
            f"{'strong' if ind.adx14 > 25 else 'moderate' if ind.adx14 > 15 else 'weak'} trend momentum. "
            f"Structural trend is {struct.trend_direction}."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 2. MomentumEvaluator
# ---------------------------------------------------------------------------

class MomentumEvaluator(BaseTraderEvaluator):
    """Evaluates RSI momentum and volume participation."""

    trader_id = "Momentum"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        direction = self._direction_str(packet)
        score = 5.0

        rsi = ind.rsi14
        rsi_direction_aligned = (
            (direction == "long" and ind.rsi_direction == "rising")
            or (direction == "short" and ind.rsi_direction == "falling")
        )

        if direction == "long":
            if 40 <= rsi <= 65:
                score += 2.0   # sweet spot for longs
            elif 65 < rsi <= 75:
                score += 0.5   # still ok, slightly extended
            elif rsi > 75:
                score -= 2.5   # overbought — chase risk
            elif rsi < 30:
                score -= 1.0   # oversold bounce territory (MeanReversion handles this better)
            # RSI direction confirmation — bigger bonus when direction aligned
            if rsi_direction_aligned:
                score += 1.5 if 40 <= rsi <= 65 else 0.5
        else:  # short
            if 35 <= rsi <= 60:
                score += 2.0
            elif 25 <= rsi < 35:
                score += 0.5
            elif rsi < 25:
                score -= 2.5   # oversold — risky short
            elif rsi > 70:
                score -= 0.5
            if rsi_direction_aligned:
                score += 1.5 if 35 <= rsi <= 60 else 0.5

        # Volume confirmation
        if ind.volume_ratio > 2.0:
            score += 1.5   # surge — strong conviction
        elif ind.volume_ratio > 1.5:
            score += 1.0
        elif ind.volume_ratio > 1.2:
            score += 0.5
        elif ind.volume_ratio < 0.8:
            score -= 1.0

        # ADX regime awareness: trend-momentum synergy
        if ind.adx14 > 25 and rsi_direction_aligned:
            score += 0.5   # trending AND RSI confirming = strong momentum setup

        vote = self._vote_from_score(score)
        confidence = min(0.9, 0.45 + abs(rsi - 50) * 0.005 + (score - 5) * 0.06)

        overbought = rsi > 75 and direction == "long"
        oversold = rsi < 25 and direction == "short"

        meta = {
            "rsi14": rsi,
            "rsi_direction": ind.rsi_direction,
            "rsi_direction_aligned": rsi_direction_aligned,
            "volume_ratio": ind.volume_ratio,
            "volume_confirmed": ind.volume_ratio > 1.2,
            "adx14": ind.adx14,
        }

        pro = (
            f"RSI {rsi:.1f} with {ind.rsi_direction} momentum supports "
            f"{direction} entry at current price levels."
        )
        anti = (
            f"{'RSI is overbought for a long entry' if overbought else 'RSI is oversold for a short entry' if oversold else 'Momentum may not be fully aligned'}; "
            f"volume ratio {ind.volume_ratio:.2f} {'confirms' if ind.volume_ratio > 1.3 else 'lacks'} participation."
        )
        exec_concern = "momentum overextended" if overbought or oversold else "none"
        risk_concern = "low volume confirmation" if ind.volume_ratio < 1.0 else "none"
        explanation = (
            f"RSI at {rsi:.1f} is {'in ideal range' if (direction == 'long' and 40 <= rsi <= 65) or (direction == 'short' and 35 <= rsi <= 60) else 'outside ideal range'} for "
            f"a {direction} trade, trending {ind.rsi_direction} ({'aligned' if rsi_direction_aligned else 'misaligned'}). "
            f"Volume ratio {ind.volume_ratio:.2f} {'provides' if ind.volume_ratio > 1.3 else 'lacks'} momentum confirmation. "
            f"Score {score:.1f} reflects overall momentum quality."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 3. MeanReversionEvaluator
# ---------------------------------------------------------------------------

class MeanReversionEvaluator(BaseTraderEvaluator):
    """Seeks counter-trend opportunities at statistical extremes."""

    trader_id = "MeanReversion"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        struct = packet.structure
        direction = self._direction_str(packet)

        meta = {
            "rsi14": ind.rsi14,
            "bb_position": ind.bb_position,
            "at_support": struct.at_support,
            "at_resistance": struct.at_resistance,
            "adx14": ind.adx14,
            "adx_trending": ind.adx14 > 25,
        }

        # ADX awareness: strong trends don't revert — this evaluator should abstain
        if ind.adx14 > 25:
            return self._make_verdict(
                5.5, "abstain", 0.3,
                "Price may eventually revert but trend strength reduces probability.",
                f"ADX {ind.adx14:.1f} > 25 indicates trending market — mean reversion setups have lower win rate.",
                "strong trend running", "none",
                f"ADX at {ind.adx14:.1f} indicates strong trend. Mean reversion specialist abstains: "
                f"trend continuation is more probable than reversal at this momentum level. "
                f"Will score normally once ADX falls below 25.",
                metadata=meta,
            )

        score = 3.0  # Default: trend-following trades are not their style

        bullish_extreme = (
            ind.rsi14 < 35
            and struct.at_support
            and ind.bb_position == "below_lower"
        )
        bearish_extreme = (
            ind.rsi14 > 70
            and struct.at_resistance
            and ind.bb_position == "above_upper"
        )

        if direction == "long" and bullish_extreme:
            score = 8.0
        elif direction == "short" and bearish_extreme:
            score = 8.0
        elif direction == "long" and ind.rsi14 < 40 and struct.at_support:
            score = 6.0
        elif direction == "short" and ind.rsi14 > 65 and struct.at_resistance:
            score = 6.0

        vote = self._vote_from_score(score)
        # Reduced confidence in 20-25 ADX zone (partial trend — reversion less reliable)
        base_confidence = 0.8 if score >= 7 else (0.55 if score >= 5.5 else 0.3)
        confidence = base_confidence * 0.8 if ind.adx14 >= 20 else base_confidence

        pro = (
            f"Price at {'support with RSI oversold' if direction == 'long' else 'resistance with RSI overbought'} "
            f"provides mean-reversion opportunity."
        )
        anti = (
            f"Mean reversion trades require {'bullish_extreme conditions' if direction == 'long' else 'bearish_extreme conditions'}; "
            f"current RSI {ind.rsi14:.1f} and BB position {ind.bb_position} may not be extreme enough."
        )
        exec_concern = "trend may continue before reverting" if score < 6 else "none"
        risk_concern = "no structural extreme present" if score < 5 else "none"
        explanation = (
            f"Mean reversion specialist scores this {'highly' if score >= 7 else 'moderately' if score >= 5 else 'poorly'} "
            f"as a {direction} trade. RSI at {ind.rsi14:.1f} and BB position '{ind.bb_position}' "
            f"{'confirm' if score >= 7 else 'partially support' if score >= 5 else 'do not support'} an extreme reversal setup. "
            f"Support/resistance {'is' if (struct.at_support or struct.at_resistance) else 'is not'} present."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 4. BreakoutEvaluator
# ---------------------------------------------------------------------------

class BreakoutEvaluator(BaseTraderEvaluator):
    """Evaluates breakout setups from chart patterns and BB squeezes."""

    trader_id = "Breakout"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        cp = packet.chart_pattern
        direction = self._direction_str(packet)
        proposal = packet.proposal

        score = 5.0

        has_confirmed = bool(cp.confirmed_patterns)
        volume_strong = ind.volume_ratio > 1.5
        volume_ok = ind.volume_ratio >= 1.2

        if has_confirmed and volume_strong:
            score = 8.0
        elif has_confirmed and volume_ok:
            score = 6.5
        elif has_confirmed:
            score = 5.0  # confirmed but weak volume
            score -= 1.0  # penalize

        if not volume_ok:
            score -= 1.0

        # Check entry proximity to breakout level
        if cp.breakout_level is not None:
            entry = float(proposal.entry_price)
            breakout = float(cp.breakout_level)
            if breakout > 0:
                proximity_pct = abs(entry - breakout) / breakout * 100
                if proximity_pct < 0.5:
                    score += 1.0  # entry tight to breakout
                elif proximity_pct > 2.0:
                    score -= 1.0  # entry far from breakout

        # BB squeeze context — tiered bonus: tighter squeeze = stronger pending move
        bb_squeeze = "none"
        if ind.bb_width_pct < 15:
            score += 1.0   # very tight squeeze — high-probability explosive breakout
            bb_squeeze = "very_tight"
        elif ind.bb_width_pct < 20:
            score += 0.5   # moderate squeeze
            bb_squeeze = "tight"

        vote = self._vote_from_score(score)
        confidence = 0.75 if has_confirmed else 0.4

        meta = {
            "confirmed_patterns": list(cp.confirmed_patterns),
            "volume_ratio": ind.volume_ratio,
            "volume_confirmed": volume_ok,
            "bb_width_pct": ind.bb_width_pct,
            "bb_squeeze": bb_squeeze,
        }

        pro = (
            f"{'Confirmed chart pattern breakout' if has_confirmed else 'Active pattern forming'} "
            f"with volume ratio {ind.volume_ratio:.2f} {'confirms' if volume_strong else 'suggests'} breakout participation."
        )
        anti = (
            f"{'Volume below breakout threshold' if not volume_ok else 'Breakout may be premature'}; "
            f"BB width percentile {ind.bb_width_pct:.0f} {'indicates tight squeeze' if bb_squeeze != 'none' else 'is normal'}."
        )
        exec_concern = "entry too far from breakout level" if cp.breakout_level is not None and score < 6 else "none"
        risk_concern = "low breakout volume" if not volume_ok else "none"
        explanation = (
            f"Breakout evaluator {'confirms' if score >= 7 else 'partially supports' if score >= 5 else 'rejects'} this {direction} setup. "
            f"{'Confirmed patterns: ' + ', '.join(cp.confirmed_patterns) if has_confirmed else 'No confirmed patterns present'}. "
            f"Volume ratio {ind.volume_ratio:.2f} {'meets' if volume_ok else 'fails'} minimum breakout threshold. "
            f"{'BB squeeze (' + bb_squeeze + ') adds breakout probability.' if bb_squeeze != 'none' else ''}"
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 5. StructureEvaluator
# ---------------------------------------------------------------------------

class StructureEvaluator(BaseTraderEvaluator):
    """Deep analysis of support/resistance structure quality."""

    trader_id = "Structure"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        struct = packet.structure
        direction = self._direction_str(packet)
        score = 5.0

        if direction == "long":
            if struct.at_support:
                score += 3.0
                if struct.support_distance_pct is not None and struct.support_distance_pct < 1.0:
                    score += 0.5  # very close to support
            if struct.higher_highs and struct.higher_lows:
                score += 1.0
        else:  # short
            if struct.at_resistance:
                score += 3.0
                if struct.resistance_distance_pct is not None and struct.resistance_distance_pct < 1.0:
                    score += 0.5
            if not struct.higher_highs and not struct.higher_lows:
                score += 1.0

        if struct.structure_quality == "strong":
            score += 2.0
        elif struct.structure_quality == "moderate":
            score += 0.5
        elif struct.structure_quality in ("weak", "none"):
            score -= 1.5

        vote = self._vote_from_score(score)
        confidence = 0.85 if struct.structure_quality == "strong" else 0.6

        at_level = (struct.at_support and direction == "long") or (struct.at_resistance and direction == "short")
        meta = {
            "at_support": struct.at_support,
            "at_resistance": struct.at_resistance,
            "structure_quality": struct.structure_quality,
            "trend_direction": struct.trend_direction,
            "higher_highs": struct.higher_highs,
            "higher_lows": struct.higher_lows,
            "at_level": at_level,
        }
        pro = (
            f"Trade is {'at key ' + ('support' if direction == 'long' else 'resistance') if at_level else 'near structure'} "
            f"with {struct.structure_quality} quality level providing solid reference point."
        )
        anti = (
            f"Structure quality '{struct.structure_quality}' {'may not hold under pressure' if struct.structure_quality != 'strong' else 'can still fail on high momentum moves'}."
        )
        exec_concern = "entry not at structure level" if not at_level else "none"
        risk_concern = f"structure quality is {struct.structure_quality}" if struct.structure_quality in ("weak", "none") else "none"
        explanation = (
            f"Structure evaluator assesses {'support' if direction == 'long' else 'resistance'} quality as {struct.structure_quality}. "
            f"{'Price is at the level' if at_level else 'Price is not precisely at structure'}. "
            f"Higher-highs/higher-lows pattern: {struct.higher_highs}/{struct.higher_lows}."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 6. CandlestickEvaluator
# ---------------------------------------------------------------------------

class CandlestickEvaluator(BaseTraderEvaluator):
    """Evaluates candlestick pattern signals."""

    trader_id = "Candlestick"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        cs = packet.candlestick
        direction = self._direction_str(packet)
        score = 4.0  # no patterns → neutral-weak

        if not cs.patterns_detected:
            vote = "abstain"
            return self._make_verdict(
                score, vote, 0.3,
                "No candlestick signal to confirm or deny the trade.",
                "Absence of candlestick pattern means no bar-level confirmation.",
                "no candle confirmation",
                "none",
                "No candlestick patterns detected on this bar. "
                "The trade lacks bar-level confirmation signal. "
                "Abstaining pending pattern formation.",
            )

        score = 5.0

        # Pattern at structure bonus
        if cs.pattern_at_structure:
            score += 2.0

        # Pattern direction alignment
        if cs.pattern_direction is not None:
            if (direction == "long" and cs.pattern_direction == "bullish") or \
               (direction == "short" and cs.pattern_direction == "bearish"):
                score += 2.0
            elif cs.pattern_direction not in (None, "neutral"):
                score -= 1.5  # opposing candle signal

        # Quality bonus for high-conviction patterns
        quality_patterns = {
            "bullish_engulfing", "bearish_engulfing",
            "morning_star", "evening_star",
            "three_white_soldiers", "three_black_crows",
            "hammer", "shooting_star",
        }
        if cs.primary_pattern and cs.primary_pattern.lower() in quality_patterns:
            score += 1.5

        vote = self._vote_from_score(score)
        confidence = 0.7 if cs.pattern_at_structure else 0.5

        direction_match = cs.pattern_direction and (
            (direction == "long" and cs.pattern_direction == "bullish")
            or (direction == "short" and cs.pattern_direction == "bearish")
        )
        meta = {
            "primary_pattern": cs.primary_pattern,
            "pattern_direction": cs.pattern_direction,
            "pattern_at_structure": cs.pattern_at_structure,
            "patterns_detected": list(cs.patterns_detected),
            "direction_match": bool(direction_match),
        }
        pro = (
            f"Candlestick '{cs.primary_pattern}' is {'at a structural level' if cs.pattern_at_structure else 'present'} "
            f"with {'matching' if direction_match else 'neutral'} direction."
        )
        anti = (
            f"Candlestick patterns are single-bar signals with {'high' if cs.pattern_at_structure else 'moderate'} "
            f"failure rate without follow-through confirmation."
        )
        exec_concern = "pattern direction opposes trade" if cs.pattern_direction and \
            ((direction == "long" and cs.pattern_direction == "bearish") or
             (direction == "short" and cs.pattern_direction == "bullish")) else "none"
        risk_concern = "none"
        explanation = (
            f"Primary pattern '{cs.primary_pattern}' detected with direction '{cs.pattern_direction}'. "
            f"Pattern {'is' if cs.pattern_at_structure else 'is not'} at a structural level, "
            f"which {'significantly enhances' if cs.pattern_at_structure else 'moderately affects'} reliability. "
            f"Score {score:.1f} reflects pattern quality and alignment with {direction} proposal."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 7. RiskParityEvaluator
# ---------------------------------------------------------------------------

class RiskParityEvaluator(BaseTraderEvaluator):
    """Evaluates position sizing and risk/reward balance."""

    trader_id = "RiskParity"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        proposal = packet.proposal
        rr = proposal.r_r_ratio
        stop_pct = proposal.stop_distance_pct

        # Score based on R:R
        # Formula: 3.0 + rr*2.0 so that R:R=2.0 → 7.0 (approve-range),
        # R:R=1.5 → 6.0 (abstain), R:R=1.0 → 5.0.
        # The original formula (rr*1.5) gave score=3.0 for R:R=2.0 while
        # simultaneously voting "approve" — an incoherent combination that
        # dragged the panel avg below the 6.5 threshold for good setups.
        score = min(9.0, 3.0 + rr * 2.0)

        # Stop width concern
        stop_concern = "none"
        if stop_pct > 5.0:
            score -= 1.5
            stop_concern = f"stop too wide at {stop_pct:.1f}% — increases loss magnitude"
        elif stop_pct < 0.5:
            score -= 1.0
            stop_concern = f"stop too tight at {stop_pct:.2f}% — likely to be stopped prematurely"

        if rr < 1.5:
            vote = "reject"
        elif rr >= 2.0:
            vote = "approve"
        else:
            vote = "abstain"

        confidence = min(0.9, 0.4 + rr * 0.15)

        pro = (
            f"R:R ratio of {rr:.2f} with stop distance {stop_pct:.2f}% provides "
            f"{'favorable' if rr >= 2.0 else 'acceptable'} risk/reward balance."
        )
        anti = (
            f"{'Insufficient R:R below 1.5 — trade not worth the risk' if rr < 1.5 else 'Risk profile acceptable but monitor stop placement'}."
        )
        exec_concern = "none"
        risk_concern = stop_concern if stop_concern != "none" else (
            f"R:R {rr:.2f} below minimum 1.5" if rr < 1.5 else "none"
        )
        explanation = (
            f"Risk parity analysis: R:R = {rr:.2f}, stop distance = {stop_pct:.2f}%. "
            f"Minimum acceptable R:R is 1.5; ideal is 2.0+. "
            f"{'Trade meets' if rr >= 2.0 else 'Trade marginally meets' if rr >= 1.5 else 'Trade fails'} risk parity criteria."
        )
        meta = {"r_r_ratio": rr, "stop_distance_pct": stop_pct}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 8. VolatilityEvaluator
# ---------------------------------------------------------------------------

class VolatilityEvaluator(BaseTraderEvaluator):
    """Evaluates volatility regime suitability for the proposed trade."""

    trader_id = "Volatility"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        proposal = packet.proposal
        vol_regime = ind.volatility_regime
        atr_ratio = ind.atr14_vs_sma20

        score = 7.0 if vol_regime == "normal" else 5.0

        exec_concern = "none"
        risk_concern = "none"

        if vol_regime == "high":
            risk_concern = "high volatility — stop may be triggered prematurely on wick"
            if proposal.stop_distance_pct < 1.5:
                score -= 2.0
                exec_concern = "stop too tight for high-volatility regime"
            else:
                score -= 1.0

        elif vol_regime == "low":
            if atr_ratio < 0.7:
                score -= 1.0
                risk_concern = "low volatility squeeze — breakout may lack follow-through"

        # Impulse candle check
        if atr_ratio > 1.5:
            exec_concern = "entry on impulse candle — overextended ATR"
            score -= 1.0

        vote = self._vote_from_score(score)
        confidence = 0.7 if vol_regime == "normal" else 0.5

        pro = (
            f"Volatility regime is '{vol_regime}' with ATR ratio {atr_ratio:.2f}, "
            f"{'suitable for' if vol_regime == 'normal' else 'requiring caution on'} this trade."
        )
        anti = (
            f"{'High volatility can trigger stops on normal price swings' if vol_regime == 'high' else 'Low volatility squeezes may produce false breakouts' if vol_regime == 'low' else 'Volatility is within normal range'}."
        )
        explanation = (
            f"Volatility regime is '{vol_regime}' (ATR vs SMA20: {atr_ratio:.2f}). "
            f"{'High volatility requires wider stops and stronger signal consensus.' if vol_regime == 'high' else 'Low volatility may reduce follow-through on breakouts.' if vol_regime == 'low' else 'Normal volatility supports standard trade execution.'} "
            f"Score adjusted to {score:.1f}."
        )
        meta = {"volatility_regime": vol_regime, "atr_ratio": atr_ratio}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 9. VolumeProfileEvaluator
# ---------------------------------------------------------------------------

class VolumeProfileEvaluator(BaseTraderEvaluator):
    """Evaluates volume character and participation quality."""

    trader_id = "VolumeProfile"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        direction = self._direction_str(packet)

        score = 5.0

        if ind.volume_ratio > 1.5:
            score += 2.0
        elif ind.volume_ratio > 1.2:
            score += 1.0
        elif ind.volume_ratio < 0.8:
            score -= 2.0

        if ind.volume_character == "surge":
            score += 3.0
        elif ind.volume_character == "above_avg":
            score += 1.0
        elif ind.volume_character == "below_avg":
            score -= 2.0

        score = min(10.0, score)

        vote = self._vote_from_score(score)
        confidence = min(0.9, 0.4 + ind.volume_ratio * 0.2)

        pro = (
            f"Volume character '{ind.volume_character}' with ratio {ind.volume_ratio:.2f} "
            f"{'strongly confirms' if ind.volume_character == 'surge' else 'supports'} institutional participation."
        )
        anti = (
            f"Volume {'is below average — weak conviction' if ind.volume_character == 'below_avg' else 'spikes can be temporary and misleading'}."
        )
        exec_concern = "none"
        risk_concern = "below average volume — low institutional interest" if ind.volume_character == "below_avg" else "none"
        explanation = (
            f"Volume profile shows {ind.volume_character} character at {ind.volume_ratio:.2f}x average. "
            f"{'Strong volume surge confirms institutional engagement.' if ind.volume_character == 'surge' else 'Volume is within normal range.' if ind.volume_character == 'normal' else 'Volume character reduces confidence.'} "
            f"Score {score:.1f} reflects volume-based conviction for this {direction} setup."
        )
        meta = {"volume_ratio": ind.volume_ratio, "volume_character": ind.volume_character, "volume_confirmed": ind.volume_ratio > 1.2}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 10. MacroRegimeEvaluator
# ---------------------------------------------------------------------------

class MacroRegimeEvaluator(BaseTraderEvaluator):
    """Evaluates macro BTC regime alignment."""

    trader_id = "MacroRegime"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        regime = packet.regime
        direction = self._direction_str(packet)
        macro = regime.btc_macro

        score = 5.0

        if macro == "bull" and direction == "long":
            score += 3.0
        elif macro == "bear" and direction == "short":
            score += 3.0
        elif macro == "bull" and direction == "short":
            score -= 2.0
        elif macro == "bear" and direction == "long":
            score -= 3.0  # most dangerous combination

        if regime.trending:
            score += 1.0

        cross_regime = (macro == "bear" and direction == "long") or \
                       (macro == "bull" and direction == "short")

        vote = self._vote_from_score(score)
        confidence = 0.8 if not cross_regime else 0.3

        pro = (
            f"BTC macro regime is '{macro}' — {'aligned with' if not cross_regime else 'opposing'} "
            f"the {direction} trade direction."
        )
        anti = (
            f"{'Cross-regime trade — macro wind is against this direction' if cross_regime else 'Macro-aligned trades can still fail on micro structure'}."
        )
        exec_concern = "none"
        risk_concern = f"trading {direction} in {macro} macro regime" if cross_regime else "none"
        explanation = (
            f"BTC macro is '{macro}' with trending={regime.trending}. "
            f"This {direction} trade {'aligns with' if not cross_regime else 'fights'} the macro regime. "
            f"{'High-probability setup with macro tailwind.' if score >= 7 else 'Neutral macro context.' if score >= 5 else 'Significant headwind from macro regime.'}"
        )
        meta = {"btc_macro": macro, "trending": regime.trending, "macro_aligned": not cross_regime}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 11. ContraryEvaluator
# ---------------------------------------------------------------------------

class ContraryEvaluator(BaseTraderEvaluator):
    """Devil's advocate — always highlights the biggest risk and is intentionally skeptical."""

    trader_id = "Contrary"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        proposal = packet.proposal
        struct = packet.structure
        ind = packet.indicators
        direction = self._direction_str(packet)
        rsi = ind.rsi14

        meta = {
            "rsi14": rsi,
            "r_r_ratio": proposal.r_r_ratio,
            "structure_quality": struct.structure_quality,
            "volume_ratio": ind.volume_ratio,
            "adx14": ind.adx14,
        }

        # RSI extreme check — momentum overextension is contrary's primary alert
        rsi_extreme = (direction == "long" and rsi > 80) or (direction == "short" and rsi < 20)

        # Score logic: skeptical but not a permaveto
        if proposal.r_r_ratio > 3.0 and struct.structure_quality == "strong":
            score = 7.5  # exceptional setup — even skeptics can't argue much
            confidence = 0.55
        elif proposal.r_r_ratio >= 2.5 and struct.structure_quality in ("strong", "moderate"):
            score = 6.0  # good setup — abstain with slight lean
            confidence = 0.5
        elif rsi_extreme:
            score = 3.0  # momentum-chasing at extreme — contrary rejects
            confidence = 0.7
        else:
            score = 5.0  # skeptical but not vetoing — abstain
            confidence = 0.5

        # Identify the biggest risk factor
        risks = []
        if proposal.r_r_ratio < 2.0:
            risks.append(f"R:R {proposal.r_r_ratio:.2f} is below 2.0")
        if struct.structure_quality in ("weak", "none"):
            risks.append(f"structure quality is {struct.structure_quality}")
        if ind.volume_ratio < 1.0:
            risks.append("volume below average")
        if ind.adx14 < 20:
            risks.append("weak trend strength")
        if ind.volatility_regime == "high":
            risks.append("high volatility regime")
        if rsi_extreme:
            risks.insert(0, f"RSI {rsi:.0f} extreme — momentum overextended")

        biggest_risk = risks[0] if risks else "market conditions uncertain"

        vote = self._vote_from_score(score)
        pro = f"Even skeptics acknowledge the {direction} trade has a defined stop and measurable target."
        anti = (
            f"Contrary view: {biggest_risk} — the market rarely moves cleanly in the proposed direction."
        )
        exec_concern = "overconfidence in setup quality" if proposal.setup_quality == "A" and score < 6 else "none"
        risk_concern = biggest_risk
        explanation = (
            f"Contrary evaluator applies skepticism to the {direction} proposal. "
            f"Primary concern: {biggest_risk}. "
            f"Approves only with R:R > 3.0 AND strong structure (current R:R {proposal.r_r_ratio:.2f}). "
            f"{'RSI extreme overextension detected.' if rsi_extreme else 'Neutral skepticism applied.'}"
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 12. ProfitTargetEvaluator
# ---------------------------------------------------------------------------

class ProfitTargetEvaluator(BaseTraderEvaluator):
    """Focuses on target quality and achievability."""

    trader_id = "ProfitTarget"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        proposal = packet.proposal
        cp = packet.chart_pattern
        rr = proposal.r_r_ratio

        if rr >= 2.5:
            score = 8.0
        elif rr >= 2.0:
            score = 7.0
        elif rr >= 1.5:
            score = 5.0
        else:
            score = 3.0

        target_notes = "no chart pattern target"
        if cp.primary_confirmed and cp.conservative_target is not None:
            score += 2.0
            target_notes = (
                f"chart pattern target at {float(cp.conservative_target):.0f}"
            )

        vote = self._vote_from_score(score)
        confidence = min(0.85, 0.4 + rr * 0.15)

        direction = self._direction_str(packet)
        pro = (
            f"R:R of {rr:.2f} with {target_notes} provides "
            f"{'excellent' if rr >= 2.5 else 'good' if rr >= 2.0 else 'marginal'} profit potential."
        )
        anti = (
            f"{'Target may be unrealistic without chart pattern confirmation' if not cp.primary_confirmed else 'Chart pattern targets have ~50% completion rate'}."
        )
        exec_concern = "target not backed by chart pattern" if not cp.primary_confirmed else "none"
        risk_concern = f"R:R {rr:.2f} below minimum 2.0" if rr < 2.0 else "none"
        explanation = (
            f"Profit target analysis: R:R = {rr:.2f}. "
            f"{'Confirmed pattern provides objective target.' if cp.primary_confirmed else 'No confirmed pattern — target is structurally derived.'} "
            f"Score {score:.1f} reflects target achievability for this {direction} trade."
        )
        meta = {"r_r_ratio": rr, "has_chart_target": bool(cp.primary_confirmed and cp.conservative_target is not None)}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 13. EntryTimingEvaluator
# ---------------------------------------------------------------------------

class EntryTimingEvaluator(BaseTraderEvaluator):
    """Evaluates whether the current bar offers good entry timing."""

    trader_id = "EntryTiming"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        struct = packet.structure
        proposal = packet.proposal
        direction = self._direction_str(packet)

        score = 5.0
        exec_concern = "none"

        # Impulse candle check
        if ind.atr14_vs_sma20 > 2.0:
            score -= 2.0
            exec_concern = "entry on impulse candle — ATR ratio overextended"
        elif ind.atr14_vs_sma20 > 1.5:
            score -= 1.0
            exec_concern = "slightly elevated ATR — entry timing marginal"

        # Structured entry bonus
        if direction == "long" and struct.at_support:
            score += 2.0
        elif direction == "short" and struct.at_resistance:
            score += 2.0

        # BB position for timing
        if direction == "long" and ind.bb_position in ("near_lower", "below_lower"):
            score += 1.0
        elif direction == "short" and ind.bb_position in ("near_upper", "above_upper"):
            score += 1.0

        vote = self._vote_from_score(score)
        confidence = 0.65

        at_level = (direction == "long" and struct.at_support) or (direction == "short" and struct.at_resistance)
        pro = (
            f"Entry {'is at key structural level' if at_level else 'is near current price'} with "
            f"ATR ratio {ind.atr14_vs_sma20:.2f} indicating {'normal' if ind.atr14_vs_sma20 <= 1.5 else 'elevated'} candle velocity."
        )
        anti = (
            f"{'Impulse candle reduces entry quality — chasing price' if ind.atr14_vs_sma20 > 2.0 else 'Entry timing is acceptable but could improve'}."
        )
        risk_concern = "none"
        explanation = (
            f"Entry timing evaluation: ATR ratio {ind.atr14_vs_sma20:.2f}, BB position '{ind.bb_position}'. "
            f"{'Structural level provides ideal entry reference.' if at_level else 'Entry lacks structural level anchor.'} "
            f"Score {score:.1f} reflects timing quality for {direction} entry."
        )
        meta = {"atr_ratio": ind.atr14_vs_sma20, "bb_position": ind.bb_position, "at_structure": at_level}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 14. ConfluenceEvaluator
# ---------------------------------------------------------------------------

class ConfluenceEvaluator(BaseTraderEvaluator):
    """Counts the number of independent signals agreeing with the proposal."""

    trader_id = "Confluence"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        struct = packet.structure
        cs = packet.candlestick
        cp = packet.chart_pattern
        regime = packet.regime
        proposal = packet.proposal
        direction = self._direction_str(packet)

        agreement_count = 0

        # 1. EMA alignment
        if direction == "long" and ind.ema_alignment in ("full_bull", "partial_bull"):
            agreement_count += 1
        elif direction == "short" and ind.ema_alignment in ("full_bear", "partial_bear"):
            agreement_count += 1

        # 2. RSI momentum
        if direction == "long" and ind.rsi_direction == "rising" and ind.rsi14 < 70:
            agreement_count += 1
        elif direction == "short" and ind.rsi_direction == "falling" and ind.rsi14 > 30:
            agreement_count += 1

        # 3. Candlestick pattern alignment
        if cs.pattern_direction is not None:
            if (direction == "long" and cs.pattern_direction == "bullish") or \
               (direction == "short" and cs.pattern_direction == "bearish"):
                agreement_count += 1

        # 4. Chart pattern confirmation
        if cp.confirmed_patterns:
            if cp.pattern_direction == direction or cp.pattern_direction is None:
                agreement_count += 1

        # 5. Structure alignment
        if direction == "long" and struct.at_support:
            agreement_count += 1
        elif direction == "short" and struct.at_resistance:
            agreement_count += 1

        # 6. Macro regime
        if regime.btc_macro == "bull" and direction == "long":
            agreement_count += 1
        elif regime.btc_macro == "bear" and direction == "short":
            agreement_count += 1

        # 7. Volume confirmation
        if ind.volume_ratio > 1.3:
            agreement_count += 1

        score = min(10.0, 3.0 + agreement_count * 1.5)
        vote = self._vote_from_score(score)
        confidence = min(0.9, agreement_count * 0.12)

        meta = {
            "agreement_count": agreement_count,
            "ema_aligned": (direction == "long" and ind.ema_alignment in ("full_bull", "partial_bull"))
                           or (direction == "short" and ind.ema_alignment in ("full_bear", "partial_bear")),
            "rsi_aligned": (direction == "long" and ind.rsi_direction == "rising" and ind.rsi14 < 70)
                           or (direction == "short" and ind.rsi_direction == "falling" and ind.rsi14 > 30),
            "volume_confirmed": ind.volume_ratio > 1.3,
        }

        pro = (
            f"{agreement_count} independent signals agree with the {direction} proposal, "
            f"providing strong confluence."
        )
        anti = (
            f"{'High confluence can still fail if macro regime shifts abruptly' if agreement_count >= 4 else 'Low confluence suggests setup lacks broad signal agreement'}."
        )
        exec_concern = "none"
        risk_concern = f"only {agreement_count} agreeing signals" if agreement_count < 3 else "none"
        explanation = (
            f"Confluence count: {agreement_count}/7 signals agree with {direction} proposal. "
            f"Score formula: 3.0 + ({agreement_count} × 1.5) = {score:.1f}. "
            f"{'Strong multi-signal agreement.' if agreement_count >= 5 else 'Moderate confluence.' if agreement_count >= 3 else 'Weak confluence — setup needs more signal alignment.'}"
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 15. DrawdownRiskEvaluator
# ---------------------------------------------------------------------------

class DrawdownRiskEvaluator(BaseTraderEvaluator):
    """Specifically assesses drawdown and stop placement risk."""

    trader_id = "DrawdownRisk"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        proposal = packet.proposal
        ind = packet.indicators
        stop_pct = proposal.stop_distance_pct
        rr = proposal.r_r_ratio

        score = 5.0
        risk_concern = "none"
        exec_concern = "none"

        # Stop too wide
        if stop_pct > 3.0:
            risk_concern = f"stop {stop_pct:.1f}% too wide for BTC — large capital at risk per trade"
            score -= 1.5

        # R:R too low — asymmetric against trader
        if rr < 2.0:
            score -= 1.5
            if rr < 1.5:
                vote = "reject"
                score = max(1.0, score - 1.0)
            else:
                vote = "abstain"
        else:
            vote = "approve"

        # Tight stop in high volatility — will be stopped out on normal swings
        if ind.volatility_regime == "high" and stop_pct < 1.5:
            risk_concern = f"stop {stop_pct:.2f}% too tight in high volatility — guaranteed premature stop-out"
            score -= 2.0
            exec_concern = "stop will be triggered by normal volatility noise"

        # Positive reward for excellent risk management.
        # Without this, DrawdownRisk has zero positive adjustments and caps at 5.0
        # (permanent abstain) even for trades with outstanding R:R and tight stops —
        # an incoherent design where good risk management earns the same score as
        # mediocre risk management.
        if rr >= 2.5 and stop_pct <= 3.0:
            score += 1.5   # excellent R:R with controlled stop → approve-range
        elif rr >= 2.0 and stop_pct <= 3.0:
            score += 0.5   # good R:R → lift toward approval zone

        score = max(1.0, score)
        # Re-evaluate vote after adjustments
        if vote != "reject":
            vote = self._vote_from_score(score)

        confidence = min(0.85, 0.5 + (score - 5.0) * 0.07)

        pro = (
            f"Stop at {stop_pct:.2f}% with R:R {rr:.2f} provides "
            f"{'controlled' if stop_pct <= 3.0 else 'aggressive'} drawdown profile."
        )
        anti = (
            f"{'Wide stop increases absolute loss' if stop_pct > 3.0 else 'Tight stop risks premature exit' if stop_pct < 1.0 else 'Stop placement is reasonable'}; "
            f"{'R:R below 2.0 makes drawdown asymmetric' if rr < 2.0 else 'R:R acceptable'}."
        )
        direction = self._direction_str(packet)
        explanation = (
            f"Drawdown risk: stop={stop_pct:.2f}%, R:R={rr:.2f}, volatility='{ind.volatility_regime}'. "
            f"{'Stop too wide for capital efficiency.' if stop_pct > 3.0 else 'Stop width acceptable.'} "
            f"{'R:R below minimum — expected value is poor.' if rr < 2.0 else 'R:R supports positive expected value.'}"
        )
        meta = {"stop_pct": stop_pct, "r_r_ratio": rr, "volatility_regime": ind.volatility_regime}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 16. LeverageSpecialistEvaluator
# ---------------------------------------------------------------------------

class LeverageSpecialistEvaluator(BaseTraderEvaluator):
    """Evaluates proposed leverage against setup quality."""

    trader_id = "LeverageSpecialist"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        proposal = packet.proposal
        leverage = proposal.proposed_leverage
        quality = proposal.setup_quality

        if leverage <= 2.0:
            score = 8.0
            leverage_note = "conservative leverage"
        elif leverage <= 3.0:
            score = 6.0
            leverage_note = "moderate leverage"
        elif leverage <= 5.0:
            score = 4.0
            leverage_note = "elevated leverage"
        else:
            score = 2.0
            leverage_note = "dangerous leverage"

        # Quality gate
        if quality == "A":
            score += 1.0
        elif quality == "B":
            pass  # neutral
        elif quality == "C":
            score -= 1.5
        elif quality == "invalid":
            score = 1.0

        if leverage > 5.0:
            vote = "reject"
        else:
            vote = self._vote_from_score(score)

        confidence = min(0.85, 0.6 + (8.0 - score) * (-0.05))
        confidence = max(0.2, confidence)

        direction = self._direction_str(packet)
        pro = (
            f"Proposed leverage {leverage:.1f}x is {leverage_note} for a {quality}-quality {direction} setup."
        )
        anti = (
            f"{'Leverage above 5x is unacceptable for BTC — liquidation risk is severe' if leverage > 5 else 'Higher leverage magnifies losses on stop-out'}."
        )
        exec_concern = f"leverage {leverage:.1f}x too high for quality {quality}" if leverage > 5 else "none"
        risk_concern = (
            f"leverage {leverage:.1f}x exceeds maximum acceptable" if leverage > 5
            else f"leverage {leverage:.1f}x with {quality}-quality setup" if leverage > 3 and quality in ("C", "invalid")
            else "none"
        )
        explanation = (
            f"Leverage specialist: {leverage:.1f}x leverage on a {quality}-quality setup. "
            f"{'Conservative leverage preserves capital on stop-out.' if leverage <= 2 else 'Moderate leverage acceptable with quality setup.' if leverage <= 3 else 'Elevated leverage significantly increases liquidation risk.'} "
            f"Setup quality '{quality}' {'supports' if quality == 'A' else 'is neutral for' if quality == 'B' else 'does not justify'} this leverage level."
        )
        meta = {"leverage": leverage, "setup_quality": quality}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 17. PatternCompletionEvaluator
# ---------------------------------------------------------------------------

class PatternCompletionEvaluator(BaseTraderEvaluator):
    """Evaluates chart pattern completion and target credibility."""

    trader_id = "PatternCompletion"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        cp = packet.chart_pattern
        direction = self._direction_str(packet)

        # Architecture-aware: if ChartPatternGroup is not active (not in
        # groups_contributed), abstain neutrally instead of penalising with
        # score=4.0.  An empty confirmed_patterns list when the group is
        # EXCLUDED is not evidence of "no pattern" — it means the capability
        # was never run.  Penalising a missing capability as if it were a
        # present-but-failed capability is architecturally incorrect.
        if "chart_pattern" not in packet.groups_contributed:
            return self._make_verdict(
                5.0, "abstain", 0.3,
                "Chart pattern capability is not active in current architecture phase.",
                "No chart pattern evidence available — ChartPatternGroup is excluded.",
                "none", "none",
                "PatternCompletion abstains: ChartPatternGroup is not wired in Phase 3. "
                "The absence of pattern data is a capability gap, not a negative signal. "
                "This evaluator will score normally when ChartPatternGroup is activated.",
            )

        if cp.confirmed_patterns:
            score = 8.0
        elif cp.active_patterns:
            score = 5.0  # forming but not confirmed — premature
        else:
            score = 4.0  # no patterns

        # Bonus for confirmed pattern with conservative target set
        if cp.primary_confirmed and cp.conservative_target is not None:
            score += 2.0

        vote = self._vote_from_score(score)
        confidence = 0.8 if cp.confirmed_patterns else (0.45 if cp.active_patterns else 0.3)

        pro = (
            f"{'Confirmed pattern(s): ' + ', '.join(cp.confirmed_patterns) if cp.confirmed_patterns else 'Active pattern(s) forming: ' + ', '.join(cp.active_patterns) if cp.active_patterns else 'No chart pattern — trade relies on other signals'}."
        )
        anti = (
            f"{'Confirmed patterns still fail ~40-50% of time' if cp.confirmed_patterns else 'Unconfirmed patterns have higher failure rate — entry is premature' if cp.active_patterns else 'No chart pattern means no measured-move target'}."
        )
        exec_concern = "pattern not yet confirmed — premature entry" if cp.active_patterns and not cp.confirmed_patterns else "none"
        risk_concern = "no chart pattern confirmation" if not cp.confirmed_patterns else "none"
        explanation = (
            f"Pattern completion status: {'confirmed — ' + str(cp.primary_confirmed) if cp.confirmed_patterns else 'active but unconfirmed' if cp.active_patterns else 'none'}. "
            f"{'Conservative target set at ' + str(cp.conservative_target) + '.' if cp.conservative_target else 'No measured-move target available.'} "
            f"Score {score:.1f} reflects pattern completion quality for {direction} trade."
        )
        meta = {
            "confirmed_patterns": list(cp.confirmed_patterns),
            "active_patterns": list(cp.active_patterns),
            "has_target": cp.conservative_target is not None,
        }
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 18. WickAnalysisEvaluator
# ---------------------------------------------------------------------------

class WickAnalysisEvaluator(BaseTraderEvaluator):
    """Analyzes candle wick rejection signals at structural levels."""

    trader_id = "WickAnalysis"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        cs = packet.candlestick
        struct = packet.structure
        direction = self._direction_str(packet)

        score = 5.0
        wick_signal = "neutral"

        # Check patterns for wick-based rejections
        wick_bullish_patterns = {"hammer", "inverted_hammer", "dragonfly_doji", "bullish_pin_bar"}
        wick_bearish_patterns = {"shooting_star", "hanging_man", "gravestone_doji", "bearish_pin_bar", "bearish_rejection"}

        patterns_lower = {p.lower() for p in cs.patterns_detected}

        has_bullish_wick = bool(patterns_lower & wick_bullish_patterns)
        has_bearish_wick = bool(patterns_lower & wick_bearish_patterns)

        if direction == "long":
            if struct.at_support and has_bullish_wick:
                score += 2.0
                wick_signal = "bullish wick rejection at support"
            elif struct.at_support:
                score += 0.5
            if has_bearish_wick:
                score -= 2.0
                wick_signal = "bearish wick present against long trade"
        else:  # short
            if struct.at_resistance and has_bearish_wick:
                score += 2.0
                wick_signal = "bearish wick rejection at resistance"
            elif struct.at_resistance:
                score += 0.5
            if has_bullish_wick:
                score -= 2.0
                wick_signal = "bullish wick present against short trade"

        vote = self._vote_from_score(score)
        confidence = 0.7 if wick_signal not in ("neutral",) else 0.45

        pro = (
            f"{'Wick rejection at structural level confirms ' + direction + ' pressure' if wick_signal not in ('neutral', 'bullish wick present against long trade', 'bearish wick present against short trade') else 'No wick rejection present — structure is the primary reference'}."
        )
        anti = (
            f"{'Opposing wick signal detected — price rejected the intended direction' if 'against' in wick_signal else 'Wick analysis requires larger context to avoid false signals'}."
        )
        exec_concern = "opposing wick signal at entry level" if "against" in wick_signal else "none"
        risk_concern = "bearish wick against long" if (direction == "long" and has_bearish_wick) else \
                       "bullish wick against short" if (direction == "short" and has_bullish_wick) else "none"
        explanation = (
            f"Wick analysis: '{wick_signal}'. "
            f"Patterns detected: {cs.patterns_detected or 'none'}. "
            f"{'Wick confirms structural rejection in trade direction.' if score >= 7 else 'No strong wick confirmation — standard candle analysis.'}"
        )
        meta = {
            "wick_signal": wick_signal,
            "has_bullish_wick": has_bullish_wick,
            "has_bearish_wick": has_bearish_wick,
            "at_support": struct.at_support,
            "at_resistance": struct.at_resistance,
        }
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 19. MarketContextEvaluator
# ---------------------------------------------------------------------------

class MarketContextEvaluator(BaseTraderEvaluator):
    """Holistic market context and timing coherence evaluator."""

    trader_id = "MarketContext"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        ind = packet.indicators
        struct = packet.structure
        regime = packet.regime
        cp = packet.chart_pattern
        direction = self._direction_str(packet)

        score = 6.0

        # Consolidation check — bad timing
        in_consolidation = ind.bb_width_pct < 30 and ind.adx14 < 20
        if in_consolidation:
            score -= 2.0

        # Uptrend pullback to support — ideal long context
        if direction == "long" and struct.trend_direction == "uptrend" and struct.at_support:
            score += 2.0
        # Downtrend bounce to resistance — ideal short context
        elif direction == "short" and struct.trend_direction == "downtrend" and struct.at_resistance:
            score += 2.0

        # Regime and pattern coherence
        if regime.btc_macro == "bull" and direction == "long" and cp.pattern_direction in ("bullish", None):
            score += 1.0
        elif regime.btc_macro == "bear" and direction == "short" and cp.pattern_direction in ("bearish", None):
            score += 1.0

        # Mixed signals penalty
        if ind.ema_alignment == "mixed":
            score -= 1.0

        vote = self._vote_from_score(score)
        confidence = 0.65

        pro = (
            f"Market context {'shows ideal pullback-to-support setup' if direction == 'long' and struct.at_support else 'shows ideal bounce-to-resistance setup' if direction == 'short' and struct.at_resistance else 'provides moderate entry context'} "
            f"with {regime.btc_macro} macro backdrop."
        )
        anti = (
            f"{'Consolidation phase detected — breakout timing uncertain' if in_consolidation else 'Market context is coherent but not perfect'}; "
            f"{'EMA alignment is mixed — trend not established' if ind.ema_alignment == 'mixed' else 'EMA alignment supports trade direction'}."
        )
        exec_concern = "market in consolidation — breakout may be false" if in_consolidation else "none"
        risk_concern = "none"
        explanation = (
            f"Market context: {regime.btc_macro} macro, {struct.trend_direction} trend, "
            f"EMA alignment '{ind.ema_alignment}', BB width pct {ind.bb_width_pct:.0f}. "
            f"{'Consolidation phase reduces confidence in breakout timing.' if in_consolidation else 'Context is coherent for trade entry.'} "
            f"Score {score:.1f} reflects overall market coherence."
        )
        meta = {
            "in_consolidation": in_consolidation,
            "trend_direction": struct.trend_direction,
            "btc_macro": regime.btc_macro,
            "ema_alignment": ind.ema_alignment,
        }
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# 20. ExecutionQualityEvaluator
# ---------------------------------------------------------------------------

class ExecutionQualityEvaluator(BaseTraderEvaluator):
    """Evaluates practical execution quality and order placement."""

    trader_id = "ExecutionQuality"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        proposal = packet.proposal
        direction = self._direction_str(packet)
        stop_pct = proposal.stop_distance_pct
        rr = proposal.r_r_ratio
        quality = proposal.setup_quality

        score = 5.0
        exec_notes = []

        # Stop distance quality for BTC
        if 1.0 <= stop_pct <= 3.0:
            score += 1.0
            exec_notes.append(f"stop {stop_pct:.2f}% in optimal BTC range")
        elif stop_pct < 0.5:
            score -= 2.0
            exec_notes.append(f"stop {stop_pct:.2f}% dangerously tight")
        elif stop_pct > 5.0:
            score -= 1.5
            exec_notes.append(f"stop {stop_pct:.2f}% too wide")

        # R:R evaluation
        if rr > 2.0:
            score += 2.0
            exec_notes.append(f"R:R {rr:.2f} favorable")
        elif rr < 1.5:
            score -= 1.5
            exec_notes.append(f"R:R {rr:.2f} below minimum")

        # Setup quality gate
        if quality == "A":
            score += 2.0
            exec_notes.append("A-quality setup")
        elif quality == "B":
            score += 1.0
            exec_notes.append("B-quality setup")
        elif quality == "C":
            score -= 1.0
            exec_notes.append("C-quality setup")
        elif quality == "invalid":
            score = 1.0
            exec_notes.append("invalid setup")

        vote = self._vote_from_score(score)
        confidence = min(0.85, 0.5 + (score - 5.0) * 0.07)

        exec_concern = "; ".join(exec_notes) if exec_notes else "none"

        pro = (
            f"Execution quality: {quality}-grade setup with stop {stop_pct:.2f}% and R:R {rr:.2f} "
            f"for {direction} trade."
        )
        anti = (
            f"{'Invalid setup should not be traded' if quality == 'invalid' else 'Execution quality depends on fill price matching proposed entry'}."
        )
        risk_concern = f"setup quality '{quality}'" if quality in ("C", "invalid") else "none"
        explanation = (
            f"Execution quality evaluation: {'; '.join(exec_notes) if exec_notes else 'standard parameters'}. "
            f"Setup quality '{quality}' with stop {stop_pct:.2f}% and R:R {rr:.2f}. "
            f"Score {score:.1f} reflects overall execution readiness for {direction} entry."
        )
        meta = {"stop_pct": stop_pct, "r_r_ratio": rr, "setup_quality": quality}
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation, metadata=meta)


# ---------------------------------------------------------------------------
# Evaluator 21: OrderFlowEvaluator
# ---------------------------------------------------------------------------

class OrderFlowEvaluator(BaseTraderEvaluator):
    """
    Evaluates order flow and institutional activity signals.

    Uses volume surge, price momentum convergence, and EMA proximity
    (as a VWAP proxy) to gauge smart money participation.

    Key signals:
    1. Volume character: surge (>2×) = institutional conviction
    2. Volume at structure: surge at S/R = strong institutional confirmation
    3. EMA20 proximity: entry within 0.5% of EMA20 = institutional anchor
    4. Price momentum: consecutive directional closes = momentum alignment
    5. Volume/ADX divergence: high volume + low ADX = possible distribution
    """
    trader_id = "OrderFlow"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        direction = self._direction_str(packet)
        indicators = packet.indicators
        structure = packet.structure

        score = 5.0
        notes: list[str] = []

        # ----------------------------------------------------------------
        # 1. Volume character (institutional participation proxy)
        # ----------------------------------------------------------------
        vol_char = indicators.volume_character   # "surge" | "above_avg" | "normal" | "below_avg"
        vol_ratio = indicators.volume_ratio

        if vol_char == "surge":
            score += 2.5
            notes.append(f"volume surge {vol_ratio:.1f}x — institutional conviction")
        elif vol_char == "above_avg":
            score += 1.0
            notes.append(f"above-average volume {vol_ratio:.1f}x")
        elif vol_char == "below_avg":
            score -= 2.0
            notes.append(f"low volume {vol_ratio:.1f}x — weak conviction")

        # ----------------------------------------------------------------
        # 2. Volume at structure (smart money S/R interaction)
        # ----------------------------------------------------------------
        if vol_char in ("surge", "above_avg"):
            if direction == "long" and structure.at_support:
                score += 2.0
                notes.append("volume surge at support — smart money buying")
            elif direction == "short" and structure.at_resistance:
                score += 2.0
                notes.append("volume surge at resistance — smart money selling")
            elif direction == "long" and structure.at_resistance:
                score -= 1.5
                notes.append("volume at resistance — selling pressure against long")
            elif direction == "short" and structure.at_support:
                score -= 1.5
                notes.append("volume at support — buying pressure against short")

        # ----------------------------------------------------------------
        # 3. EMA20 proximity (VWAP proxy — institutional reference anchor)
        # ----------------------------------------------------------------
        close = float(indicators.close)
        ema20 = float(indicators.ema20)
        if ema20 > 0:
            ema20_dist_pct = abs(close - ema20) / ema20 * 100
            if ema20_dist_pct <= 0.5:
                score += 1.5
                notes.append(f"entry within 0.5% of EMA20 — clean institutional level")
            elif ema20_dist_pct <= 1.5:
                score += 0.5
                notes.append(f"near EMA20 ({ema20_dist_pct:.1f}%)")
            elif ema20_dist_pct > 4.0:
                score -= 1.0
                notes.append(f"far from EMA20 ({ema20_dist_pct:.1f}%) — extended entry")

        # ----------------------------------------------------------------
        # 4. Price momentum from recent closes (5-bar directional consistency)
        # ----------------------------------------------------------------
        if len(packet.recent_closes) >= 5:
            recent = [float(c) for c in packet.recent_closes[-5:]]
            up_bars = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
            if direction == "long":
                if up_bars >= 3:
                    score += 1.0
                    notes.append(f"price momentum: {up_bars}/4 bars rising")
                elif up_bars <= 1:
                    score -= 1.5
                    notes.append("price momentum opposing long direction")
            else:  # short
                down_bars = 4 - up_bars
                if down_bars >= 3:
                    score += 1.0
                    notes.append(f"price momentum: {down_bars}/4 bars falling")
                elif down_bars <= 1:
                    score -= 1.5
                    notes.append("price momentum opposing short direction")

        # ----------------------------------------------------------------
        # 5. Volume/ADX divergence (distribution/accumulation warning)
        # ----------------------------------------------------------------
        if vol_char == "surge" and indicators.adx14 < 20:
            score -= 1.0
            notes.append(f"volume surge in low-ADX range (ADX={indicators.adx14:.0f}) — possible distribution")

        # ----------------------------------------------------------------
        # Verdict
        # ----------------------------------------------------------------
        vote = self._vote_from_score(score)
        confidence = min(0.85, 0.4 + (score - 5.0) * 0.07)

        pro = (
            f"Order flow ({direction.upper()}): "
            f"{'; '.join(notes[:2]) if notes else 'neutral volume participation'}."
        )
        anti = (
            "Volume signals can be misleading; surges may indicate distribution "
            "rather than accumulation in ranging markets."
        )
        exec_concern = "low volume may widen spreads at fill" if vol_char == "below_avg" else "none"
        risk_concern = "counter-trend institutional flow detected" if score < 4.0 else "none"
        explanation = (
            f"Order flow evaluation ({direction.upper()}): "
            f"{'; '.join(notes) if notes else 'no exceptional volume signals'}. "
            f"Volume ratio {vol_ratio:.1f}x, ADX {indicators.adx14:.0f}. "
            f"Score {score:.1f} reflects institutional participation quality."
        )
        meta = {
            "volume_ratio": vol_ratio,
            "volume_character": vol_char,
            "at_support": structure.at_support,
            "at_resistance": structure.at_resistance,
        }
        return self._make_verdict(
            score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation,
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# Evaluator #22 — ML Signal (LightGBM walk-forward classifier)
# ---------------------------------------------------------------------------

class MLSignalEvaluator(BaseTraderEvaluator):
    """
    LightGBM-based binary classifier predicting P(win) for each trade setup.

    Reads the pre-trained BTCClassifier singleton. If the model is not yet
    trained (< 100 labelled outcomes in the learning DB), the evaluator
    abstains rather than voting randomly.

    Scoring:
      P(win) >= 0.65 → approve,  score = P(win) × 10  (e.g. 0.80 → 8.0)
      P(win) <= 0.40 → reject,   score = P(win) × 10  (e.g. 0.25 → 2.5)
      else           → abstain  (uncertain, let human traders decide)

    The abstain band (0.40–0.65) is intentionally wide so the model only
    votes when it has clear conviction — avoiding noise-injection into the panel.
    """

    trader_id = "MLSignal"

    # Lazy singleton — loaded once at first evaluate() call per process
    _classifier = None
    _classifier_loaded = False

    @classmethod
    def _get_classifier(cls):
        if not cls._classifier_loaded:
            cls._classifier_loaded = True
            try:
                from ml.btc_classifier import BTCClassifier
                cls._classifier = BTCClassifier()
                if cls._classifier.is_trained:
                    logger.info(
                        "MLSignalEvaluator: loaded trained BTCClassifier "
                        "(n=%d).", cls._classifier._n_training_samples
                    )
                else:
                    logger.info(
                        "MLSignalEvaluator: BTCClassifier not yet trained "
                        "(need 100 labelled outcomes). Will abstain."
                    )
            except Exception as exc:
                logger.warning("MLSignalEvaluator: could not load classifier: %s", exc)
                cls._classifier = None
        return cls._classifier

    def evaluate(self, packet: "BTCSetupPacket") -> "TraderVerdict":
        clf = self._get_classifier()

        if clf is None or not clf.is_trained:
            return self._make_verdict(
                score=5.0, vote="abstain", confidence=0.0,
                pro_reason="ML model not yet trained",
                anti_reason="none",
                exec_concern="none",
                risk_concern="none",
                explanation="MLSignalEvaluator: model not trained — abstaining.",
            )

        try:
            from ml.feature_extractor import extract_features
            features = extract_features(packet)
            p_win = clf.predict_proba(features)
        except Exception as exc:
            logger.debug("MLSignalEvaluator: feature extraction failed: %s", exc)
            return self._make_verdict(
                score=5.0, vote="abstain", confidence=0.0,
                pro_reason="feature extraction failed",
                anti_reason="none",
                exec_concern="none",
                risk_concern="none",
                explanation=f"MLSignalEvaluator: abstaining due to error: {exc}",
            )

        score = p_win * 10.0

        if p_win >= 0.65:
            vote = "approve"
            confidence = min(1.0, (p_win - 0.50) * 4.0)
            pro = f"ML model P(win)={p_win:.0%} — strong win probability"
            anti = "none"
            risk = "none"
        elif p_win <= 0.40:
            vote = "reject"
            confidence = min(1.0, (0.50 - p_win) * 4.0)
            pro = "none"
            anti = f"ML model P(win)={p_win:.0%} — low win probability"
            risk = f"ML predicts {1-p_win:.0%} chance of loss"
        else:
            vote = "abstain"
            confidence = 0.0
            pro = "none"
            anti = "none"
            risk = "none"

        explanation = (
            f"MLSignal: P(win)={p_win:.1%} → {vote} "
            f"(score={score:.1f}, confidence={confidence:.2f})"
        )
        return self._make_verdict(
            score=score, vote=vote, confidence=confidence,
            pro_reason=pro, anti_reason=anti,
            exec_concern="none", risk_concern=risk,
            explanation=explanation,
            metadata={"p_win": p_win, "n_training_samples": clf._n_training_samples},
        )


# ---------------------------------------------------------------------------
# Registry — convenience tuple of all evaluator classes
# ---------------------------------------------------------------------------

ALL_EVALUATOR_CLASSES = (
    TrendFollowingEvaluator,
    MomentumEvaluator,
    MeanReversionEvaluator,
    BreakoutEvaluator,
    StructureEvaluator,
    CandlestickEvaluator,
    RiskParityEvaluator,
    VolatilityEvaluator,
    VolumeProfileEvaluator,
    MacroRegimeEvaluator,
    ContraryEvaluator,
    ProfitTargetEvaluator,
    EntryTimingEvaluator,
    ConfluenceEvaluator,
    DrawdownRiskEvaluator,
    LeverageSpecialistEvaluator,
    PatternCompletionEvaluator,
    WickAnalysisEvaluator,
    MarketContextEvaluator,
    ExecutionQualityEvaluator,
    OrderFlowEvaluator,    # evaluator #21 — order flow / institutional signals
    MLSignalEvaluator,     # evaluator #22 — LightGBM win-probability predictor
)
