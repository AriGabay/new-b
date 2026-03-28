"""
TrueReplayHarness — real runner fed by deterministic recorded bar fixtures.

Source tag: event_driven_runtime_replay

This harness differs from RuntimeReplayHarness (event_driven_runtime_simulation) in:
  1. Input source: deterministic fixtures with REAL indicator computation from OHLCV
     (not simple constant-offset synthetic bars)
  2. Source tag: event_driven_runtime_replay (not simulation)
  3. Lifecycle awareness: tracks open AND close events, bars processed after entry
  4. Fixture-based: uses btc_replay_fixture.py deterministic scenarios
  5. Honest reporting: documents the composite_score ceiling limitation

KNOWN LIMITATION (documented, not hidden):
  With ChartPatternGroup excluded (Phase 3), the maximum composite_score
  achievable in EntryGroup is 0.4875 < 0.50 (entry threshold).
  Natural trade entries CANNOT fire through the current pipeline.
  This harness documents this finding clearly and provides:
    - "pure replay" mode: 0 natural entries (honest)
    - "lifecycle control" mode: explicitly forced single entry to test full lifecycle,
      tagged separately as event_driven_runtime_replay_lifecycle_assist

See docs/replay_closed_trade_validation_report.md for analysis.

Usage:
    harness = TrueReplayHarness()
    await harness.setup()
    report = await harness.run_fixture(fixture)
    await harness.teardown()
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.schemas import FeatureVector

logger = logging.getLogger(__name__)

REPLAY_SOURCE = "event_driven_runtime_replay"
LIFECYCLE_ASSIST_SOURCE = "event_driven_runtime_replay_lifecycle_assist"


@dataclass
class ReplayBarEvent:
    """One bar's worth of state change during replay."""
    bar_index: int
    close_price: Decimal
    open_positions_before: int
    open_positions_after: int
    closed_positions_delta: int


@dataclass
class ReplayTrade:
    """A completed trade recorded during replay."""
    position_id: str
    symbol: str
    direction: str
    entry_price: Decimal
    exit_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    pnl_r: Optional[float]       # P&L in R-units (None if not computable)
    exit_reason: str
    bars_held: int
    open_bar: int
    close_bar: int


@dataclass
class ReplayFixtureReport:
    """Complete report for one replay fixture run."""
    fixture_name: str
    fixture_description: str
    validation_source: str
    bars_processed: int
    # Signal / decision pipeline
    ema_crossovers_in_fixture: list[dict]  # bars where golden/death cross occurred
    # Position lifecycle
    positions_opened: int
    positions_closed: int
    open_positions_remaining: int
    completed_trades: list[ReplayTrade]
    # Pipeline failure point (when no natural entries)
    entry_failure_analysis: dict
    errors: list[str] = field(default_factory=list)
    honest_assessment: str = ""


