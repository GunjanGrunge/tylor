"""
server/tests/test_ui_server.py — Tests for Story 6.1: Local UI Server.

Tests:
- GET / serves index.html (200) or 404 if missing
- GET /api/threads returns JSON array
- GET /api/threads/{id}/messages returns JSON array
- WS /ws/threads: initial payload on connect
- WS broadcast: all clients receive update
- Port-in-use: server starts gracefully, ui_available = False
"""
import asyncio
import json
import socket
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web


# ── Fixture helpers ──────────────────────────────────────────────────────────

MOCK_THREADS = [
    {"thread_id": "abc123", "name": "Backend", "status": "active",
     "last_activity": "2026-05-13T10:00:00Z", "message_count": 5},
    {"thread_id": "def456", "name": "Frontend", "status": "idle",
     "last_activity": "2026-05-13T09:00:00Z", "message_count": 2},
]

MOCK_MESSAGES = [
    {"role": "user", "content": "Hello", "timestamp": "2026-05-13T09:00:00Z"},
    {"role": "assistant", "content": "Hi there", "timestamp": "2026-05-13T09:01:00Z"},
]


def _mock_list_threads():
    return {"threads": MOCK_THREADS}


def _mock_fetch_messages(thread_id, limit=50):
    if thread_id == "abc123":
        return MOCK_MESSAGES
    return []


# ── Test: REST endpoints ──────────────────────────────────────────────────────

class TestRestEndpoints(AioHTTPTestCase):

    async def get_application(self):
        # Patch storage calls before building the app
        with patch("server.ui_server._fetch_threads", return_value=[
            {"id": t["thread_id"], "title": t["name"], "status": t["status"],
             "created_at": t["last_activity"], "message_count": t["message_count"]}
            for t in MOCK_THREADS
        ]):
            from ..ui_server import _make_app
            return _make_app()

    async def test_get_threads_returns_json_array(self):
        with patch("server.ui_server._fetch_threads", return_value=[
            {"id": "abc123", "title": "Backend", "status": "active",
             "created_at": "2026-05-13T10:00:00Z", "message_count": 5}
        ]):
            resp = await self.client.get("/api/threads")
            assert resp.status == 200
            data = await resp.json()
            assert "projects" in data
            thread = data["projects"][0]["threads"][0]
            assert thread["id"] == "abc123"
            assert thread["title"] == "Backend"

    async def test_get_messages_returns_json_array(self):
        with patch("server.ui_server._fetch_messages", return_value=MOCK_MESSAGES):
            resp = await self.client.get("/api/threads/abc123/messages")
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, list)
            assert data[0]["role"] == "user"

    async def test_get_index_404_when_missing(self):
        with patch.object(Path, "exists", return_value=False):
            resp = await self.client.get("/")
            assert resp.status == 404


# ── Test: WebSocket ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_websocket_initial_payload():
    """Client receives full thread list on connect."""
    from ..ui_server import _make_app, WsManager
    import aiohttp
    from aiohttp.test_utils import TestServer, TestClient

    app = _make_app()

    with patch("server.ui_server._fetch_threads", return_value=[
        {"id": "abc123", "title": "Backend", "status": "active",
         "created_at": "2026-05-13T10:00:00Z", "message_count": 5}
    ]):
        async with TestClient(TestServer(app)) as client:
            ws = await client.ws_connect("/ws/threads")
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
            data = json.loads(msg.data)
            assert data["type"] == "thread_update"
            assert "projects" in data
            assert data["projects"][0]["threads"][0]["id"] == "abc123"
            assert "seq" in data
            await ws.close()


