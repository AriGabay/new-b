"""
Unit tests for src/analysis/exit_diagnosis.py.

Coverage:
  1. ranging_score on flat (choppy) vs trending bar data
  2. would_have_won logic for LONG and SHORT directions
  3. CSV output format correctness
  4. ExitDiagnosticsRecorder lifecycle (on_trade_close → on_bar → CSV)
  5. flush_pending / print_summary with no trades
  6. Edge cases: empty bars, zero ATR, missing bar_provider
"""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from analysis.exit_diagnosis import (
    CSV_COLUMNS,
    RANGING_CHOPPY_THRESHOLD,
    ExitDiagnosticsRecorder,
    PendingDiagnosis,
    _append_to_csv,
    _build_record,
    _compute_atr14_from_bars,
    compute_post_close_snapshot,
    compute_ranging_score,
)


# ---------------------------------------------------------------------------
# Minimal bar stub (duck-typed — no OHLCVBar validation rules)
# ---------------------------------------------------------------------------

@dataclass
class _Bar:
    """Minimal bar with the four attributes used by the diagnostics module."""
    timestamp: datetime
    high:      Decimal
    low:       Decimal
    close:     Decimal
    open:      Decimal = Decimal("0")


def _flat_bars(n: int = 72, price: float = 100.0, spread: float = 1.0) -> list[_Bar]:
    """
    n identical flat bars: close=price, high=price+spread/2, low=price-spread/2.
    True range ≈ spread on every bar → ATR14 ≈ spread.
    Price range over all bars ≈ spread  →  ranging_score ≈ 1.0  (<3.0 = choppy).
    """
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    half = Decimal(str(spread / 2))
    p    = Decimal(str(price))
    return [
        _Bar(
            timestamp=base + timedelta(hours=i),
            high=p + half,
            low=p - half,
            close=p,
            open=p,
        )
        for i in range(n)
    ]


def _trending_bars(n: int = 72, start: float = 100.0, step: float = 1.0) -> list[_Bar]:
    """
    n bars trending upward by ``step`` per bar.
    High = close + 0.5, low = open - 0.5.
    True range ≈ step + 1.0 per bar.
    Price range ≈ n * step, ATR14 ≈ step + 1.0.
    ranging_score ≈ n * step / (step + 1.0)  →  >> 3.0 for n=72, step=1.0.
    """
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(n):
        o = Decimal(str(start + i * step))
        c = Decimal(str(start + (i + 1) * step))
        h = c + Decimal("0.5")
        lo = o - Decimal("0.5")
        bars.append(_Bar(timestamp=base + timedelta(hours=i), high=h, low=lo, close=c, open=o))
    return bars


# ---------------------------------------------------------------------------
# 1. ranging_score — flat vs trending
# ---------------------------------------------------------------------------

class TestRangingScore:

    def test_flat_bars_score_is_below_threshold(self):
        """72 flat bars: price range ≈ ATR → score ≈ 1.0 < 3.0 (choppy)."""
        bars = _flat_bars(n=72, price=100.0, spread=2.0)
        score = compute_ranging_score(bars)
        assert score < RANGING_CHOPPY_THRESHOLD, (
            f"Expected flat score < {RANGING_CHOPPY_THRESHOLD}, got {score}"
        )

    def test_trending_bars_score_exceeds_threshold(self):
        """72 trending bars: price range >> ATR → score >> 3.0 (trending)."""
        bars = _trending_bars(n=72, start=100.0, step=1.0)
        score = compute_ranging_score(bars)
        assert score >= RANGING_CHOPPY_THRESHOLD, (
            f"Expected trending score >= {RANGING_CHOPPY_THRESHOLD}, got {score}"
        )

    def test_empty_bars_returns_zero(self):
        assert compute_ranging_score([]) == 0.0

    def test_single_bar_returns_choppy_score(self):
        """One bar: price_range = high-low, ATR14 = high-low → score = 1.0 (choppy)."""
        bars = _flat_bars(n=1)
        score = compute_ranging_score(bars)
        # 1 bar: price_range = spread, ATR14 = spread → score = 1.0 < 3.0
        assert score < RANGING_CHOPPY_THRESHOLD

    def test_score_increases_with_trend_magnitude(self):
        """Steeper trend → higher ranging_score."""
        slow = compute_ranging_score(_trending_bars(n=72, step=0.5))
        fast = compute_ranging_score(_trending_bars(n=72, step=2.0))
        assert fast > slow

    def test_score_is_non_negative(self):
        for spread in [0.5, 1.0, 5.0]:
            score = compute_ranging_score(_flat_bars(n=72, spread=spread))
            assert score >= 0.0, f"Negative score for spread={spread}"


