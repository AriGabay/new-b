"""
Event system: typed events and the async EventBus.
All inter-group communication passes through EventBus.

Source: /docs/data_contracts/data_contracts.md (Event Bus Contract)
        /docs/architecture/runtime_model.md
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Optional
import uuid

from .schemas import (
    OHLCVBar, FeatureVector, GroupSignalBundle,
    CandidateTradeProposal, RiskApprovedOrder, RiskRejectedEvent,
    ExitSignal, Position,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event Base and Concrete Types
# ---------------------------------------------------------------------------

@dataclass
class SystemEvent:
    event_id:  str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source:    str = "system"


@dataclass
class BarCloseEvent(SystemEvent):
    """Fired when a new OHLCV bar is finalized."""
    bar: Optional[OHLCVBar] = None


@dataclass
class FeatureReadyEvent(SystemEvent):
    """Fired when feature computation is complete for a symbol."""
    features: Optional[FeatureVector] = None


@dataclass
class UniverseUpdateEvent(SystemEvent):
    """Fired hourly when the eligible symbol universe is refreshed."""
    eligible_symbols: set[str] = field(default_factory=set)
    excluded_symbols: dict[str, str] = field(default_factory=dict)  # symbol → reason


@dataclass
class GroupSignalEvent(SystemEvent):
    """A group has completed processing and produced a signal bundle."""
    bundle: Optional[GroupSignalBundle] = None


@dataclass
class CandidateTradeEvent(SystemEvent):
    """Entry Group has proposed a trade."""
    proposal: Optional[CandidateTradeProposal] = None


@dataclass
class PanelApprovedProposalEvent(SystemEvent):
    """
    Emitted by PanelDecisionGroup (Layer B+C) when the 20-trader panel
    and FinalDecisionGroup both approve a CandidateTradeProposal.

    RiskLeverageGroup subscribes to this event instead of CandidateTradeEvent.
    This enforces the 3-layer architecture: all proposals must pass Layer B+C
    before reaching risk evaluation.

    Fields:
      proposal       — original CandidateTradeProposal from EntryGroup
      panel_approve_count — number of "approve" votes (out of 20)
      panel_avg_score     — average trader score (1–10)
      panel_decision      — always "enter" when this event is published
      packet_id           — ID of the archived BTCSetupPacket
      panel_id            — ID of the archived PanelSummary
      decision_id         — ID of the archived FinalDecision
    """
    proposal: Optional[CandidateTradeProposal] = None
    panel_approve_count: int = 0
    panel_avg_score: float = 0.0
    panel_decision: str = "enter"   # always "enter"; hold decisions are swallowed
    packet_id: str = ""
    panel_id: str = ""
    decision_id: str = ""
    state_snapshot_id: str = ""   # mdp_transitions.transition_id for reward backfill
    size_multiplier: float = 1.0  # MDP size modifier (0.5=small, 1.0=medium, 1.5=high)


@dataclass
class RiskDecisionEvent(SystemEvent):
    """Risk Engine has made a final decision on a proposal."""
    approved: bool = False
    order:    Optional[RiskApprovedOrder] = None
    rejection: Optional[RiskRejectedEvent] = None


@dataclass
class PositionOpenEvent(SystemEvent):
    position: Optional[Position] = None


@dataclass
class PositionCloseEvent(SystemEvent):
    exit_signal: Optional[ExitSignal] = None
    final_position: Optional[Position] = None
    reward_signal: float = 0.0         # risk-adjusted reward for MDP transition logger
    state_snapshot_id: str = ""        # mdp_transitions.transition_id for reward backfill


@dataclass
class JournalEntryEvent(SystemEvent):
    entry_type: str = ""   # "signal" | "trade_open" | "trade_close" | "bar"
    payload:    dict = field(default_factory=dict)


@dataclass
class SystemAlertEvent(SystemEvent):
    severity:    str = "info"   # "info" | "warning" | "critical"
    alert_code:  str = ""
    description: str = ""


@dataclass
class DataQualityAlert(SystemEvent):
    symbol:      str = ""
    timeframe:   str = ""
    issue_type:  str = ""   # "gap" | "invalid_ohlc" | "stale_data"
    description: str = ""


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

EventCallback = Callable[[SystemEvent], Coroutine[Any, Any, None]]


class EventBus:
    """
    Asyncio-based publish/subscribe event bus.

    Phase 2: In-process asyncio queues.
    Phase 3+: Replace backend with Redis Streams for multi-process.

    Guarantees:
    - Events delivered in publication order within each channel.
    - Subscriber exceptions are caught and logged; other subscribers unaffected.
    - EventBus.publish() never raises.
    """

    def __init__(self) -> None:
        # event_type_name → list of async callbacks
        self._subscribers: dict[str, list[EventCallback]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, event_type: type, callback: EventCallback) -> str:
        """
        Subscribe to an event type. Returns subscription token (event_type name).
        """
        key = event_type.__name__
        async with self._lock:
            if key not in self._subscribers:
                self._subscribers[key] = []
            self._subscribers[key].append(callback)
        return key

    async def unsubscribe(self, event_type: type, callback: EventCallback) -> None:
        key = event_type.__name__
        async with self._lock:
            if key in self._subscribers:
                self._subscribers[key] = [
                    cb for cb in self._subscribers[key] if cb is not callback
                ]

    async def publish(self, event: SystemEvent) -> None:
        """
        Publish event to all subscribers. Never raises.
        Subscriber exceptions are caught and logged.
        """
        key = type(event).__name__
        callbacks = list(self._subscribers.get(key, []))

        for callback in callbacks:
            try:
                await callback(event)
            except Exception:
                logger.exception(
                    "EventBus: subscriber %s raised on event %s",
                    getattr(callback, "__qualname__", repr(callback)),
                    key,
                )


# ---------------------------------------------------------------------------
# Global bus instance (injected at startup)
# ---------------------------------------------------------------------------

_bus: Optional[EventBus] = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_bus() -> None:
    """For testing only."""
    global _bus
    _bus = EventBus()
