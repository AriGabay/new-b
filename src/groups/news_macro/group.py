"""
News & Macro Group (Group 2 — always_on=False, implementation_priority=5).

Responsibilities:
  - Load static event calendar (CSV in Phase 2; no live news feed yet).
  - Identify scheduled risk events for the next 48h window.
  - Emit macro event risk flags that Entry group uses to suppress or
    reduce size before high-impact events (FOMC, CPI, options expiry).
  - BTC MVRV filter: mark btc_macro regime as overheated if MVRV > 3.0.

LLM: PERMITTED for live news parsing (Phase 3+).
     Phase 2: deterministic CSV calendar only — LLM NOT used.
Always-on: NO — triggered once daily at bar close.

Phase 2 deliverable: Static event calendar (CSV). No live news in Phase 2.

Source: /docs/agent_registry/group_registry.md (NEWS_MACRO entry)
        /research/hypotheses/hypothesis_registry.md (H4-002)
"""
from __future__ import annotations

import logging
from typing import Optional

from agents.base.group import BaseGroup
from core.events import BarCloseEvent, EventBus, GroupSignalEvent, SystemEvent
from core.registry import GroupID
from core.schemas import GroupSignalBundle, RegimeContext
from core.state import SystemState

logger = logging.getLogger(__name__)


class NewsMacroGroup(BaseGroup):
    """
    Macro event risk and BTC regime context provider.

    Cross-bar state:
    -   _event_calendar: list[dict]  — loaded from CSV at startup
    -   _btc_mvrv: float             — updated periodically (Phase 3: live API)
    -   _last_regime: RegimeContext  — most recent regime, used by Entry group
    """

    group_id = GroupID.NEWS_MACRO

    def __init__(self, state: SystemState, bus: EventBus, config: Optional[dict] = None) -> None:
        super().__init__(state, bus, config)
        self._event_calendar: list = []
        self._btc_mvrv: float = 0.0

    async def _setup(self) -> None:
        await self.bus.subscribe(BarCloseEvent, self.handle_event)
        await self._load_event_calendar()
        logger.info("NewsMacroGroup subscribed to BarCloseEvent.")

    async def _handle_event(self, event: SystemEvent) -> None:
        if isinstance(event, BarCloseEvent):
            await self._process_bar_close(event)

    async def _process_bar_close(self, event: BarCloseEvent) -> None:
        """
        On each daily bar close:
        1. Check event calendar for high-impact events in next 48h.
        2. Compute BTC macro regime from FeatureVector (EMA200 position, ATR regime).
        3. Build GroupSignalBundle with macro metadata.
        4. Publish GroupSignalEvent.
        """
        raise NotImplementedError("NewsMacroGroup._process_bar_close() — Phase 2 implementation pending")

    async def _load_event_calendar(self) -> None:
        """
        Load static event calendar from config path.
        CSV schema: date, event_name, impact_level (high/medium/low), asset_scope
        """
        calendar_path = self.config.get("event_calendar_path")
        if not calendar_path:
            logger.warning("NewsMacroGroup: no event_calendar_path configured. Macro events disabled.")
            return
        raise NotImplementedError("NewsMacroGroup._load_event_calendar() — Phase 2 implementation pending")

    def _has_high_impact_event_next_48h(self, reference_ts) -> bool:
        """Return True if a high-impact event falls within 48h of reference_ts."""
        raise NotImplementedError("Phase 2 pending")

    def _classify_btc_macro(self, features) -> str:
        """
        Classify BTC macro regime: 'bull' | 'bear' | 'ranging'.
        Phase 2: based on EMA200 position and ATR regime.
        Phase 3: augment with MVRV if live data available.
        """
        raise NotImplementedError("Phase 2 pending")
