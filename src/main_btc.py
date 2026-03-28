"""
main_btc.py — BTC/Bybit Vertical Slice Entrypoint.

Phase 3: Paper/simulation mode only.
Connects to Bybit V5 REST API, fetches BTC bars, runs the analysis pipeline,
produces trade decisions (RESEARCH mode — no real orders).

Usage:
    cd src && python main_btc.py
    cd src && python main_btc.py --timeframe 4h --bars 500
    cd src && python main_btc.py --backtest --start 2024-01-01 --end 2024-06-01

Environment:
    BYBIT_BASE_URL (optional): Override Bybit API base URL
    LOG_LEVEL (optional): Set logging level (default: INFO)
    DB_PATH (optional): SQLite journal path (default: data/journal.db)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Ensure src/ is on the path when running as script
sys.path.insert(0, str(Path(__file__).parent))

from data.bybit import BybitAdapter
from features.compute import FeatureComputer
from core.events import EventBus
from core.state import SystemState
from core.schemas import ModeGate
from journal.db import JournalDB

logger = logging.getLogger(__name__)

SYMBOL = "BTCUSDT"
DEFAULT_TIMEFRAME = "1h"
INTERVAL_MAP = {"1h": "60", "4h": "240", "1d": "D"}


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def fetch_btc_bars(timeframe: str = "1h", bars: int = 500) -> list:
    """
    Fetch BTC bars from Bybit V5 REST API.

    Bybit's klines endpoint returns at most 200 bars per request.
    This function paginates backwards in time to collect up to `bars` bars.
    Returns a list of OHLCVBar objects sorted oldest-first.
    """
    interval = INTERVAL_MAP.get(timeframe, "60")
    adapter = BybitAdapter(
        base_url=os.environ.get("BYBIT_BASE_URL", "https://api.bybit.com")
    )
    await adapter.setup()
    try:
        all_bars = []
        end_time_ms = None
        remaining = bars

        while remaining > 0:
            limit = min(200, remaining)
            chunk = await adapter.fetch_bars(
                symbol=SYMBOL,
                interval=interval,
                limit=limit,
                end_time_ms=end_time_ms,
            )
            if not chunk:
                break

            # chunk is oldest-first; prepend to accumulate oldest at front
            all_bars = chunk + all_bars
            remaining -= len(chunk)

            if len(chunk) < limit:
                break  # No more history available from the exchange

            # Paginate: fetch bars older than the oldest we have so far
            oldest_ts_ms = int(all_bars[0].timestamp.timestamp() * 1000)
            end_time_ms = oldest_ts_ms - 1

            if remaining > 0:
                await asyncio.sleep(0.2)  # Rate-limit courtesy delay

        logger.info(
            "Fetched %d %s bars for %s", len(all_bars), timeframe, SYMBOL
        )
        return all_bars
    finally:
        await adapter.teardown()


def compute_features_for_bars(bars: list) -> list:
    """
    Compute a FeatureVector for every bar in `bars` that has enough history.

    Returns a list of (OHLCVBar, FeatureVector) tuples for bars where
    FeatureComputer had >= 200 preceding bars. The first ~199 bars will
    produce no output due to the warm-up requirement.
    """
    computer = FeatureComputer()
    results = []
    bar_buffer = []

    for bar in bars:
        bar_buffer.append(bar)
        features = computer.compute(bar_buffer)
        if features is not None:
            results.append((bar, features))

    return results


async def run_analysis(timeframe: str = "1h", bars: int = 500) -> None:
    """
    Full BTC analysis pipeline (RESEARCH mode).

    Fetches bars from Bybit → computes features → logs regime classification
    and any detected signals. Does NOT execute any orders.

    Outputs are written to:
      - stdout via logging
      - SQLite journal (DB_PATH env var, default: data/journal.db)
    """
    logger.info("=== BTC/Bybit Vertical Slice — RESEARCH mode ===")
    logger.info(
        "Symbol: %s | Timeframe: %s | Bars requested: %d",
        SYMBOL, timeframe, bars,
    )

    # --- Journal setup ---
    db_path = os.environ.get("DB_PATH", "data/journal.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    journal = JournalDB(db_path=db_path)
    journal.initialize()

    # --- Fetch bars ---
    bar_list = await fetch_btc_bars(timeframe=timeframe, bars=bars)
    if len(bar_list) < 200:
        logger.error(
            "Insufficient bars (%d). Need at least 200 for feature computation.",
            len(bar_list),
        )
        journal.close()
        return

    # --- Feature computation ---
    bar_features = compute_features_for_bars(bar_list)
    logger.info(
        "Computed features for %d bars (out of %d fetched)",
        len(bar_features), len(bar_list),
    )

    if not bar_features:
        logger.error("No features computed. Check bar data quality.")
        journal.close()
        return

    # --- Latest bar analysis ---
    latest_bar, latest_features = bar_features[-1]

    logger.info("=== LATEST BAR ANALYSIS ===")
    logger.info("Timestamp : %s", latest_bar.timestamp.isoformat())
    logger.info("OHLCV     : O=%.2f H=%.2f L=%.2f C=%.2f V=%.2f",
                float(latest_bar.open), float(latest_bar.high),
                float(latest_bar.low), float(latest_bar.close),
                float(latest_bar.volume))
    logger.info("EMA20     : %.2f", float(latest_features.ema20))
    logger.info("EMA50     : %.2f", float(latest_features.ema50))
    logger.info("EMA200    : %.2f", float(latest_features.ema200))
    logger.info("RSI14     : %.1f", latest_features.rsi14)
    logger.info("ADX14     : %.1f", latest_features.adx14)
    logger.info("ATR14     : %.2f", float(latest_features.atr14))
    logger.info("BB Upper  : %.2f", float(latest_features.bb_upper))
    logger.info("BB Lower  : %.2f", float(latest_features.bb_lower))
    logger.info("BB Width%% : %.1f", latest_features.bb_width_pct)
    logger.info("Volume/SMA: %.2f", latest_features.volume_ratio)
    logger.info(
        "Candle    : impulse=%s doji=%s body_ratio=%.2f",
        latest_features.impulse_flag,
        latest_features.doji_flag,
        latest_features.body_ratio,
    )

    # --- Regime classification ---
    close = float(latest_features.close)
    ema200 = float(latest_features.ema200)
    ema50 = float(latest_features.ema50)
    adx14 = latest_features.adx14

    atr14_sma20 = float(latest_features.atr14_sma20)
    atr_vs_sma = (
        float(latest_features.atr14) / atr14_sma20
        if atr14_sma20 > 0 else 1.0
    )

    if adx14 < 20:
        macro = "ranging"
    elif close > ema200 and close > ema50:
        macro = "bull"
    elif close < ema200:
        macro = "bear"
    else:
        macro = "ranging"

    trending = adx14 > 25
    vol_regime = (
        "high" if atr_vs_sma > 1.5
        else ("low" if atr_vs_sma < 0.75 else "normal")
    )

    logger.info("=== REGIME ===")
    logger.info("BTC Macro : %s", macro)
    logger.info(
        "Trending  : %s (ADX=%.1f, threshold=25)", trending, adx14
    )
    logger.info(
        "Volatility: %s (ATR/SMA20=%.2f)", vol_regime, atr_vs_sma
    )

    # --- Signal detection on most recent bar ---
    signals_detected = []

    if len(bar_features) >= 2:
        prev_bar, prev_feat = bar_features[-2]

        # H3-002: EMA-20/50 crossover
        if (
            float(prev_feat.ema20) < float(prev_feat.ema50)
            and float(latest_features.ema20) > float(latest_features.ema50)
        ):
            msg = "Golden Cross (EMA20 crossed above EMA50) — H3-002 LONG"
            logger.info(">>> SIGNAL: %s", msg)
            signals_detected.append(("LONG", "ema_golden_cross", msg))

        elif (
            float(prev_feat.ema20) > float(prev_feat.ema50)
            and float(latest_features.ema20) < float(latest_features.ema50)
        ):
            msg = "Death Cross (EMA20 crossed below EMA50) — H3-002 SHORT"
            logger.info(">>> SIGNAL: %s", msg)
            signals_detected.append(("SHORT", "ema_death_cross", msg))

        # H3-001: RSI divergence (simplified — oversold/overbought detection)
        if latest_features.rsi14 < 30 and macro != "bear":
            msg = f"RSI oversold ({latest_features.rsi14:.1f}) — H3-001 potential LONG"
            logger.info(">>> WATCH : %s", msg)
            signals_detected.append(("LONG", "rsi_oversold", msg))
        elif latest_features.rsi14 > 70:
            msg = f"RSI overbought ({latest_features.rsi14:.1f}) — H3-001 potential SHORT"
            logger.info(">>> WATCH : %s", msg)
            signals_detected.append(("SHORT", "rsi_overbought", msg))

        # H3-004: Bollinger Band squeeze (low percentile → potential breakout)
        if latest_features.bb_width_pct < 20:
            msg = (
                f"BB squeeze (width percentile={latest_features.bb_width_pct:.1f}) "
                f"— H3-004 watching for breakout"
            )
            logger.info(">>> SQUEEZE: %s", msg)
            signals_detected.append(("NEUTRAL", "bb_squeeze", msg))

    # --- EMA alignment context ---
    if close > float(latest_features.ema200) > float(latest_features.ema50) > float(latest_features.ema20):
        logger.info("EMA Align : Inverse bull (price > EMA200 > EMA50 > EMA20) — potential mean reversion")
    elif float(latest_features.ema20) > float(latest_features.ema50) > float(latest_features.ema200):
        logger.info("EMA Align : Full bull (EMA20 > EMA50 > EMA200)")
    elif float(latest_features.ema20) < float(latest_features.ema50) < float(latest_features.ema200):
        logger.info("EMA Align : Full bear (EMA20 < EMA50 < EMA200)")
    else:
        logger.info("EMA Align : Mixed / transitional")

    # --- Mode gate reminder ---
    logger.info("=== MODE GATE: RESEARCH — no orders will be placed ===")
    logger.info("=== ANALYSIS COMPLETE ===")

    # --- Journal event ---
    journal.insert_journal_event(
        event_type="analysis_complete",
        source="main_btc",
        payload={
            "symbol": SYMBOL,
            "timeframe": timeframe,
            "bars_fetched": len(bar_list),
            "bars_analyzed": len(bar_features),
            "latest_close": str(latest_bar.close),
            "latest_timestamp": latest_bar.timestamp.isoformat(),
            "macro": macro,
            "trending": trending,
            "volatility_regime": vol_regime,
            "rsi14": latest_features.rsi14,
            "adx14": latest_features.adx14,
            "atr14": str(latest_features.atr14),
            "ema20": str(latest_features.ema20),
            "ema50": str(latest_features.ema50),
            "ema200": str(latest_features.ema200),
            "bb_width_pct": latest_features.bb_width_pct,
            "signals_detected": [
                {"direction": d, "type": t, "message": m}
                for d, t, m in signals_detected
            ],
        },
    )
    journal.close()


async def run_backtest(
    timeframe: str = "1h",
    start: str = "2024-01-01",
    end: str = "2024-06-01",
) -> None:
    """
    Run a simplified bar-by-bar backtest using BacktestEngine.

    Fetches up to 500 bars from Bybit, filters to the requested date range,
    runs the EMA-crossover strategy (H3-002 baseline), and logs results.
    """
    from backtest.engine import BacktestEngine, BacktestConfig

    logger.info("=== BTC/Bybit Backtest: %s to %s ===", start, end)

    bar_list = await fetch_btc_bars(timeframe=timeframe, bars=500)

    if not bar_list:
        logger.error("No bars fetched for backtest.")
        return

    # Filter bars to the requested date range
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    filtered = [
        b for b in bar_list
        if start_dt <= b.timestamp <= end_dt
    ]
    logger.info(
        "Bars in date range [%s, %s]: %d", start, end, len(filtered)
    )

    # Fall back to all bars if the date filter gives us too few
    if len(filtered) < 200:
        logger.warning(
            "Date filter resulted in %d bars (< 200). "
            "Using all %d available bars for warm-up.",
            len(filtered), len(bar_list),
        )
        filtered = bar_list

    config = BacktestConfig(
        symbols=[SYMBOL],
        timeframe=timeframe,
        start_date=start_dt,
        end_date=end_dt,
        initial_equity=Decimal("100000"),
        risk_fraction=Decimal("0.01"),
        commission_pct=Decimal("0.001"),
        slippage_pct=Decimal("0.0005"),
        enforce_holdout=False,  # Phase 3: no holdout enforcement
    )

    engine = BacktestEngine(config=config)
    result = await engine.run({SYMBOL: filtered})

    logger.info("=== BACKTEST RESULTS ===")
    logger.info(result.summary())
    logger.info("  Total Trades  : %d", result.total_trades)
    logger.info("  Winning       : %d", result.winning_trades)
    logger.info("  Losing        : %d", result.losing_trades)
    logger.info("  Win Rate      : %.1f%%", result.win_rate * 100)
    logger.info("  Profit Factor : %.2f", result.profit_factor)
    logger.info("  Avg R-Multiple: %.2f", result.avg_r_multiple)
    logger.info("  Max Drawdown  : %.1f%%", result.max_drawdown_pct * 100)
    logger.info("  Final Equity  : $%.0f", float(result.final_equity))
    logger.info("  Total PnL     : $%.0f", float(result.total_pnl_usd))
    logger.info(
        "NOTE: Backtest uses simplified EMA-crossover only (H3-002 baseline). "
        "Full pipeline backtest requires Phase 4 group wiring."
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="BTC/Bybit Trading System — Phase 3 Vertical Slice",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main_btc.py                          # Live analysis, 1h bars, last 500
  python main_btc.py --timeframe 4h           # 4-hour analysis
  python main_btc.py --bars 300               # Fetch only 300 bars
  python main_btc.py --backtest               # Run backtest (2024-01-01 to 2024-06-01)
  python main_btc.py --backtest --start 2024-03-01 --end 2024-09-01
  LOG_LEVEL=DEBUG python main_btc.py          # Verbose debug logging
        """,
    )
    p.add_argument(
        "--timeframe",
        default="1h",
        choices=["1h", "4h", "1d"],
        help="Bar timeframe (default: 1h)",
    )
    p.add_argument(
        "--bars",
        type=int,
        default=500,
        help="Number of bars to fetch (default: 500)",
    )
    p.add_argument(
        "--backtest",
        action="store_true",
        help="Run backtest instead of live analysis",
    )
    p.add_argument(
        "--start",
        default="2024-01-01",
        help="Backtest start date YYYY-MM-DD (default: 2024-01-01)",
    )
    p.add_argument(
        "--end",
        default="2024-06-01",
        help="Backtest end date YYYY-MM-DD (default: 2024-06-01)",
    )
    p.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Logging level (default: INFO)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level)

    if args.backtest:
        asyncio.run(
            run_backtest(
                timeframe=args.timeframe,
                start=args.start,
                end=args.end,
            )
        )
    else:
        asyncio.run(
            run_analysis(
                timeframe=args.timeframe,
                bars=args.bars,
            )
        )
