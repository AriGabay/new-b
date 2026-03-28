"""
main_btc.py — BTC/Bybit paper trading entrypoint.

Modes:
  --run          : Full event-driven paper trading loop (requires Bybit connectivity)
  --simulate N   : Inject N synthetic bars through the full 3-layer pipeline (no Bybit)
  --backtest     : Simplified EMA-crossover backtest (independent of group pipeline)
  --analyze      : Standalone feature analysis (legacy; no group pipeline)

The --run and --simulate modes use BtcBybitPaperRunner which wires the
complete 3-layer architecture:

  Layer A: MarketData → Indicators → Candlestick → TechnicalStructure → Entry
  Layer B: PanelDecisionGroup (20-trader evaluators)
  Layer C: FinalDecisionGroup (6 safety rails) → RiskLeverageGroup → ExitGroup → Journal

Bybit connectivity note:
  Bybit API returns HTTP 404 from this machine's IP (CDN restriction, not a code defect).
  Run --simulate for a full pipeline test without live connectivity.
  Run --run from a clean deployment environment with Bybit access.

Source: /docs/final_runtime_path_btc_bybit.md
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Mode 1: Full event-driven runner (requires Bybit)
# ---------------------------------------------------------------------------

async def run_paper_mode(args) -> None:
    """
    Start the full 3-layer event-driven pipeline with live Bybit data.
    Requires clean network environment (Bybit HTTP 404 in current dev env).
    """
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(
        simulation_mode=False,
        journal_db_path=args.journal_db,
        log_level=args.log_level,
    )
    try:
        await runner.setup()
        max_bars = getattr(args, "max_bars", None)
        await runner.run_paper_loop(max_bars=max_bars)
    except KeyboardInterrupt:
        logging.info("Run interrupted by user.")
    finally:
        await runner.teardown()


# ---------------------------------------------------------------------------
# Mode 2: Simulation (synthetic bars through full pipeline)
# ---------------------------------------------------------------------------

async def run_simulation_mode(args) -> None:
    """
    Inject synthetic FeatureReadyEvents through the full 3-layer pipeline.
    Does NOT require Bybit connectivity. Used for integration testing and
    verifying the runtime wiring is correct.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.schemas import FeatureVector

    n_bars = getattr(args, "simulate", 5)
    logger = logging.getLogger("simulation")
    logger.info("Starting simulation mode: %d synthetic bars.", n_bars)

    runner = BtcBybitPaperRunner(
        simulation_mode=True,
        journal_db_path=args.journal_db,
        log_level=args.log_level,
    )
    # setup() wires all groups including JournalExtension + DecisionTraceLogger
    await runner.setup()

    # Build synthetic FeatureVectors with alternating signal conditions
    now = datetime.now(timezone.utc)
    base_price = Decimal("65000")

    for i in range(n_bars):
        # Alternate between bullish and neutral conditions
        # to trigger the confirmation gate on some bars
        bullish = (i % 3 == 0)
        price = base_price + Decimal(str(i * 100))
        ema20 = price - Decimal("200") if bullish else price + Decimal("200")
        ema50 = price - Decimal("500") if bullish else price + Decimal("500")
        ema200 = price - Decimal("1000") if bullish else price + Decimal("1000")

        fv = FeatureVector(
            symbol="BTCUSDT",
            timeframe="1h",
            timestamp=now,
            open=price - Decimal("50"),
            high=price + Decimal("150"),
            low=price - Decimal("100"),
            close=price,
            volume=Decimal("1500"),
            true_range=Decimal("250"),
            atr14=Decimal("800"),
            atr14_sma20=Decimal("750"),
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            prev_ema20=ema20 - Decimal("10"),
            prev_ema50=ema50 - Decimal("20"),
            rsi14=62.0 if bullish else 48.0,
            prev_rsi14=58.0 if bullish else 51.0,
            bb_upper=price + Decimal("1500"),
            bb_middle=price,
            bb_lower=price - Decimal("1500"),
            bb_width=Decimal("3000"),
            bb_width_pct=45.0,
            adx14=28.0 if bullish else 15.0,
            volume_sma20=Decimal("1200"),
            volume_ratio=1.25 if bullish else 0.95,
            candle_body=Decimal("100"),
            candle_range=Decimal("250"),
            body_ratio=0.40,
            upper_shadow=Decimal("100"),
            lower_shadow=Decimal("50"),
            impulse_flag=False,
            doji_flag=False,
        )

        logger.info("Simulation: injecting bar %d/%d (bullish=%s, price=%s)",
                    i + 1, n_bars, bullish, price)
        await runner.simulate_bar(fv)
        # Small delay to let async events propagate
        await asyncio.sleep(0.01)

    logger.info("Simulation complete. %d bars processed.", n_bars)
    logger.info(
        "Portfolio state: equity=%s, open_positions=%d, total_trades=%d",
        runner.state.portfolio.equity,
        len(runner.state.portfolio.open_positions),
        runner.state.portfolio.total_trades,
    )
    await runner.teardown()


