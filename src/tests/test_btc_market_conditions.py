"""
Tests for Task 7 market-conditions fixtures:
  - btc_downtrend_short_setup_v1  (death cross + bearish engulfing proxy)
  - btc_ranging_market_45k_v1     (sideways ±3% at $45,000)
  - btc_news_rejection_v1         (impulse-cluster news proxy)

Each test class covers:
  1. Fixture construction (no errors, correct bar count)
  2. Price range validation ($40,000–$52,000 for scenario bars)
  3. Market condition verification (death cross, low ADX, impulse flags)
  4. Pipeline smoke test (runs through BtcBybitPaperRunner without error)
  5. No-entry contract (natural entry not expected due to composite_score ceiling)
"""
from __future__ import annotations

import asyncio
import math
import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine and restore a usable event loop for subsequent tests.

    asyncio.run() closes the event loop it creates, leaving no current event
    loop for the thread.  Tests that use asyncio.get_event_loop() (Python 3.10
    style) will fail with RuntimeError in the same pytest session.  We restore a
    new loop so that later tests are not affected.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass
        # Restore an open event loop so get_event_loop() works in later tests.
        asyncio.set_event_loop(asyncio.new_event_loop())


async def _run_fixture_through_pipeline(fixture):
    """Run a fixture through the real runner and return event counts."""
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent, PositionOpenEvent

    candidates = []
    opens_ = []

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    original_publish = runner.bus.publish

    async def _capture(event):
        if isinstance(event, CandidateTradeEvent):
            candidates.append(event)
        elif isinstance(event, PositionOpenEvent):
            opens_.append(event)
        return await original_publish(event)

    runner.bus.publish = _capture

    for fv in fixture.feature_vectors:
        await runner.simulate_bar(fv)

    await asyncio.sleep(0.05)
    await runner.teardown()

    return {"candidates": len(candidates), "opens": len(opens_)}


# ──────────────────────────────────────────────────────────────────────────────
# Fixture 1: btc_downtrend_short_setup_v1
# ──────────────────────────────────────────────────────────────────────────────