@pytest.mark.asyncio
async def test_websocket_broadcast_reaches_all_clients():
    """After broadcast(), all connected clients receive the message."""
    from ..ui_server import WsManager
    import aiohttp
    from aiohttp.test_utils import TestServer, TestClient
    from ..ui_server import _make_app

    app = _make_app()

    with patch("server.ui_server._fetch_threads", return_value=[]):
        async with TestClient(TestServer(app)) as client:
            ws1 = await client.ws_connect("/ws/threads")
            ws2 = await client.ws_connect("/ws/threads")

            # Drain initial payloads
            await asyncio.wait_for(ws1.receive(), timeout=1.0)
            await asyncio.wait_for(ws2.receive(), timeout=1.0)

            # Broadcast a custom payload
            from ..ui_server import ws_manager
            await ws_manager.broadcast({"type": "thread_update", "threads": [{"id": "x1"}]})

            msg1 = await asyncio.wait_for(ws1.receive(), timeout=1.0)
            msg2 = await asyncio.wait_for(ws2.receive(), timeout=1.0)

            d1 = json.loads(msg1.data)
            d2 = json.loads(msg2.data)
            assert d1["threads"][0]["id"] == "x1"
            assert d2["threads"][0]["id"] == "x1"
            assert d1["seq"] == d2["seq"]

            await ws1.close()
            await ws2.close()


# ── Test: Port-in-use ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_port_in_use_sets_ui_unavailable():
    """When port 8765 is occupied, start_ui_server returns None and ui_available=False."""
    import server.ui_server as ui_mod

    # Occupy the port
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        blocker.bind(("localhost", 8765))
        blocker.listen(1)

        runner = await ui_mod.start_ui_server()
        assert runner is None
        assert ui_mod.ui_available is False
    finally:
        blocker.close()
        # Reset for other tests
        ui_mod.ui_available = False


# ── Test: WsManager ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ws_manager_drops_closed_clients():
    """WsManager removes clients that fail to receive."""
    from ..ui_server import WsManager

    mgr = WsManager()

    # Mock a closed WebSocket
    dead_ws = MagicMock()
    dead_ws.closed = True

    mgr.connect(dead_ws)
    assert mgr.count == 1

    await mgr.broadcast({"type": "test"})
    # Dead client should be dropped
    assert mgr.count == 0


@pytest.mark.asyncio
async def test_ws_manager_sequence_increments():
    """Each broadcast increments the seq counter."""
    from ..ui_server import WsManager
    import server.ui_server as ui_mod

    ui_mod._seq = 0
    mgr = WsManager()

    received = []
    live_ws = MagicMock()
    live_ws.closed = False

    async def fake_send(text):
        received.append(json.loads(text))

    live_ws.send_str = fake_send
    mgr.connect(live_ws)

    await mgr.broadcast({"type": "thread_update", "threads": []})
    await mgr.broadcast({"type": "thread_update", "threads": []})

    assert received[0]["seq"] == 1
    assert received[1]["seq"] == 2


# ── Story 6.2: API shape tests ────────────────────────────────────────────────

FULL_MOCK_THREADS = [
    {"id": "abc123def456abc123def456abc12345", "title": "Backend",
     "status": "active", "created_at": "2026-05-13T10:00:00Z", "message_count": 5},
    {"id": "def456abc123def456abc123def45678", "title": "Frontend",
     "status": "idle", "created_at": "2026-05-13T09:00:00Z", "message_count": 2},
]


@pytest.mark.asyncio
async def test_api_threads_returns_all_five_fields():
    """GET /api/threads returns {projects:[{id,name,threads:[...]}]} grouped by project."""
    from ..ui_server import _make_app
    from aiohttp.test_utils import TestServer, TestClient

    app = _make_app()
    with patch("server.ui_server._fetch_threads", return_value=FULL_MOCK_THREADS):
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/threads")
            assert resp.status == 200
            data = await resp.json()
            assert "projects" in data
            all_threads = [t for p in data["projects"] for t in p["threads"]]
            assert len(all_threads) == 2
            for t in all_threads:
                assert "id" in t
                assert "title" in t
                assert "status" in t
                assert "created_at" in t
                assert "message_count" in t


@pytest.mark.asyncio
async def test_api_threads_returns_empty_list_not_null():
    """GET /api/threads with no threads returns {projects:[]} not null."""
    from ..ui_server import _make_app
    from aiohttp.test_utils import TestServer, TestClient

    app = _make_app()
    with patch("server.ui_server._fetch_threads", return_value=[]):
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/threads")
            assert resp.status == 200
            data = await resp.json()
            assert "projects" in data
            assert data["projects"] == []


