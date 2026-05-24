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
PORT = 8765          # updated to the actual bound port on startup
PORT_RANGE = (8765, 8775)  # try these ports in order

# ── Global state ────────────────────────────────────────────────────────────
# Shared across the process lifetime; safe because asyncio is single-threaded.
ui_available: bool = False
_seq: int = 0  # monotonic broadcast sequence counter
_ui_loop: asyncio.AbstractEventLoop | None = None


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


def broadcast_from_any_thread(payload: dict) -> None:
    """Best-effort WebSocket broadcast callable from sync MCP tools/threads."""
    if _ui_loop is None or _ui_loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(ws_manager.broadcast(payload), _ui_loop)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _flatten_content(raw) -> str:
    """Flatten a Content field that may be a string, list of dicts, or list of typed blocks."""
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for b in raw:
            if isinstance(b, dict):
                parts.append(b.get("text", ""))
            elif hasattr(b, "text"):
                parts.append(b.text)
            else:
                parts.append(str(b))
        return " ".join(parts)
    return str(raw)


def _fetch_threads() -> list[dict]:
    """Fetch current thread list from storage. Returns [] on any error."""
    try:
        from .tools.tylor import list_threads, _get_db
        result = list_threads()
        raw = result.get("threads", [])
        db = _get_db()  # single client for all queries
        threads = []
        for t in raw:
            thread_id = t.get("thread_id", "")
            last_message = ""
            try:
                prefix = f"THREAD#{thread_id}#MSG#"
                items = db.query_all(prefix)
                if items:
                    items.sort(key=lambda i: i.get("SK", ""))
                    last_message = _flatten_content(items[-1].get("Content", ""))[:80]
            except Exception:
                pass
            agents = _fetch_agents(thread_id) if thread_id else []
            active_agents = [a for a in agents if a.get("status") in {"active", "running"}]
            threads.append({
                "id":            thread_id,
                "title":         t.get("name", ""),
                "status":        t.get("status", "idle"),
                "created_at":    t.get("last_activity", ""),
                "message_count": t.get("message_count", 0),
                "project":       t.get("project", ""),
                "last_message":  last_message,
                "agent_count":   len(agents),
                "active_agent_count": len(active_agents),
                "agents":        agents,
            })
        return threads
    except Exception as exc:
        logger.warning("ui_server: could not fetch threads: %s", exc)
        return []


def _group_threads_by_project(threads: list[dict]) -> list[dict]:
    """Group flat thread list into project buckets for the UI."""
    from collections import OrderedDict
    buckets: OrderedDict = OrderedDict()
    for t in threads:
        proj = t.get("project") or "default"
        if proj not in buckets:
            buckets[proj] = []
        buckets[proj].append(t)
    return [
        {"id": name, "name": name, "threads": ts}
        for name, ts in buckets.items()
    ]


def _fetch_messages(thread_id: str, limit: int = 50, before: str | None = None) -> list[dict]:
    """Fetch the last `limit` messages for a thread, optionally before a timestamp.

    `before` is an ISO timestamp string (CreatedAt of the oldest message already
    shown in the UI). Only messages strictly older than `before` are returned,
    enabling "load earlier" pagination without re-fetching the same items.
    """
    try:
        from .tools.tylor import _get_db
        db = _get_db()
        prefix = f"THREAD#{thread_id}#MSG#"
        items = db.query_all(prefix)
        items.sort(key=lambda i: i.get("SK", ""))
        if before:
            items = [i for i in items if i.get("CreatedAt", "") < before]
        tail = items[-limit:]
        return [
            {
                "role":      i.get("Role", "unknown"),
                "content":   _flatten_content(i.get("Content", "")),
                "timestamp": i.get("CreatedAt", ""),
            }
            for i in tail
        ]
    except Exception as exc:
        logger.warning("ui_server: could not fetch messages for %s: %s", thread_id, exc)
        return []


def _fetch_current_thread_id() -> str | None:
    """Return the ID of the currently active thread, or None."""
    try:
        from .tools.tylor import _get_db
        db = _get_db()
        marker = db.get_current_thread_marker()
        return marker.get("CurrentThreadId") if marker else None
    except Exception:
        return None