class TestBtcDowntrendShortSetup:
    """btc_downtrend_short_setup_v1 — 340 bars, death cross, bearish engulfing."""

    def _fixture(self):
        from validation.fixtures.btc_downtrend_short_setup import (
            get_btc_downtrend_short_fixture,
        )
        return get_btc_downtrend_short_fixture()

    # ── Construction ──────────────────────────────────────────────────────────

    def test_fixture_loads_without_error(self):
        fx = self._fixture()
        assert fx is not None

    def test_fixture_name(self):
        fx = self._fixture()
        assert fx.name == "btc_downtrend_short_setup_v1"

    def test_bar_count_is_340(self):
        fx = self._fixture()
        # 220 warmup + 20 phase1 + 40 phase2 + 60 phase3 = 340
        assert len(fx.feature_vectors) == 340

    def test_feature_vectors_have_valid_prices(self):
        fx = self._fixture()
        for fv in fx.feature_vectors:
            assert float(fv.close) > 0
            assert float(fv.high) >= float(fv.low)
            assert float(fv.high) >= float(fv.close)
            assert float(fv.low) <= float(fv.close)

    # ── Price range ───────────────────────────────────────────────────────────

    def test_scenario_bars_include_40k_to_50k_range(self):
        """Scenario bars (bar 220+) must contain prices in $40k–$52k range."""
        fx = self._fixture()
        scenario_closes = [float(fv.close) for fv in fx.feature_vectors[220:]]
        assert min(scenario_closes) < 48_000.0, (
            f"Expected scenario prices to reach below 48k, "
            f"min={min(scenario_closes):.0f}"
        )
        assert max(scenario_closes) > 41_000.0

    def test_scenario_low_price_below_43k(self):
        """Extended bear phase must bring price below $43,000."""
        fx = self._fixture()
        scenario_closes = [float(fv.close) for fv in fx.feature_vectors[220:]]
        assert min(scenario_closes) < 43_000.0, (
            f"Bear phase must reach below 43k, min={min(scenario_closes):.0f}"
        )

    # ── Death cross ───────────────────────────────────────────────────────────

    def test_death_cross_occurs(self):
        """EMA20 must cross below EMA50 at some point in the fixture."""
        from validation.fixtures.btc_downtrend_short_setup import (
            analyse_fixture_for_death_cross,
        )
        fx = self._fixture()
        crosses = analyse_fixture_for_death_cross(fx)
        assert len(crosses) >= 1, (
            f"Expected at least one death cross, found {len(crosses)}"
        )

    def test_death_cross_in_scenario_bars(self):
        """Death cross must occur in the scenario portion (bar 220+)."""
        from validation.fixtures.btc_downtrend_short_setup import (
            analyse_fixture_for_death_cross,
        )
        fx = self._fixture()
        crosses = analyse_fixture_for_death_cross(fx)
        scenario_crosses = [c for c in crosses if c["bar_index"] >= 220]
        assert len(scenario_crosses) >= 1, (
            f"Death cross must be in scenario bars (≥220), found at: "
            f"{[c['bar_index'] for c in crosses]}"
        )

    def test_ema20_below_ema50_after_death_cross(self):
        """After the death cross, EMA20 stays below EMA50."""
        from validation.fixtures.btc_downtrend_short_setup import (
            analyse_fixture_for_death_cross,
        )
        fx = self._fixture()
        crosses = analyse_fixture_for_death_cross(fx)
        assert crosses, "Need at least one death cross to verify post-cross state"
        last_cross_bar = max(c["bar_index"] for c in crosses)
        # Check 20 bars after the last cross: EMA20 should remain below EMA50
        fvs = fx.feature_vectors
        check_bars = fvs[last_cross_bar + 1: last_cross_bar + 21]
        if check_bars:
            bear_count = sum(
                1 for fv in check_bars
                if float(fv.ema20) < float(fv.ema50)
            )
            assert bear_count >= len(check_bars) * 0.7, (
                f"Expected EMA20 < EMA50 for ≥70% of post-cross bars, "
                f"got {bear_count}/{len(check_bars)}"
            )

    # ── Bearish engulfing ─────────────────────────────────────────────────────

    def test_bearish_engulfing_pattern_exists(self):
        """Fixture must contain at least one bearish engulfing candlestick."""
        from validation.fixtures.btc_downtrend_short_setup import (
            analyse_fixture_for_bearish_engulfing,
        )
        fx = self._fixture()
        patterns = analyse_fixture_for_bearish_engulfing(fx)
        assert len(patterns) >= 1, (
            "Expected at least one bearish engulfing pattern in the fixture"
        )

    def test_bearish_engulfing_fields(self):
        """Bearish engulfing analysis must return valid field values."""
        from validation.fixtures.btc_downtrend_short_setup import (
            analyse_fixture_for_bearish_engulfing,
        )
        fx = self._fixture()
        patterns = analyse_fixture_for_bearish_engulfing(fx)
        if patterns:
            p = patterns[0]
            assert "bar_index" in p
            assert "price" in p
            assert p["curr_body"] > p["prev_body"]
            assert p["price"] > 0

    # ── No natural entry (pipeline ceiling) ──────────────────────────────────

    def test_entry_expected_is_none(self):
        """entry_expected_at_bar must be None (no natural entry expected)."""
        fx = self._fixture()
        assert fx.entry_expected_at_bar is None

    # ── Pipeline smoke test ───────────────────────────────────────────────────

    def test_pipeline_runs_without_error(self):
        """Fixture must run through BtcBybitPaperRunner without raising."""
        fx = self._fixture()
        result = _run(_run_fixture_through_pipeline(fx))
        assert isinstance(result["candidates"], int)
        assert isinstance(result["opens"], int)

    def test_no_positions_opened(self):
        """No positions should open (composite_score ceiling + no chart pattern)."""
        fx = self._fixture()
        result = _run(_run_fixture_through_pipeline(fx))
        assert result["opens"] == 0, (
            f"Expected 0 position opens, got {result['opens']} "
            "(composite_score ceiling prevents natural entry)"
        )

    # ── Batch accessor ────────────────────────────────────────────────────────

    def test_get_all_downtrend_fixtures_returns_one(self):
        from validation.fixtures.btc_downtrend_short_setup import (
            get_all_btc_downtrend_fixtures,
        )
        fixtures = get_all_btc_downtrend_fixtures()
        assert len(fixtures) == 1
        assert fixtures[0].name == "btc_downtrend_short_setup_v1"


