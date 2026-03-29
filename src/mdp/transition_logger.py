"""
TransitionLogger: logs (state, action, reward, next_state) tuples to SQLite.

Table: mdp_transitions
  transition_id  TEXT PRIMARY KEY
  timestamp      TEXT               — ISO UTC when logged
  episode_id     TEXT               — groups related decisions per session
  state_json     TEXT               — MDPState.to_dict() serialized
  action         TEXT               — MDPAction.value
  reasoning      TEXT (JSON)        — policy reasoning dict
  reward         REAL               — NULL until trade closes; 0.0 for NO_TRADE/DEFER
  next_state_json TEXT              — NULL until next decision point
  trade_id       TEXT               — position_id when trade opens; NULL otherwise

Usage:
    logger = TransitionLogger(journal_extension)
    t_id = logger.log_transition(state, action, reasoning, trade_id="pos_123")
    # ... later, when trade closes:
    logger.update_reward(t_id, reward=2.3, next_state=next_state)

This data drives:
  Phase 2: Offline policy evaluation (which rules earned most reward?)
  Phase 3: Online learning (policy gradient / Q-learning update)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from mdp.state import MDPState
from mdp.actions import MDPAction

logger = logging.getLogger(__name__)


class TransitionLogger:
    """
    Logs MDP transitions to the mdp_transitions SQLite table.

    Injected with a JournalExtension instance (shares the same SQLite
    connection as all other learning-layer tables).
    """

    def __init__(self, journal_extension, episode_id: Optional[str] = None) -> None:
        """
        Args:
            journal_extension: JournalExtension instance (has ._conn attribute)
            episode_id:        Groups related transitions. Auto-generated if None.
        """
        self._ext = journal_extension
        self._conn = journal_extension._conn
        self._episode_id = episode_id or str(uuid.uuid4())
        self._create_table()
        logger.info(
            "TransitionLogger initialized: episode_id=%s", self._episode_id
        )

    def _create_table(self) -> None:
        """Create mdp_transitions table if not exists."""
        try:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS mdp_transitions (
                    transition_id   TEXT PRIMARY KEY,
                    timestamp       TEXT NOT NULL,
                    episode_id      TEXT NOT NULL,
                    state_json      TEXT NOT NULL,
                    action          TEXT NOT NULL,
                    reasoning       TEXT NOT NULL,
                    reward          REAL,
                    next_state_json TEXT,
                    trade_id        TEXT
                )
            """)
            self._conn.commit()
        except Exception as exc:
            logger.error("TransitionLogger._create_table failed: %s", exc)

    def log_transition(
        self,
        state: MDPState,
        action: MDPAction,
        reasoning: dict,
        trade_id: Optional[str] = None,
    ) -> str:
        """
        Log state + action at decision time.

        reward and next_state are NULL until trade closes (backfilled via
        update_reward). For NO_TRADE / DEFER, reward is immediately set to 0.0.

        Returns:
            transition_id (str) — use to backfill reward later.
        """
        from mdp.actions import ENTER_ACTIONS

        transition_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # For non-entry actions, reward is immediately 0.0 (no trade = no reward)
        immediate_reward: Optional[float] = None
        if action not in ENTER_ACTIONS:
            immediate_reward = 0.0

        try:
            self._conn.execute(
                """INSERT INTO mdp_transitions
                   (transition_id, timestamp, episode_id,
                    state_json, action, reasoning, reward, next_state_json, trade_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)""",
                (
                    transition_id,
                    timestamp,
                    self._episode_id,
                    json.dumps(state.to_dict()),
                    action.value,
                    json.dumps(reasoning),
                    immediate_reward,
                    trade_id,
                ),
            )
            self._conn.commit()
            logger.debug(
                "TransitionLogger: logged %s → %s (trade_id=%s)",
                transition_id[:8], action.value, trade_id,
            )
        except Exception as exc:
            logger.error("TransitionLogger.log_transition failed: %s", exc)
            return ""

        return transition_id

    def update_reward(
        self,
        transition_id: str,
        reward: float,
        next_state: Optional[MDPState] = None,
        trade_id: Optional[str] = None,
    ) -> None:
        """
        Backfill reward (and optionally next_state) when a trade closes.

        Called by PanelDecisionGroup or a dedicated PositionCloseEvent handler
        once ExitGroup fires PositionCloseEvent with reward_signal.

        Args:
            transition_id: returned by log_transition()
            reward:        risk-adjusted reward from RewardComputer
            next_state:    MDPState at the time of trade close (optional)
            trade_id:      position_id to backfill if not set at log time
        """
        if not transition_id:
            return

        next_state_json = (
            json.dumps(next_state.to_dict()) if next_state is not None else None
        )

        try:
            params: list = [reward, next_state_json]
            sql = "UPDATE mdp_transitions SET reward=?, next_state_json=?"
            if trade_id is not None:
                sql += ", trade_id=?"
                params.append(trade_id)
            sql += " WHERE transition_id=?"
            params.append(transition_id)

            self._conn.execute(sql, params)
            self._conn.commit()
            logger.debug(
                "TransitionLogger: reward backfilled %s → %.3f",
                transition_id[:8], reward,
            )
        except Exception as exc:
            logger.error("TransitionLogger.update_reward failed: %s", exc)

    def query_transitions(
        self,
        episode_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Query logged transitions. Useful for offline policy evaluation.

        Args:
            episode_id: filter by episode (None = all)
            action:     filter by action value (None = all)
            limit:      max rows to return
        """
        import sqlite3
        try:
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()
            conditions = []
            params: list = []
            if episode_id is not None:
                conditions.append("episode_id = ?")
                params.append(episode_id)
            if action is not None:
                conditions.append("action = ?")
                params.append(action)
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cursor.execute(
                f"SELECT * FROM mdp_transitions {where} "
                f"ORDER BY timestamp DESC LIMIT ?",
                params + [limit],
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("TransitionLogger.query_transitions failed: %s", exc)
            return []
