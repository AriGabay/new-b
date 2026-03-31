"""
reset_learning_data.py — Wipe all learned data and CSV outputs.

Clears all 14 learning/journal tables and removes 5 CSV files so the
system starts from a clean baseline at the sweep-optimal configuration:
  T=15 all regimes, Rail6=16.

Usage:
  python -m scripts.reset_learning_data
  # or from repo root:
  python src/scripts/reset_learning_data.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (relative to project root — script can be run from either src/ or /)
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
# Support running from src/ or from project root
_SRC = _HERE.parent.parent          # .../new-b/src
_ROOT = _SRC.parent                 # .../new-b

_DB_CANDIDATES = [
    _ROOT / "data" / "journal.db",
    _SRC  / "data" / "journal.db",
]

_TABLES = [
    "trades",
    "signals",
    "journal_events",
    "mdp_transitions",
    "setup_packets",
    "trader_reviews",
    "panel_summaries",
    "final_decisions",
    "outcome_attributions",
    "calibration_records",
    "trader_calibration",
    "setup_family_records",
    "specialist_group_records",
    "learning_recommendations",
]

_CSV_FILES = [
    _ROOT / "analysis" / "backtest_trades.csv",
    _ROOT / "analysis" / "backtest_trades_no_ts.csv",
    _ROOT / "data"     / "horizon_log.csv",
    _ROOT / "data"     / "exit_diagnosis.csv",
    _SRC  / "data"     / "exit_diagnosis.csv",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_db(db_path: Path) -> dict[str, int]:
    """DELETE FROM each known table; skip silently if table doesn't exist."""
    counts: dict[str, int] = {}
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        existing = {
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in _TABLES:
            if table not in existing:
                counts[table] = -1          # -1 = skipped (table not found)
                continue
            cur.execute(f"DELETE FROM {table}")
            counts[table] = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return counts


def _delete_csv(path: Path) -> bool:
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print()
    print("━" * 60)
    print("  RESET LEARNING DATA")
    print("━" * 60)
    print()
    print("  This will permanently delete:")
    print("  • All rows in 14 learning / journal tables")
    print("  • 5 CSV output files (trades, exit_diagnosis …)")
    print()

    answer = input("  Type 'yes' to confirm: ").strip().lower()
    if answer != "yes":
        print()
        print("  Aborted — nothing was changed.")
        sys.exit(0)

    print()

    # -----------------------------------------------------------------------
    # Clear DB tables
    # -----------------------------------------------------------------------
    cleared_any_db = False
    for db_path in _DB_CANDIDATES:
        if not db_path.exists():
            continue
        cleared_any_db = True
        print(f"  DB: {db_path}")
        counts = _clear_db(db_path)
        for table, n in counts.items():
            if n == -1:
                print(f"    {table:<35} (table not found — skipped)")
            else:
                print(f"    {table:<35} {n:>6} rows deleted")
        print()

    if not cleared_any_db:
        print("  (No journal.db found — nothing to clear)")
        print()

    # -----------------------------------------------------------------------
    # Delete CSV files
    # -----------------------------------------------------------------------
    print("  CSV files:")
    for csv_path in _CSV_FILES:
        if _delete_csv(csv_path):
            print(f"    ✓ deleted  {csv_path}")
        else:
            print(f"    –  (not found) {csv_path}")

    print()
    print("━" * 60)
    print("  ✓ Clean slate ready.")
    print("    Optimal config: T=15 all regimes, Rail6=16")
    print("    Next: run backtest to verify, then start shadow mode")
    print("━" * 60)
    print()


if __name__ == "__main__":
    main()
