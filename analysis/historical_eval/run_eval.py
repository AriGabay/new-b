#!/usr/bin/env python3
"""
ONE-TIME Historical Evaluation: BTCUSDT 2024-01-01 to 2025-12-31
Starting balance: $500

This script:
  1. Downloads 1h BTCUSDT data from Bybit public API (no key needed)
  2. Converts to FeatureVectors via real FeatureComputer (200-bar warmup)
  3. Feeds FeatureVectors through the full RuntimeReplayHarness
     (real 10-group pipeline: Indicators → Candlestick → TechnicalStructure →
      EntryGroup → PanelDecisionGroup → RiskLeverageGroup → ExitGroup)
  4. Extracts trade results from the temporary journal DB
  5. Produces performance report

Not a permanent product feature. One-time research artifact.
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode

# ── Path setup ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

DATA_DIR = SCRIPT_DIR / "data"
CSV_PATH = DATA_DIR / "btcusdt_1h_2024_2025.csv"
RESULTS_PATH = SCRIPT_DIR / "results.json"
REPORT_PATH = SCRIPT_DIR / "report.txt"

# ── Config ──────────────────────────────────────────────────────────────────
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"
INITIAL_EQUITY = Decimal("500")

# Extra warmup bars before 2024-01-01 (FeatureComputer needs 200 bars)
WARMUP_START = datetime(2023, 12, 1, tzinfo=timezone.utc)
EVAL_START   = datetime(2024, 1, 1, tzinfo=timezone.utc)
EVAL_END     = datetime(2025, 12, 31, 23, 0, 0, tzinfo=timezone.utc)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("historical_eval")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Download data from Bybit
# ═══════════════════════════════════════════════════════════════════════════

def download_bybit_klines(
    symbol: str,
    interval: str,
    start_dt: datetime,
    end_dt: datetime,
    csv_path: Path,
) -> int:
    """Download historical klines from Bybit V5 public API and save as CSV."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if csv_path.exists():
        # Count existing rows
        with open(csv_path) as f:
            existing = sum(1 for _ in f) - 1  # minus header
        if existing > 0:
            logger.info("CSV already exists with %d rows: %s", existing, csv_path)
            return existing

    base_url = "https://api.bybit.com/v5/market/kline"
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    limit = 1000

    all_bars = []
    cursor_end = end_ms
    request_count = 0

    logger.info(
        "Downloading %s %s from %s to %s ...",
        symbol, interval, start_dt.date(), end_dt.date(),
    )

    while cursor_end > start_ms:
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "end": cursor_end,
        }
        url = f"{base_url}?{urlencode(params)}"
        request_count += 1

        try:
            req = Request(url, headers={"User-Agent": "historical-eval/1.0"})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            logger.error("Request %d failed: %s", request_count, e)
            if request_count > 3:
                raise
            time.sleep(2)
            continue

        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {data}")

        klines = data["result"]["list"]
        if not klines:
            break

        # Bybit returns newest-first; each item: [ts, open, high, low, close, vol, turnover]
        for k in klines:
            ts_ms = int(k[0])
            if ts_ms < start_ms:
                continue
            all_bars.append(k)

        # Move cursor to before the oldest bar in this batch
        oldest_ts = int(klines[-1][0])
        if oldest_ts <= start_ms:
            break
        cursor_end = oldest_ts - 1

        if request_count % 5 == 0:
            logger.info("  ... %d requests, %d bars collected", request_count, len(all_bars))
        time.sleep(0.15)  # rate limit courtesy

    # Deduplicate by timestamp and sort ascending
    seen = set()
    unique_bars = []
    for b in all_bars:
        ts = int(b[0])
        if ts not in seen:
            seen.add(ts)
            unique_bars.append(b)
    unique_bars.sort(key=lambda x: int(x[0]))

    # Write CSV
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "volume_usd"])
        for b in unique_bars:
            ts = datetime.fromtimestamp(int(b[0]) / 1000, tz=timezone.utc).isoformat()
            writer.writerow([ts, b[1], b[2], b[3], b[4], b[5], b[6]])

    logger.info(
        "Downloaded %d bars in %d requests → %s",
        len(unique_bars), request_count, csv_path,
    )
    return len(unique_bars)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: Load and build FeatureVectors
# ═══════════════════════════════════════════════════════════════════════════

