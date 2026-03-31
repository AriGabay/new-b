"""
Exit Diagnostics — post-trade analysis module.

Records a diagnostic snapshot for every closed trade and writes it to
data/exit_diagnosis.csv (append mode, created on first write).

Two diagnostic questions:
  1. Impatience check:  did price move our way AFTER we were time-stopped?
     → post_close snapshots at 12h / 24h / 48h / 72h / 96h after close.
  2. Market regime check: were we entering a choppy/ranging market?
     → ranging_score = (highest_high − lowest_low) / ATR14
       over the 72 bars immediately BEFORE entry.
       score < 3.0 = market barely moved 3 ATRs over 3 days = choppy.

Usage
-----
Recorder is created by the runner and injected into PerformanceJournalGroup:

    recorder = ExitDiagnosticsRecorder()
    recorder.bar_provider = lambda sym, tf: mdg.get_bar_history(sym, tf)
    perf_journal._exit_diagnostics = recorder

PerformanceJournalGroup then calls:
    recorder.on_trade_close(position, exit_signal)   — on every PositionCloseEvent
    recorder.on_bar(features)                         — on every FeatureReadyEvent
    recorder.flush_pending()                          — at teardown (writes stragglers)
    recorder.print_summary()                          — at teardown (prints stats)
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RANGING_BARS: int = 72                   # bars to look back at entry time
RANGING_CHOPPY_THRESHOLD: float = 3.0   # score < this → choppy/ranging market

# Post-close snapshot bar counts (1H timeframe → hours)
POST_CLOSE_INTERVALS: list[int] = [12, 24, 48, 72, 96]

# Flat CSV column order
CSV_COLUMNS: list[str] = [
    "trade_id", "direction", "entry_price", "close_price", "close_reason",
    "bars_held", "was_time_stopped", "pnl_r",
    "post_close_12h_price", "post_close_12h_pct_from_entry", "post_close_12h_would_have_won",
    "post_close_24h_price", "post_close_24h_pct_from_entry", "post_close_24h_would_have_won",
    "post_close_48h_price", "post_close_48h_pct_from_entry", "post_close_48h_would_have_won",
    "post_close_72h_price", "post_close_72h_pct_from_entry", "post_close_72h_would_have_won",
    "post_close_96h_price", "post_close_96h_pct_from_entry", "post_close_96h_would_have_won",
    "ranging_score",
]


# ---------------------------------------------------------------------------
# Pure functions — all testable without any external state
# ---------------------------------------------------------------------------

def _compute_atr14_from_bars(bars: list) -> float:
    """
    Approximate ATR14 from a list of bar-like objects (with .high, .low, .close).

    Uses a simple rolling-14 average of true ranges (SMA seed — matches
    the initial ATR computation in FeatureComputer).  Returns 0.0 if fewer
    than 2 bars are provided.
    """
    if len(bars) < 2:
        return float(bars[-1].high - bars[-1].low) if bars else 0.0

    true_ranges: list[float] = []
    for i in range(1, len(bars)):
        hl  = float(bars[i].high  - bars[i].low)
        hpc = abs(float(bars[i].high) - float(bars[i - 1].close))
        lpc = abs(float(bars[i].low)  - float(bars[i - 1].close))
        true_ranges.append(max(hl, hpc, lpc))

    # Use last 14 true-range values
    window = true_ranges[-14:] if len(true_ranges) >= 14 else true_ranges
    return sum(window) / len(window) if window else 0.0


def compute_ranging_score(bars: list) -> float:
    """
    Compute market regime score for the given bars.

    ranging_score = (highest_high − lowest_low) / ATR14

    A score below RANGING_CHOPPY_THRESHOLD (3.0) indicates the market moved
    less than 3 average ranges over the entire window — i.e. it was choppy
    and not trending.

    Args:
        bars: List of bar-like objects with .high, .low, .close (Decimal or float).
              Typically the 72 bars immediately before the entry.

    Returns:
        Float ranging score, or 0.0 if bars is empty.
    """
    if not bars:
        return 0.0

    highs = [float(b.high) for b in bars]
    lows  = [float(b.low)  for b in bars]

    price_range = max(highs) - min(lows)
    atr14 = _compute_atr14_from_bars(bars)

    if atr14 <= 0.0:
        return 0.0

    return round(price_range / atr14, 4)


def compute_post_close_snapshot(
    entry_price: float,
    future_price: float,
    direction: str,
) -> dict:
    """
    Build a single post-close snapshot dict.

    Args:
        entry_price:  The original trade entry price.
        future_price: The bar's close price N hours after the trade closed.
        direction:    "LONG" or "SHORT" (case-insensitive).

    Returns:
        {
            "price": float,
            "pct_from_entry": float,   # % move from entry (sign = price direction)
            "would_have_won": bool,    # True if holding the original direction was profitable
        }
    """
    pct_from_entry = (
        round((future_price - entry_price) / entry_price * 100.0, 4)
        if entry_price > 0.0
        else 0.0
    )

    dir_upper = direction.upper()
    if dir_upper == "LONG":
        would_have_won = future_price > entry_price
    else:  # SHORT
        would_have_won = future_price < entry_price

    return {
        "price": round(future_price, 2),
        "pct_from_entry": pct_from_entry,
        "would_have_won": would_have_won,
    }


# ---------------------------------------------------------------------------
# Pending record dataclass
# ---------------------------------------------------------------------------

@dataclass
class PendingDiagnosis:
    """Accumulates data for one trade until all post-close snapshots are filled."""
    trade_id:         str
    direction:        str       # "LONG" or "SHORT"
    entry_price:      float
    close_price:      float
    close_reason:     str
    bars_held:        int
    was_time_stopped: bool
    pnl_r:            float
    ranging_score:    float
    symbol:           str
    timeframe:        str
    # Filled incrementally; key = "12h" / "24h" / "48h" / "72h" / "96h"
    post_close:       dict = field(default_factory=dict)
    bars_after_close: int = 0


# ---------------------------------------------------------------------------
# Record builder and CSV writer
# ---------------------------------------------------------------------------

def _build_record(pending: PendingDiagnosis) -> dict:
    """Flatten a PendingDiagnosis into a CSV-ready flat dict."""
    record: dict[str, Any] = {
        "trade_id":        pending.trade_id,
        "direction":       pending.direction,
        "entry_price":     pending.entry_price,
        "close_price":     pending.close_price,
        "close_reason":    pending.close_reason,
        "bars_held":       pending.bars_held,
        "was_time_stopped": pending.was_time_stopped,
        "pnl_r":           round(pending.pnl_r, 4),
        "ranging_score":   pending.ranging_score,
    }
    for n in POST_CLOSE_INTERVALS:
        label = f"{n}h"
        snap  = pending.post_close.get(label)
        if snap is not None:
            record[f"post_close_{label}_price"]          = snap["price"]
            record[f"post_close_{label}_pct_from_entry"] = snap["pct_from_entry"]
            record[f"post_close_{label}_would_have_won"] = snap["would_have_won"]
        else:
            record[f"post_close_{label}_price"]          = ""
            record[f"post_close_{label}_pct_from_entry"] = ""
            record[f"post_close_{label}_would_have_won"] = ""
    return record


def _append_to_csv(csv_path: str, record: dict) -> None:
    """Append one record to the CSV; writes the header row on first write."""
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    write_header = (not path.exists()) or path.stat().st_size == 0

    try:
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=CSV_COLUMNS,
                extrasaction="ignore",  # tolerate any extra keys in record
            )
            if write_header:
                writer.writeheader()
            writer.writerow(record)
    except Exception as exc:
        logger.error("ExitDiagnostics: failed to write CSV: %s", exc)


# ---------------------------------------------------------------------------
# Timezone helper
# ---------------------------------------------------------------------------

def _naive_dt(dt: datetime) -> datetime:
    """Strip timezone info so naive and aware datetimes can be compared."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


