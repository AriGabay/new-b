"""
System entrypoint.

Usage:
  python src/main.py              # Live/Shadow mode (reads MODE_GATE env var)
  python src/main.py --backtest   # Backtest mode

At startup:
  1. Load config (env vars + optional YAML).
  2. Configure logging.
  3. Initialize SystemState singleton.
  4. Initialize EventBus.
  5. Initialize all 10 groups and call group.setup().
  6. Initialize FeatureStore.
  7. Start polling loop (MarketDataGroup).
  8. Run asyncio event loop until signal (SIGINT/SIGTERM).

Phase 2 scope: research mode only. No live execution.

Source: /docs/architecture/runtime_model.md (Process Topology)
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from decimal import Decimal

from config.settings import load_config
from core.events import get_bus, reset_bus
from core.state import SystemState
from data.store import FeatureStore
from groups.candlestick import CandlestickGroup
from groups.chart_pattern import ChartPatternGroup
from groups.entry import EntryGroup
from groups.exit import ExitGroup
from groups.indicators import IndicatorsGroup
from groups.market_data import MarketDataGroup
from groups.news_macro import NewsMacroGroup
from groups.performance_journal import PerformanceJournalGroup
from groups.risk_leverage import RiskLeverageGroup
from groups.technical_structure import TechnicalStructureGroup
from utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)


async def run_system(config_file: str | None = None) -> None:
    """Main async system runner."""
    configure_logging()
    config = load_config(config_file)

    logger.info("=" * 60)
    logger.info("Crypto Trading System starting.")
    logger.info("Mode: %s | Equity: $%s", config.mode.value, config.initial_equity)
    logger.info("=" * 60)

    # Initialize core singletons
    reset_bus()
    bus = get_bus()
    state = SystemState(mode=config.mode, initial_equity=config.initial_equity)

    # Initialize feature store
    feature_store = FeatureStore(data_dir=config.backtest.data_dir)

    # Initialize all groups (dependency order: lower priority = initialized first)
    group_config = {
        "event_calendar_path": config.event_calendar_path,
        "journal_db_path":     config.journal.db_path,
        "min_composite_score": config.entry.min_composite_score,
    }

    groups = [
        MarketDataGroup(state, bus, {"symbols": config.market_data.symbols, **group_config}),
        PerformanceJournalGroup(state, bus, group_config),
        IndicatorsGroup(state, bus, group_config),
        TechnicalStructureGroup(state, bus, group_config),
        CandlestickGroup(state, bus, group_config),
        ChartPatternGroup(state, bus, group_config),
        NewsMacroGroup(state, bus, group_config),
        EntryGroup(state, bus, group_config),
        RiskLeverageGroup(state, bus, group_config),
        ExitGroup(state, bus, group_config),
    ]

    # Setup all groups (subscribes to EventBus, initializes caches)
    for group in groups:
        await group.setup()

    logger.info("All %d groups initialized.", len(groups))

    # Graceful shutdown handler
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def _handle_signal(sig):
        logger.info("Received %s — initiating shutdown.", sig.name)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal, sig)

    logger.info("System running. Press Ctrl+C to stop.")

    # Main event loop (Phase 2: polling; Phase 3: WebSocket)
    raise NotImplementedError(
        "Main polling loop — Phase 2 implementation pending. "
        "Implement MarketDataGroup polling loop here."
    )


def main() -> None:
    """CLI entrypoint."""
    config_file = None
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_file = sys.argv[idx + 1]

    asyncio.run(run_system(config_file))


if __name__ == "__main__":
    main()