@pytest.mark.asyncio
async def test_api_thread_messages_valid_id_returns_array():
    """GET /api/threads/{id}/messages with valid hex id returns array."""
    from ..ui_server import _make_app
    from aiohttp.test_utils import TestServer, TestClient

    app = _make_app()
    valid_id = "abc123def456abc123def456abc12345"
    mock_msgs = [
        {"role": "user", "content": "Hello", "timestamp": "2026-05-13T09:00:00Z"},
    ]
    with patch("server.ui_server._fetch_messages", return_value=mock_msgs):
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(f"/api/threads/{valid_id}/messages")
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, list)
            assert data[0]["role"] == "user"


# ── Story 6.4: message shape tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_thread_messages_returns_role_content_timestamp():
    """GET /api/threads/{id}/messages returns [{role, content, timestamp}]."""
    from ..ui_server import _make_app
    from aiohttp.test_utils import TestServer, TestClient

    app = _make_app()
    valid_id = "abc123def456abc123def456abc12345"
    mock_msgs = [
        {"role": "user",      "content": "Hello",    "timestamp": "2026-05-13T09:00:00Z"},
        {"role": "assistant", "content": "Hi there", "timestamp": "2026-05-13T09:01:00Z"},
    ]
    with patch("server.ui_server._fetch_messages", return_value=mock_msgs):
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(f"/api/threads/{valid_id}/messages")
            assert resp.status == 200
            data = await resp.json()
            assert isinstance(data, list)
            for msg in data:
                assert "role"      in msg
                assert "content"   in msg
                assert "timestamp" in msg


@pytest.mark.asyncio
async def test_api_thread_messages_before_param_accepted():
    """GET /api/threads/{id}/messages?before=<ts> is accepted (pagination)."""
    from ..ui_server import _make_app
    from aiohttp.test_utils import TestServer, TestClient

    app = _make_app()
    valid_id = "abc123def456abc123def456abc12345"
    with patch("server.ui_server._fetch_messages", return_value=[]):
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                f"/api/threads/{valid_id}/messages?before=2026-05-13T09:00:00Z"
            )
            assert resp.status == 200


# ── Story 6.5: Live state sync tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_ws_thread_update_broadcasts_to_all_clients():
    """After a thread state change, all WS clients receive thread_update."""
    from ..ui_server import _make_app, ws_manager
    from aiohttp.test_utils import TestServer, TestClient
    import server.ui_server as ui_mod

    app = _make_app()
    with patch("server.ui_server._fetch_threads", return_value=[
        {"id": "abc123", "title": "Backend", "status": "active",
         "created_at": "2026-05-13T10:00:00Z", "message_count": 5}
    ]):
        async with TestClient(TestServer(app)) as client:
            ws1 = await client.ws_connect("/ws/threads")
            ws2 = await client.ws_connect("/ws/threads")
            # Drain initial payloads
            await asyncio.wait_for(ws1.receive(), timeout=1.0)
            await asyncio.wait_for(ws2.receive(), timeout=1.0)

            # Simulate thread status change broadcast
            await ws_manager.broadcast({
                "type": "thread_update",
                "threads": [{"id": "abc123", "title": "Backend", "status": "killed",
                              "created_at": "2026-05-13T10:00:00Z", "message_count": 5}]
            })

            m1 = await asyncio.wait_for(ws1.receive(), timeout=1.0)
            m2 = await asyncio.wait_for(ws2.receive(), timeout=1.0)
            d1 = json.loads(m1.data)
            d2 = json.loads(m2.data)
            assert d1["type"] == "thread_update"
            assert d1["threads"][0]["status"] == "killed"
            assert d2["threads"][0]["status"] == "killed"
            await ws1.close(); await ws2.close()


@pytest.mark.asyncio
async def test_ws_initial_payload_has_thread_update_type():
    """Initial WS payload on connect uses type=thread_update."""
    from ..ui_server import _make_app
    from aiohttp.test_utils import TestServer, TestClient

    app = _make_app()
    with patch("server.ui_server._fetch_threads", return_value=[]):
        async with TestClient(TestServer(app)) as client:
            ws = await client.ws_connect("/ws/threads")
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
            data = json.loads(msg.data)
            assert data["type"] == "thread_update"
            assert "projects" in data
            assert isinstance(data["projects"], list)
            await ws.close()
