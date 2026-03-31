"""
BacktestLearningDB: manages the evaluator_performance table and provides
summary queries for the persistent backtest training-data store.

The trades, signals, mdp_transitions, setup_packets, trader_reviews,
panel_summaries, final_decisions tables are all handled by JournalDB +
JournalExtension on the same SQLite connection.  This class only adds the
evaluator_performance table (new, not present in those schemas) and exposes
the cross-table summary query needed by run_backtest.py.

Written to: data/backtest_learning.db  (NEVER data/journal.db)
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BACKTEST_LEARNING_DB_PATH = "data/backtest_learning.db"


class BacktestLearningDB:
    """
    Attaches the evaluator_performance table to an existing SQLite connection
    (shared with JournalDB / JournalExtension in the runner).

    Usage (from engine.py, after runner.setup()):
        journal_db = runner._performance_journal._journal_db
        learning_db = BacktestLearningDB(journal_db._conn)
        learning_db.create_evaluator_performance_table()
        # … set verdict_sink, subscribe to events …
        learning_db.insert_evaluator_verdicts(…)
        learning_db.update_evaluator_outcomes(…)

    Standalone queries (from run_backtest.py):
        learning_db = BacktestLearningDB.from_path("data/backtest_learning.db")
        summary = learning_db.get_summary()
        learning_db.close()
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._owns_conn = False  # True only when opened via from_path()

    @classmethod
    def from_path(cls, db_path: str) -> "BacktestLearningDB":
        """Open an existing DB file for standalone summary queries."""
        path = Path(db_path)
        if not path.exists():
            raise FileNotFoundError(f"Learning DB not found: {db_path}")
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        obj = cls(conn)
        obj._owns_conn = True
        return obj

    def create_evaluator_performance_table(self) -> None:
        """Create evaluator_performance table if not exists."""
        try:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluator_performance (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluator_name  TEXT NOT NULL,
                    trade_id        TEXT,
                    verdict         TEXT NOT NULL,
                    evaluator_score REAL,
                    direction       TEXT NOT NULL,
                    regime          TEXT NOT NULL,
                    volatility      TEXT NOT NULL,
                    outcome         TEXT,
                    pnl_r           REAL,
                    opened_at       TEXT NOT NULL,
                    closed_at       TEXT,
                    UNIQUE(evaluator_name, trade_id)
                )
            """)
            self._conn.commit()
            logger.info("BacktestLearningDB: evaluator_performance table ready")
        except Exception as exc:
            logger.error("create_evaluator_performance_table failed: %s", exc)

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def insert_evaluator_verdicts(
        self,
        verdicts: list,
        trade_id: str,
        direction: str,
        regime: str,
        volatility: str,
        opened_at: str,
    ) -> None:
        """Write one row per evaluator verdict for a specific trade.

        Called when a PositionOpenEvent fires so that trade_id is already
        known.  The verdicts were captured earlier at panel evaluation time
        and buffered in _pending_verdicts keyed by packet_id.
        """
        if not verdicts or self._conn is None:
            return
        try:
            for v in verdicts:
                # TraderVerdict uses trader_id; fall back to trader_name then repr
                name = (
                    getattr(v, "trader_id", None)
                    or getattr(v, "trader_name", None)
                    or str(v)
                )
                vote = getattr(v, "vote", "")
                score = float(getattr(v, "score", 0.0) or 0.0)
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO evaluator_performance
                    (evaluator_name, trade_id, verdict, evaluator_score,
                     direction, regime, volatility, opened_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, trade_id, vote, score,
                     direction, regime, volatility, opened_at),
                )
            self._conn.commit()
            logger.debug(
                "BacktestLearningDB: wrote %d evaluator verdicts for trade %s",
                len(verdicts),
                (trade_id[:8] if trade_id else "None"),
            )
        except Exception as exc:
            logger.error("insert_evaluator_verdicts failed: %s", exc)

    def update_evaluator_outcomes(
        self,
        trade_id: str,
        outcome: str,
        pnl_r: float,
        closed_at: str,
    ) -> None:
        """Backfill outcome + pnl_r into evaluator_performance rows on close."""
        if self._conn is None or not trade_id:
            return
        try:
            self._conn.execute(
                """
                UPDATE evaluator_performance
                SET outcome = ?, pnl_r = ?, closed_at = ?
                WHERE trade_id = ?
                """,
                (outcome, pnl_r, closed_at, trade_id),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("update_evaluator_outcomes failed: %s", exc)

    def close(self) -> None:
        """Close connection (only if we own it, i.e. opened via from_path)."""
        if self._conn and self._owns_conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Summary queries (Task 4 — called from run_backtest.py after the run)
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        """Return counts and per-evaluator approval stats from the learning DB."""
        if self._conn is None:
            return {}
        try:
            self._conn.row_factory = sqlite3.Row
            cur = self._conn.cursor()

            # Which tables exist?
            tables = {
                r[0]
                for r in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            n_trades = 0
            if "trades" in tables:
                n_trades = cur.execute(
                    "SELECT COUNT(*) FROM trades WHERE closed_at IS NOT NULL"
                ).fetchone()[0]

            n_mdp = 0
            if "mdp_transitions" in tables:
                n_mdp = cur.execute(
                    "SELECT COUNT(*) FROM mdp_transitions"
                ).fetchone()[0]

            n_verdicts = 0
            n_unique = 0
            evaluator_stats: list[dict] = []

            if "evaluator_performance" in tables:
                n_verdicts = cur.execute(
                    "SELECT COUNT(*) FROM evaluator_performance"
                ).fetchone()[0]
                n_unique = cur.execute(
                    "SELECT COUNT(DISTINCT evaluator_name) FROM evaluator_performance"
                ).fetchone()[0]
                rows = cur.execute(
                    """
                    SELECT
                        evaluator_name,
                        COUNT(*)                                              AS approvals,
                        SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END)        AS wins
                    FROM evaluator_performance
                    WHERE verdict = 'approve'
                      AND outcome IS NOT NULL
                    GROUP BY evaluator_name
                    ORDER BY
                        CAST(SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END)
                             AS REAL) / MAX(COUNT(*), 1) DESC
                    """
                ).fetchall()
                evaluator_stats = [dict(r) for r in rows]

            return {
                "n_trades":        n_trades,
                "n_mdp":           n_mdp,
                "n_verdicts":      n_verdicts,
                "n_unique":        n_unique,
                "evaluator_stats": evaluator_stats,
            }
        except Exception as exc:
            logger.error("get_summary failed: %s", exc)
            return {}