def _normalise_agent_state(item: dict, latest_event: dict | None = None) -> dict:
    return {
        "agent_id": item.get("AgentId", ""),
        "persona": item.get("Persona", ""),
        "status": str(item.get("Status", "unknown")).lower(),
        "task": item.get("Task", ""),
        "tools_loaded": item.get("ToolsLoaded", []),
        "updated_at": item.get("UpdatedAt", item.get("CreatedAt", "")),
        "last_event": _flatten_content((latest_event or {}).get("Content", ""))[:160],
        "last_event_type": (latest_event or {}).get("EventType", ""),
    }


def _fetch_agents(thread_id: str) -> list[dict]:
    """Fetch agent states and latest streamed events for a thread."""
    try:
        from .tools.tylor import _get_db
        db = _get_db()
        states = db.query_agent_states(thread_id) if hasattr(db, "query_agent_states") else []
        events = db.query_agent_events(thread_id) if hasattr(db, "query_agent_events") else []
        latest_by_agent: dict[str, dict] = {}
        for event in events:
            aid = event.get("AgentId")
            if aid:
                latest_by_agent[aid] = event
        return [
            _normalise_agent_state(state, latest_by_agent.get(state.get("AgentId", "")))
            for state in states
        ]
    except Exception as exc:
        logger.warning("ui_server: could not fetch agents for %s: %s", thread_id, exc)
        return []


def _fetch_agent_events(thread_id: str, agent_id: str | None = None, limit: int = 200) -> list[dict]:
    """Fetch streamed verbose events for one thread or one agent."""
    try:
        from .tools.tylor import _get_db
        db = _get_db()
        if hasattr(db, "query_agent_events"):
            items = db.query_agent_events(thread_id, agent_id)
        else:
            prefix = f"THREAD#{thread_id}#AGENT#"
            if agent_id:
                prefix += f"{agent_id}#EVENT#"
            items = [i for i in db.query_all(prefix) if "#EVENT#" in i.get("SK", "")]
            items.sort(key=lambda i: i.get("SK", ""))
        return [
            {
                "thread_id": item.get("ThreadId", thread_id),
                "agent_id": item.get("AgentId", ""),
                "persona": item.get("Persona", ""),
                "event_type": item.get("EventType", "chunk"),
                "content": _flatten_content(item.get("Content", "")),
                "timestamp": item.get("CreatedAt", item.get("UpdatedAt", "")),
            }
            for item in items[-limit:]
        ]
    except Exception as exc:
        logger.warning("ui_server: could not fetch agent events for %s/%s: %s", thread_id, agent_id, exc)
        return []


async def thread_update_payload() -> dict:
    """Build the standard thread_update broadcast payload."""
    threads = _fetch_threads()
    current_id = _fetch_current_thread_id()
    return {
        "type":             "thread_update",
        "projects":         _group_threads_by_project(threads),
        "current_thread_id": current_id,
    }


# ── Route handlers ───────────────────────────────────────────────────────────

async def handle_index(request: web.Request) -> web.Response:
    index = UI_DIR / "index.html"
    if not index.exists():
        return web.Response(status=404, text="UI not built — run: cd ui && npm run build")
    # Inject the actual bound port so API/WS URLs are always correct,
    # even when the server falls back to a non-default port (e.g. 8766).
    html = index.read_text(encoding="utf-8")
    html = html.replace(
        "const API = 'http://localhost:8765'",
        f"const API = 'http://localhost:{PORT}'"
    ).replace(
        "const WS  = 'ws://localhost:8765/ws/threads'",
        f"const WS  = 'ws://localhost:{PORT}/ws/threads'"
    )
    return web.Response(text=html, content_type="text/html",
                        headers={"Cache-Control": "no-store"})


async def handle_threads(request: web.Request) -> web.Response:
    loop = asyncio.get_running_loop()
    threads = await loop.run_in_executor(None, _fetch_threads)
    projects = _group_threads_by_project(threads)
    current_id = await loop.run_in_executor(None, _fetch_current_thread_id)
    return web.json_response({"projects": projects, "current_thread_id": current_id})


async def handle_thread_messages(request: web.Request) -> web.Response:
    thread_id = request.match_info["thread_id"]
    if not _THREAD_ID_RE.match(thread_id):
        return web.json_response({"error": "invalid thread_id"}, status=400)
    before = request.rel_url.query.get("before") or None
    loop = asyncio.get_running_loop()
    messages = await loop.run_in_executor(None, _fetch_messages, thread_id, 50, before)
    return web.json_response(messages)