# ---------------------------------------------------------------------------
# Mode 3: Simplified backtest (EMA-crossover, independent of group pipeline)
# ---------------------------------------------------------------------------

async def run_backtest_mode(args) -> None:
    """
    Simplified EMA-crossover backtest. Uses BacktestEngine directly.
    NOT the 3-layer group pipeline. Results are tagged simplified_backtest.

    Do not compare these results to event_driven_runtime outcomes.
    """
    from data.bybit import BybitAdapter
    from backtest.engine import BacktestEngine, BacktestConfig
    from features.compute import FeatureComputer
    from journal.db import JournalDB

    logger = logging.getLogger("backtest")
    logger.info("Starting simplified EMA-crossover backtest...")
    logger.warning(
        "BACKTEST NOTE: This uses EMA-20/50 crossover only, NOT the full "
        "3-layer pipeline. Outcomes are tagged 'simplified_backtest' and "
        "must NOT be mixed with event_driven_runtime calibration."
    )

    adapter = BybitAdapter()
    await adapter.setup()

    try:
        bars = await adapter.fetch_bars("BTCUSDT", args.timeframe, limit=args.bars)
        if not bars:
            logger.error("No bars returned from Bybit. Check connectivity.")
            return
        logger.info("Fetched %d bars.", len(bars))
    except Exception as exc:
        logger.error("Bybit fetch failed: %s", exc)
        return
    finally:
        await adapter.teardown()

    config = BacktestConfig(
        symbol="BTCUSDT",
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        initial_equity=Decimal("10000"),
        risk_fraction=Decimal("0.01"),
    )
    engine = BacktestEngine(config)
    result = engine.run(bars)

    logger.info("Backtest complete:")
    logger.info("  Total trades: %d", result.total_trades)
    logger.info("  Win rate: %.1f%%", result.win_rate * 100)
    logger.info("  Total PnL: $%.2f", result.total_pnl_usd)
    logger.info("  Max drawdown: %.1f%%", result.max_drawdown_pct * 100)

    if getattr(args, "journal_db", None):
        db = JournalDB(args.journal_db)
        db.initialize()
        db.insert_journal_event(
            "backtest_result", "backtest_engine",
            {
                "outcome_source": "simplified_backtest",
                "total_trades": result.total_trades,
                "win_rate": result.win_rate,
                "total_pnl_usd": float(result.total_pnl_usd),
            },
        )
        db.close()


# ---------------------------------------------------------------------------
# Mode 4: Legacy standalone analysis (no group pipeline)
# ---------------------------------------------------------------------------

async def run_analysis_mode(args) -> None:
    """
    Legacy standalone feature analysis. Calls Bybit directly, no groups.
    Preserved for quick debugging. Does not exercise the 3-layer pipeline.
    """
    from data.bybit import BybitAdapter
    from features.compute import FeatureComputer

    logger = logging.getLogger("analysis")
    logger.info("Running standalone analysis (legacy mode — no group pipeline).")

    adapter = BybitAdapter()
    await adapter.setup()
    try:
        bars = await adapter.fetch_bars("BTCUSDT", args.timeframe, limit=args.bars)
        if not bars:
            logger.error("No bars from Bybit.")
            return
        computer = FeatureComputer()
        fv = computer.compute(bars)
        if fv:
            logger.info(
                "Features: close=%s ema20=%s rsi14=%.1f adx14=%.1f vol_ratio=%.2f",
                fv.close, fv.ema20, fv.rsi14, fv.adx14, fv.volume_ratio,
            )
        else:
            logger.info("FeatureComputer still warming up (%d bars).", len(bars))
    finally:
        await adapter.teardown()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BTC/Bybit paper trading system")
    p.add_argument("--run", action="store_true",
                   help="Start full event-driven paper trading loop (requires Bybit)")
    p.add_argument("--simulate", type=int, metavar="N", default=None,
                   help="Inject N synthetic bars through full pipeline (no Bybit needed)")
    p.add_argument("--backtest", action="store_true",
                   help="Run simplified EMA-crossover backtest")
    p.add_argument("--analyze", action="store_true",
                   help="Legacy standalone feature analysis")
    p.add_argument("--max-bars", type=int, default=None, dest="max_bars",
                   help="Stop after N bars (--run mode only)")
    p.add_argument("--timeframe", default="60",
                   help="Bybit interval (60=1h, 240=4h, D=1d)")
    p.add_argument("--bars", type=int, default=200,
                   help="Number of historical bars to fetch")
    p.add_argument("--start", default=None, help="Backtest start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="Backtest end date YYYY-MM-DD")
    p.add_argument("--journal-db", default="data/journal.db", dest="journal_db",
                   help="Path to SQLite journal DB")
    p.add_argument("--log-level", default="INFO", dest="log_level",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    if args.run:
        await run_paper_mode(args)
    elif args.simulate is not None:
        await run_simulation_mode(args)
    elif args.backtest:
        await run_backtest_mode(args)
    else:
        await run_analysis_mode(args)


if __name__ == "__main__":
    asyncio.run(main())
