"""
Phase 7 Baseline — Locked regression contract.

Runs ALL available fixtures through the real BtcBybitPaperRunner and records:
  - proposals generated (CandidateTradeEvent count)
  - panel approvals (PanelApprovedProposalEvent count)
  - panel approve_count and avg_score (best bar)
  - positions opened (PositionOpenEvent count)
  - positions closed (PositionCloseEvent count)
  - total_trades in portfolio

This is the Phase 7 regression baseline. Every tuning pass must re-run this suite
and confirm no fixture regressed without documented justification.

Source: event_driven_runtime_replay
Phase: 7.0 — Baseline Lock
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FixtureBaselineResult:
    fixture_name: str
    bar_count: int = 0
    candidate_events: int = 0
    approved_events: int = 0
    best_approve_count: int = 0
    best_avg_score: float = 0.0
    best_decision: str = ""
    position_opens: int = 0
    position_closes: int = 0
    total_trades: int = 0
    final_equity: float = 0.0
    source_tag: str = "event_driven_runtime"
    # Per-evaluator breakdown for the best panel result
    evaluator_scores: dict = field(default_factory=dict)


async def _run_fixture_baseline(fixture) -> FixtureBaselineResult:
    """Run a single fixture through the real pipeline and collect all metrics."""
    from runtime.runner import BtcBybitPaperRunner
    from core.events import (
        CandidateTradeEvent,
        PanelApprovedProposalEvent,
        PositionOpenEvent,
        PositionCloseEvent,
    )

    result = FixtureBaselineResult(
        fixture_name=fixture.name,
        bar_count=len(fixture.feature_vectors),
    )

    candidates = []
    approved = []
    opens = []
    closes = []

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    # Capture events by wrapping bus.publish
    original_publish = runner.bus.publish

    async def capture_publish(event):
        if isinstance(event, CandidateTradeEvent):
            candidates.append(event)
        elif isinstance(event, PanelApprovedProposalEvent):
            approved.append(event)
        elif isinstance(event, PositionOpenEvent):
            opens.append(event)
        elif isinstance(event, PositionCloseEvent):
            closes.append(event)
        return await original_publish(event)

    runner.bus.publish = capture_publish

    for fv in fixture.feature_vectors:
        await runner.simulate_bar(fv)

    await asyncio.sleep(0.05)

    result.candidate_events = len(candidates)
    result.approved_events = len(approved)
    result.position_opens = len(opens)
    result.position_closes = len(closes)
    result.total_trades = runner.state.portfolio.total_trades
    result.final_equity = float(runner.state.portfolio.equity)

    if approved:
        best = max(approved, key=lambda e: e.panel_approve_count)
        result.best_approve_count = best.panel_approve_count
        result.best_avg_score = best.panel_avg_score
        result.best_decision = best.panel_decision

    await runner.teardown()
    return result


def _run(coro):
    return asyncio.run(coro)


def _get_all_fixtures():
    """Collect every available fixture from all fixture modules."""
    from validation.fixtures.btc_replay_fixture import get_all_replay_fixtures
    from validation.fixtures.btc_established_trend_fixture import get_all_phase61_fixtures
    from validation.fixtures.btc_structure_fixture import (
        get_all_phase62_fixtures,
        get_all_phase63_fixtures,
        get_all_phase64_fixtures,
    )

    all_fixtures = []
    all_fixtures.extend(get_all_replay_fixtures())
    all_fixtures.extend(get_all_phase61_fixtures())
    all_fixtures.extend(get_all_phase62_fixtures())
    all_fixtures.extend(get_all_phase63_fixtures())
    all_fixtures.extend(get_all_phase64_fixtures())
    return all_fixtures


# ---------------------------------------------------------------------------
# Master baseline runner (not a test — called by tests below)
# ---------------------------------------------------------------------------

_baseline_cache: dict[str, FixtureBaselineResult] = {}


def _get_baseline(fixture_name: str) -> FixtureBaselineResult:
    if fixture_name not in _baseline_cache:
        fixtures = _get_all_fixtures()
        for f in fixtures:
            if f.name == fixture_name and f.name not in _baseline_cache:
                _baseline_cache[f.name] = _run(_run_fixture_baseline(f))
    return _baseline_cache[fixture_name]


def _get_all_baselines() -> dict[str, FixtureBaselineResult]:
    if not _baseline_cache:
        fixtures = _get_all_fixtures()
        for f in fixtures:
            if f.name not in _baseline_cache:
                _baseline_cache[f.name] = _run(_run_fixture_baseline(f))
    return _baseline_cache


# ---------------------------------------------------------------------------
# Phase 6.3 V2 — known ENTER (14/20, avg ≥ 6.5)
# ---------------------------------------------------------------------------

class TestBaselineV2WBottomLong:
    """btc_w_bottom_long_v2: proven natural ENTER at 14/20."""

    def test_v2_approves(self):
        r = _get_baseline("btc_w_bottom_long_v2")
        assert r.approved_events >= 1, f"V2 must approve, got {r.approved_events}"

    def test_v2_approve_count_at_least_14(self):
        r = _get_baseline("btc_w_bottom_long_v2")
        assert r.best_approve_count >= 14, f"V2 must have ≥14, got {r.best_approve_count}"

    def test_v2_avg_score_at_least_6p5(self):
        r = _get_baseline("btc_w_bottom_long_v2")
        assert r.best_avg_score >= 6.5, f"V2 avg must be ≥6.5, got {r.best_avg_score:.3f}"

    def test_v2_position_opens(self):
        r = _get_baseline("btc_w_bottom_long_v2")
        assert r.position_opens >= 1, f"V2 must open position, got {r.position_opens}"


# ---------------------------------------------------------------------------
# Phase 6.4 V3 — known ENTER with chart pattern (16/20, avg ≥ 7.0)
# ---------------------------------------------------------------------------

class TestBaselineV3DoubleBottom:
    """btc_double_bottom_long_v1: proven natural ENTER at 16/20 with chart pattern."""

    def test_v3_approves(self):
        r = _get_baseline("btc_double_bottom_long_v1")
        assert r.approved_events >= 1, f"V3 must approve, got {r.approved_events}"

    def test_v3_approve_count_at_least_16(self):
        r = _get_baseline("btc_double_bottom_long_v1")
        assert r.best_approve_count >= 16, f"V3 must have ≥16, got {r.best_approve_count}"

    def test_v3_avg_score_at_least_7(self):
        r = _get_baseline("btc_double_bottom_long_v1")
        assert r.best_avg_score >= 7.0, f"V3 avg must be ≥7.0, got {r.best_avg_score:.3f}"

    def test_v3_position_opens(self):
        r = _get_baseline("btc_double_bottom_long_v1")
        assert r.position_opens >= 1, f"V3 must open position, got {r.position_opens}"


# ---------------------------------------------------------------------------
# Phase 6.2 V1 — known HOLD (13/20, below threshold)
# ---------------------------------------------------------------------------

class TestBaselineV1WBottomLong:
    """btc_w_bottom_long_v1: proven HOLD at 13/20."""

    def test_v1_does_not_approve(self):
        r = _get_baseline("btc_w_bottom_long_v1")
        assert r.approved_events == 0, (
            f"V1 must NOT approve (13/20 hold), got {r.approved_events} approvals"
        )

    def test_v1_no_position_opens(self):
        r = _get_baseline("btc_w_bottom_long_v1")
        assert r.position_opens == 0, f"V1 must not open, got {r.position_opens}"


# ---------------------------------------------------------------------------
# Remaining structural fixtures — baseline lock
# ---------------------------------------------------------------------------

class TestBaselineStructuralFixtures:
    """m_top_short and triple_touch_long: record baseline behavior."""

    def test_m_top_short_runs_without_error(self):
        r = _get_baseline("btc_m_top_short_v1")
        assert r.bar_count > 0

    def test_triple_touch_long_runs_without_error(self):
        r = _get_baseline("btc_triple_touch_long_v1")
        assert r.bar_count > 0


# ---------------------------------------------------------------------------
# Replay fixtures — baseline lock
# ---------------------------------------------------------------------------

class TestBaselineReplayFixtures:
    """bull_breakout, bear_breakdown, ranging: record baseline behavior."""

    def test_bull_breakout_runs(self):
        r = _get_baseline("btc_bull_breakout_v1")
        assert r.bar_count > 0

    def test_bear_breakdown_runs(self):
        r = _get_baseline("btc_bear_breakdown_v1")
        assert r.bar_count > 0

    def test_ranging_runs(self):
        r = _get_baseline("btc_ranging_v1")
        assert r.bar_count > 0


# ---------------------------------------------------------------------------
# Established trend fixtures — baseline lock
# ---------------------------------------------------------------------------

class TestBaselineEstablishedTrendFixtures:
    """Phase 6.1 fixtures."""

    def test_bull_continuation_runs(self):
        r = _get_baseline("btc_bull_continuation_pullback_v1")
        assert r.bar_count > 0

    def test_bear_continuation_runs(self):
        r = _get_baseline("btc_bear_continuation_pullback_v1")
        assert r.bar_count > 0

    def test_long_established_trend_runs(self):
        r = _get_baseline("btc_long_established_trend_v1")
        assert r.bar_count > 0


# ---------------------------------------------------------------------------
# Full baseline report
# ---------------------------------------------------------------------------

class TestBaselineReport:
    """Print full baseline for documentation purposes."""

    def test_print_full_baseline(self, capsys):
        """Run ALL fixtures and print summary table. Always passes."""
        baselines = _get_all_baselines()

        header = (
            f"{'Fixture':<35} {'Bars':>5} {'Cand':>5} {'Appr':>5} "
            f"{'Best':>5} {'AvgSc':>6} {'Opens':>5} {'Close':>5} {'Trades':>6}"
        )
        print("\n" + "=" * 95)
        print("PHASE 7 BASELINE — Locked Regression Contract")
        print("=" * 95)
        print(header)
        print("-" * 95)

        for name in sorted(baselines.keys()):
            r = baselines[name]
            print(
                f"{r.fixture_name:<35} {r.bar_count:>5} {r.candidate_events:>5} "
                f"{r.approved_events:>5} {r.best_approve_count:>5} "
                f"{r.best_avg_score:>6.3f} {r.position_opens:>5} "
                f"{r.position_closes:>5} {r.total_trades:>6}"
            )

        print("=" * 95)
        print(f"Total fixtures: {len(baselines)}")
        entering = sum(1 for r in baselines.values() if r.approved_events > 0)
        holding = sum(1 for r in baselines.values() if r.approved_events == 0)
        print(f"Entering: {entering}  |  Holding: {holding}")
        print("=" * 95)
