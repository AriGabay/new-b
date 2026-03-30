#!/usr/bin/env python3
"""
Signal diagnostic — count how often each hypothesis fires over the full dataset.

Processes all 18,288 bars through FeatureComputer and checks each signal
condition independently.  Output: per-hypothesis fire count + combined stats.
"""
from __future__ import annotations

import csv
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Silence all logging
import logging
logging.basicConfig(level=logging.WARNING)

from core.schemas import OHLCVBar
from features.compute import FeatureComputer

DATA_FILE = os.path.join(
    os.path.abspath(os.path.join(_SRC_DIR, "..", "..")),
    "analysis", "historical_eval", "data", "btcusdt_1h_2024_2025.csv"
)


def load_bars(path: str) -> list[OHLCVBar]:
    bars = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            bars.append(OHLCVBar(
                symbol="BTCUSDT",
                timeframe="1h",
                timestamp=datetime.fromisoformat(row["timestamp"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=Decimal(row["volume"]),
                volume_usd=Decimal(row.get("volume_usd", "0")),
            ))
    return bars


def main():
    print("Loading bars...")
    bars = load_bars(DATA_FILE)
    print(f"Loaded {len(bars)} bars")

    computer = FeatureComputer()
    WINDOW = 200

    counts = Counter()
    bars_with_any_indicator = 0
    bars_with_candlestick_potential = 0
    bars_processed = 0

    # Per-hypothesis tracking
    hyp_counts = defaultdict(int)

    t0 = time.time()
    prev_fv = None

    for i in range(WINDOW, len(bars)):
        window = bars[i - WINDOW: i + 1]
        fv = computer.compute(window)
        if fv is None:
            continue

        bars_processed += 1
        bar_has_indicator = False

        # --- H3-002: EMA crossover ---
        if prev_fv is not None:
            golden = prev_fv.ema20 < prev_fv.ema50 and fv.ema20 > fv.ema50
            death = prev_fv.ema20 > prev_fv.ema50 and fv.ema20 < fv.ema50
            if (golden or death) and fv.adx14 >= 15:
                hyp_counts["H3-002_ema_cross"] += 1
                bar_has_indicator = True

        # --- H3-005: Trend continuation ---
        ema20, ema50, ema200 = float(fv.ema20), float(fv.ema50), float(fv.ema200)
        close = float(fv.close)
        full_bull = ema20 > ema50 > ema200
        full_bear = ema20 < ema50 < ema200
        ema_sep = abs(ema50 - ema20) / ema50 if ema50 > 0 else 0

        if (full_bull or full_bear) and fv.adx14 >= 20 and fv.volume_ratio >= 0.8 and ema_sep >= 0.001:
            if full_bull:
                near = close < ema20 * 1.05 and close >= ema20 * 0.98
            else:
                near = close > ema20 * 0.95 and close <= ema20 * 1.02
            rsi_ok = 30.0 < fv.rsi14 < 70.0
            if near and rsi_ok:
                hyp_counts["H3-005_trend_cont"] += 1
                bar_has_indicator = True

        # --- H3-006: Trend aligned ---
        if (full_bull or full_bear) and fv.adx14 >= 20:
            if (full_bull and close >= ema20) or (full_bear and close <= ema20):
                hyp_counts["H3-006_trend_aligned"] += 1
                bar_has_indicator = True

        # --- H3-001: RSI signals ---
        rsi = fv.rsi14
        prev_rsi = fv.prev_rsi14
        rsi_rising = rsi > prev_rsi
        if rsi < 30 and rsi_rising and fv.adx14 >= 15:
            hyp_counts["H3-001_oversold"] += 1
            bar_has_indicator = True
        if rsi > 70 and not rsi_rising and fv.adx14 >= 15:
            hyp_counts["H3-001_overbought"] += 1
            bar_has_indicator = True
        # Divergence
        if i >= WINDOW + 5:
            price_5ago = bars[i - 5].close
            # Use simple RSI proxy — not exact but indicative
            if fv.close < price_5ago and rsi > prev_rsi and rsi_rising and fv.adx14 >= 18:
                hyp_counts["H3-001_bull_div"] += 1
                bar_has_indicator = True
            if fv.close > price_5ago and rsi < prev_rsi and not rsi_rising and fv.adx14 >= 18:
                hyp_counts["H3-001_bear_div"] += 1
                bar_has_indicator = True

        # --- H3-004: BB squeeze breakout ---
        if fv.bb_width_pct < 35.0:
            hyp_counts["H3-004_squeeze_active"] += 1
        if fv.bb_width_pct >= 35.0:  # Was in squeeze, now expanded
            if close > float(fv.bb_upper) and fv.volume_ratio > 1.2:
                hyp_counts["H3-004_breakout_long"] += 1
                bar_has_indicator = True
            elif close < float(fv.bb_lower) and fv.volume_ratio > 1.2:
                hyp_counts["H3-004_breakout_short"] += 1
                bar_has_indicator = True

        # --- H3-007: RSI mean reversion ---
        if not fv.impulse_flag:
            if prev_rsi < 35 and rsi >= 35 and rsi < 55:
                hyp_counts["H3-007_rsi_mr_long"] += 1
                bar_has_indicator = True
            elif prev_rsi > 65 and rsi <= 65 and rsi > 45:
                hyp_counts["H3-007_rsi_mr_short"] += 1
                bar_has_indicator = True

        # --- H3-008: Volume breakout ---
        if fv.volume_ratio >= 2.0 and fv.adx14 >= 15:
            bar_move = abs(float(fv.close - fv.open))
            atr = float(fv.atr14) if float(fv.atr14) > 0 else 1.0
            if bar_move >= 0.5 * atr:
                if fv.close > fv.open:
                    hyp_counts["H3-008_vol_break_long"] += 1
                else:
                    hyp_counts["H3-008_vol_break_short"] += 1
                bar_has_indicator = True

        # --- Candlestick potential: strong engulfing (body > 1.5× ATR) ---
        if prev_fv is not None:
            body = fv.candle_body
            atr_val = fv.atr14
            if atr_val > 0 and body > 0:
                body_atr = float(body / atr_val)
                if body_atr >= 1.5:
                    # Check engulfing
                    p_bear = prev_fv.open > prev_fv.close
                    p_bull = prev_fv.open < prev_fv.close
                    c_bull = fv.close > fv.open
                    c_bear = fv.close < fv.open
                    if (p_bear and c_bull and fv.open <= prev_fv.close and fv.close >= prev_fv.open):
                        hyp_counts["H2-006_strong_eng_bull"] += 1
                        bars_with_candlestick_potential += 1
                    elif (p_bull and c_bear and fv.open >= prev_fv.close and fv.close <= prev_fv.open):
                        hyp_counts["H2-006_strong_eng_bear"] += 1
                        bars_with_candlestick_potential += 1

        if bar_has_indicator:
            bars_with_any_indicator += 1

        prev_fv = fv

    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"SIGNAL DIAGNOSTIC — {bars_processed} bars processed ({elapsed:.1f}s)")
    print(f"{'='*60}\n")

    print("Per-hypothesis signal counts:")
    print(f"  {'Hypothesis':<30s} {'Count':>8s}  {'%bars':>8s}")
    print(f"  {'-'*30} {'-'*8}  {'-'*8}")
    for key in sorted(hyp_counts.keys()):
        c = hyp_counts[key]
        pct = c / bars_processed * 100 if bars_processed > 0 else 0
        print(f"  {key:<30s} {c:>8d}  {pct:>7.2f}%")

    # Group totals
    h3_001 = sum(v for k, v in hyp_counts.items() if k.startswith("H3-001"))
    h3_002 = hyp_counts.get("H3-002_ema_cross", 0)
    h3_004_bo = sum(v for k, v in hyp_counts.items() if "breakout" in k and k.startswith("H3-004"))
    h3_005 = hyp_counts.get("H3-005_trend_cont", 0)
    h3_006 = hyp_counts.get("H3-006_trend_aligned", 0)
    h3_007 = sum(v for k, v in hyp_counts.items() if k.startswith("H3-007"))
    h3_008 = sum(v for k, v in hyp_counts.items() if k.startswith("H3-008"))
    h2_006 = sum(v for k, v in hyp_counts.items() if k.startswith("H2-006"))

    print(f"\n{'='*60}")
    print("GROUP TOTALS:")
    print(f"  H3-001 (RSI signals):      {h3_001:>6d}")
    print(f"  H3-002 (EMA crossover):    {h3_002:>6d}")
    print(f"  H3-004 (BB breakout):      {h3_004_bo:>6d}")
    print(f"  H3-005 (Trend cont):       {h3_005:>6d}")
    print(f"  H3-006 (Trend aligned):    {h3_006:>6d}")
    print(f"  H3-007 (RSI mean rev):     {h3_007:>6d}")
    print(f"  H3-008 (Volume break):     {h3_008:>6d}")
    print(f"  H2-006 (Strong engulf):    {h2_006:>6d}")
    total = h3_001 + h3_002 + h3_004_bo + h3_005 + h3_006 + h3_007 + h3_008 + h2_006
    print(f"  {'TOTAL SIGNALS':<25s}  {total:>6d}")
    print(f"\n  Bars with ANY indicator:   {bars_with_any_indicator:>6d} ({bars_with_any_indicator/bars_processed*100:.1f}%)")
    print(f"  Bars with candlestick:     {bars_with_candlestick_potential:>6d} ({bars_with_candlestick_potential/bars_processed*100:.1f}%)")

    weeks = bars_processed / (24 * 7)
    print(f"\n  Estimated signals/week:    {total / weeks:.1f}")
    print(f"  Bars span ~{weeks:.0f} weeks")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