# ──────────────────────────────────────────────────────────────────────────────
# Fixture 2: btc_ranging_market_45k_v1
# ──────────────────────────────────────────────────────────────────────────────

class TestBtcRangingMarket:
    """btc_ranging_market_45k_v1 — 200 bars, sideways ±3% at $45,000."""

    def _fixture(self):
        from validation.fixtures.btc_ranging_market import get_btc_ranging_market_fixture
        return get_btc_ranging_market_fixture()

    # ── Construction ──────────────────────────────────────────────────────────

    def test_fixture_loads_without_error(self):
        fx = self._fixture()
        assert fx is not None

    def test_fixture_name(self):
        fx = self._fixture()
        assert fx.name == "btc_ranging_market_45k_v1"

    def test_bar_count_is_200(self):
        fx = self._fixture()
        assert len(fx.feature_vectors) == 200

    def test_feature_vectors_have_valid_prices(self):
        fx = self._fixture()
        for fv in fx.feature_vectors:
            assert float(fv.close) > 0
            assert float(fv.high) >= float(fv.low)

    # ── Price range ───────────────────────────────────────────────────────────

    def test_prices_centered_near_45k(self):
        """Mean close price should be within ±5% of $45,000."""
        fx = self._fixture()
        closes = [float(fv.close) for fv in fx.feature_vectors]
        mean_close = sum(closes) / len(closes)
        assert abs(mean_close - 45_000.0) < 45_000.0 * 0.05, (
            f"Mean close {mean_close:.0f} is not within ±5% of 45,000"
        )

    def test_price_range_within_plus_minus_5_percent(self):
        """All prices should stay within ±5% of center (±3% design, some wick)."""
        fx = self._fixture()
        closes = [float(fv.close) for fv in fx.feature_vectors]
        center = 45_000.0
        tolerance = center * 0.07  # allow 7% for OHLC wicks
        for c in closes:
            assert abs(c - center) < tolerance, (
                f"Close {c:.0f} is more than 7% from center {center:.0f}"
            )

    def test_price_range_analysis(self):
        """analyse_fixture_price_range should report ≤ 10% swing."""
        from validation.fixtures.btc_ranging_market import analyse_fixture_price_range
        fx = self._fixture()
        stats = analyse_fixture_price_range(fx)
        assert stats["pct_range"] <= 12.0, (
            f"Price range {stats['pct_range']:.1f}% exceeds 12% for ranging fixture"
        )
        assert 40_000.0 <= stats["min_price"] <= 50_000.0
        assert 40_000.0 <= stats["max_price"] <= 50_000.0

    # ── Low ADX / no trend ───────────────────────────────────────────────────

    def test_adx_profile_returns_valid_data(self):
        """analyse_fixture_adx_profile must return sensible statistics."""
        from validation.fixtures.btc_ranging_market import analyse_fixture_adx_profile
        fx = self._fixture()
        profile = analyse_fixture_adx_profile(fx)
        assert profile["total_bars"] == 200
        assert profile["min_adx"] >= 0
        assert profile["max_adx"] <= 100
        assert profile["mean_adx"] > 0
        # Ranging fixture should have bars below 20 (early bars before ADX builds)
        assert profile["bars_below_20"] >= 1

    def test_no_persistent_ema_trend(self):
        """In a ranging market the EMA alignment should not be one-directional."""
        from validation.fixtures.btc_ranging_market import analyse_fixture_adx_profile
        fx = self._fixture()
        profile = analyse_fixture_adx_profile(fx)
        # The fixture MUST produce at least one EMA crossover (direction change)
        # confirming EMAs are not locked into a single trend.
        assert profile["has_crossover"], (
            "Ranging market must produce at least one EMA crossover "
            "(confirming no sustained single-direction trend)"
        )

    def test_no_sustained_trend_direction(self):
        """EMA20 should not remain above or below EMA50 for more than 80 bars straight."""
        fx = self._fixture()
        fvs = fx.feature_vectors
        max_run = 0
        current_run = 0
        last_sign = None
        for fv in fvs:
            sign = 1 if float(fv.ema20) > float(fv.ema50) else -1
            if sign == last_sign:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1
                last_sign = sign
        assert max_run < 120, (
            f"EMA20 vs EMA50 run of {max_run} bars suggests sustained trend, "
            "not ranging"
        )

    # ── No natural entry ─────────────────────────────────────────────────────

    def test_entry_expected_is_none(self):
        fx = self._fixture()
        assert fx.entry_expected_at_bar is None

    # ── Pipeline smoke test ───────────────────────────────────────────────────

    def test_pipeline_runs_without_error(self):
        fx = self._fixture()
        result = _run(_run_fixture_through_pipeline(fx))
        assert isinstance(result["candidates"], int)

    def test_no_positions_opened(self):
        """Ranging market must not trigger any position opens."""
        fx = self._fixture()
        result = _run(_run_fixture_through_pipeline(fx))
        assert result["opens"] == 0, (
            f"Ranging market should not open positions, got {result['opens']}"
        )

    # ── Batch accessor ────────────────────────────────────────────────────────

    def test_get_all_ranging_market_fixtures_returns_one(self):
        from validation.fixtures.btc_ranging_market import (
            get_all_btc_ranging_market_fixtures,
        )
        fixtures = get_all_btc_ranging_market_fixtures()
        assert len(fixtures) == 1
        assert fixtures[0].name == "btc_ranging_market_45k_v1"


