"""
Logging configuration for the trading system.

All logs go to:
  1. Console (INFO level)
  2. File: logs/system.log (DEBUG level, rotating)

Group loggers: logging.getLogger(group_class.__module__ + '.' + group_class.__name__)
"""
import logging
import logging.handlers
from pathlib import Path


def configure_logging(
    log_dir: str = "logs",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> None:
    """
    Set up root logger with console and rotating file handlers.
    Call once at system startup.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)   # Let handlers filter

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))

    # Rotating file handler (10MB max, keep 7 days)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "system.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s %(funcName)s:%(lineno)d: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root.addHandler(console)
    root.addHandler(file_handler)