async def handle_thread_agents(request: web.Request) -> web.Response:
    thread_id = request.match_info["thread_id"]
    if not _THREAD_ID_RE.match(thread_id):
        return web.json_response({"error": "invalid thread_id"}, status=400)
    loop = asyncio.get_running_loop()
    agents = await loop.run_in_executor(None, _fetch_agents, thread_id)
    return web.json_response({"agents": agents})


async def handle_thread_agent_events(request: web.Request) -> web.Response:
    thread_id = request.match_info["thread_id"]
    agent_id = request.match_info.get("agent_id")
    if not _THREAD_ID_RE.match(thread_id) or (agent_id and not _THREAD_ID_RE.match(agent_id)):
        return web.json_response({"error": "invalid id"}, status=400)
    loop = asyncio.get_running_loop()
    events = await loop.run_in_executor(None, _fetch_agent_events, thread_id, agent_id, 200)
    return web.json_response({"events": events})


async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    ws_manager.connect(ws)
    logger.debug("ui_server: WS client connected (total=%d)", ws_manager.count)

    # Send full thread state immediately on connect (seq=0 = initial snapshot)
    loop = asyncio.get_running_loop()
    threads_now = await loop.run_in_executor(None, _fetch_threads)
    initial = {
        "type": "thread_update",
        "projects": _group_threads_by_project(threads_now),
        "current_thread_id": _fetch_current_thread_id(),
        "seq": 0,
    }
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
    # Simple CORS middleware to allow UI served from other origins (dev)
    @web.middleware
    async def _cors_middleware(request: web.Request, handler):
        # Handle preflight
        if request.method == 'OPTIONS':
            resp = web.Response(status=204)
        else:
            resp = await handler(request)
        # Allow all origins for local development. Narrow this in production.
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        return resp

    app = web.Application(middlewares=[_cors_middleware])
    app.router.add_get("/",                            handle_index)
    app.router.add_get("/api/threads",                 handle_threads)
    app.router.add_get("/api/threads/{thread_id}/messages", handle_thread_messages)
    app.router.add_get("/api/threads/{thread_id}/agents", handle_thread_agents)
    app.router.add_get("/api/threads/{thread_id}/agents/events", handle_thread_agent_events)
    app.router.add_get("/api/threads/{thread_id}/agents/{agent_id}/events", handle_thread_agent_events)
    app.router.add_get("/ws/threads",                  handle_websocket)

    # Serve static assets from ui/ (dist/ when built, raw files in dev)
    if UI_DIR.exists():
        app.router.add_static("/", UI_DIR, show_index=False, follow_symlinks=False)

    return app


# ── Startup / shutdown ───────────────────────────────────────────────────────

async def start_ui_server() -> web.AppRunner | None:
    """
    Start the aiohttp UI server, trying PORT_RANGE in order until one binds.
    Updates the module-level PORT to the actual bound port.
    Returns the AppRunner on success, None if all ports are unavailable.
    Sets module-level `ui_available` accordingly.
    """
    global ui_available, PORT, _ui_loop
    _ui_loop = asyncio.get_running_loop()

    app = _make_app()
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()

    for candidate in range(PORT_RANGE[0], PORT_RANGE[1]):
        site = web.TCPSite(runner, "localhost", candidate)
        try:
            await site.start()
            PORT = candidate
            ui_available = True
            logger.info("ui_server: Thread Visualizer running at http://localhost:%d", PORT)
            return runner
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                logger.debug("ui_server: port %d in use, trying next…", candidate)
                continue
            # Non-EADDRINUSE error — give up immediately
            await runner.cleanup()
            ui_available = False
            logger.warning(
                "ui_server: could not start on port %d (%s) — Thread Visualizer unavailable.",
                candidate, exc,
            )
            return None

    # All ports exhausted
    await runner.cleanup()
    ui_available = False
    logger.warning(
        "ui_server: all ports %d–%d in use — Thread Visualizer unavailable. "
        "MCP tools continue to work normally.",
        PORT_RANGE[0], PORT_RANGE[1] - 1,
    )
    return None
