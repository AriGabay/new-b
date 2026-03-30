"""
HistorianGroup (Group 11 — always_on=False).

Responsibilities:
  - Listen to PositionCloseEvent and accumulate in-memory trade stats.
  - Track hypothesis-level performance (win_rate, avg_r_multiple) keyed by
    hypothesis_ref.
  - Track regime-level performance keyed by "{btc_macro}_{volatility_regime}".
  - Detect consecutive-loss streaks and encode size reduction warnings into
    HistoricalAnalog.common_failure_modes.
  - Expose query(symbol, direction, hypothesis_refs, regime_key) → HistoricalAnalog
    for use by EntryGroup before composite score computation.

Minimum trade samples:
  - Hypothesis-level stats: 10 closed trades before contributing to query result.
  - Regime-level stats: 15 closed trades before contributing to query result.

Composite win_rate formula:
  historian_win_rate = 0.6 × hyp_win_rate + 0.4 × regime_win_rate
  Capped to [0.0, 1.0].

Streak detection:
  3+ consecutive losses → "CAUTION: 3-loss streak, size -20%"
  5+ consecutive losses → "CAUTION: 5-loss streak, size -40%"

JournalExtension injection:
  _extension is set by runner._finalize_learning_wiring() after DB is live.
  The group works without _extension (in-memory stats only).
"""
from __future__ import annotations

import logging
from typing import Optional

from agents.base.group import BaseGroup
from core.events import EventBus, PositionCloseEvent, SystemEvent
from core.registry import GroupID
from core.schemas import Direction, HistoricalAnalog
from core.state import SystemState

logger = logging.getLogger(__name__)

# Minimum closed trades before stats are considered reliable
_HYP_MIN_TRADES = 10
_REGIME_MIN_TRADES = 15

# Streak thresholds → size reduction labels
_STREAK_WARNINGS = [
    (5, "CAUTION: 5-loss streak, size -40%"),
    (3, "CAUTION: 3-loss streak, size -20%"),
]


