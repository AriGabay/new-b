"""
Base AgentRole class and RoleContext.

Every role inside every group extends AgentRole.
Roles are not persistent processes — they are invoked synchronously
within a group's processing cycle and return a result.

Source: /docs/agent_registry/role_registry.md
        /docs/architecture/runtime_model.md (Sub-agent spawning policy)
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.events import EventBus
from core.state import SystemState

logger = logging.getLogger(__name__)


@dataclass
class RoleContext:
    """
    Execution context passed to each role invocation.
    Contains everything a role needs to do its work without
    reaching into global state directly.
    """
    group_id:        str
    symbol:          str
    timeframe:       str
    timestamp:       datetime
    state:           SystemState
    bus:             EventBus
    config:          dict = field(default_factory=dict)
    metadata:        dict = field(default_factory=dict)


@dataclass
class RoleResult:
    """
    Typed output from a role invocation.
    All roles return a RoleResult — callers inspect .success and .payload.
    """
    success:       bool
    payload:       Any = None          # Role-specific output schema
    error:         Optional[str] = None
    latency_ms:    float = 0.0
    metadata:      dict = field(default_factory=dict)

    @classmethod
    def ok(cls, payload: Any = None, **metadata) -> "RoleResult":
        return cls(success=True, payload=payload, metadata=metadata)

    @classmethod
    def fail(cls, error: str, **metadata) -> "RoleResult":
        return cls(success=False, error=error, metadata=metadata)


class AgentRole(ABC):
    """
    Abstract base class for all agent roles.

    Lifecycle
    ---------
    1.  Group creates RoleContext for the current bar.
    2.  Group calls role.run(context) — awaitable.
    3.  Role executes, returns RoleResult.
    4.  Group inspects result and passes it to the next role.

    Constraints
    -----------
    -   Roles MUST NOT write to SystemState directly (use state mutation
        methods on SystemState — only Risk Engine and Journal may call them).
    -   Roles MUST NOT publish events directly (groups publish on their behalf).
    -   Roles MUST NOT retain state between calls (stateless per invocation).
        Groups own any cross-bar state caches.
    -   Roles that call LLMs MUST respect the 2000ms timeout and treat
        LLM output as advisory (see ADR-003).
    """

    #: Override in subclasses with the role's canonical name.
    role_name: str = "base"

    #: Set True only for CriticAgent, SummarizerAgent, ParserAgent (ADR-003).
    llm_permitted: bool = False

    def __init__(self) -> None:
        self._logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    async def run(self, context: RoleContext) -> RoleResult:
        """
        Execute the role. Measures latency, catches unexpected exceptions.
        Subclasses implement _execute().
        """
        t0 = time.monotonic()
        try:
            result = await self._execute(context)
            result.latency_ms = (time.monotonic() - t0) * 1000
            return result
        except asyncio.TimeoutError:
            self._logger.warning(
                "%s timed out for %s/%s",
                self.role_name, context.symbol, context.timeframe,
            )
            return RoleResult.fail(
                error="timeout",
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self._logger.exception(
                "%s raised unexpected exception for %s/%s: %s",
                self.role_name, context.symbol, context.timeframe, exc,
            )
            return RoleResult.fail(
                error=str(exc),
                latency_ms=(time.monotonic() - t0) * 1000,
            )

    @abstractmethod
    async def _execute(self, context: RoleContext) -> RoleResult:
        """Subclasses implement actual logic here."""
        ...