# ---------------------------------------------------------------------------
# Main recorder class
# ---------------------------------------------------------------------------

class ExitDiagnosticsRecorder:
    """
    Accumulates per-trade diagnostic data and writes to CSV.

    Lifecycle
    ---------
    1. Injected with ``bar_provider`` (callable) by the runner at startup.
    2. ``on_trade_close()`` is called by PerformanceJournalGroup every time
       a PositionCloseEvent fires.  It computes ranging_score from pre-entry
       bars and registers a PendingDiagnosis.
    3. ``on_bar()`` is called on every FeatureReadyEvent.  It increments the
       post-close bar counter and fills in snapshot data at each checkpoint
       (12h / 24h / 48h / 72h / 96h).  When the 96h snapshot is recorded
       the record is finalised and written to CSV.
    4. ``flush_pending()`` is called at teardown to write any records that
       haven't yet received all five snapshots (e.g. short backtests).
    5. ``print_summary()`` prints a human-readable summary table.
    """

    def __init__(self, csv_path: str = "data/exit_diagnosis.csv") -> None:
        self._csv_path = csv_path
        self._pending:   dict[str, PendingDiagnosis] = {}
        self._completed: list[dict] = []

        # Injectable: (symbol: str, timeframe: str) -> list[OHLCVBar | bar-like]
        # Returns bars in chronological order (oldest first).
        # Default None = ranging_score computation is skipped.
        self.bar_provider: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def on_trade_close(self, position: Any, exit_signal: Any) -> None:
        """
        Register a closed trade for diagnostic tracking.

        Computes ranging_score from the 72 bars before entry if
        ``bar_provider`` is wired; otherwise ranging_score = 0.0.

        Args:
            position:    core.schemas.Position instance.
            exit_signal: core.schemas.ExitSignal instance.
        """
        try:
            self._register_close(position, exit_signal)
        except Exception as exc:
            logger.warning("ExitDiagnosticsRecorder.on_trade_close failed: %s", exc)

    def on_bar(self, features: Any) -> None:
        """
        Called on every FeatureReadyEvent bar.  Fills post-close snapshots
        for pending trades matching this symbol/timeframe.

        When all five snapshots are collected the record is finalised and
        written to CSV immediately (no need to wait for flush_pending).
        """
        try:
            self._process_bar(features)
        except Exception as exc:
            logger.warning("ExitDiagnosticsRecorder.on_bar failed: %s", exc)

    def flush_pending(self) -> None:
        """
        Write all incomplete pending records to CSV.
        Called at teardown to capture trades that closed near the end of
        the backtest window before all 5 post-close snapshots could be filled.
        """
        for pending in list(self._pending.values()):
            record = _build_record(pending)
            self._completed.append(record)
            _append_to_csv(self._csv_path, record)
        self._pending.clear()
        if self._completed:
            logger.info(
                "ExitDiagnosticsRecorder: flushed %d pending records to %s",
                len(self._completed), self._csv_path,
            )

    def print_summary(self) -> None:
        """Print a human-readable end-of-backtest summary to stdout."""
        records = self._completed
        total = len(records)

        print("\n" + "=" * 45)
        print("       EXIT DIAGNOSTICS SUMMARY")
        print("=" * 45)

        if total == 0:
            print("  No trades recorded.")
            print("=" * 45 + "\n")
            return

        time_stopped = sum(1 for r in records if r.get("was_time_stopped") is True)
        time_stop_pct = time_stopped / total * 100.0

        # % of time-stopped trades where holding 48h would have been profitable
        ts_favourable_48h = 0
        if time_stopped > 0:
            ts_favourable_48h = sum(
                1 for r in records
                if r.get("was_time_stopped") is True
                and r.get("post_close_48h_would_have_won") is True
            )
        ts_fav_48h_pct = ts_favourable_48h / time_stopped * 100.0 if time_stopped else 0.0

        # % with ranging_score < RANGING_CHOPPY_THRESHOLD
        valid_scores = [
            r["ranging_score"] for r in records
            if isinstance(r.get("ranging_score"), (int, float))
            and r["ranging_score"] > 0.0
        ]
        choppy_pct = (
            sum(1 for s in valid_scores if s < RANGING_CHOPPY_THRESHOLD)
            / len(valid_scores) * 100.0
            if valid_scores
            else 0.0
        )

        avg_bars = sum(r.get("bars_held", 0) for r in records) / total

        print(f"  Total trades closed:                {total}")
        print(f"  % closed by time_stop:              {time_stop_pct:5.1f}%")
        print(
            f"  % time-stopped → favourable 48h:    {ts_fav_48h_pct:5.1f}%"
            "  ← impatience check"
        )
        print(
            f"  % entries with ranging_score < 3.0: {choppy_pct:5.1f}%"
            "  ← choppy-market check"
        )
        print(f"  Average bars_held:                  {avg_bars:5.1f}")
        print("=" * 45 + "\n")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_close(self, position: Any, exit_signal: Any) -> None:
        """Build and store a PendingDiagnosis from the closed position."""
        direction = (
            position.direction.value.upper()
            if hasattr(position.direction, "value")
            else str(position.direction).upper()
        )
        close_reason = (
            exit_signal.exit_reason.value
            if hasattr(exit_signal.exit_reason, "value")
            else str(exit_signal.exit_reason)
        )
        timeframe = getattr(position, "timeframe", "1h") or "1h"

        ranging_score = self._compute_ranging(position, timeframe)

        pending = PendingDiagnosis(
            trade_id=position.position_id,
            direction=direction,
            entry_price=float(position.entry_price),
            close_price=float(exit_signal.exit_price),
            close_reason=close_reason,
            bars_held=exit_signal.bars_held,
            was_time_stopped=(close_reason == "time_stop"),
            pnl_r=float(exit_signal.pnl_r),
            ranging_score=ranging_score,
            symbol=position.symbol,
            timeframe=timeframe,
        )
        self._pending[position.position_id] = pending
        logger.debug(
            "ExitDiagnosticsRecorder: registered %s (%s) ranging_score=%.2f",
            position.position_id, close_reason, ranging_score,
        )

    def _compute_ranging(self, position: Any, timeframe: str) -> float:
        """Return ranging_score; 0.0 if bar_provider is None or lookup fails."""
        if self.bar_provider is None:
            return 0.0
        try:
            all_bars = self.bar_provider(position.symbol, timeframe)
            if not all_bars:
                return 0.0
            # Keep only bars whose open time is strictly before the entry time.
            # Handles both timezone-aware and naive datetimes.
            entry_dt = _naive_dt(position.opened_at)
            pre_bars = [
                b for b in all_bars
                if _naive_dt(b.timestamp) < entry_dt
            ][-RANGING_BARS:]
            return compute_ranging_score(pre_bars)
        except Exception as exc:
            logger.warning("ExitDiagnosticsRecorder: ranging_score lookup failed: %s", exc)
            return 0.0

    def _process_bar(self, features: Any) -> None:
        """Increment bar counter for matching pending trades; fill snapshots."""
        completed_ids: list[str] = []

        for trade_id, pending in self._pending.items():
            if pending.symbol != features.symbol:
                continue

            pending.bars_after_close += 1
            n = pending.bars_after_close

            if n in POST_CLOSE_INTERVALS:
                label = f"{n}h"
                pending.post_close[label] = compute_post_close_snapshot(
                    entry_price=pending.entry_price,
                    future_price=float(features.close),
                    direction=pending.direction,
                )
                logger.debug(
                    "ExitDiagnosticsRecorder: %s post_close_%s price=%.2f "
                    "would_have_won=%s",
                    trade_id, label,
                    pending.post_close[label]["price"],
                    pending.post_close[label]["would_have_won"],
                )

            # Finalise once last snapshot is captured
            if pending.bars_after_close >= POST_CLOSE_INTERVALS[-1]:
                record = _build_record(pending)
                self._completed.append(record)
                _append_to_csv(self._csv_path, record)
                completed_ids.append(trade_id)
                logger.info(
                    "ExitDiagnosticsRecorder: finalised trade %s → %s",
                    trade_id, self._csv_path,
                )

        for tid in completed_ids:
            del self._pending[tid]