def load_and_build_fvs(csv_path: Path) -> list:
    """Load CSV → OHLCVBars → FeatureVectors using real project infrastructure."""
    from optimization.data_loader import load_csv
    from optimization.featurevector_builder import build_feature_vectors

    result = load_csv(str(csv_path), symbol=SYMBOL, timeframe=TIMEFRAME)
    logger.info(
        "Loaded %d bars: %s to %s (%d warnings)",
        result.bar_count,
        result.first_timestamp,
        result.last_timestamp,
        len(result.warnings),
    )
    if result.warnings:
        for w in result.warnings[:5]:
            logger.warning("  %s", w)

    fvs = build_feature_vectors(result.bars)
    logger.info("Built %d FeatureVectors (200-bar warmup consumed)", len(fvs))

    # Filter to evaluation period only
    eval_fvs = [fv for fv in fvs if fv.timestamp >= EVAL_START]
    logger.info(
        "Evaluation period: %d bars (%s to %s)",
        len(eval_fvs),
        eval_fvs[0].timestamp.date() if eval_fvs else "?",
        eval_fvs[-1].timestamp.date() if eval_fvs else "?",
    )
    return eval_fvs


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: Run through full pipeline
# ═══════════════════════════════════════════════════════════════════════════

async def run_full_pipeline(fvs: list) -> dict:
    """Run FeatureVectors through RuntimeReplayHarness with $500 equity."""
    import tempfile
    import uuid as _uuid
    from runtime.runner import BtcBybitPaperRunner

    tmp_dir = tempfile.mkdtemp(prefix="hist_eval_")
    db_path = os.path.join(tmp_dir, f"eval_{_uuid.uuid4().hex[:8]}.db")

    logger.info("Setting up runner (equity=$%s, db=%s)...", INITIAL_EQUITY, db_path)

    runner = BtcBybitPaperRunner(
        simulation_mode=True,
        journal_db_path=db_path,
    )
    await runner.setup()

    # Seed equity to $500
    runner.state.portfolio.equity = INITIAL_EQUITY
    runner.state.portfolio.available = INITIAL_EQUITY
    runner.state.portfolio.high_water_mark = INITIAL_EQUITY

    logger.info("Running %d bars through full pipeline...", len(fvs))
    start_time = time.time()

    positions_opened = 0
    positions_closed = 0
    last_log_pct = 0

    for i, fv in enumerate(fvs):
        open_before = len(runner.state.portfolio.open_positions)

        await runner.simulate_bar(fv)
        await asyncio.sleep(0)  # let event handlers settle

        open_after = len(runner.state.portfolio.open_positions)
        new_opened = max(0, open_after - open_before)
        new_closed = max(0, open_before - open_after + new_opened)
        positions_opened += new_opened
        positions_closed += new_closed

        # Progress log every 5%
        pct = int((i + 1) / len(fvs) * 100)
        if pct >= last_log_pct + 5:
            last_log_pct = pct
            eq = runner.state.portfolio.equity
            logger.info(
                "  %d%% (%d/%d bars) | equity=$%.2f | open=%d | opened=%d closed=%d",
                pct, i + 1, len(fvs), eq, open_after, positions_opened, positions_closed,
            )

    elapsed = time.time() - start_time
    logger.info("Pipeline complete in %.1fs (%.0f bars/sec)", elapsed, len(fvs) / elapsed)

    # Extract final state
    portfolio = runner.state.portfolio
    final_equity = float(portfolio.equity)
    hwm = float(portfolio.high_water_mark)
    drawdown = portfolio.drawdown_pct
    total_trades = portfolio.total_trades

    # Extract trade details from journal DB
    trades = _extract_trades(db_path)

    await runner.teardown()

    result = {
        "method": "full_pipeline_replay",
        "method_detail": "RuntimeReplayHarness with real 10-group pipeline",
        "eval_start": str(EVAL_START.date()),
        "eval_end": str(EVAL_END.date()),
        "initial_equity": float(INITIAL_EQUITY),
        "final_equity": final_equity,
        "pnl_usd": round(final_equity - float(INITIAL_EQUITY), 2),
        "return_pct": round((final_equity / float(INITIAL_EQUITY) - 1) * 100, 2),
        "total_bars": len(fvs),
        "total_trades": len(trades),
        "positions_opened_runtime": positions_opened,
        "positions_closed_runtime": positions_closed,
        "final_open_positions": len(portfolio.open_positions),
        "high_water_mark": hwm,
        "max_drawdown_pct": round(drawdown * 100, 4),
        "consecutive_losses_at_end": portfolio.consecutive_losses,
        "elapsed_seconds": round(elapsed, 1),
        "db_path": db_path,
        "trades": trades,
    }

    # Compute trade statistics
    if trades:
        wins = [t for t in trades if t["pnl_usd"] > 0]
        losses = [t for t in trades if t["pnl_usd"] <= 0]
        result["winners"] = len(wins)
        result["losers"] = len(losses)
        result["win_rate"] = round(len(wins) / len(trades) * 100, 1) if trades else 0
        result["avg_trade_pnl"] = round(sum(t["pnl_usd"] for t in trades) / len(trades), 2)
        result["avg_winner"] = round(sum(t["pnl_usd"] for t in wins) / len(wins), 2) if wins else 0
        result["avg_loser"] = round(sum(t["pnl_usd"] for t in losses) / len(losses), 2) if losses else 0

        # Longest losing streak
        max_streak = 0
        current_streak = 0
        for t in trades:
            if t["pnl_usd"] <= 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        result["longest_losing_streak"] = max_streak

        # Monthly breakdown
        monthly = {}
        for t in trades:
            opened = t.get("opened_at", "")
            if opened:
                month_key = opened[:7]  # YYYY-MM
                if month_key not in monthly:
                    monthly[month_key] = {"trades": 0, "pnl": 0.0, "wins": 0, "losses": 0}
                monthly[month_key]["trades"] += 1
                monthly[month_key]["pnl"] = round(monthly[month_key]["pnl"] + t["pnl_usd"], 2)
                if t["pnl_usd"] > 0:
                    monthly[month_key]["wins"] += 1
                else:
                    monthly[month_key]["losses"] += 1
        result["monthly_breakdown"] = dict(sorted(monthly.items()))
    else:
        result["winners"] = 0
        result["losers"] = 0
        result["win_rate"] = 0
        result["avg_trade_pnl"] = 0
        result["avg_winner"] = 0
        result["avg_loser"] = 0
        result["longest_losing_streak"] = 0
        result["monthly_breakdown"] = {}

    return result


