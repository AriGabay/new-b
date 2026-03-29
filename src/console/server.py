"""
Management Console — FastAPI server.

Endpoints:
  GET  /                            → serve console UI
  GET  /api/status                  → runner + system status
  GET  /api/state                   → SystemState snapshot
  GET  /api/groups                  → group statuses
  GET  /api/logs                    → recent log lines
  GET  /api/journal/stats           → DB counts
  GET  /api/journal/trades          → trade records
  GET  /api/journal/signals         → signal records
  GET  /api/journal/events          → journal events
  GET  /api/journal/panels          → panel summaries
  GET  /api/journal/decisions       → final decisions
  GET  /api/journal/reviews         → trader reviews (by packet_id)
  GET  /api/journal/packets         → setup packets
  GET  /api/journal/attributions    → outcome attributions
  GET  /api/journal/calibration     → calibration records
  GET  /api/tests/list              → available test files
  GET  /api/tests/results           → all test run results
  POST /api/tests/run               → start test run
  GET  /api/tests/result/{run_id}   → specific test result
  GET  /api/replay/fixtures         → available fixtures
  GET  /api/replay/results          → all replay run results
  POST /api/replay/run              → start replay run
  GET  /api/replay/result/{run_id}  → specific replay result
  POST /api/actions/start_runner    → start runner
  POST /api/actions/stop_runner     → stop runner
  WS   /ws/events                   → real-time event stream
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

# ─── Project root detection ───────────────────────────────────────────────────

def _find_project_root() -> Path:
    """Walk up from this file until we find src/ and docs/."""
    p = Path(__file__).resolve().parent
    for _ in range(5):
        if (p / "src").exists() and (p / "docs").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _find_project_root()
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# ─── Install log capture before anything else imports ─────────────────────────
from console.log_capture import install_log_capture, get_log_buffer
_log_handler = install_log_capture(logging.DEBUG)

# ─── Module imports ───────────────────────────────────────────────────────────
from console.event_bridge import get_bridge
from console.journal_reader import JournalReader
from console.runner_manager import get_runner_manager, RunnerManager
from console.test_runner import TestRunner, set_test_runner, get_test_runner
from console.replay_manager import get_replay_manager

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    logger.info("Console server starting up. PROJECT_ROOT=%s", PROJECT_ROOT)

    # Wire global instances
    db_path = str(PROJECT_ROOT / "src" / "data" / "journal.db")
    mgr = RunnerManager(journal_db_path=db_path)

    import console.runner_manager as rm_mod
    rm_mod._manager = mgr

    # Journal reader
    reader = JournalReader(db_path)
    reader.connect()
    app.state.journal_reader = reader

    # Test runner
    tr = TestRunner(str(PROJECT_ROOT))
    set_test_runner(tr)

    yield

    # Shutdown
    logger.info("Console server shutting down.")
    bridge = get_bridge()
    if bridge.is_attached:
        await bridge.detach()
    runner_mgr = get_runner_manager()
    if runner_mgr.is_running:
        await runner_mgr.stop()
    reader.close()
    root = logging.getLogger()
    root.removeHandler(_log_handler)


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BTC/Bybit Trading Console",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Static UI ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_console():
    """Serve the operator console HTML."""
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse("<h1>Console UI not found. Run build step.</h1>", status_code=503)


# ─── Status / State ───────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    mgr = get_runner_manager()
    bridge = get_bridge()
    return {
        "runner": mgr.get_status(),
        "event_bridge_attached": bridge.is_attached,
        "server": "online",
        "phase": "Phase 6",
        "architecture": {
            "active_groups": [
                "MarketDataGroup", "IndicatorsGroup", "CandlestickGroup",
                "TechnicalStructureGroup", "EntryGroup", "PanelDecisionGroup",
                "RiskLeverageGroup", "ExitGroup", "PerformanceJournalGroup",
            ],
            "excluded_groups": [
                "ChartPatternGroup", "NewsMacroGroup",
                "HistorianAgent", "CriticAgent",
            ],
            "panel_policy": {
                "approve_threshold": 14,
                "min_avg_score": 6.5,
                "trader_count": 20,
            },
        },
    }


@app.get("/api/state")
async def get_system_state():
    mgr = get_runner_manager()
    return mgr.get_system_state()


@app.get("/api/groups")
async def get_groups():
    mgr = get_runner_manager()
    status = mgr.get_status()
    return {"groups": status.get("groups", [])}


# ─── Logs ─────────────────────────────────────────────────────────────────────

@app.get("/api/logs")
async def get_logs(
    limit: int = Query(200, ge=1, le=2000),
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    lines = get_log_buffer().recent(limit=limit * 2)
    if level:
        lines = [l for l in lines if l.get("level") == level.upper()]
    if search:
        lines = [l for l in lines if search.lower() in l.get("message", "").lower()]
    return {"lines": lines[-limit:], "total": len(lines)}


# ─── Journal ──────────────────────────────────────────────────────────────────

def _reader() -> JournalReader:
    """Get the journal reader. Reconnects if needed."""
    from fastapi import Request
    # Fall back to global reader
    import console.server as _self
    return app.state.journal_reader


@app.get("/api/journal/stats")
async def journal_stats():
    reader = app.state.journal_reader
    if not reader.is_connected:
        reader.reconnect()
    return reader.get_stats()


@app.get("/api/journal/trades")
async def journal_trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    outcome: Optional[str] = Query(None),
):
    reader = app.state.journal_reader
    return {"trades": reader.get_trades(limit=limit, offset=offset, outcome=outcome)}


@app.get("/api/journal/signals")
async def journal_signals(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    group_id: Optional[str] = Query(None),
):
    reader = app.state.journal_reader
    return {"signals": reader.get_signals(limit=limit, offset=offset, group_id=group_id)}


@app.get("/api/journal/events")
async def journal_events(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None),
):
    reader = app.state.journal_reader
    return {"events": reader.get_journal_events(limit=limit, offset=offset, event_type=event_type)}


@app.get("/api/journal/panels")
async def journal_panels(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    reader = app.state.journal_reader
    return {"panels": reader.get_panel_summaries(limit=limit, offset=offset)}


@app.get("/api/journal/decisions")
async def journal_decisions(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    reader = app.state.journal_reader
    return {"decisions": reader.get_final_decisions(limit=limit, offset=offset)}


@app.get("/api/journal/reviews")
async def journal_reviews(
    packet_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    reader = app.state.journal_reader
    return {"reviews": reader.get_trader_reviews(packet_id=packet_id, limit=limit)}


@app.get("/api/journal/packets")
async def journal_packets(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    reader = app.state.journal_reader
    return {"packets": reader.get_setup_packets(limit=limit, offset=offset)}


@app.get("/api/journal/packets/{packet_id}")
async def journal_packet_detail(packet_id: str):
    reader = app.state.journal_reader
    packet = reader.get_setup_packet(packet_id)
    if packet is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    reviews = reader.get_trader_reviews(packet_id=packet_id)
    return {"packet": packet, "reviews": reviews}


@app.get("/api/journal/attributions")
async def journal_attributions(limit: int = Query(20, ge=1, le=200)):
    reader = app.state.journal_reader
    return {"attributions": reader.get_outcome_attributions(limit=limit)}


@app.get("/api/journal/calibration")
async def journal_calibration():
    reader = app.state.journal_reader
    return {"calibration": reader.get_calibration_records()}


# ─── Tests ────────────────────────────────────────────────────────────────────

@app.get("/api/tests/list")
async def tests_list():
    tr = get_test_runner()
    if tr is None:
        return {"files": []}
    return {"files": tr.list_files()}


@app.post("/api/tests/run")
async def tests_run(body: dict = None):
    tr = get_test_runner()
    if tr is None:
        return JSONResponse({"error": "TestRunner not initialized."}, status_code=503)
    files = (body or {}).get("files", None)
    run_id = await tr.run(files=files)
    return {"run_id": run_id, "message": "Test run started."}


@app.get("/api/tests/results")
async def tests_results():
    tr = get_test_runner()
    if tr is None:
        return {"results": []}
    return {"results": tr.list_results()}


@app.get("/api/tests/result/{run_id}")
async def tests_result(run_id: str):
    tr = get_test_runner()
    if tr is None:
        return JSONResponse({"error": "TestRunner not initialized."}, status_code=503)
    r = tr.get_result(run_id)
    if r is None:
        return JSONResponse({"error": "run_id not found"}, status_code=404)
    return r


# ─── Replay ───────────────────────────────────────────────────────────────────

@app.get("/api/replay/fixtures")
async def replay_fixtures():
    rm = get_replay_manager()
    return {"fixtures": rm.list_fixtures()}


@app.post("/api/replay/run")
async def replay_run(body: dict = None):
    rm = get_replay_manager()
    b = body or {}
    fixture_id = b.get("fixture_id", "btc_bull_breakout_v1")
    harness_type = b.get("harness_type", "simulation")
    run_id = await rm.run(fixture_id=fixture_id, harness_type=harness_type)
    return {"run_id": run_id, "message": "Replay started."}


@app.get("/api/replay/results")
async def replay_results():
    rm = get_replay_manager()
    return {"results": rm.list_results()}


@app.get("/api/replay/result/{run_id}")
async def replay_result(run_id: str):
    rm = get_replay_manager()
    r = rm.get_result(run_id)
    if r is None:
        return JSONResponse({"error": "run_id not found"}, status_code=404)
    return r


# ─── Actions ──────────────────────────────────────────────────────────────────

@app.post("/api/actions/start_runner")
async def action_start_runner(body: dict = None):
    b = body or {}
    simulation_mode = b.get("simulation_mode", True)
    mgr = get_runner_manager()
    result = await mgr.start(simulation_mode=simulation_mode)

    if result["ok"]:
        # Attach event bridge to the new runner's bus
        bridge = get_bridge()
        await bridge.attach(mgr.runner.bus)
        logger.info("EventBridge attached to runner bus.")

    return result


@app.post("/api/actions/stop_runner")
async def action_stop_runner():
    bridge = get_bridge()
    await bridge.detach()
    mgr = get_runner_manager()
    return await mgr.stop()


@app.post("/api/actions/refresh_journal")
async def action_refresh_journal():
    reader = app.state.journal_reader
    ok = reader.reconnect()
    return {"ok": ok, "message": "Journal reader reconnected." if ok else "DB not found."}


@app.post("/api/actions/clear_logs")
async def action_clear_logs():
    get_log_buffer().clear()
    return {"ok": True, "message": "Log buffer cleared."}


# ─── WebSocket Event Stream ────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    """
    Real-time event stream WebSocket.

    On connect:
      1. Server sends recent events from ring buffer.
      2. Server streams new events as they arrive from the EventBus.

    Client can send JSON:
      {"cmd": "filter", "types": ["CandidateTradeEvent", "PanelApprovedProposalEvent"]}
      {"cmd": "ping"}
    """
    await websocket.accept()
    bridge = get_bridge()
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    bridge.subscribe_queue(q)

    # Also stream logs as console events
    log_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    active_filters: set[str] = set()

    try:
        # Send recent history immediately
        recent = bridge.recent_events(limit=100)
        for ev in recent:
            await websocket.send_json(ev)

        # Also send recent log lines as ConsoleLogEvent
        for line in get_log_buffer().recent(limit=50):
            await websocket.send_json({**line, "event_type": "ConsoleLogEvent"})

        # Stream new events
        async def recv_client():
            """Handle commands from the client."""
            nonlocal active_filters
            while True:
                try:
                    data = await websocket.receive_text()
                    msg = json.loads(data)
                    cmd = msg.get("cmd", "")
                    if cmd == "filter":
                        types = msg.get("types", [])
                        active_filters = set(types)
                    elif cmd == "clear_filter":
                        active_filters = set()
                except Exception:
                    break

        recv_task = asyncio.create_task(recv_client())

        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                # Apply type filter if set
                if active_filters and event.get("event_type") not in active_filters:
                    continue
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"event_type": "Heartbeat", "ts": asyncio.get_event_loop().time()})
            except WebSocketDisconnect:
                break
            except Exception:
                break

        recv_task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket error: %s", e)
    finally:
        bridge.unsubscribe_queue(q)