class HistorianGroup(BaseGroup):
    """
    Learns from closed trades and answers historical-analog queries.

    State (all in-memory; no DB required for basic operation):
      _hyp_stats:    dict[str, dict]  keyed by hypothesis_ref
      _regime_stats: dict[str, dict]  keyed by "{btc_macro}_{volatility_regime}"
      _consecutive_losses: int        running count reset on any win
      _recent_outcomes:   list[bool]  last 10 outcomes (True=win)
    """

    group_id = GroupID.HISTORIAN

    def __init__(
        self,
        state: SystemState,
        bus: EventBus,
        config: Optional[dict] = None,
    ) -> None:
        super().__init__(state, bus, config)
        self._hyp_stats: dict[str, dict] = {}
        self._regime_stats: dict[str, dict] = {}
        self._consecutive_losses: int = 0
        self._recent_outcomes: list[bool] = []
        # Injected by runner after DB is ready (optional)
        self._extension = None

    # ------------------------------------------------------------------
    # BaseGroup interface
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        await self.bus.subscribe(PositionCloseEvent, self.handle_event)
        logger.info("HistorianGroup subscribed to PositionCloseEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, PositionCloseEvent) and event.final_position is not None:
            self._record_closed_trade(event)

    # ------------------------------------------------------------------
    # Internal recording
    # ------------------------------------------------------------------

    def _record_closed_trade(self, event: PositionCloseEvent) -> None:
        pos = event.final_position
        pnl_r: float = getattr(pos, "current_pnl_r", 0.0)
        won: bool = pnl_r > 0.0

        # Update streak tracking
        if won:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1

        # Keep last-10 outcomes ring buffer
        self._recent_outcomes.append(won)
        if len(self._recent_outcomes) > 10:
            self._recent_outcomes.pop(0)

        # Hypothesis-level stats
        for href in getattr(pos, "hypothesis_refs", []):
            if href not in self._hyp_stats:
                self._hyp_stats[href] = {
                    "wins": 0, "total": 0, "r_sum": 0.0
                }
            s = self._hyp_stats[href]
            s["total"] += 1
            if won:
                s["wins"] += 1
            s["r_sum"] += pnl_r

        # Regime-level stats — needs btc_macro + volatility_regime from position metadata
        # These are stored in position.setup_refs as a convention: "regime:<key>"
        regime_key = self._extract_regime_key(pos)
        if regime_key:
            if regime_key not in self._regime_stats:
                self._regime_stats[regime_key] = {
                    "wins": 0, "total": 0, "r_sum": 0.0
                }
            r = self._regime_stats[regime_key]
            r["total"] += 1
            if won:
                r["wins"] += 1
            r["r_sum"] += pnl_r

    @staticmethod
    def _extract_regime_key(pos) -> Optional[str]:
        """Extract regime key from position.setup_refs ("regime:<key>" entry)."""
        for ref in getattr(pos, "setup_refs", []):
            if isinstance(ref, str) and ref.startswith("regime:"):
                return ref[len("regime:"):]
        return None

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def query(
        self,
        symbol: str,
        direction,
        hypothesis_refs: Optional[list[str]] = None,
        regime_key: Optional[str] = None,
    ) -> HistoricalAnalog:
        """
        Return a HistoricalAnalog for the given setup context.

        If insufficient data (<_HYP_MIN_TRADES or <_REGIME_MIN_TRADES), falls
        back to neutral values (win_rate=0.5) for the under-sampled component.
        """
        hyp_wr, hyp_r, hyp_total = self._query_hypothesis(hypothesis_refs or [])
        regime_wr, regime_r, regime_total = self._query_regime(regime_key)

        # Blend win rates: 60% hypothesis, 40% regime
        # Use neutral 0.5 for any component below minimum sample threshold
        if hyp_total >= _HYP_MIN_TRADES and regime_total >= _REGIME_MIN_TRADES:
            blended_wr = 0.6 * hyp_wr + 0.4 * regime_wr
        elif hyp_total >= _HYP_MIN_TRADES:
            blended_wr = 0.6 * hyp_wr + 0.4 * 0.5
        elif regime_total >= _REGIME_MIN_TRADES:
            blended_wr = 0.6 * 0.5 + 0.4 * regime_wr
        else:
            blended_wr = 0.5  # no data at all

        blended_wr = max(0.0, min(1.0, blended_wr))

        # avg_r_multiple: weight by sample count if both available
        if hyp_total > 0 and regime_total > 0:
            avg_r = (hyp_r * hyp_total + regime_r * regime_total) / (hyp_total + regime_total)
        elif hyp_total > 0:
            avg_r = hyp_r
        elif regime_total > 0:
            avg_r = regime_r
        else:
            avg_r = 0.0

        similar_count = max(hyp_total, regime_total)

        # Streak warnings
        failure_modes: list[str] = []
        for threshold, label in _STREAK_WARNINGS:
            if self._consecutive_losses >= threshold:
                failure_modes.append(label)
                break  # only the most severe

        # Regime caution flag
        if regime_total >= _REGIME_MIN_TRADES and regime_wr < 0.40:
            failure_modes.append(
                f"CAUTION: regime '{regime_key}' win_rate={regime_wr:.0%} ({regime_total} trades)"
            )

        # last_10_outcomes
        last_10 = ["win" if w else "loss" for w in self._recent_outcomes[-10:]]

        return HistoricalAnalog(
            similar_trades_count=similar_count,
            win_rate=round(blended_wr, 4),
            avg_r_multiple=round(avg_r, 4),
            common_failure_modes=failure_modes,
            last_10_outcomes=last_10,
        )

    def _query_hypothesis(self, hrefs: list[str]) -> tuple[float, float, int]:
        """Aggregate stats across all provided hypothesis refs."""
        total_wins = 0
        total_trades = 0
        total_r = 0.0
        for href in hrefs:
            s = self._hyp_stats.get(href)
            if s is None:
                continue
            total_trades += s["total"]
            total_wins += s["wins"]
            total_r += s["r_sum"]
        if total_trades == 0:
            return 0.5, 0.0, 0
        return total_wins / total_trades, total_r / total_trades, total_trades

    def _query_regime(self, regime_key: Optional[str]) -> tuple[float, float, int]:
        """Look up regime-level stats for the given key."""
        if not regime_key:
            return 0.5, 0.0, 0
        r = self._regime_stats.get(regime_key)
        if r is None or r["total"] == 0:
            return 0.5, 0.0, 0
        wr = r["wins"] / r["total"]
        avg_r = r["r_sum"] / r["total"]
        return wr, avg_r, r["total"]
