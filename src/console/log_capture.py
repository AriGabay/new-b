"""
Log capture: intercepts Python logging and stores recent log lines
in a thread-safe ring buffer for the management console.

The ConsoleLogHandler installs itself as a root logger handler.
The LogBuffer provides a read API for the REST/WebSocket layer.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime
from typing import Optional

MAX_LOG_LINES = 2000


class LogLine:
    __slots__ = ("ts", "level", "name", "message", "lineno")

    def __init__(self, record: logging.LogRecord) -> None:
        self.ts = datetime.utcfromtimestamp(record.created).isoformat() + "Z"
        self.level = record.levelname
        self.name = record.name
        self.message = record.getMessage()
        self.lineno = record.lineno

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "level": self.level,
            "name": self.name,
            "message": self.message,
            "lineno": self.lineno,
        }


class LogBuffer:
    """Thread-safe ring buffer of recent log lines."""

    def __init__(self, maxlen: int = MAX_LOG_LINES) -> None:
        self._buf: deque[LogLine] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, line: LogLine) -> None:
        with self._lock:
            self._buf.append(line)

    def recent(self, limit: int = 200) -> list[dict]:
        with self._lock:
            items = list(self._buf)
        tail = items[-limit:] if len(items) > limit else items
        return [x.to_dict() for x in tail]

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


# Global buffer shared by server
_global_buffer = LogBuffer()


def get_log_buffer() -> LogBuffer:
    return _global_buffer


class ConsoleLogHandler(logging.Handler):
    """Logging handler that writes to the global LogBuffer."""

    def __init__(self, buf: Optional[LogBuffer] = None) -> None:
        super().__init__()
        self._buf = buf or _global_buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = LogLine(record)
            self._buf.append(line)
        except Exception:
            pass  # Never crash due to logging


def install_log_capture(level: int = logging.DEBUG) -> ConsoleLogHandler:
    """
    Install ConsoleLogHandler on the root logger.
    Returns the handler so it can be removed later.
    """
    handler = ConsoleLogHandler()
    handler.setLevel(level)
    root = logging.getLogger()
    root.addHandler(handler)
    return handler
