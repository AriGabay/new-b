"""
JournalReader: read-only access to the trading journal SQLite database.

Opens the DB in read-only WAL mode so the console never interferes
with ongoing writes from the runner.

Supports both the base JournalDB tables and the JournalExtension
learning-layer tables (if present).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "src/data/journal.db"


class JournalReader:
    """
    Read-only SQLite interface for the management console.
    Opens in WAL mode — safe for concurrent reader while runner writes.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> bool:
        """Open connection. Returns True on success."""
        if not self._db_path.exists():
            logger.warning("JournalReader: DB not found at %s", self._db_path)
            return False
        try:
            self._conn = sqlite3.connect(
                f"file:{self._db_path}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            logger.info("JournalReader: connected to %s", self._db_path)
            return True
        except Exception as e:
            logger.warning("JournalReader: cannot open read-only, trying normal: %s", e)
            try:
                self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                logger.info("JournalReader: connected (rw) to %s", self._db_path)
                return True
            except Exception as e2:
                logger.error("JournalReader: failed to connect: %s", e2)
                return False

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def reconnect(self) -> bool:
        self.close()
        return self.connect()

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def _tables(self) -> list[str]:
        if not self._conn:
            return []
        try:
            cur = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            return [r[0] for r in cur.fetchall()]
        except Exception:
            return []

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        if not self._conn:
            return []
        try:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                # Parse JSON fields
                for key in ("payload", "metadata", "hypothesis_refs", "setup_refs",
                            "packet_json", "calibration_json"):
                    if key in d and d[key] and isinstance(d[key], str):
                        try:
                            d[key] = json.loads(d[key])
                        except Exception:
                            pass
                result.append(d)
            return result
        except Exception as e:
            logger.warning("JournalReader query failed: %s | sql=%s", e, sql[:80])
            return []

    # -----------------------------------------------------------------------
    # Base journal tables
    # -----------------------------------------------------------------------

    def get_trades(self, limit: int = 50, offset: int = 0,
                   outcome: Optional[str] = None) -> list[dict]:
        if outcome:
            return self._query(
                "SELECT * FROM trades WHERE outcome=? ORDER BY opened_at DESC LIMIT ? OFFSET ?",
                (outcome, limit, offset),
            )
        return self._query(
            "SELECT * FROM trades ORDER BY opened_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get_trade(self, trade_id: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM trades WHERE trade_id=?", (trade_id,))
        return rows[0] if rows else None

    def get_open_trades(self) -> list[dict]:
        return self._query(
            "SELECT * FROM trades WHERE closed_at IS NULL ORDER BY opened_at DESC"
        )

    def get_signals(self, limit: int = 50, offset: int = 0,
                    group_id: Optional[str] = None) -> list[dict]:
        if group_id:
            return self._query(
                "SELECT * FROM signals WHERE group_id=? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (group_id, limit, offset),
            )
        return self._query(
            "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get_journal_events(self, limit: int = 100, offset: int = 0,
                           event_type: Optional[str] = None) -> list[dict]:
        if event_type:
            return self._query(
                "SELECT * FROM journal_events WHERE event_type=? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (event_type, limit, offset),
            )
        return self._query(
            "SELECT * FROM journal_events ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    # -----------------------------------------------------------------------
    # Learning extension tables (may not exist)
    # -----------------------------------------------------------------------

    def get_panel_summaries(self, limit: int = 20, offset: int = 0) -> list[dict]:
        tables = self._tables()
        if "panel_summaries" not in tables:
            return []
        return self._query(
            "SELECT * FROM panel_summaries ORDER BY evaluated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get_final_decisions(self, limit: int = 20, offset: int = 0) -> list[dict]:
        tables = self._tables()
        if "final_decisions" not in tables:
            return []
        return self._query(
            "SELECT * FROM final_decisions ORDER BY decided_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get_trader_reviews(self, packet_id: Optional[str] = None,
                           limit: int = 100) -> list[dict]:
        tables = self._tables()
        if "trader_reviews" not in tables:
            return []
        if packet_id:
            return self._query(
                "SELECT * FROM trader_reviews WHERE packet_id=? ORDER BY reviewed_at DESC LIMIT ?",
                (packet_id, limit),
            )
        return self._query(
            "SELECT * FROM trader_reviews ORDER BY reviewed_at DESC LIMIT ?",
            (limit,),
        )

    def get_setup_packets(self, limit: int = 20, offset: int = 0) -> list[dict]:
        tables = self._tables()
        if "setup_packets" not in tables:
            return []
        return self._query(
            "SELECT packet_id, symbol, timeframe, bar_timestamp, stored_at, outcome_source, trade_id "
            "FROM setup_packets ORDER BY stored_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def get_setup_packet(self, packet_id: str) -> Optional[dict]:
        tables = self._tables()
        if "setup_packets" not in tables:
            return None
        rows = self._query(
            "SELECT * FROM setup_packets WHERE packet_id=?", (packet_id,)
        )
        return rows[0] if rows else None

    def get_outcome_attributions(self, limit: int = 20) -> list[dict]:
        tables = self._tables()
        if "outcome_attributions" not in tables:
            return []
        return self._query(
            "SELECT * FROM outcome_attributions ORDER BY attributed_at DESC LIMIT ?",
            (limit,),
        )

    def get_calibration_records(self) -> list[dict]:
        tables = self._tables()
        if "calibration_records" not in tables:
            return []
        return self._query("SELECT * FROM calibration_records ORDER BY trader_name")

    # -----------------------------------------------------------------------
    # Stats / summary
    # -----------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Quick stats for the overview panel."""
        tables = self._tables()
        out: dict = {
            "tables": tables,
            "total_trades": 0,
            "open_trades": 0,
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_signals": 0,
            "total_events": 0,
            "total_panel_summaries": 0,
        }
        if "trades" in tables:
            r = self._query("SELECT COUNT(*) as n FROM trades")
            out["total_trades"] = r[0]["n"] if r else 0
            r = self._query("SELECT COUNT(*) as n FROM trades WHERE closed_at IS NULL")
            out["open_trades"] = r[0]["n"] if r else 0
            r = self._query("SELECT COUNT(*) as n FROM trades WHERE closed_at IS NOT NULL")
            out["closed_trades"] = r[0]["n"] if r else 0
            r = self._query("SELECT COUNT(*) as n FROM trades WHERE outcome='win'")
            out["wins"] = r[0]["n"] if r else 0
            r = self._query("SELECT COUNT(*) as n FROM trades WHERE outcome='loss'")
            out["losses"] = r[0]["n"] if r else 0
        if "signals" in tables:
            r = self._query("SELECT COUNT(*) as n FROM signals")
            out["total_signals"] = r[0]["n"] if r else 0
        if "journal_events" in tables:
            r = self._query("SELECT COUNT(*) as n FROM journal_events")
            out["total_events"] = r[0]["n"] if r else 0
        if "panel_summaries" in tables:
            r = self._query("SELECT COUNT(*) as n FROM panel_summaries")
            out["total_panel_summaries"] = r[0]["n"] if r else 0
        return out