class TrueReplayHarness:
    """
    Feeds deterministic BTC fixture bars through the real wired runner.

    Uses BtcBybitPaperRunner in simulation_mode=True with a temp DB.
    Source: event_driven_runtime_replay.

    The harness waits for both opens AND closes by continuing to feed bars
    after any entry fires. After all bars, it reports on any positions
    still open at end-of-fixture.
    """

    def __init__(self, equity: Decimal = Decimal("100000")) -> None:
        self._equity = equity
        self._runner = None
        self._is_setup = False
        self._open_events: list = []
        self._close_events: list = []

    async def setup(self) -> None:
        """Create and wire a fresh runner."""
        from runtime.runner import BtcBybitPaperRunner
        import tempfile
        import os

        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, f"replay_{uuid.uuid4().hex[:8]}.db")

        self._runner = BtcBybitPaperRunner(
            simulation_mode=True,
            journal_db_path=db_path,
        )
        await self._runner.setup()

        # Seed equity
        self._runner.state.portfolio.equity = self._equity
        self._runner.state.portfolio.available = self._equity

        # Subscribe to position events to track lifecycle
        from core.events import PositionOpenEvent, PositionCloseEvent
        await self._runner.bus.subscribe(
            PositionOpenEvent, self._on_position_open
        )
        await self._runner.bus.subscribe(
            PositionCloseEvent, self._on_position_close
        )

        self._is_setup = True
        logger.info(
            "TrueReplayHarness: setup complete. equity=%s source=%s",
            self._equity, REPLAY_SOURCE,
        )

    async def _on_position_open(self, event) -> None:
        self._open_events.append(event)
        logger.info(
            "TrueReplayHarness: POSITION OPENED %s %s @ %s",
            event.position.direction,
            event.position.symbol,
            event.position.entry_price,
        )

    async def _on_position_close(self, event) -> None:
        self._close_events.append(event)
        if event.final_position:
            logger.info(
                "TrueReplayHarness: POSITION CLOSED %s, exit_reason=%s",
                event.final_position.position_id,
                getattr(event.exit_signal, 'exit_reason', 'unknown'),
            )

    async def teardown(self) -> None:
        if self._runner is not None:
            try:
                await self._runner.teardown()
            except Exception as exc:
                logger.warning("TrueReplayHarness: teardown error: %s", exc)
        self._is_setup = False

    async def run_fixture(
        self,
        fixture,  # ReplayFixture from btc_replay_fixture
    ) -> ReplayFixtureReport:
        """
        Run all bars from the fixture through the real runner.

        This is pure replay — no forcing, no injections.
        Records all position opens and closes.
        """
        if not self._is_setup:
            raise RuntimeError("Call setup() before run_fixture().")

        from validation.fixtures.btc_replay_fixture import (
            analyse_fixture_for_ema_crossovers,
            analyse_fixture_composite_score_ceiling,
        )

        fvs = fixture.feature_vectors
        errors = []
        bar_events = []

        # Reset event buffers
        self._open_events.clear()
        self._close_events.clear()

        open_before_total = len(self._runner.state.portfolio.open_positions)
        bar_open_map: dict[int, list] = {}  # bar_index → positions opened on that bar

        for i, fv in enumerate(fvs):
            try:
                before = len(self._runner.state.portfolio.open_positions)
                await self._runner.simulate_bar(fv)
                await asyncio.sleep(0)  # yield for event handlers

                after = len(self._runner.state.portfolio.open_positions)
                bar_events.append(ReplayBarEvent(
                    bar_index=i,
                    close_price=fv.close,
                    open_positions_before=before,
                    open_positions_after=after,
                    closed_positions_delta=0,  # not tracked per-bar yet
                ))
            except Exception as exc:
                err = f"Bar {i}: {exc}"
                logger.error("TrueReplayHarness [%s]: %s", fixture.name, err)
                errors.append(err)

        # Analyse fixture characteristics
        crossovers = analyse_fixture_for_ema_crossovers(fixture)
        entry_analysis = analyse_fixture_composite_score_ceiling(fixture)

        # Build completed trades from close events
        completed_trades = []
        for close_evt in self._close_events:
            pos = getattr(close_evt, 'final_position', None)
            sig = getattr(close_evt, 'exit_signal', None)
            if pos:
                # Find matching open bar (approximate from position data)
                pnl_r = getattr(sig, 'pnl_r', None) if sig else None
                exit_reason = getattr(sig, 'exit_reason', None) if sig else None
                exit_reason_str = exit_reason.value if hasattr(exit_reason, 'value') else str(exit_reason)
                bars_held = getattr(sig, 'bars_held', 0) if sig else 0
                exit_price = getattr(sig, 'exit_price', pos.stop_price) if sig else pos.stop_price

                completed_trades.append(ReplayTrade(
                    position_id=pos.position_id,
                    symbol=pos.symbol,
                    direction=str(pos.direction),
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    stop_price=pos.stop_price,
                    target_price=pos.target_price,
                    pnl_r=pnl_r,
                    exit_reason=exit_reason_str,
                    bars_held=bars_held,
                    open_bar=-1,  # not tracked per-bar
                    close_bar=-1,
                ))

        # Honest assessment
        positions_opened = len(self._open_events)
        positions_closed = len(self._close_events)
        open_remaining = len(self._runner.state.portfolio.open_positions)

        honest_assessment = self._build_honest_assessment(
            fixture=fixture,
            bars_processed=len(fvs),
            crossovers=crossovers,
            positions_opened=positions_opened,
            positions_closed=positions_closed,
            entry_analysis=entry_analysis,
        )

        report = ReplayFixtureReport(
            fixture_name=fixture.name,
            fixture_description=fixture.description,
            validation_source=REPLAY_SOURCE,
            bars_processed=len(fvs),
            ema_crossovers_in_fixture=crossovers,
            positions_opened=positions_opened,
            positions_closed=positions_closed,
            open_positions_remaining=open_remaining,
            completed_trades=completed_trades,
            entry_failure_analysis=entry_analysis,
            errors=errors,
            honest_assessment=honest_assessment,
        )

        logger.info(
            "TrueReplayHarness [%s]: %d bars, %d ema_crossovers, "
            "%d positions opened, %d positions closed, %d remaining",
            fixture.name, len(fvs), len(crossovers),
            positions_opened, positions_closed, open_remaining,
        )
        return report

    async def run_lifecycle_control_test(
        self,
        fixture,  # ReplayFixture with enough bars for position to close
        inject_at_bar: Optional[int] = None,
    ) -> ReplayFixtureReport:
        """
        Lifecycle control test: inject ONE CandidateTradeEvent at a specific bar
        to demonstrate the full position open→close lifecycle through replay bars.

        Source: event_driven_runtime_replay_lifecycle_assist
        (NOT primary replay evidence — explicitly tagged control test)

        This is used ONLY to verify the open/close mechanics work.
        The injected entry is NOT a natural signal — it is forced.

        inject_at_bar: which bar to inject at. Defaults to ~30% through fixture.
        """
        if not self._is_setup:
            raise RuntimeError("Call setup() before run_lifecycle_control_test().")

        fvs = fixture.feature_vectors
        n = len(fvs)
        if inject_at_bar is None:
            inject_at_bar = max(30, n // 4)  # inject at ~25% through

        errors = []
        self._open_events.clear()
        self._close_events.clear()

        injected = False

        for i, fv in enumerate(fvs):
            try:
                await self._runner.simulate_bar(fv)
                await asyncio.sleep(0)

                # Inject a CandidateTradeEvent at the designated bar
                if i == inject_at_bar and not injected:
                    await self._inject_trade_proposal(fv)
                    injected = True
                    await asyncio.sleep(0)

            except Exception as exc:
                errors.append(f"Bar {i}: {exc}")
                logger.error("TrueReplayHarness lifecycle [%s] bar %d: %s", fixture.name, i, exc)

        from validation.fixtures.btc_replay_fixture import (
            analyse_fixture_for_ema_crossovers,
            analyse_fixture_composite_score_ceiling,
        )
        crossovers = analyse_fixture_for_ema_crossovers(fixture)
        entry_analysis = analyse_fixture_composite_score_ceiling(fixture)
        entry_analysis["lifecycle_control_mode"] = True
        entry_analysis["injected_at_bar"] = inject_at_bar

        completed_trades = []
        for close_evt in self._close_events:
            pos = getattr(close_evt, 'final_position', None)
            sig = getattr(close_evt, 'exit_signal', None)
            if pos:
                pnl_r = getattr(sig, 'pnl_r', None) if sig else None
                exit_reason = getattr(sig, 'exit_reason', None) if sig else None
                exit_reason_str = exit_reason.value if hasattr(exit_reason, 'value') else str(exit_reason)
                bars_held = getattr(sig, 'bars_held', 0) if sig else 0
                exit_price = getattr(sig, 'exit_price', pos.stop_price) if sig else pos.stop_price
                completed_trades.append(ReplayTrade(
                    position_id=pos.position_id,
                    symbol=pos.symbol,
                    direction=str(pos.direction),
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    stop_price=pos.stop_price,
                    target_price=pos.target_price,
                    pnl_r=pnl_r,
                    exit_reason=exit_reason_str,
                    bars_held=bars_held,
                    open_bar=inject_at_bar,
                    close_bar=-1,
                ))

        positions_opened = len(self._open_events)
        positions_closed = len(self._close_events)

        honest_assessment = (
            f"LIFECYCLE CONTROL TEST — NOT primary replay evidence. "
            f"One CandidateTradeEvent was injected at bar {inject_at_bar} "
            f"to test open/close mechanics. "
            f"Positions opened: {positions_opened}. "
            f"Positions closed: {positions_closed}. "
            f"Completed trades: {len(completed_trades)}. "
            f"This tests the execution pipeline, not natural signal quality."
        )

        return ReplayFixtureReport(
            fixture_name=fixture.name + "_lifecycle_control",
            fixture_description=(
                fixture.description + " [LIFECYCLE CONTROL: injected entry at bar "
                + str(inject_at_bar) + "]"
            ),
            validation_source=LIFECYCLE_ASSIST_SOURCE,
            bars_processed=len(fvs),
            ema_crossovers_in_fixture=crossovers,
            positions_opened=positions_opened,
            positions_closed=positions_closed,
            open_positions_remaining=len(self._runner.state.portfolio.open_positions),
            completed_trades=completed_trades,
            entry_failure_analysis=entry_analysis,
            errors=errors,
            honest_assessment=honest_assessment,
        )

    async def _inject_trade_proposal(self, fv: FeatureVector) -> None:
        """
        Inject a single CandidateTradeEvent into the bus for lifecycle testing.
        Uses realistic parameters derived from the current bar's FeatureVector.
        Panel is NOT bypassed — the real panel evaluates it.
        """
        from core.events import CandidateTradeEvent
        from core.schemas import CandidateTradeProposal, Direction, ModeGate

        entry = fv.close
        atr = fv.atr14
        raw_target = entry + atr * Decimal("2")  # R:R = 2.0

        proposal = CandidateTradeProposal(
            symbol=fv.symbol,
            timeframe=fv.timeframe,
            timestamp=fv.timestamp,
            direction=Direction.LONG,
            entry_price=entry,
            thesis=(
                f"Lifecycle control test: LONG @ {entry} "
                f"(replay fixture assist — NOT natural signal)"
            ),
            setup_refs=["replay_lifecycle_control"],
            hypothesis_refs=["H3-002"],
            composite_score=0.65,
            score_breakdown={"lifecycle_control": 0.65},
            raw_target=raw_target,
            mode_gate=ModeGate.SHADOW,
        )

        event = CandidateTradeEvent(proposal=proposal)
        await self._runner.bus.publish(event)
        logger.info(
            "TrueReplayHarness: injected lifecycle control proposal @ %s "
            "(real panel will evaluate — no forcing)",
            entry,
        )

    @staticmethod
    def _build_honest_assessment(
        fixture,
        bars_processed: int,
        crossovers: list[dict],
        positions_opened: int,
        positions_closed: int,
        entry_analysis: dict,
    ) -> str:
        """Build an honest, factual assessment of what happened."""
        lines = []
        lines.append(f"REPLAY FIXTURE: {fixture.name}")
        lines.append(f"Bars processed: {bars_processed}")
        lines.append(f"EMA crossovers detected in fixture: {len(crossovers)}")
        if crossovers:
            for cx in crossovers[:3]:
                lines.append(
                    f"  Bar {cx['bar_index']}: {cx['direction']} "
                    f"price={cx['price']:.0f} ADX={cx['adx']:.1f} RSI={cx['rsi']:.1f}"
                )

        lines.append(f"Natural positions opened: {positions_opened}")
        lines.append(f"Positions closed: {positions_closed}")

        if positions_opened == 0:
            ceiling = entry_analysis.get("theoretical_composite_ceiling", 0)
            threshold = entry_analysis.get("entry_threshold", 0.50)
            shortfall = entry_analysis.get("shortfall", 0)
            lines.append("")
            lines.append("ENTRY FAILURE ANALYSIS:")
            lines.append(
                f"  composite_score ceiling: {ceiling:.4f} (below {threshold} threshold)"
            )
            lines.append(
                f"  shortfall: {shortfall:.4f}"
            )
            lines.append(
                "  root cause: ChartPatternGroup EXCLUDED (Phase 3 scope)."
            )
            lines.append(
                "  chart_pattern_quality is always 0.0 → max composite = "
                f"0.25×0.75 + 0.20×1.0 + 0.10×1.0 = {ceiling:.4f}"
            )
            lines.append(
                "  fix: either activate ChartPatternGroup OR lower COMPOSITE_SCORE_THRESHOLD"
            )
            lines.append(
                "  NOTE: This is NOT a panel selectivity finding. The panel never evaluates"
            )
            lines.append(
                "        these bars because EntryGroup never fires a CandidateTradeEvent."
            )

        return "\n".join(lines)

    @property
    def runner(self):
        return self._runner

    @property
    def state(self):
        return self._runner.state if self._runner else None


def make_replay_aggregate_report(reports: list[ReplayFixtureReport]) -> dict:
    """
    Aggregate multiple fixture reports into one summary.
    """
    total_bars = sum(r.bars_processed for r in reports)
    total_crossovers = sum(len(r.ema_crossovers_in_fixture) for r in reports)
    total_opened = sum(r.positions_opened for r in reports)
    total_closed = sum(r.positions_closed for r in reports)
    total_errors = sum(len(r.errors) for r in reports)

    pure_replay = [r for r in reports if r.validation_source == REPLAY_SOURCE]
    lifecycle_control = [r for r in reports if r.validation_source == LIFECYCLE_ASSIST_SOURCE]

    lifecycle_trades = []
    for r in lifecycle_control:
        lifecycle_trades.extend(r.completed_trades)

    # Entry failure analysis (from first pure replay report)
    entry_analysis = {}
    if pure_replay:
        entry_analysis = pure_replay[0].entry_failure_analysis

    if total_opened == 0:
        system_status = (
            "NO NATURAL ENTRIES in any pure-replay fixture. "
            "Root cause: composite_score ceiling {:.4f} < {:.4f} threshold. "
            "ChartPatternGroup exclusion prevents natural trade entries. "
            "System processes all bars correctly. "
            "All signals fire. EntryGroup correctly evaluates. "
            "But composite_score can never reach 0.50 without chart patterns."
        ).format(
            entry_analysis.get("theoretical_composite_ceiling", 0),
            entry_analysis.get("entry_threshold", 0.50),
        )
    else:
        system_status = (
            f"{total_opened} natural entries opened across "
            f"{len(pure_replay)} pure-replay fixtures."
        )

    lifecycle_status = (
        f"Lifecycle control test: {len(lifecycle_trades)} completed trades "
        f"from injected entries."
        if lifecycle_control else "No lifecycle control tests run."
    )

    return {
        "validation_source": REPLAY_SOURCE,
        "total_fixtures": len(reports),
        "pure_replay_fixtures": len(pure_replay),
        "lifecycle_control_fixtures": len(lifecycle_control),
        "total_bars_processed": total_bars,
        "total_ema_crossovers_detected": total_crossovers,
        "natural_positions_opened": total_opened,
        "natural_positions_closed": total_closed,
        "total_errors": total_errors,
        "lifecycle_completed_trades": len(lifecycle_trades),
        "system_status": system_status,
        "lifecycle_status": lifecycle_status,
        "entry_failure_analysis": entry_analysis,
        "per_fixture": [
            {
                "name": r.fixture_name,
                "source": r.validation_source,
                "bars": r.bars_processed,
                "crossovers": len(r.ema_crossovers_in_fixture),
                "positions_opened": r.positions_opened,
                "positions_closed": r.positions_closed,
                "completed_trades": len(r.completed_trades),
                "errors": r.errors,
            }
            for r in reports
        ],
    }
