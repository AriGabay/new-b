"""
20 Trader Evaluator classes for BTC/Bybit setup evaluation.

Each evaluator receives a BTCSetupPacket and returns a TraderVerdict.
Every evaluator uses a distinct analytical lens.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.setup_packet import BTCSetupPacket

from core.schemas import Direction


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
    def _vote_from_score(score: float, approve_threshold: float = 6.5, reject_threshold: float = 4.5) -> str:
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

        # EMA alignment bonus
        if direction == "long" and ind.ema_alignment in ("full_bull", "partial_bull"):
            score += 2.0
        elif direction == "short" and ind.ema_alignment in ("full_bear", "partial_bear"):
            score += 2.0
        else:
            score -= 2.0  # counter-trend penalty

        # ADX strength
        if ind.adx14 > 25:
            score += 1.5

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

        pro = (
            f"EMA alignment is {ind.ema_alignment} and ADX {ind.adx14:.1f} confirms "
            f"trend strength for a {direction} trade."
        )
        anti = (
            f"Trend-following entries can chase price; structure trend is "
            f"{struct.trend_direction} which may diverge from proposal."
        )
        exec_concern = "entry may be late in trend" if ind.adx14 > 40 else "none"
        risk_concern = "counter-trend trade risk" if score < 5 else "none"
        explanation = (
            f"EMA alignment ({ind.ema_alignment}) {'supports' if score >= 6 else 'opposes'} the "
            f"{direction} direction. ADX at {ind.adx14:.1f} indicates "
            f"{'strong' if ind.adx14 > 25 else 'weak'} trend momentum. "
            f"Structural trend is {struct.trend_direction}."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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

        if direction == "long":
            if 40 <= rsi <= 65:
                score += 2.0
            elif rsi > 75:
                score -= 2.0  # overbought
            elif rsi < 30:
                score -= 1.0
            if ind.rsi_direction == "rising":
                score += 1.0
        else:  # short
            if 35 <= rsi <= 60:
                score += 2.0
            elif rsi < 25:
                score -= 2.0  # oversold, risky short
            elif rsi > 70:
                score -= 0.5
            if ind.rsi_direction == "falling":
                score += 1.0

        # Volume confirmation
        if ind.volume_ratio > 1.5:
            score += 1.0
        elif ind.volume_ratio < 0.8:
            score -= 1.0

        vote = self._vote_from_score(score)
        confidence = min(0.9, 0.45 + abs(rsi - 50) * 0.005 + (score - 5) * 0.06)

        overbought = rsi > 75 and direction == "long"
        oversold = rsi < 25 and direction == "short"

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
            f"RSI at {rsi:.1f} is {'in ideal range' if 40 <= rsi <= 65 else 'outside ideal range'} for "
            f"a {direction} trade, trending {ind.rsi_direction}. "
            f"Volume ratio {ind.volume_ratio:.2f} {'provides' if ind.volume_ratio > 1.3 else 'lacks'} momentum confirmation. "
            f"Score {score:.1f} reflects overall momentum quality."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        confidence = 0.8 if score >= 7 else (0.55 if score >= 5.5 else 0.3)

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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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

        # BB squeeze context
        if ind.bb_width_pct < 20:
            score += 0.5  # possible squeeze setup

        vote = self._vote_from_score(score)
        confidence = 0.75 if has_confirmed else 0.4

        pro = (
            f"{'Confirmed chart pattern breakout' if has_confirmed else 'Active pattern forming'} "
            f"with volume ratio {ind.volume_ratio:.2f} {'confirms' if volume_strong else 'suggests'} breakout participation."
        )
        anti = (
            f"{'Volume below breakout threshold' if not volume_ok else 'Breakout may be premature'}; "
            f"BB width percentile {ind.bb_width_pct:.0f} {'indicates squeeze' if ind.bb_width_pct < 20 else 'is normal'}."
        )
        exec_concern = "entry too far from breakout level" if cp.breakout_level is not None and score < 6 else "none"
        risk_concern = "low breakout volume" if not volume_ok else "none"
        explanation = (
            f"Breakout evaluator {'confirms' if score >= 7 else 'partially supports' if score >= 5 else 'rejects'} this {direction} setup. "
            f"{'Confirmed patterns: ' + ', '.join(cp.confirmed_patterns) if has_confirmed else 'No confirmed patterns present'}. "
            f"Volume ratio {ind.volume_ratio:.2f} {'meets' if volume_ok else 'fails'} minimum breakout threshold."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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

        pro = (
            f"Candlestick '{cs.primary_pattern}' is {'at a structural level' if cs.pattern_at_structure else 'present'} "
            f"with {'matching' if cs.pattern_direction and ((direction == 'long' and cs.pattern_direction == 'bullish') or (direction == 'short' and cs.pattern_direction == 'bearish')) else 'neutral'} direction."
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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        score = min(9.0, rr * 1.5)

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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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

        # Only approve if very high quality
        if proposal.r_r_ratio > 3.0 and struct.structure_quality == "strong":
            score = 7.0
            vote = "approve"
            confidence = 0.55
        else:
            # Skeptical by default
            score = 4.0
            vote = "reject"
            confidence = 0.6

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

        biggest_risk = risks[0] if risks else "market conditions uncertain"

        pro = f"Even skeptics acknowledge the {direction} trade has a defined stop and measurable target."
        anti = (
            f"Contrary view: {biggest_risk} — the market rarely moves cleanly in the proposed direction."
        )
        exec_concern = "overconfidence in setup quality" if proposal.setup_quality == "A" else "none"
        risk_concern = biggest_risk
        explanation = (
            f"Contrary evaluator applies maximum skepticism to the {direction} proposal. "
            f"Primary concern: {biggest_risk}. "
            f"Only approves trades with R:R > 3.0 AND strong structure; current R:R is {proposal.r_r_ratio:.2f}."
        )
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        vote = "approve" if score >= 7.0 else ("reject" if score < 4.5 else "abstain")
        confidence = min(0.9, agreement_count * 0.12)

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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


# ---------------------------------------------------------------------------
# 17. PatternCompletionEvaluator
# ---------------------------------------------------------------------------

class PatternCompletionEvaluator(BaseTraderEvaluator):
    """Evaluates chart pattern completion and target credibility."""

    trader_id = "PatternCompletion"

    def evaluate(self, packet: "BTCSetupPacket") -> TraderVerdict:
        cp = packet.chart_pattern
        direction = self._direction_str(packet)

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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
        return self._make_verdict(score, vote, confidence, pro, anti, exec_concern, risk_concern, explanation)


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
)