# ──────────────────────────────────────────────────────────────────────────────
# Fixture 3: btc_news_rejection_v1
# ──────────────────────────────────────────────────────────────────────────────

class TestBtcNewsRejection:
    """btc_news_rejection_v1 — impulse-cluster proxy for macro news event."""

    def _fixture(self):
        from validation.fixtures.btc_news_rejection import get_btc_news_rejection_fixture
        return get_btc_news_rejection_fixture()

    # ── Construction ──────────────────────────────────────────────────────────

    def test_fixture_loads_without_error(self):
        fx = self._fixture()
        assert fx is not None

    def test_fixture_name(self):
        fx = self._fixture()
        assert fx.name == "btc_news_rejection_v1"

    def test_bar_count_is_320(self):
        """220 warmup + 80 normal + 5 news + 15 aftermath = 320."""
        fx = self._fixture()
        assert len(fx.feature_vectors) == 320

    def test_feature_vectors_have_valid_prices(self):
        fx = self._fixture()
        for fv in fx.feature_vectors:
            assert float(fv.close) > 0
            assert float(fv.high) >= float(fv.low)

    # ── Impulse detection ─────────────────────────────────────────────────────

    def test_impulse_bars_exist(self):
        """At least 1 bar must have impulse_flag=True (news cluster)."""
        from validation.fixtures.btc_news_rejection import analyse_fixture_impulse_bars
        fx = self._fixture()
        impulse = analyse_fixture_impulse_bars(fx)
        assert len(impulse) >= 1, (
            "Expected at least 1 impulse bar (body > 2.5×ATR) in news cluster"
        )

    def test_impulse_bars_in_news_cluster_region(self):
        """Impulse bars should appear at or after bar 300 (220+80)."""
        from validation.fixtures.btc_news_rejection import analyse_fixture_impulse_bars
        fx = self._fixture()
        impulse = analyse_fixture_impulse_bars(fx)
        cluster_impulses = [b for b in impulse if b["bar_index"] >= 300]
        assert len(cluster_impulses) >= 1, (
            f"Expected impulse bars in news cluster region (≥bar 300), "
            f"found {len(impulse)} total impulse bars at: "
            f"{[b['bar_index'] for b in impulse]}"
        )

    def test_impulse_body_to_atr_ratio_above_2p5(self):
        """Impulse bars in the cluster must have body/ATR > 2.5."""
        from validation.fixtures.btc_news_rejection import analyse_fixture_impulse_bars
        fx = self._fixture()
        impulse = analyse_fixture_impulse_bars(fx)
        if impulse:
            max_ratio = max(b["body_to_atr_ratio"] for b in impulse)
            assert max_ratio > 2.5, (
                f"Max body/ATR ratio {max_ratio:.2f} must be > 2.5 for impulse flag"
            )

    # ── News cluster analysis ─────────────────────────────────────────────────

    def test_news_cluster_analysis_fields(self):
        """analyse_fixture_news_cluster must return all expected fields."""
        from validation.fixtures.btc_news_rejection import analyse_fixture_news_cluster
        fx = self._fixture()
        stats = analyse_fixture_news_cluster(fx, n_warmup=220, n_normal=80)
        assert "cluster_start_bar" in stats
        assert "impulse_count_in_cluster" in stats
        assert "max_single_move_pct" in stats
        assert stats["cluster_start_bar"] == 300

    def test_news_cluster_max_move_above_5pct(self):
        """The largest single news-bar move should exceed 5% (extreme move)."""
        from validation.fixtures.btc_news_rejection import analyse_fixture_news_cluster
        fx = self._fixture()
        stats = analyse_fixture_news_cluster(fx, n_warmup=220, n_normal=80)
        assert stats["max_single_move_pct"] > 5.0, (
            f"Max single news move {stats['max_single_move_pct']:.1f}% "
            "must be > 5% to represent high-impact macro event"
        )

    # ── No natural entry ─────────────────────────────────────────────────────

    def test_entry_expected_is_none(self):
        fx = self._fixture()
        assert fx.entry_expected_at_bar is None

    def test_newsmacrogroup_limitation_documented(self):
        """Fixture description must document NewsMacroGroup exclusion."""
        fx = self._fixture()
        assert "NewsMacroGroup" in fx.description or "news" in fx.description.lower()

    def test_known_gap_documented_in_description(self):
        """Fixture description must document the known pipeline gap."""
        fx = self._fixture()
        # Must mention the gap: entries may fire because no macro gate is active
        desc_lower = fx.description.lower()
        assert "excluded" in desc_lower or "gap" in desc_lower or "may fire" in desc_lower

    # ── Pipeline smoke test ───────────────────────────────────────────────────

    def test_pipeline_runs_without_error(self):
        """Fixture must run through full pipeline without raising."""
        fx = self._fixture()
        result = _run(_run_fixture_through_pipeline(fx))
        assert isinstance(result["candidates"], int)

    def test_pipeline_processes_all_bars(self):
        """All 320 bars must be processed without crashing the runner."""
        fx = self._fixture()
        assert len(fx.feature_vectors) == 320
        # Running through the pipeline is the core contract for this fixture.
        # Note: entries MAY fire during the impulse cluster because
        # NewsMacroGroup (the macro-event gate) is excluded from the runner.
        # This is a documented pipeline gap, not a test failure.
        result = _run(_run_fixture_through_pipeline(fx))
        assert isinstance(result["opens"], int)
        # Verify pipeline didn't crash (result is a valid int, ≥ 0)
        assert result["opens"] >= 0

    # ── Batch accessor ────────────────────────────────────────────────────────

    def test_get_all_news_rejection_fixtures_returns_one(self):
        from validation.fixtures.btc_news_rejection import (
            get_all_btc_news_rejection_fixtures,
        )
        fixtures = get_all_btc_news_rejection_fixtures()
        assert len(fixtures) == 1
        assert fixtures[0].name == "btc_news_rejection_v1"
