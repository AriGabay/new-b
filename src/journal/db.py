"""
JournalDB: append-only SQLite journal for all trades, signals, and system events.

Schema (3 tables):

trades:
  trade_id          TEXT PRIMARY KEY
  order_id          TEXT
  proposal_id       TEXT
  symbol            TEXT
  timeframe         TEXT
  direction         TEXT
  entry_price       REAL
  stop_price        REAL
  target_price      REAL
  position_size_usd REAL
  r_amount          REAL
  opened_at         TEXT  (ISO8601)
  closed_at         TEXT  (ISO8601, NULL if open)
  exit_reason       TEXT  (NULL if open)
  exit_price        REAL  (NULL if open)
  pnl_usd           REAL  (NULL if open)
  pnl_r             REAL  (NULL if open)
  outcome           TEXT  (win/loss/breakeven/open)
  hypothesis_refs   TEXT  (JSON array)
  setup_refs        TEXT  (JSON array)
  composite_score   REAL
  bars_held         INTEGER

signals:
  signal_id         TEXT PRIMARY KEY
  group_id          TEXT
  symbol            TEXT
  timeframe         TEXT
  timestamp         TEXT
  direction         TEXT
  signal_type       TEXT
  signal_subtype    TEXT
  hypothesis_ref    TEXT
  quality_score     REAL
  trade_id          TEXT  (NULL if signal did not result in trade)
  metadata          TEXT  (JSON)

journal_events:
  event_id          TEXT PRIMARY KEY
  timestamp         TEXT
  event_type        TEXT  (signal/trade_open/trade_close/risk_decision/alert/bar)
  source            TEXT
  payload           TEXT  (JSON)
  severity          TEXT  (NULL unless alert)

Rules:
  - Append only. No UPDATE or DELETE on trades/signals/journal_events.
  - Exceptions: trades.closed_at, exit_reason, exit_price, pnl_usd, pnl_r, outcome
    are updated when a position closes (single allowed UPDATE per trade_id).
  - All timestamps stored as ISO8601 UTC strings.
  - metadata and payload stored as JSON strings.

Source: /docs/learning_system/learning_contract.md (Journal Schema)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from core.schemas import ExitSignal, Position, RiskApprovedOrder

logger = logging.getLogger(__name__)


class JournalDB:
    """
    Thread-safe (asyncio single-thread) SQLite journal.
    All operations are synchronous SQLite calls wrapped in the asyncio event loop.
    For Phase 3 high-throughput: migrate to aiosqlite or TimescaleDB.
    """

    def __init__(self, db_path: str = "data/journal.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Open DB connection and create tables if not exist."""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")   # Write-ahead log for concurrent reads
        self._create_tables()
        logger.info("JournalDB initialized at %s", self._db_path)

    def _create_tables(self) -> None:
        """Create trades, signals, journal_events tables."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                order_id TEXT,
                proposal_id TEXT,
                symbol TEXT NOT NULL,
                timeframe TEXT,
                direction TEXT,
                entry_price REAL,
                stop_price REAL,
                target_price REAL,
                position_size_usd REAL,
                r_amount REAL,
                opened_at TEXT,
                closed_at TEXT,
                exit_reason TEXT,
                exit_price REAL,
                pnl_usd REAL,
                pnl_r REAL,
                outcome TEXT DEFAULT 'open',
                hypothesis_refs TEXT,
                setup_refs TEXT,
                composite_score REAL,
                bars_held INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                group_id TEXT,
                symbol TEXT,
                timeframe TEXT,
                timestamp TEXT,
                direction TEXT,
                signal_type TEXT,
                signal_subtype TEXT,
                hypothesis_ref TEXT,
                quality_score REAL,
                trade_id TEXT,
                metadata TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS journal_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT,
                event_type TEXT,
                source TEXT,
                payload TEXT,
                severity TEXT
            )
        """)
        self._conn.commit()

    def insert_trade_open(self, position: Position, proposal_id: str, composite_score: float) -> None:
        """
        Insert new trade record with status=open.
        closed_at, exit fields are NULL.
        """
        if self._conn is None:
            logger.error("insert_trade_open: DB connection is not initialized")
            return
        try:
            direction = (
                position.direction.value
                if hasattr(position.direction, "value")
                else str(position.direction)
            )
            self._conn.execute(
                """
                INSERT INTO trades (
                    trade_id, order_id, proposal_id, symbol, timeframe, direction,
                    entry_price, stop_price, target_price, position_size_usd, r_amount,
                    opened_at, closed_at, exit_reason, exit_price, pnl_usd, pnl_r,
                    outcome, hypothesis_refs, setup_refs, composite_score, bars_held
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.position_id,
                    position.order_id,
                    proposal_id,
                    position.symbol,
                    "",
                    direction,
                    float(position.entry_price),
                    float(position.stop_price),
                    float(position.target_price),
                    float(position.position_size_usd),
                    float(position.r_amount),
                    position.opened_at.isoformat(),
                    None,
                    None,
                    None,
                    None,
                    None,
                    "open",
                    json.dumps(position.hypothesis_refs),
                    json.dumps(position.setup_refs),
                    composite_score,
                    0,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_trade_open failed: %s", exc)

    def update_trade_close(self, exit_signal: ExitSignal, position: Position) -> None:
        """
        Update existing trade record with exit data.
        This is the ONLY allowed UPDATE on the trades table.
        """
        if self._conn is None:
            logger.error("update_trade_close: DB connection is not initialized")
            return
        try:
            exit_reason = (
                exit_signal.exit_reason.value
                if hasattr(exit_signal.exit_reason, "value")
                else str(exit_signal.exit_reason)
            )
            if exit_signal.pnl_r > 0:
                outcome = "win"
            elif exit_signal.pnl_r < 0:
                outcome = "loss"
            else:
                outcome = "breakeven"
            self._conn.execute(
                """
                UPDATE trades
                SET closed_at=?, exit_reason=?, exit_price=?, pnl_usd=?, pnl_r=?,
                    outcome=?, bars_held=?
                WHERE trade_id=?
                """,
                (
                    exit_signal.timestamp.isoformat(),
                    exit_reason,
                    float(exit_signal.exit_price),
                    float(exit_signal.pnl_usd),
                    exit_signal.pnl_r,
                    outcome,
                    exit_signal.bars_held,
                    position.position_id,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("update_trade_close failed: %s", exc)

    def insert_signal(self, signal: object, trade_id: Optional[str] = None) -> None:
        """Insert a CandidateSignal record into signals table."""
        if self._conn is None:
            logger.error("insert_signal: DB connection is not initialized")
            return
        try:
            raw_direction = getattr(signal, "direction", "")
            direction = getattr(raw_direction, "value", str(raw_direction))
            raw_ts = getattr(signal, "timestamp", datetime.utcnow())
            timestamp = raw_ts.isoformat() if hasattr(raw_ts, "isoformat") else str(raw_ts)
            self._conn.execute(
                """
                INSERT OR IGNORE INTO signals (
                    signal_id, group_id, symbol, timeframe, timestamp, direction,
                    signal_type, signal_subtype, hypothesis_ref, quality_score,
                    trade_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    getattr(signal, "signal_id", str(uuid.uuid4())),
                    getattr(signal, "group_id", ""),
                    getattr(signal, "symbol", ""),
                    getattr(signal, "timeframe", ""),
                    timestamp,
                    direction,
                    getattr(signal, "signal_type", ""),
                    getattr(signal, "signal_subtype", ""),
                    getattr(signal, "hypothesis_ref", None),
                    getattr(signal, "quality_score", 0.0),
                    trade_id,
                    json.dumps(getattr(signal, "metadata", {})),
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_signal failed: %s", exc)

    def insert_journal_event(
        self,
        event_type: str,
        source: str,
        payload: dict,
        severity: Optional[str] = None,
    ) -> None:
        """Append a record to journal_events. Always appends, never modifies."""
        if self._conn is None:
            logger.error("insert_journal_event: DB connection is not initialized")
            return
        try:
            self._conn.execute(
                """
                INSERT INTO journal_events (event_id, timestamp, event_type, source, payload, severity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    datetime.utcnow().isoformat(),
                    event_type,
                    source,
                    json.dumps(payload),
                    severity,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("insert_journal_event failed: %s", exc)

    def query_hypothesis_trades(
        self,
        hypothesis_id: str,
        n: Optional[int] = None,
    ) -> list[dict]:
        """
        Return closed trade records for a specific hypothesis.
        Ordered by closed_at DESC (newest first).
        If n provided: return last n trades.
        """
        if self._conn is None:
            logger.error("query_hypothesis_trades: DB connection is not initialized")
            return []
        try:
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            like_val = f"%{hypothesis_id}%"
            if n is not None:
                cursor.execute(
                    """
                    SELECT * FROM trades
                    WHERE hypothesis_refs LIKE ? AND closed_at IS NOT NULL
                    ORDER BY closed_at DESC
                    LIMIT ?
                    """,
                    (like_val, n),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM trades
                    WHERE hypothesis_refs LIKE ? AND closed_at IS NOT NULL
                    ORDER BY closed_at DESC
                    """,
                    (like_val,),
                )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.error("query_hypothesis_trades failed: %s", exc)
            return []

    def query_recent_outcomes(
        self,
        hypothesis_id: str,
        n: int = 10,
    ) -> list[str]:
        """Return list of n most recent outcome strings for a hypothesis."""
        rows = self.query_hypothesis_trades(hypothesis_id, n=n)
        return [row["outcome"] for row in rows]

    def close(self) -> None:
        """Close DB connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
