"""
BtcBybitPaperRunner: runtime orchestrator for the BTC/Bybit paper trading pipeline.

Instantiates all active groups, wires them to a shared EventBus,
drives the polling/bar-processing loop, and supports a simulation mode
for integration testing without live Bybit connectivity.

Active groups (Layer A + gates + journal):
  MarketDataGroup         — data ingestion
  ChartPatternGroup       — chart pattern state machines (Phase 6.4: DoubleBottomMachine active)
  IndicatorsGroup         — EMA/RSI/BB/ADX signals
  CandlestickGroup        — candlestick pattern signals
  TechnicalStructureGroup — S/R level signals
  EntryGroup              — signal aggregation → CandidateTradeProposal
  PanelDecisionGroup      — Layer B+C: 20-trader panel + FinalDecisionGroup
  RiskLeverageGroup       — 9 deterministic risk rules
  ExitGroup               — position exit logic
  PerformanceJournalGroup — event journaling

Excluded groups (stubbed — raise NotImplementedError if triggered):
  NewsMacroGroup          — EXCLUDED: _process_bar_close raises NotImplementedError

Learning layer:
  JournalExtension        — wired to PerformanceJournalGroup's DB connection
  DecisionTraceLogger     — injected into PanelDecisionGroup
  OutcomeSource           — always EVENT_DRIVEN_RUNTIME for this runner

Bybit connectivity:
  Live Bybit data requires a clean network environment (HTTP 404 from Bybit CDN
  in current dev environment — IP restriction). Simulation mode injects synthetic
  FeatureReadyEvents for integration testing.

Source: /docs/runtime_runner_design.md
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.events import EventBus, FeatureReadyEvent
from core.schemas import FeatureVector, ModeGate
from core.state import SystemState

logger = logging.getLogger(__name__)

BTC_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "60"   # 1h bars
POLL_INTERVAL_SECONDS = 60


class BtcBybitPaperRunner:
    """
    Runtime orchestrator. Wires all active groups to a shared EventBus
    and drives the bar-close polling loop.

    Usage (live polling):
        runner = BtcBybitPaperRunner()
        await runner.setup()
        await runner.run_paper_loop(max_bars=None)  # runs indefinitely
        await runner.teardown()

    Usage (simulation / integration test):
        runner = BtcBybitPaperRunner(simulation_mode=True)
        await runner.setup()
        await runner.simulate_bar(feature_vector)
        await runner.teardown()
    """

    def __init__(
        self,
        simulation_mode: bool = False,
        journal_db_path: str = "data/journal.db",
        log_level: str = "INFO",
    ) -> None:
        self._simulation_mode = simulation_mode
        self._journal_db_path = journal_db_path
        self._log_level = log_level
        self._running = False

        # Shared state and bus.
        # Use ModeGate.SHADOW (paper trade with real-time data) so proposals are
        # not blocked by Risk Rule 1. ModeGate.RESEARCH blocks ALL orders —
        # it is for pure research/observation runs only.
        self._state = SystemState(mode=ModeGate.SHADOW)
        self._bus = EventBus()

        # Group references (populated in setup())
        self._market_data = None
        self._indicators = None
        self._candlestick = None
        self._chart_pattern = None
        self._technical_structure = None
        self._entry = None
        self._panel_decision = None
        self._risk_leverage = None
        self._exit = None
        self._performance_journal = None
        self._historian = None

        # Learning layer
        self._journal_extension = None
        self._all_groups: list = []

    async def setup(self) -> None:
        """Instantiate all groups, wire caches, call setup() on each."""
        logger.info("BtcBybitPaperRunner: starting setup...")

        # 1. Create all group instances
        self._create_groups()

        # 2. Wire cross-group caches (before setup() subscribes to events)
        self._wire_caches()

        # 3. Wire learning layer
        await self._wire_learning_layer()

        # 4. Call setup() on each group (registers EventBus subscriptions)
        for group in self._all_groups:
            try:
                await group.setup()
            except Exception as exc:
                logger.error("Runner: group %s setup failed: %s", type(group).__name__, exc)
                raise

        # 5. Mark BTC as eligible
        await self._state.update_universe({BTC_SYMBOL})

        # 6. Wire learning layer now that PerformanceJournalGroup._initialize_db()
        #    has been called (during step 4). JournalExtension and DecisionTraceLogger
        #    are created and injected into PanelDecisionGroup.
        await self._finalize_learning_wiring()

        # 7. Engage the panel gate on RiskLeverageGroup.
        #    Prevents CandidateTradeEvent from bypassing PanelDecisionGroup.
        self._risk_leverage.set_panel_wired(True)

        self._running = True
        logger.info(
            "BtcBybitPaperRunner: setup complete. Active groups: %s mode=%s panel_gate=active",
            [type(g).__name__ for g in self._all_groups],
            self._state.mode.value,
        )

    def _create_groups(self) -> None:
        """Instantiate all active groups with shared state + bus."""
        from groups.market_data.group import MarketDataGroup
        from groups.indicators.group import IndicatorsGroup
        from groups.candlestick.group import CandlestickGroup
        from groups.chart_pattern.group import ChartPatternGroup
        from groups.technical_structure.group import TechnicalStructureGroup
        from groups.entry.group import EntryGroup
        from groups.panel_decision.group import PanelDecisionGroup
        from groups.risk_leverage.group import RiskLeverageGroup
        from groups.exit.group import ExitGroup
        from groups.performance_journal.group import PerformanceJournalGroup
        from groups.historian.group import HistorianGroup

        config = {"journal_db_path": self._journal_db_path}

        self._market_data = MarketDataGroup(self._state, self._bus)
        self._indicators = IndicatorsGroup(self._state, self._bus)
        self._candlestick = CandlestickGroup(self._state, self._bus)
        self._chart_pattern = ChartPatternGroup(self._state, self._bus)
        self._technical_structure = TechnicalStructureGroup(self._state, self._bus)
        self._entry = EntryGroup(self._state, self._bus)
        self._panel_decision = PanelDecisionGroup(self._state, self._bus)
        self._risk_leverage = RiskLeverageGroup(self._state, self._bus)
        self._exit = ExitGroup(self._state, self._bus)
        self._performance_journal = PerformanceJournalGroup(self._state, self._bus, config)
        self._historian = HistorianGroup(self._state, self._bus)

        self._all_groups = [
            self._market_data,
            self._chart_pattern,        # Must precede CandlestickGroup so cache is populated
            self._indicators,           # before EntryGroup fires CandidateTradeEvent
            self._candlestick,
            self._technical_structure,
            self._historian,            # Must precede EntryGroup so query() is callable
            self._entry,
            self._panel_decision,
            self._risk_leverage,
            self._exit,
            self._performance_journal,
        ]

    def _wire_caches(self) -> None:
        """
        Inject cross-group cache references into PanelDecisionGroup and CandlestickGroup.

        PanelDecisionGroup also needs:
        - ChartPatternSignal cache (from ChartPatternGroup)
        - active chart pattern name cache (from ChartPatternGroup)

        PanelDecisionGroup needs:
        - FeatureVector cache (from MarketDataGroup)
        - StructuralLevelBundle cache (from TechnicalStructureGroup)
        - CandlestickSignal cache (from CandlestickGroup)

        CandlestickGroup needs:
        - TechnicalStructureGroup reference (for structural context)
        """
        # Give PanelDecisionGroup access to MarketDataGroup's feature cache
        self._panel_decision.set_feature_cache(
            self._market_data._feature_cache
        )
        # Give PanelDecisionGroup access to TechnicalStructureGroup's structural cache
        self._panel_decision.set_structural_cache(
            self._technical_structure._structural_cache
        )
        # Give PanelDecisionGroup access to CandlestickGroup's signals cache.
        # Fix: Phase 6.2.5 — this wire was documented but never implemented,
        # causing patterns_detected=[] in every BTCSetupPacket.
        self._panel_decision.set_candlestick_signal_cache(
            self._candlestick._signals_cache
        )
        # Give CandlestickGroup reference to TechnicalStructureGroup
        if hasattr(self._candlestick, "set_technical_structure_group"):
            self._candlestick.set_technical_structure_group(self._technical_structure)

        # Give PanelDecisionGroup access to ChartPatternGroup's signal and active caches
        self._panel_decision.set_chart_pattern_signal_cache(
            self._chart_pattern._signals_cache
        )
        self._panel_decision.set_active_chart_pattern_cache(
            self._chart_pattern._active_cache
        )

        logger.debug("Runner: cross-group caches wired (including candlestick signals cache).")

    async def _wire_learning_layer(self) -> None:
        """
        Wire JournalExtension to PerformanceJournalGroup's DB connection.
        Inject DecisionTraceLogger into PanelDecisionGroup.
        Source tagging: EVENT_DRIVEN_RUNTIME for all runtime writes.
        """
        try:
            from learning.outcome_source import OutcomeSource
            from learning.journal_extension import JournalExtension

            outcome_source = OutcomeSource.EVENT_DRIVEN_RUNTIME

            # JournalExtension shares the DB connection from PerformanceJournalGroup.
            # We initialize it lazily after PerformanceJournalGroup._setup() creates
            # the JournalDB. We defer this to post-setup.
            self._outcome_source = outcome_source
            logger.debug("Runner: learning layer outcome_source=%s", outcome_source.value)
        except ImportError as exc:
            logger.warning("Runner: learning layer not available: %s", exc)
            self._outcome_source = None

    async def _finalize_learning_wiring(self) -> None:
        """
        Called after all groups are set up. Wires JournalExtension to the
        live DB connection from PerformanceJournalGroup.
        """
        try:
            from learning.journal_extension import JournalExtension
            from learning.decision_logger import DecisionTraceLogger

            journal_db = getattr(self._performance_journal, "_journal_db", None)
            if journal_db is None or getattr(journal_db, "_conn", None) is None:
                logger.warning(
                    "Runner: JournalDB not initialized — learning layer not wired."
                )
                return

            self._journal_extension = JournalExtension(journal_db._conn)
            self._journal_extension.initialize()

            # Inject into PanelDecisionGroup
            self._panel_decision._journal_extension = self._journal_extension
            self._panel_decision._outcome_source = self._outcome_source
            if self._panel_decision._running:
                # Re-create trace logger now that extension is available
                trace_logger = DecisionTraceLogger(
                    self._journal_extension, self._outcome_source
                )
                self._panel_decision._trace_logger = trace_logger

            # Wire OutcomeAttributor into PerformanceJournalGroup so closed trades
            # trigger calibration updates and learning DB writes (outcome_attributions table).
            from learning.attribution import OutcomeAttributor
            outcome_attributor = OutcomeAttributor(
                self._journal_extension, self._outcome_source
            )
            self._performance_journal._outcome_attributor = outcome_attributor

            # Wire HistorianGroup into EntryGroup so historian_analog feeds composite score.
            if self._historian is not None and self._entry is not None:
                self._entry._historian = self._historian
                self._historian._extension = self._journal_extension
                logger.info("Runner: HistorianGroup wired to EntryGroup.")

            logger.info(
                "Runner: JournalExtension initialized and wired. "
                "DecisionTraceLogger active. OutcomeAttributor wired to PerformanceJournalGroup."
            )
        except Exception as exc:
            logger.warning("Runner: learning layer wiring failed: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def startup_load(self) -> None:
        """
        Load historical bars for all timeframes at startup.
        Skipped in simulation mode.

        Note: _finalize_learning_wiring() is called in setup() and does NOT
        need to be called here again. startup_load() only fetches Bybit bars.
        """
        if self._simulation_mode:
            logger.info("Runner: simulation mode — skipping Bybit startup_load.")
            return
        try:
            await self._market_data.startup_load(BTC_SYMBOL)
        except Exception as exc:
            logger.error("Runner: startup_load failed: %s", exc)

    async def run_one_bar(self, interval: str = DEFAULT_INTERVAL) -> bool:
        """
        Fetch one bar cycle from Bybit and process it through the pipeline.
        Returns True if new data was processed, False otherwise.

        In simulation mode, raises RuntimeError (use simulate_bar instead).
        """
        if self._simulation_mode:
            raise RuntimeError("Use simulate_bar() in simulation mode.")
        try:
            fv = await self._market_data.fetch_and_process(BTC_SYMBOL, interval)
            return fv is not None
        except Exception as exc:
            logger.error("Runner: run_one_bar failed: %s", exc)
            return False

    async def simulate_bar(self, fv: FeatureVector) -> None:
        """
        Inject a synthetic FeatureReadyEvent for integration testing.
        Bypasses Bybit fetch entirely.

        Populates:
        - MarketDataGroup._feature_cache[(symbol, timeframe)]: so PanelDecisionGroup
          can build BTCSetupPacket when EntryGroup fires a CandidateTradeEvent.
        - state.last_close_by_symbol: so EntryGroup._build_proposal() has an entry price.
        - Publishes FeatureReadyEvent: so IndicatorsGroup, CandlestickGroup,
          TechnicalStructureGroup, ExitGroup all receive bar data.

        Without populating the feature cache, PanelDecisionGroup silently drops
        every proposal with "no FeatureVector for symbol" — Layer B+C never runs.
        """
        # Mirror what fetch_and_process() does: update cache + last_close + publish
        self._market_data._feature_cache[(fv.symbol, fv.timeframe)] = fv
        await self._state.update_last_close(fv.symbol, fv.close)
        await self._bus.publish(
            FeatureReadyEvent(source="runner_simulation", features=fv)
        )

    async def run_paper_loop(
        self,
        max_bars: Optional[int] = None,
        interval: str = DEFAULT_INTERVAL,
    ) -> None:
        """
        Live polling loop. Runs until max_bars reached or cancelled.

        Polls Bybit every POLL_INTERVAL_SECONDS seconds.
        New bars arrive at most once per interval period (e.g. once per hour
        for interval="60"). Most polls will find no new bar and log "idle".

        For production: call with max_bars=None (runs indefinitely).
        For smoke tests: call with max_bars=3.

        Bybit connectivity must be available. Will log errors and continue
        on fetch failures — does not crash the loop.

        Observability contract:
          - Every poll cycle is logged (productive or idle).
          - "NEW BAR" log confirms downstream chain was triggered.
          - "idle" log confirms the chain was correctly skipped.
          - "bars_processed" counts only genuine new bars, not poll cycles.
        """
        if self._simulation_mode:
            raise RuntimeError("Use simulate_bar() in simulation mode.")

        await self.startup_load()
        bars_processed = 0
        poll_count = 0
        logger.info(
            "Runner: paper loop started "
            "(max_bars=%s, interval=%s, poll_every=%ds).",
            max_bars, interval, POLL_INTERVAL_SECONDS,
        )

        while self._running:
            poll_count += 1
            try:
                got_new = await self.run_one_bar(interval)
                if got_new:
                    bars_processed += 1
                    logger.info(
                        "Runner: [poll #%d] NEW BAR — bar %d processed. "
                        "Downstream chain triggered.",
                        poll_count, bars_processed,
                    )
                    if max_bars is not None and bars_processed >= max_bars:
                        logger.info("Runner: max_bars=%d reached, stopping.", max_bars)
                        break
                else:
                    logger.debug(
                        "Runner: [poll #%d] idle — no new bar. "
                        "Downstream chain not triggered. (bars_processed=%d)",
                        poll_count, bars_processed,
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Runner: [poll #%d] error: %s", poll_count, exc)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def teardown(self) -> None:
        """Gracefully stop all groups."""
        self._running = False
        for group in reversed(self._all_groups):
            try:
                await group.teardown()
            except Exception as exc:
                logger.warning("Runner: teardown error for %s: %s", type(group).__name__, exc)
        logger.info("Runner: teardown complete.")

    @property
    def state(self) -> SystemState:
        return self._state

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def journal_extension(self):
        return self._journal_extension
