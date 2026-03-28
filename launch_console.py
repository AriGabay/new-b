#!/usr/bin/env python3
"""
BTC/Bybit Trading System — Management Console Launcher.

Usage:
    cd /path/to/new-b
    python launch_console.py [--port 8765] [--host 0.0.0.0] [--reload]

    Then open http://localhost:8765 in your browser.
"""
import argparse
import logging
import os
import sys

# ── Ensure src/ is on sys.path ─────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

os.chdir(PROJECT_ROOT)

# ── Configure logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("console_launcher")


def main():
    parser = argparse.ArgumentParser(description="BTC/Bybit Trading Console")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev only)")
    parser.add_argument("--log-level", default="info", help="Uvicorn log level")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn not installed. Run: pip install fastapi uvicorn websockets")
        sys.exit(1)

    logger.info("Starting BTC/Bybit Trading Console at http://%s:%d", args.host, args.port)
    logger.info("PROJECT_ROOT=%s", PROJECT_ROOT)
    logger.info("Press Ctrl+C to stop.")

    uvicorn.run(
        "console.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        app_dir=SRC_ROOT,
    )


if __name__ == "__main__":
    main()
