"""
server/ui_server.py — aiohttp web server for the Thread Visualizer UI.

Serves static UI files, REST endpoints for thread data, and a WebSocket
endpoint for real-time thread state updates.

Architecture: shares the asyncio event loop with FastMCP (started as a
concurrent task in server/main.py). Never blocks the MCP control plane.
"""
from __future__ import annotations
import asyncio
import errno
import json
import logging
import re
from pathlib import Path
from typing import Set

from aiohttp import web, WSMsgType

_THREAD_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent.parent / "ui"
PORT = 8765

# ── Global state ────────────────────────────────────────────────────────────
# Shared across the process lifetime; safe because asyncio is single-threaded.
ui_available: bool = False
_seq: int = 0  # monotonic broadcast sequence counter


# ── WebSocket manager ────────────────────────────────────────────────────────

class WsManager:
    """Registry of connected WebSocket clients with fan-out broadcast."""

    def __init__(self) -> None:
        self._clients: Set[web.WebSocketResponse] = set()

    def connect(self, ws: web.WebSocketResponse) -> None:
        self._clients.add(ws)

    def disconnect(self, ws: web.WebSocketResponse) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        """Send payload to all connected clients. Slow/closed clients are dropped."""
        global _seq
        _seq += 1
        # Copy to avoid mutating the caller's dict
        outbound = {**payload, "seq": _seq}
        text = json.dumps(outbound)

        dead: list[web.WebSocketResponse] = []
        for ws in list(self._clients):
            if ws.closed:
                dead.append(ws)
                continue
            try:
                await asyncio.wait_for(ws.send_str(text), timeout=0.5)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    @property
    def count(self) -> int:
        return len(self._clients)


# Module-level singleton — imported by tools that need to broadcast.
ws_manager = WsManager()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_threads() -> list[dict]:
    """Fetch current thread list from storage. Returns [] on any error."""
    try:
        from .tools.tylor import list_threads
        result = list_threads()
        raw = result.get("threads", [])
        return [
            {
                "id":            t.get("thread_id", ""),
                "title":         t.get("name", ""),
                "status":        t.get("status", "idle"),
                "created_at":    t.get("last_activity", ""),
                "message_count": t.get("message_count", 0),
            }
            for t in raw
        ]
    except Exception as exc:
        logger.warning("ui_server: could not fetch threads: %s", exc)
        return []


def _fetch_messages(thread_id: str, limit: int = 50) -> list[dict]:
    """Fetch the last `limit` messages for a thread. Returns [] on any error."""
    try:
        from . import config
        from .storage.dynamo import DynamoClient

        db = DynamoClient(
            table_name=config.get("dynamo_table", "agent101"),
            user_id=config.get("user_id", "default"),
            profile=config.get("aws_profile"),
        )
        prefix = f"THREAD#{thread_id}#MSG#"
        items = db.query_all(prefix)
        items.sort(key=lambda i: i.get("SK", ""))
        tail = items[-limit:]
        return [
            {
                "role":      i.get("Role", "unknown"),
                "content":   i.get("Content", ""),
                "timestamp": i.get("CreatedAt", ""),
            }
            for i in tail
        ]
    except Exception as exc:
        logger.warning("ui_server: could not fetch messages for %s: %s", thread_id, exc)
        return []


async def thread_update_payload() -> dict:
    """Build the standard thread_update broadcast payload."""
    return {
        "type":    "thread_update",
        "threads": _fetch_threads(),
    }


# ── Route handlers ───────────────────────────────────────────────────────────

async def handle_index(request: web.Request) -> web.Response:
    index = UI_DIR / "index.html"
    if not index.exists():
        return web.Response(status=404, text="UI not built — run: cd ui && npm run build")
    return web.FileResponse(index)


async def handle_threads(request: web.Request) -> web.Response:
    loop = asyncio.get_running_loop()
    threads = await loop.run_in_executor(None, _fetch_threads)
    return web.json_response(threads)


async def handle_thread_messages(request: web.Request) -> web.Response:
    thread_id = request.match_info["thread_id"]
    if not _THREAD_ID_RE.match(thread_id):
        return web.json_response({"error": "invalid thread_id"}, status=400)
    loop = asyncio.get_running_loop()
    messages = await loop.run_in_executor(None, _fetch_messages, thread_id)
    return web.json_response(messages)


async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    ws_manager.connect(ws)
    logger.debug("ui_server: WS client connected (total=%d)", ws_manager.count)

    # Send full thread state immediately on connect (seq=0 = initial snapshot)
    loop = asyncio.get_running_loop()
    threads_now = await loop.run_in_executor(None, _fetch_threads)
    initial = {"type": "thread_update", "threads": threads_now, "seq": 0}
    await ws.send_str(json.dumps(initial))

    try:
        async for msg in ws:
            if msg.type == WSMsgType.PING:
                await ws.pong(msg.data)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break
    finally:
        ws_manager.disconnect(ws)
        logger.debug("ui_server: WS client disconnected (total=%d)", ws_manager.count)

    return ws


# ── App factory ──────────────────────────────────────────────────────────────

def _make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/",                            handle_index)
    app.router.add_get("/api/threads",                 handle_threads)
    app.router.add_get("/api/threads/{thread_id}/messages", handle_thread_messages)
    app.router.add_get("/ws/threads",                  handle_websocket)

    # Serve static assets from ui/ (dist/ when built, raw files in dev)
    if UI_DIR.exists():
        app.router.add_static("/", UI_DIR, show_index=False, follow_symlinks=False)

    return app


# ── Startup / shutdown ───────────────────────────────────────────────────────

async def start_ui_server() -> web.AppRunner | None:
    """
    Start the aiohttp UI server on PORT.
    Returns the AppRunner on success, None if port is in use.
    Sets module-level `ui_available` accordingly.
    """
    global ui_available

    app = _make_app()
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()

    site = web.TCPSite(runner, "localhost", PORT)
    try:
        await site.start()
        ui_available = True
        logger.info("ui_server: Thread Visualizer running at http://localhost:%d", PORT)
        return runner
    except OSError as exc:
        await runner.cleanup()
        ui_available = False
        if exc.errno == errno.EADDRINUSE:
            logger.warning(
                "ui_server: port %d already in use — Thread Visualizer unavailable. "
                "MCP tools continue to work normally.",
                PORT,
            )
        else:
            logger.warning(
                "ui_server: could not start on port %d (%s) — Thread Visualizer unavailable.",
                PORT, exc,
            )
        return None
