"""
ML Feature Extractor — converts BTCSetupPacket → 20-dimensional float vector.

Features are designed to:
  1. Capture momentum, trend, volatility, and volume state
  2. Encode regime and structural context
  3. Be robust to missing data (graceful fallbacks)
  4. Be scale-normalised so LightGBM doesn't need further preprocessing

Feature vector (20 dimensions):
  0  rsi14_norm          RSI14 / 100  (0.0–1.0)
  1  rsi_trend           +1 rising, -1 falling, 0 flat
  2  bb_position         (close - bb_lower) / bb_width  (clamped 0–1)
  3  bb_width_pct_norm   BB-width percentile / 100
  4  adx14_norm          ADX14 / 100
  5  ema20_50_ratio      EMA20/EMA50 − 1  (positive = price above mid-trend)
  6  ema50_200_ratio     EMA50/EMA200 − 1 (positive = mid above long-trend)
  7  atr_vs_sma          ATR14 / ATR-SMA20  (>1 = expanding volatility)
  8  volume_ratio_capped current_volume / SMA20, capped at 5.0
  9  price_mom_5bar      (close − close_5bar_ago) / close  (momentum)
  10 ema_alignment_enc   full_bull=1 partial_bull=0.5 mixed=0 partial_bear=−0.5 full_bear=−1
  11 at_structure        1 if at support/resistance, 0 otherwise
  12 structure_dist_pct  nearest S/R distance / price  (fallback 0.05)
  13 regime_enc          bull=1 trending=0.5 ranging=0 bear=−1
  14 vol_regime_enc      high=1 normal=0 low=−1
  15 direction_enc       LONG=1 SHORT=−1
  16 r_r_ratio_norm      min(r_r_ratio, 5.0) / 5.0
  17 stop_dist_norm      min(stop_distance_pct, 0.10) / 0.10
  18 hour_sin            sin(hour × 2π / 24)  — intraday seasonality
  19 hour_cos            cos(hour × 2π / 24)
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.setup_packet import BTCSetupPacket

FEATURE_DIM = 20
FEATURE_NAMES = [
    "rsi14_norm",
    "rsi_trend",
    "bb_position",
    "bb_width_pct_norm",
    "adx14_norm",
    "ema20_50_ratio",
    "ema50_200_ratio",
    "atr_vs_sma",
    "volume_ratio_capped",
    "price_mom_5bar",
    "ema_alignment_enc",
    "at_structure",
    "structure_dist_pct",
    "regime_enc",
    "vol_regime_enc",
    "direction_enc",
    "r_r_ratio_norm",
    "stop_dist_norm",
    "hour_sin",
    "hour_cos",
]

_EMA_ALIGN_MAP: dict[str, float] = {
    "full_bull":    1.0,
    "partial_bull": 0.5,
    "mixed":        0.0,
    "partial_bear": -0.5,
    "full_bear":    -1.0,
}
_REGIME_MAP: dict[str, float] = {
    "bull":     1.0,
    "trending": 0.5,
    "ranging":  0.0,
    "bear":     -1.0,
}
_VOL_MAP: dict[str, float] = {
    "low":    -1.0,
    "normal":  0.0,
    "high":    1.0,
}


def extract_features(packet: "BTCSetupPacket") -> list[float]:
    """
    Extract a 20-dimensional float feature vector from a BTCSetupPacket.

    Returns a list of FEATURE_DIM floats, all finite (no NaN/inf).
    Missing or invalid fields fall back to neutral defaults so the model
    never receives corrupted input.
    """
    ind  = packet.indicators
    struc = packet.structure
    prop = packet.proposal
    reg  = packet.regime

    # ------------------------------------------------------------------
    # 0: RSI14 normalised
    rsi14_norm = float(ind.rsi14) / 100.0

    # 1: RSI trend direction
    rsi_trend = 0.0
    if ind.rsi14 > ind.prev_rsi14 + 0.5:
        rsi_trend = 1.0
    elif ind.rsi14 < ind.prev_rsi14 - 0.5:
        rsi_trend = -1.0

    # 2: Bollinger Band position (close within bands)
    try:
        bb_range = float(ind.bb_upper - ind.bb_lower)
        if bb_range > 0:
            bb_position = float(ind.close - ind.bb_lower) / bb_range
            bb_position = max(0.0, min(1.0, bb_position))
        else:
            bb_position = 0.5
    except Exception:
        bb_position = 0.5

    # 3: BB width percentile normalised
    bb_width_pct_norm = float(ind.bb_width_pct) / 100.0

    # 4: ADX normalised
    adx14_norm = float(ind.adx14) / 100.0

    # 5: EMA20/50 ratio
    try:
        ema20_50_ratio = float(ind.ema20 / ind.ema50) - 1.0 if ind.ema50 > 0 else 0.0
    except Exception:
        ema20_50_ratio = 0.0

    # 6: EMA50/200 ratio
    try:
        ema50_200_ratio = float(ind.ema50 / ind.ema200) - 1.0 if ind.ema200 > 0 else 0.0
    except Exception:
        ema50_200_ratio = 0.0

    # 7: ATR vs its 20-bar SMA (volatility expansion)
    atr_vs_sma = float(ind.atr14_vs_sma20) if hasattr(ind, "atr14_vs_sma20") else 1.0

    # 8: Volume ratio (capped at 5× to prevent outlier dominance)
    volume_ratio_capped = min(float(ind.volume_ratio), 5.0) / 5.0

    # 9: 5-bar price momentum from recent_closes
    price_mom_5bar = 0.0
    closes = packet.recent_closes
    if closes and len(closes) >= 6:
        try:
            c_now  = float(closes[-1])
            c_5ago = float(closes[-6])
            if c_5ago > 0:
                price_mom_5bar = (c_now - c_5ago) / c_5ago
                price_mom_5bar = max(-0.1, min(0.1, price_mom_5bar))  # clip ±10%
        except Exception:
            pass

    # 10: EMA alignment encoded
    ema_alignment_enc = _EMA_ALIGN_MAP.get(getattr(ind, "ema_alignment", "mixed"), 0.0)

    # 11: At structural level (support or resistance)
    at_structure = 1.0 if (struc.at_support or struc.at_resistance) else 0.0

    # 12: Distance to nearest S/R (as fraction of price; fallback = 5%)
    structure_dist_pct = 0.05
    try:
        dists = [
            d for d in [struc.resistance_distance_pct, struc.support_distance_pct]
            if d is not None and d >= 0
        ]
        if dists:
            structure_dist_pct = min(dists) / 100.0  # convert percent to fraction
    except Exception:
        pass

    # 13: Macro regime encoded
    regime_enc = _REGIME_MAP.get(getattr(reg, "btc_macro", "ranging"), 0.0)

    # 14: Volatility regime encoded
    vol_regime_enc = _VOL_MAP.get(getattr(ind, "volatility_regime", "normal"), 0.0)

    # 15: Direction (LONG=+1, SHORT=−1)
    from core.schemas import Direction
    direction_enc = 1.0 if prop.direction == Direction.LONG else -1.0

    # 16: R:R ratio normalised (cap at 5.0)
    r_r_ratio_norm = min(float(prop.r_r_ratio), 5.0) / 5.0

    # 17: Stop distance normalised (cap at 10%)
    stop_dist_norm = min(float(prop.stop_distance_pct), 0.10) / 0.10

    # 18 & 19: Hour-of-day seasonality (UTC)
    hour = packet.bar_timestamp.hour
    hour_sin = math.sin(hour * 2 * math.pi / 24)
    hour_cos = math.cos(hour * 2 * math.pi / 24)

    features = [
        rsi14_norm,
        rsi_trend,
        bb_position,
        bb_width_pct_norm,
        adx14_norm,
        ema20_50_ratio,
        ema50_200_ratio,
        atr_vs_sma,
        volume_ratio_capped,
        price_mom_5bar,
        ema_alignment_enc,
        at_structure,
        structure_dist_pct,
        regime_enc,
        vol_regime_enc,
        direction_enc,
        r_r_ratio_norm,
        stop_dist_norm,
        hour_sin,
        hour_cos,
    ]

    # Final sanity: replace any non-finite with 0
    return [f if math.isfinite(f) else 0.0 for f in features]
