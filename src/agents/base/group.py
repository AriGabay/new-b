"""
BaseGroup: abstract base class for all 10 agent groups.

Groups are the unit of activation in the system. Each group:
- Subscribes to relevant events on the EventBus at startup
- Maintains cross-bar caches (e.g., pattern state machines, feature history)
- Orchestrates a pipeline of roles when triggered
- Publishes a GroupSignalEvent (or other typed event) on completion

Groups are always-on if GroupRegistryEntry.always_on == True.
Otherwise they are activated per BarCloseEvent for symbols in eligible_symbols.

Source: /docs/agent_registry/group_registry.md
        /docs/architecture/runtime_model.md
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

from core.events import EventBus, SystemEvent
from core.registry import GroupID
from core.state import SystemState


class BaseGroup(ABC):
    """
    Abstract base class for all agent groups.

    Responsibilities:
    -   Subscribe to EventBus at startup (call setup()).
    -   Maintain any cross-bar state (pattern state machines, caches).
    -   Implement process() to run the role pipeline for one bar/trigger.
    -   Never write to SystemState directly (only Risk Engine and Journal may).

    Threading model:
    -   All asyncio — single-threaded event loop.
    -   No shared mutable state across groups.
    """

    group_id: GroupID   # Override in each group subclass

    def __init__(
        self,
        state: SystemState,
        bus: EventBus,
        config: Optional[dict] = None,
    ) -> None:
        self.state = state
        self.bus = bus
        self.config = config or {}
        self._logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )
        self._running = False

    async def setup(self) -> None:
        """
        Subscribe to EventBus and initialize caches.
        Called once at system startup before the main event loop begins.
        Subclasses override _setup() to register subscriptions.
        """
        await self._setup()
        self._running = True
        self._logger.info("Group %s ready.", self.group_id)

    @abstractmethod
    async def _setup(self) -> None:
        """Register EventBus subscriptions and initialize state here."""
        ...

    async def teardown(self) -> None:
        """Unsubscribe and clean up. Called at system shutdown."""
        self._running = False
        await self._teardown()

    async def _teardown(self) -> None:
        """Override to clean up resources."""
        ...

    async def handle_event(self, event: SystemEvent) -> None:
        """
        Main event handler. Groups receive events through EventBus callbacks.
        Measures processing time; logs if over budget.
        """
        if not self._running:
            return
        t0 = time.monotonic()
        try:
            await self._handle_event(event)
        except Exception as exc:
            self._logger.exception(
                "Group %s unhandled exception on %s: %s",
                self.group_id, type(event).__name__, exc,
            )
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if elapsed_ms > 200:
                self._logger.warning(
                    "Group %s slow: %.1fms for %s",
                    self.group_id, elapsed_ms, type(event).__name__,
                )

    @abstractmethod
    async def _handle_event(self, event: SystemEvent) -> None:
        """
        Process one event. Each group implements its own dispatch logic.
        """
        ...