class TestAtr14Computation:

    def test_constant_bars_atr_equals_range(self):
        """Flat bars: TR = high - low on every bar → ATR = spread."""
        bars = _flat_bars(n=20, spread=2.0)
        atr = _compute_atr14_from_bars(bars)
        assert abs(atr - 2.0) < 0.01, f"Expected ATR≈2.0, got {atr}"

    def test_fewer_than_14_bars_uses_available(self):
        """With only 5 bars, ATR is computed from 4 true ranges (ok)."""
        bars = _flat_bars(n=5, spread=4.0)
        atr = _compute_atr14_from_bars(bars)
        assert atr > 0.0

    def test_two_bars_returns_nonzero(self):
        bars = _flat_bars(n=2, spread=3.0)
        atr = _compute_atr14_from_bars(bars)
        assert atr > 0.0


# ---------------------------------------------------------------------------
# 2. compute_post_close_snapshot — would_have_won logic
# ---------------------------------------------------------------------------

class TestPostCloseSnapshot:

    # --- LONG ---
    def test_long_price_rises_would_have_won_true(self):
        snap = compute_post_close_snapshot(
            entry_price=70_000.0, future_price=75_000.0, direction="LONG"
        )
        assert snap["would_have_won"] is True

    def test_long_price_falls_would_have_won_false(self):
        snap = compute_post_close_snapshot(
            entry_price=70_000.0, future_price=65_000.0, direction="LONG"
        )
        assert snap["would_have_won"] is False

    def test_long_price_unchanged_would_have_won_false(self):
        snap = compute_post_close_snapshot(
            entry_price=70_000.0, future_price=70_000.0, direction="LONG"
        )
        assert snap["would_have_won"] is False   # not strictly > entry

    # --- SHORT ---
    def test_short_price_falls_would_have_won_true(self):
        snap = compute_post_close_snapshot(
            entry_price=70_000.0, future_price=65_000.0, direction="SHORT"
        )
        assert snap["would_have_won"] is True

    def test_short_price_rises_would_have_won_false(self):
        snap = compute_post_close_snapshot(
            entry_price=70_000.0, future_price=75_000.0, direction="SHORT"
        )
        assert snap["would_have_won"] is False

    def test_short_price_unchanged_would_have_won_false(self):
        snap = compute_post_close_snapshot(
            entry_price=70_000.0, future_price=70_000.0, direction="SHORT"
        )
        assert snap["would_have_won"] is False

    # --- Case insensitivity ---
    def test_direction_lowercase_accepted(self):
        snap = compute_post_close_snapshot(70_000.0, 75_000.0, "long")
        assert snap["would_have_won"] is True

    # --- pct_from_entry ---
    def test_pct_from_entry_positive_when_price_rises(self):
        snap = compute_post_close_snapshot(100.0, 110.0, "LONG")
        assert abs(snap["pct_from_entry"] - 10.0) < 0.01

    def test_pct_from_entry_negative_when_price_falls(self):
        snap = compute_post_close_snapshot(100.0, 90.0, "LONG")
        assert abs(snap["pct_from_entry"] - (-10.0)) < 0.01

    def test_pct_from_entry_zero_entry_price_returns_zero(self):
        snap = compute_post_close_snapshot(0.0, 100.0, "LONG")
        assert snap["pct_from_entry"] == 0.0

    def test_snapshot_price_field_matches_future_price(self):
        snap = compute_post_close_snapshot(70_000.0, 72_500.0, "LONG")
        assert abs(snap["price"] - 72_500.0) < 0.01


# ---------------------------------------------------------------------------
# 3. CSV output format
# ---------------------------------------------------------------------------

