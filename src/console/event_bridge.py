"""
EventBridge: subscribes to the runtime EventBus and forwards all events
to connected WebSocket clients via an asyncio broadcast queue.

Design:
- One EventBridge per server lifetime.
- On runner start, call attach(bus) to subscribe.
- On runner stop, call detach() to unsubscribe.
- Events are serialized to JSON-safe dicts and queued.
- WebSocket connections call subscribe() to receive events.
- A ring buffer of the last 1000 events allows late-joining clients
  to receive recent history immediately on connect.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_BUFFERED_EVENTS = 1000


def _safe_str(val: Any) -> Any:
    """Convert non-JSON-serializable types to strings."""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, datetime):
        return val.isoformat() + "Z"
    if hasattr(val, "value"):          # Enum
        return val.value
    if hasattr(val, "__dict__"):        # Dataclass / object
        return _serialize(val.__dict__)
    if isinstance(val, (list, tuple)):
        return [_safe_str(v) for v in val]
    if isinstance(val, dict):
        return {k: _safe_str(v) for k, v in val.items()}
    return val


def _serialize(d: dict) -> dict:
    return {k: _safe_str(v) for k, v in d.items() if not k.startswith("_")}


def _event_to_dict(event: Any) -> dict:
    """Convert a SystemEvent to a JSON-serializable dict."""
    typ = type(event).__name__
    base = {
        "event_type": typ,
        "event_id": getattr(event, "event_id", ""),
        "timestamp": _safe_str(getattr(event, "timestamp", datetime.utcnow())),
        "source": getattr(event, "source", ""),
    }
    # Include all public fields
    for attr in vars(event):
        if attr.startswith("_") or attr in ("event_id", "timestamp", "source"):
            continue
        val = getattr(event, attr, None)
        if val is None:
            base[attr] = None
        elif hasattr(val, "__dict__"):
            try:
                base[attr] = _serialize(val.__dict__)
            except Exception:
                base[attr] = str(val)
        else:
            base[attr] = _safe_str(val)
    return base


class EventBridge:
    """
    Bridges the runtime EventBus to WebSocket clients.

    Usage:
        bridge = EventBridge()
        bridge.attach(runner.bus)
        # ... later
        bridge.detach()
    """

    def __init__(self) -> None:
        self._bus = None
        self._ring: deque[dict] = deque(maxlen=MAX_BUFFERED_EVENTS)
        self._queues: list[asyncio.Queue] = []
        self._attached = False
        self._lock = asyncio.Lock()

    async def attach(self, bus: Any) -> None:
        """Subscribe to all event types on the given EventBus."""
        if self._attached:
            await self.detach()

        self._bus = bus

        # Import all event types
        try:
            from core.events import (
                BarCloseEvent, FeatureReadyEvent, GroupSignalEvent,
                CandidateTradeEvent, PanelApprovedProposalEvent,
                RiskDecisionEvent, PositionOpenEvent, PositionCloseEvent,
                JournalEntryEvent, SystemAlertEvent, DataQualityAlert,
                UniverseUpdateEvent,
            )
            event_types = [
                BarCloseEvent, FeatureReadyEvent, GroupSignalEvent,
                CandidateTradeEvent, PanelApprovedProposalEvent,
                RiskDecisionEvent, PositionOpenEvent, PositionCloseEvent,
                JournalEntryEvent, SystemAlertEvent, DataQualityAlert,
                UniverseUpdateEvent,
            ]
        except ImportError as e:
            logger.warning("EventBridge: cannot import event types: %s", e)
            return

        self._subscribed_callbacks = []
        for et in event_types:
            cb = self._make_handler(et.__name__)
            await bus.subscribe(et, cb)
            self._subscribed_callbacks.append((et, cb))

        self._attached = True
        logger.info("EventBridge: attached to EventBus, %d event types.", len(event_types))

    async def detach(self) -> None:
        """Unsubscribe from all event types."""
        if not self._attached or self._bus is None:
            return
        for et, cb in getattr(self, "_subscribed_callbacks", []):
            try:
                await self._bus.unsubscribe(et, cb)
            except Exception:
                pass
        self._bus = None
        self._attached = False
        self._subscribed_callbacks = []
        logger.info("EventBridge: detached from EventBus.")

    def _make_handler(self, event_type_name: str):
        """Create an async handler for a specific event type."""
        async def handler(event):
            try:
                d = _event_to_dict(event)
                self._ring.append(d)
                # Broadcast to all connected WS queues
                dead = []
                for q in self._queues:
                    try:
                        q.put_nowait(d)
                    except asyncio.QueueFull:
                        dead.append(q)
                for q in dead:
                    self._queues.remove(q)
            except Exception as e:
                logger.debug("EventBridge handler error: %s", e)
        return handler

    def subscribe_queue(self, q: asyncio.Queue) -> None:
        """Register a new WebSocket client queue."""
        self._queues.append(q)

    def unsubscribe_queue(self, q: asyncio.Queue) -> None:
        """Remove a WebSocket client queue."""
        if q in self._queues:
            self._queues.remove(q)

    def recent_events(self, limit: int = 200) -> list[dict]:
        """Return the most recent N events from the ring buffer."""
        items = list(self._ring)
        return items[-limit:] if len(items) > limit else items

    @property
    def is_attached(self) -> bool:
        return self._attached

    def inject_log_event(self, log_dict: dict) -> None:
        """Inject a log-captured entry as a console_log event."""
        d = {**log_dict, "event_type": "ConsoleLogEvent"}
        self._ring.append(d)
        for q in self._queues:
            try:
                q.put_nowait(d)
            except asyncio.QueueFull:
                pass


# Global bridge instance
_bridge = EventBridge()


def get_bridge() -> EventBridge:
    return _bridge