def _extract_trades(db_path: str) -> list[dict]:
    """Read closed trades from the journal DB."""
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Check if trades table exists
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "trades" not in tables:
            return []

        rows = conn.execute(
            "SELECT * FROM trades WHERE closed_at IS NOT NULL ORDER BY opened_at"
        ).fetchall()

        trades = []
        for row in rows:
            d = dict(row)
            pnl = d.get("pnl_usd") or d.get("realized_pnl") or 0
            trades.append({
                "trade_id": d.get("trade_id", ""),
                "symbol": d.get("symbol", ""),
                "direction": d.get("direction", ""),
                "entry_price": float(d.get("entry_price", 0)),
                "exit_price": float(d.get("exit_price", 0)),
                "stop_price": float(d.get("stop_price", 0)),
                "target_price": float(d.get("target_price", 0)),
                "position_size_usd": float(d.get("position_size_usd", 0)),
                "pnl_usd": float(pnl),
                "pnl_r": float(d.get("pnl_r", 0)),
                "outcome": d.get("outcome", ""),
                "exit_reason": d.get("exit_reason", ""),
                "opened_at": d.get("opened_at", ""),
                "closed_at": d.get("closed_at", ""),
                "bars_held": int(d.get("bars_held", 0)),
            })
        return trades
    except Exception as e:
        logger.error("Error extracting trades: %s", e)
        return []
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Generate report
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(result: dict) -> str:
    """Generate human-readable performance report."""
    lines = []
    lines.append("=" * 72)
    lines.append("  BTCUSDT HISTORICAL EVALUATION REPORT")
    lines.append("  Period: 2024-01-01 to 2025-12-31 | Timeframe: 1h")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"  Method:            {result['method_detail']}")
    lines.append(f"  Total bars:        {result['total_bars']:,}")
    lines.append(f"  Elapsed:           {result['elapsed_seconds']}s")
    lines.append("")
    lines.append("─" * 72)
    lines.append("  ACCOUNT PERFORMANCE")
    lines.append("─" * 72)
    lines.append(f"  Starting Balance:  ${result['initial_equity']:,.2f}")
    lines.append(f"  Ending Balance:    ${result['final_equity']:,.2f}")
    lines.append(f"  Net P&L:           ${result['pnl_usd']:,.2f}")
    lines.append(f"  Return:            {result['return_pct']:.2f}%")
    lines.append(f"  High Water Mark:   ${result['high_water_mark']:,.2f}")
    lines.append(f"  Max Drawdown:      {result['max_drawdown_pct']:.2f}%")
    lines.append("")
    lines.append("─" * 72)
    lines.append("  TRADE STATISTICS")
    lines.append("─" * 72)
    lines.append(f"  Total Trades:      {result['total_trades']}")
    lines.append(f"  Winners:           {result['winners']}")
    lines.append(f"  Losers:            {result['losers']}")
    lines.append(f"  Win Rate:          {result['win_rate']:.1f}%")
    lines.append(f"  Avg Trade P&L:     ${result['avg_trade_pnl']:,.2f}")
    lines.append(f"  Avg Winner:        ${result['avg_winner']:,.2f}")
    lines.append(f"  Avg Loser:         ${result['avg_loser']:,.2f}")
    lines.append(f"  Longest Losing:    {result['longest_losing_streak']} streak")
    lines.append(f"  Open at End:       {result['final_open_positions']}")
    lines.append("")

    monthly = result.get("monthly_breakdown", {})
    if monthly:
        lines.append("─" * 72)
        lines.append("  MONTHLY BREAKDOWN")
        lines.append("─" * 72)
        lines.append(f"  {'Month':<12} {'Trades':>8} {'Wins':>6} {'Losses':>8} {'P&L ($)':>12}")
        lines.append(f"  {'─'*12} {'─'*8} {'─'*6} {'─'*8} {'─'*12}")
        for month, stats in monthly.items():
            lines.append(
                f"  {month:<12} {stats['trades']:>8} {stats['wins']:>6} "
                f"{stats['losses']:>8} {stats['pnl']:>12,.2f}"
            )
        lines.append("")

    lines.append("─" * 72)
    lines.append("  METHODOLOGY NOTES")
    lines.append("─" * 72)
    lines.append("  - Full 10-group event-driven pipeline (not simplified backtest)")
    lines.append("  - Real 20-trader panel evaluation with 14/20 consensus threshold")
    lines.append("  - Real 9-rule risk gate (RiskLeverageGroup)")
    lines.append("  - Real exit logic (ExitGroup: stop/target/time exits)")
    lines.append("  - 200-bar warmup for indicator computation (FeatureComputer)")
    lines.append("  - No forced approvals, no look-ahead, no curve fitting")
    lines.append("  - Position sizing: 1% risk per trade, max 3x leverage")
    lines.append(f"  - Data source: Bybit V5 public API (BTCUSDT perpetual, 1h)")
    lines.append("")
    lines.append("=" * 72)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    logger.info("=" * 60)
    logger.info("BTCUSDT Historical Evaluation: 2024-01-01 to 2025-12-31")
    logger.info("Starting balance: $%s | Timeframe: %s", INITIAL_EQUITY, TIMEFRAME)
    logger.info("=" * 60)

    # Phase 1: Download data
    bar_count = download_bybit_klines(
        symbol=SYMBOL,
        interval="60",  # Bybit uses "60" for 1h
        start_dt=WARMUP_START,
        end_dt=EVAL_END,
        csv_path=CSV_PATH,
    )
    logger.info("Data ready: %d bars", bar_count)

    # Phase 2: Load and build FeatureVectors
    fvs = load_and_build_fvs(CSV_PATH)
    if not fvs:
        logger.error("No FeatureVectors built. Aborting.")
        return

    # Phase 3: Run full pipeline
    result = await run_full_pipeline(fvs)

    # Phase 4: Save results
    with open(RESULTS_PATH, "w") as f:
        # Exclude full trade list from JSON for readability
        save_result = {k: v for k, v in result.items() if k != "trades"}
        save_result["trade_count_detail"] = len(result.get("trades", []))
        json.dump(save_result, f, indent=2, default=str)

    report = generate_report(result)
    with open(REPORT_PATH, "w") as f:
        f.write(report)

    print("\n")
    print(report)
    print(f"\nResults saved to: {RESULTS_PATH}")
    print(f"Report saved to:  {REPORT_PATH}")
    print(f"Journal DB:       {result.get('db_path', '?')}")


if __name__ == "__main__":
    asyncio.run(main())