class TestCsvOutputFormat:

    def _make_pending(self, **kwargs) -> PendingDiagnosis:
        defaults = dict(
            trade_id="trade-001",
            direction="LONG",
            entry_price=70_000.0,
            close_price=68_000.0,
            close_reason="time_stop",
            bars_held=120,
            was_time_stopped=True,
            pnl_r=-0.25,
            ranging_score=2.1,
            symbol="BTCUSDT",
            timeframe="1h",
        )
        defaults.update(kwargs)
        return PendingDiagnosis(**defaults)

    def test_build_record_has_all_csv_columns(self):
        pending = self._make_pending()
        record = _build_record(pending)
        for col in CSV_COLUMNS:
            assert col in record, f"Missing column: {col}"

    def test_build_record_missing_snapshots_are_empty_string(self):
        """If a post-close snapshot wasn't collected, cell must be ''."""
        pending = self._make_pending()   # no post_close data
        record = _build_record(pending)
        assert record["post_close_12h_price"] == ""
        assert record["post_close_48h_would_have_won"] == ""

    def test_build_record_filled_snapshot_correct_values(self):
        pending = self._make_pending()
        pending.post_close["48h"] = {
            "price": 72_000.0,
            "pct_from_entry": 2.857,
            "would_have_won": True,
        }
        record = _build_record(pending)
        assert record["post_close_48h_price"] == 72_000.0
        assert abs(record["post_close_48h_pct_from_entry"] - 2.857) < 0.001
        assert record["post_close_48h_would_have_won"] is True

    def test_build_record_was_time_stopped_flag(self):
        pending = self._make_pending(close_reason="time_stop", was_time_stopped=True)
        record = _build_record(pending)
        assert record["was_time_stopped"] is True

    def test_build_record_non_time_stop_flag_false(self):
        pending = self._make_pending(close_reason="stop_loss", was_time_stopped=False)
        record = _build_record(pending)
        assert record["was_time_stopped"] is False

    def test_append_to_csv_creates_file_with_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "diag.csv")
            pending = self._make_pending()
            record = _build_record(pending)
            _append_to_csv(path, record)

            assert os.path.exists(path)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 1
            assert rows[0]["trade_id"] == "trade-001"
            assert rows[0]["close_reason"] == "time_stop"

    def test_append_to_csv_header_columns_match_csv_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "diag.csv")
            pending = self._make_pending()
            record = _build_record(pending)
            _append_to_csv(path, record)

            with open(path, newline="") as f:
                reader = csv.reader(f)
                header = next(reader)

            assert header == CSV_COLUMNS

    def test_append_to_csv_appends_multiple_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "diag.csv")
            for i in range(3):
                pending = self._make_pending(trade_id=f"trade-{i:03d}")
                _append_to_csv(path, _build_record(pending))

            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))

            assert len(rows) == 3
            assert [r["trade_id"] for r in rows] == ["trade-000", "trade-001", "trade-002"]

    def test_append_to_csv_no_duplicate_header_on_append(self):
        """Second call must NOT write another header row."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "diag.csv")
            for i in range(2):
                pending = self._make_pending(trade_id=f"trade-{i:03d}")
                _append_to_csv(path, _build_record(pending))

            with open(path, newline="") as f:
                all_rows = list(csv.reader(f))

            # First row = header, remaining = data rows  (no second header)
            assert all_rows[0] == CSV_COLUMNS
            assert len(all_rows) == 3   # 1 header + 2 data rows

    def test_append_to_csv_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "deep", "diag.csv")
            pending = self._make_pending()
            _append_to_csv(path, _build_record(pending))
            assert os.path.exists(path)


# ---------------------------------------------------------------------------
# 4. ExitDiagnosticsRecorder — lifecycle tests
# ---------------------------------------------------------------------------

def _make_position(
    position_id: str = "pos-001",
    symbol: str = "BTCUSDT",
    direction: str = "long",
    entry_price: float = 70_000.0,
    stop_price: float = 68_000.0,
    opened_at: datetime | None = None,
):
    """Return a minimal mock position object."""
    from core.schemas import Direction, Position
    from decimal import Decimal as D

    dir_enum = Direction.LONG if direction == "long" else Direction.SHORT
    pos = Position(
        position_id=position_id,
        symbol=symbol,
        direction=dir_enum,
        entry_price=D(str(entry_price)),
        stop_price=D(str(stop_price)),
        target_price=D(str(entry_price + 5 * (entry_price - stop_price))),
        position_size_usd=D("70000"),
        r_amount=D("2000"),
    )
    if opened_at is not None:
        object.__setattr__(pos, "opened_at", opened_at) if False else None
        pos.opened_at = opened_at
    return pos


def _make_exit_signal(
    position_id: str = "pos-001",
    exit_reason: str = "time_stop",
    exit_price: float = 70_000.0,
    bars_held: int = 120,
    pnl_r: float = 0.0,
):
    """Return a minimal mock exit signal."""
    from core.schemas import ExitReason, ExitSignal
    from decimal import Decimal as D

    reason_map = {
        "stop_loss":    ExitReason.STOP_LOSS,
        "time_stop":    ExitReason.TIME_STOP,
        "target_reached": ExitReason.TARGET_REACHED,
        "trailing_stop": ExitReason.TRAILING_STOP,
    }
    return ExitSignal(
        position_id=position_id,
        exit_reason=reason_map.get(exit_reason, ExitReason.TIME_STOP),
        exit_price=D(str(exit_price)),
        bars_held=bars_held,
        pnl_usd=D(str(pnl_r * 2000)),
        pnl_r=pnl_r,
    )


def _make_feature_vector(symbol: str, close: float, bars_since_start: int = 0):
    """Minimal FeatureVector for testing on_bar."""
    from core.schemas import FeatureVector
    from decimal import Decimal as D

    ts    = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc) + timedelta(hours=bars_since_start)
    price = D(str(close))
    atr   = D("1000")
    return FeatureVector(
        symbol=symbol, timeframe="1h", timestamp=ts,
        open=price, high=price + atr, low=price - atr, close=price, volume=D("10000"),
        true_range=atr, atr14=atr, atr14_sma20=atr,
        ema20=price, ema50=price, ema200=price, prev_ema20=price, prev_ema50=price,
        rsi14=50.0, prev_rsi14=50.0,
        bb_upper=price + atr, bb_middle=price, bb_lower=price - atr,
        bb_width=atr * 2, bb_width_pct=2.0, adx14=25.0,
        volume_sma20=D("8000"), volume_ratio=1.25,
        candle_body=D("200"), candle_range=D("2000"), body_ratio=0.1,
        upper_shadow=D("900"), lower_shadow=D("900"),
        impulse_flag=False, doji_flag=False,
    )


class TestExitDiagnosticsRecorder:

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.tmpdir, "diag.csv")
        self.recorder = ExitDiagnosticsRecorder(csv_path=self.csv_path)

    # --- on_trade_close / on_bar lifecycle ---

    def test_trade_close_adds_to_pending(self):
        pos = _make_position()
        sig = _make_exit_signal()
        self.recorder.on_trade_close(pos, sig)
        assert "pos-001" in self.recorder._pending

    def test_pending_removed_after_96_bars(self):
        pos = _make_position()
        sig = _make_exit_signal()
        self.recorder.on_trade_close(pos, sig)

        for i in range(96):
            self.recorder.on_bar(_make_feature_vector("BTCUSDT", 70_000.0, i))

        assert "pos-001" not in self.recorder._pending
        assert len(self.recorder._completed) == 1

    def test_csv_written_after_96_bars(self):
        pos = _make_position()
        sig = _make_exit_signal()
        self.recorder.on_trade_close(pos, sig)

        for i in range(96):
            self.recorder.on_bar(_make_feature_vector("BTCUSDT", 70_000.0, i))

        assert os.path.exists(self.csv_path)
        with open(self.csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["trade_id"] == "pos-001"

    def test_snapshots_at_correct_bar_intervals(self):
        """post_close_12h captured at bar 12, post_close_48h at bar 48, etc."""
        pos = _make_position()
        sig = _make_exit_signal()
        self.recorder.on_trade_close(pos, sig)

        price_at = {12: 71_000.0, 24: 72_000.0, 48: 73_000.0, 72: 74_000.0, 96: 75_000.0}
        for i in range(1, 97):
            p = price_at.get(i, 70_000.0)
            self.recorder.on_bar(_make_feature_vector("BTCUSDT", p, i))

        record = self.recorder._completed[0]
        assert abs(record["post_close_12h_price"] - 71_000.0) < 0.01
        assert abs(record["post_close_48h_price"] - 73_000.0) < 0.01
        assert abs(record["post_close_96h_price"] - 75_000.0) < 0.01

    def test_wrong_symbol_bars_ignored(self):
        """Bars for a different symbol must not advance the bar counter."""
        pos = _make_position(symbol="BTCUSDT")
        sig = _make_exit_signal()
        self.recorder.on_trade_close(pos, sig)

        for i in range(96):
            self.recorder.on_bar(_make_feature_vector("ETHUSDT", 70_000.0, i))

        # Pending should still be there — wrong symbol
        assert "pos-001" in self.recorder._pending

    def test_multiple_trades_tracked_independently(self):
        """Two concurrent open trades accumulate snapshots independently."""
        pos1 = _make_position(position_id="pos-001", symbol="BTCUSDT")
        pos2 = _make_position(position_id="pos-002", symbol="BTCUSDT")
        sig1 = _make_exit_signal(position_id="pos-001")
        sig2 = _make_exit_signal(position_id="pos-002")

        self.recorder.on_trade_close(pos1, sig1)
        self.recorder.on_bar(_make_feature_vector("BTCUSDT", 70_000.0, 0))  # 1 bar for pos-1 only
        self.recorder.on_trade_close(pos2, sig2)  # pos-2 starts here

        # Feed 95 more bars
        for i in range(1, 96):
            self.recorder.on_bar(_make_feature_vector("BTCUSDT", 70_000.0, i))

        # pos-1 has 96 bars total → finalised
        assert "pos-001" not in self.recorder._pending
        # pos-2 has 95 bars → still pending
        assert "pos-002" in self.recorder._pending

    def test_was_time_stopped_set_for_time_stop(self):
        pos = _make_position()
        sig = _make_exit_signal(exit_reason="time_stop")
        self.recorder.on_trade_close(pos, sig)
        pending = self.recorder._pending["pos-001"]
        assert pending.was_time_stopped is True

    def test_was_time_stopped_false_for_stop_loss(self):
        pos = _make_position()
        sig = _make_exit_signal(exit_reason="stop_loss")
        self.recorder.on_trade_close(pos, sig)
        pending = self.recorder._pending["pos-001"]
        assert pending.was_time_stopped is False

    # --- flush_pending ---

    def test_flush_pending_writes_incomplete_records(self):
        pos = _make_position()
        sig = _make_exit_signal()
        self.recorder.on_trade_close(pos, sig)

        # Only feed 24 bars (not the full 96)
        for i in range(24):
            self.recorder.on_bar(_make_feature_vector("BTCUSDT", 70_000.0, i))

        self.recorder.flush_pending()

        assert len(self.recorder._pending) == 0
        assert len(self.recorder._completed) == 1

        with open(self.csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        # 12h and 24h should be filled; 48h should be empty
        assert rows[0]["post_close_12h_price"] != ""
        assert rows[0]["post_close_48h_price"] == ""

    def test_flush_pending_when_no_pending_is_noop(self):
        self.recorder.flush_pending()   # should not raise
        assert not os.path.exists(self.csv_path)

    # --- print_summary ---

    def test_print_summary_no_trades_does_not_raise(self, capsys):
        self.recorder.print_summary()
        captured = capsys.readouterr()
        assert "No trades recorded" in captured.out

    def test_print_summary_with_trades(self, capsys):
        """After feeding trades, print_summary must not raise and must print stats."""
        pos = _make_position()
        sig = _make_exit_signal(exit_reason="time_stop", pnl_r=-0.1)
        self.recorder.on_trade_close(pos, sig)
        # Feed 96 bars so it finalises
        for i in range(96):
            self.recorder.on_bar(_make_feature_vector("BTCUSDT", 71_000.0, i))

        self.recorder.print_summary()
        captured = capsys.readouterr()
        assert "Total trades closed" in captured.out
        assert "time_stop" in captured.out or "%" in captured.out

    # --- bar_provider for ranging_score ---

    def test_ranging_score_zero_when_no_provider(self):
        pos = _make_position()
        sig = _make_exit_signal()
        self.recorder.bar_provider = None
        self.recorder.on_trade_close(pos, sig)
        assert self.recorder._pending["pos-001"].ranging_score == 0.0

    def test_ranging_score_computed_when_provider_given(self):
        pos = _make_position(
            opened_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        )
        sig = _make_exit_signal()

        # Provide 100 trending bars all before the opened_at timestamp
        bars = _trending_bars(n=100, start=60_000.0, step=100.0)
        # All bar timestamps are in Jan 2024, which is before June 2024 → all qualify
        self.recorder.bar_provider = lambda sym, tf: bars
        self.recorder.on_trade_close(pos, sig)

        ranging = self.recorder._pending["pos-001"].ranging_score
        assert ranging >= RANGING_CHOPPY_THRESHOLD, (
            f"Expected trending ranging_score >= 3.0, got {ranging}"
        )

    def test_ranging_score_choppy_when_flat_bars(self):
        pos = _make_position(
            opened_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        )
        sig = _make_exit_signal()

        bars = _flat_bars(n=80, price=70_000.0, spread=200.0)
        self.recorder.bar_provider = lambda sym, tf: bars
        self.recorder.on_trade_close(pos, sig)

        ranging = self.recorder._pending["pos-001"].ranging_score
        assert ranging < RANGING_CHOPPY_THRESHOLD, (
            f"Expected choppy ranging_score < 3.0, got {ranging}"
        )

    def test_provider_exception_does_not_crash(self):
        """If bar_provider raises, ranging_score defaults to 0.0 and trade is still registered."""
        pos = _make_position()
        sig = _make_exit_signal()

        def _bad_provider(sym, tf):
            raise RuntimeError("simulated failure")

        self.recorder.bar_provider = _bad_provider
        self.recorder.on_trade_close(pos, sig)

        # Should still be registered with ranging_score=0.0
        assert "pos-001" in self.recorder._pending
        assert self.recorder._pending["pos-001"].ranging_score == 0.0
