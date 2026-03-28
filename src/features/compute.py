"""
FeatureComputer: stateless computation of FeatureVector from OHLCVBar history.

All methods are pure functions — same input always yields same output.
No external calls. No I/O. No state.

Warm-up requirements:
  - EMA200: 200 bars minimum
  - ATR14:   14 bars minimum
  - RSI14:   15 bars minimum (14 changes needed)
  - ADX14:   28 bars minimum (14 bars DX + 14 bars smoothing)
  - BB(20):  20 bars minimum
  - BB width percentile rank: 100 bars

Minimum bars before any FeatureVector can be produced: 200 bars.

Source: /docs/data_contracts/data_contracts.md (FeatureVector)
        /research/extracted_rules/candidate_rule_families.md (Volatility/Regime rules)
"""
from __future__ import annotations

import math
from collections import deque
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from core.schemas import FeatureVector, OHLCVBar

WARM_UP_BARS = 200


class FeatureComputer:
    """
    Stateless feature computation from a fixed window of OHLCV bars.

    Usage:
        computer = FeatureComputer()
        feature_vec = computer.compute(bars[-200:])  # returns None if < 200 bars

    All EMA calculations use Wilder's method where specified (ATR, RSI, ADX).
    BB uses standard 20-period SMA + 2σ.
    """

    def compute(self, bars: list[OHLCVBar]) -> Optional[FeatureVector]:
        """
        Compute all features from bar history.
        Returns None if insufficient bars (< WARM_UP_BARS).

        bars: list of OHLCVBar, chronological order (oldest first).
              bars[-1] is the most recent closed bar.
        """
        if len(bars) < WARM_UP_BARS:
            return None

        current_bar = bars[-1]

        closes:      list[Decimal] = [b.close      for b in bars]
        highs:       list[Decimal] = [b.high       for b in bars]
        lows:        list[Decimal] = [b.low        for b in bars]
        volumes:     list[Decimal] = [b.volume     for b in bars]
        volume_usds: list[Decimal] = [b.volume_usd for b in bars]

        # ---- ATR family -------------------------------------------------------
        atr14 = self._atr_wilder(bars, period=14)
        true_range = self._true_range(current_bar, bars[-2].close)

        # 20-bar SMA of ATR14: compute ATR14 for each of the last 20 ending windows
        atr14_history: list[Decimal] = []
        for end_idx in range(len(bars) - 19, len(bars) + 1):
            # Need at least 15 bars (1 prev + 14 TRs) to compute ATR14
            window = bars[max(0, end_idx - 50): end_idx]
            if len(window) >= 15:
                atr14_history.append(self._atr_wilder(window, period=14))
        if atr14_history:
            atr14_sma20 = sum(atr14_history) / Decimal(len(atr14_history))
        else:
            atr14_sma20 = atr14

        # ---- EMA family -------------------------------------------------------
        ema20,  prev_ema20 = self._ema(closes, period=20)
        ema50,  prev_ema50 = self._ema(closes, period=50)
        ema200, _          = self._ema(closes, period=200)

        # ---- RSI --------------------------------------------------------------
        rsi14, prev_rsi14 = self._rsi_wilder(closes, period=14)

        # ---- MACD (computed but not stored in FeatureVector; kept for future) -
        # _macd_line, _signal_line, _histogram = self._macd(closes)

        # ---- Bollinger Bands --------------------------------------------------
        bb_upper, bb_middle, bb_lower, bb_width = self._bollinger_bands(
            closes, period=20, num_std=2.0
        )

        # BB width percentile over the last 100 bars (excluding current)
        bb_widths_historical: list[Decimal] = []
        for end_idx in range(len(bars) - 99, len(bars)):
            window_closes = closes[max(0, end_idx - 20): end_idx]
            if len(window_closes) >= 20:
                _, _, _, w = self._bollinger_bands(window_closes, period=20, num_std=2.0)
                bb_widths_historical.append(w)
        bb_width_pct = self._bb_width_percentile(bb_width, bb_widths_historical)

        # ---- ADX --------------------------------------------------------------
        adx14 = self._adx(bars, period=14)

        # ---- Volume -----------------------------------------------------------
        recent_volumes = volumes[-20:]
        volume_sma20 = sum(recent_volumes) / Decimal(len(recent_volumes))
        if volume_sma20 > 0:
            volume_ratio = float(current_bar.volume / volume_sma20)
        else:
            volume_ratio = 0.0

        # ---- VWAP (computed for reference) ------------------------------------
        # _vwap_20 = self._vwap(bars, lookback=20)

        # ---- Candle anatomy ---------------------------------------------------
        body, candle_range, body_ratio, upper_shadow, lower_shadow = self._candle_anatomy(
            current_bar
        )

        # ---- Derived flags ----------------------------------------------------
        impulse_flag = candle_range > Decimal("2") * atr14
        doji_flag    = body_ratio < 0.1

        return FeatureVector(
            symbol    = current_bar.symbol,
            timeframe = current_bar.timeframe,
            timestamp = current_bar.timestamp,

            open   = current_bar.open,
            high   = current_bar.high,
            low    = current_bar.low,
            close  = current_bar.close,
            volume = current_bar.volume,

            true_range  = true_range,
            atr14       = atr14,
            atr14_sma20 = atr14_sma20,

            ema20      = ema20,
            ema50      = ema50,
            ema200     = ema200,
            prev_ema20 = prev_ema20,
            prev_ema50 = prev_ema50,

            rsi14      = rsi14,
            prev_rsi14 = prev_rsi14,

            bb_upper    = bb_upper,
            bb_middle   = bb_middle,
            bb_lower    = bb_lower,
            bb_width    = bb_width,
            bb_width_pct = bb_width_pct,

            adx14 = adx14,

            volume_sma20 = volume_sma20,
            volume_ratio = volume_ratio,

            candle_body  = body,
            candle_range = candle_range,
            body_ratio   = body_ratio,
            upper_shadow = upper_shadow,
            lower_shadow = lower_shadow,

            impulse_flag = impulse_flag,
            doji_flag    = doji_flag,
        )

    # ------------------------------------------------------------------
    # ATR family
    # ------------------------------------------------------------------

    def _true_range(self, bar: OHLCVBar, prev_close: Decimal) -> Decimal:
        """TR = max(high-low, abs(high-prev_close), abs(low-prev_close))."""
        hl  = bar.high - bar.low
        hpc = abs(bar.high - prev_close)
        lpc = abs(bar.low  - prev_close)
        return max(hl, hpc, lpc)

    def _atr_wilder(self, bars: list[OHLCVBar], period: int = 14) -> Decimal:
        """
        Wilder's ATR: first ATR = simple mean of first 14 TRs.
        Subsequent: ATR = (prev_ATR × (period-1) + TR) / period
        """
        if len(bars) < period + 1:
            # Not enough bars to compute even the seed; return the only TR we can.
            if len(bars) >= 2:
                return self._true_range(bars[-1], bars[-2].close)
            return bars[-1].high - bars[-1].low

        # Compute all TRs starting from bar index 1
        trs: list[Decimal] = []
        for i in range(1, len(bars)):
            trs.append(self._true_range(bars[i], bars[i - 1].close))

        # Seed: simple average of the first `period` TRs
        seed_trs = trs[:period]
        atr = sum(seed_trs) / Decimal(period)

        # Wilder smoothing over remaining TRs
        for tr in trs[period:]:
            atr = (atr * Decimal(period - 1) + tr) / Decimal(period)

        return atr

    # ------------------------------------------------------------------
    # EMA family
    # ------------------------------------------------------------------

    def _ema(self, values: list[Decimal], period: int) -> tuple[Decimal, Decimal]:
        """
        Standard EMA with multiplier = 2 / (period + 1).
        Seed with SMA of first 'period' values.

        Returns (current_ema, previous_ema).
        """
        if len(values) < period:
            # Not enough values — return last value as best estimate
            val = values[-1] if values else Decimal("0")
            return val, val

        mult = Decimal(2) / Decimal(period + 1)
        one_minus_mult = Decimal(1) - mult

        # Seed: SMA of first `period` values
        ema = sum(values[:period]) / Decimal(period)
        prev_ema = ema

        for i in range(period, len(values)):
            prev_ema = ema
            ema = values[i] * mult + ema * one_minus_mult

        return ema, prev_ema

    def _ema_series(self, values: list[Decimal], period: int) -> list[Decimal]:
        """
        Compute full EMA series, same length as values.
        First (period-1) entries are filled with the seed SMA value so the
        series can be used for subsequent EMA-of-EMA calculations (MACD signal).

        Returns list of Decimal, length == len(values).
        """
        if len(values) < period:
            return [Decimal("0")] * len(values)

        mult          = Decimal(2) / Decimal(period + 1)
        one_minus     = Decimal(1) - mult

        # Seed
        seed = sum(values[:period]) / Decimal(period)
        result: list[Decimal] = [seed] * period  # fill first `period` slots with seed

        ema = seed
        for i in range(period, len(values)):
            ema = values[i] * mult + ema * one_minus
            result.append(ema)

        return result

    # ------------------------------------------------------------------
    # RSI
    # ------------------------------------------------------------------

    def _rsi_wilder(
        self, closes: list[Decimal], period: int = 14
    ) -> tuple[float, float]:
        """
        Wilder's RSI.

        Returns (current_rsi, previous_rsi) as floats.
        Seed: simple avg gain/loss over first period changes.
        Subsequent: smoothed avg gain = (prev_avg_gain × (period-1) + gain) / period
        """
        if len(closes) < period + 1:
            return 50.0, 50.0

        # Compute raw deltas
        deltas: list[Decimal] = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        gains:  list[Decimal] = [max(d, Decimal("0")) for d in deltas]
        losses: list[Decimal] = [max(-d, Decimal("0")) for d in deltas]

        # Seed averages from first `period` changes
        avg_gain = sum(gains[:period])  / Decimal(period)
        avg_loss = sum(losses[:period]) / Decimal(period)

        def _rsi_from(ag: Decimal, al: Decimal) -> float:
            if al == 0:
                return 100.0
            rs = ag / al
            return float(Decimal("100") - Decimal("100") / (Decimal("1") + rs))

        prev_rsi = _rsi_from(avg_gain, avg_loss)
        current_rsi = prev_rsi

        # Wilder smoothing over remaining deltas
        for i in range(period, len(deltas)):
            prev_rsi    = current_rsi
            prev_gain   = avg_gain
            prev_loss   = avg_loss
            avg_gain    = (prev_gain * Decimal(period - 1) + gains[i])  / Decimal(period)
            avg_loss    = (prev_loss * Decimal(period - 1) + losses[i]) / Decimal(period)
            current_rsi = _rsi_from(avg_gain, avg_loss)

        return current_rsi, prev_rsi

    # ------------------------------------------------------------------
    # MACD
    # ------------------------------------------------------------------

    def _macd(
        self,
        closes: list[Decimal],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        MACD = EMA(fast) - EMA(slow) of closes.
        Signal = EMA(signal) of MACD line series.
        Histogram = MACD line - signal line.

        Returns (macd_line, signal_line, histogram).
        """
        fast_ema_series = self._ema_series(closes, fast)
        slow_ema_series = self._ema_series(closes, slow)

        # MACD line series (valid from index `slow-1` onward, but we compute all)
        macd_series: list[Decimal] = [
            f - s for f, s in zip(fast_ema_series, slow_ema_series)
        ]

        signal_series = self._ema_series(macd_series, signal)

        macd_line   = macd_series[-1]
        signal_line = signal_series[-1]
        histogram   = macd_line - signal_line

        return macd_line, signal_line, histogram

    # ------------------------------------------------------------------
    # Bollinger Bands
    # ------------------------------------------------------------------

    def _bollinger_bands(
        self,
        closes: list[Decimal],
        period: int = 20,
        num_std: float = 2.0,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """
        Returns (upper, middle, lower, width).
        middle = SMA(period) of last `period` closes
        upper  = middle + num_std × population_std
        lower  = middle − num_std × population_std
        width  = upper − lower
        """
        window = closes[-period:]
        n = Decimal(len(window))

        middle = sum(window) / n

        # Population standard deviation
        variance = sum((p - middle) ** 2 for p in window) / n
        std = Decimal(str(math.sqrt(float(variance))))

        num_std_d = Decimal(str(num_std))
        upper = middle + num_std_d * std
        lower = middle - num_std_d * std
        width = upper - lower

        return upper, middle, lower, width

    def _bb_width_percentile(
        self,
        current_width: Decimal,
        historical_widths: list[Decimal],
    ) -> float:
        """
        Percentile rank of current_width within historical_widths.
        Returns float in [0.0, 100.0].
        Low value = squeeze, high value = expansion.
        """
        if not historical_widths:
            return 50.0
        count_below = sum(1 for w in historical_widths if w < current_width)
        return 100.0 * count_below / len(historical_widths)

    # ------------------------------------------------------------------
    # ADX
    # ------------------------------------------------------------------

    def _adx(self, bars: list[OHLCVBar], period: int = 14) -> float:
        """
        Wilder's ADX.

        Steps:
          1. Compute +DM, -DM, TR for each bar pair.
          2. Seed Wilder smoothed series (sum of first `period` values).
          3. Continue smoothing: val = prev - (prev/period) + current.
          4. +DI = 100 * smoothed_+DM / smoothed_TR
             -DI = 100 * smoothed_-DM / smoothed_TR
          5. DX  = 100 * abs(+DI - -DI) / (+DI + -DI)
          6. ADX = Wilder smooth of DX (seed = mean of first `period` DX values).
        """
        if len(bars) < period * 2 + 1:
            return 0.0

        plus_dms:  list[float] = []
        minus_dms: list[float] = []
        trs:       list[float] = []

        for i in range(1, len(bars)):
            curr = bars[i]
            prev = bars[i - 1]

            up_move   = float(curr.high - prev.high)
            down_move = float(prev.low  - curr.low)

            plus_dm  = 0.0
            minus_dm = 0.0
            if up_move > down_move and up_move > 0:
                plus_dm = up_move
            elif down_move > up_move and down_move > 0:
                minus_dm = down_move
            # If equal or both non-positive, both remain 0

            tr = float(self._true_range(curr, prev.close))

            plus_dms.append(plus_dm)
            minus_dms.append(minus_dm)
            trs.append(tr)

        if len(trs) < period:
            return 0.0

        # Wilder smoothing seed: sum of first `period` values
        smooth_plus_dm  = sum(plus_dms[:period])
        smooth_minus_dm = sum(minus_dms[:period])
        smooth_tr       = sum(trs[:period])

        def _di(smoothed_dm: float, smoothed_tr: float) -> float:
            if smoothed_tr == 0:
                return 0.0
            return 100.0 * smoothed_dm / smoothed_tr

        def _dx(plus_di: float, minus_di: float) -> float:
            denom = plus_di + minus_di
            if denom == 0:
                return 0.0
            return 100.0 * abs(plus_di - minus_di) / denom

        # Collect DX values starting from the seed bar
        dx_values: list[float] = []
        plus_di  = _di(smooth_plus_dm, smooth_tr)
        minus_di = _di(smooth_minus_dm, smooth_tr)
        dx_values.append(_dx(plus_di, minus_di))

        # Continue smoothing for remaining bars
        for i in range(period, len(trs)):
            smooth_plus_dm  = smooth_plus_dm  - (smooth_plus_dm  / period) + plus_dms[i]
            smooth_minus_dm = smooth_minus_dm - (smooth_minus_dm / period) + minus_dms[i]
            smooth_tr       = smooth_tr       - (smooth_tr       / period) + trs[i]

            plus_di  = _di(smooth_plus_dm, smooth_tr)
            minus_di = _di(smooth_minus_dm, smooth_tr)
            dx_values.append(_dx(plus_di, minus_di))

        if len(dx_values) < period:
            return 0.0

        # ADX: Wilder smooth of DX — seed = mean of first `period` DX values
        adx = sum(dx_values[:period]) / period

        for dx in dx_values[period:]:
            adx = (adx * (period - 1) + dx) / period

        return adx

    # ------------------------------------------------------------------
    # VWAP
    # ------------------------------------------------------------------

    def _vwap(self, bars: list[OHLCVBar], lookback: int = 20) -> Decimal:
        """
        VWAP over the last `lookback` bars.
        typical_price = (high + low + close) / 3
        vwap = sum(typical_price * volume_usd) / sum(volume_usd)
        """
        window = bars[-lookback:]
        three  = Decimal("3")

        numerator   = Decimal("0")
        denominator = Decimal("0")

        for bar in window:
            tp = (bar.high + bar.low + bar.close) / three
            numerator   += tp * bar.volume_usd
            denominator += bar.volume_usd

        if denominator == 0:
            # Fallback: simple average of typical prices
            return sum(
                (b.high + b.low + b.close) / three for b in window
            ) / Decimal(len(window))

        return numerator / denominator

    # ------------------------------------------------------------------
    # Candle anatomy
    # ------------------------------------------------------------------

    def _candle_anatomy(
        self,
        bar: OHLCVBar,
    ) -> tuple[Decimal, Decimal, float, Decimal, Decimal]:
        """
        Returns (body, candle_range, body_ratio, upper_shadow, lower_shadow).
        body         = abs(close - open)
        candle_range = high - low
        body_ratio   = float(body / candle_range) if candle_range > 0 else 0.0
        upper_shadow = high - max(open, close)
        lower_shadow = min(open, close) - low
        """
        body         = abs(bar.close - bar.open)
        candle_range = bar.high - bar.low
        body_ratio   = float(body / candle_range) if candle_range > 0 else 0.0
        upper_shadow = bar.high - max(bar.open, bar.close)
        lower_shadow = min(bar.open, bar.close) - bar.low
        return body, candle_range, body_ratio, upper_shadow, lower_shadow
