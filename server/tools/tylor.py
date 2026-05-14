"""
server/tools/tylor.py — Tier 1 thread lifecycle MCP tools.
FR1-FR8: new_thread, switch_thread, kill_thread, recall_memory, list_threads.

Stories 2.3–2.5 implement storage. switch_thread (2.4), kill_thread (2.7),
recall_memory (2.5) remain stubs until their stories are implemented.
"""
import re
import asyncio
import uuid
from datetime import datetime, timezone

from mcp.server.fastmcp.exceptions import ToolError

from server.tools._mcp import mcp
from server.tools.summarizer import summarize_thread
from server.tools.thread_resolver import resolve_thread_name


# ---------------------------------------------------------------------------
# Broadcast helper
# ---------------------------------------------------------------------------

_broadcast_tasks: set = set()  # holds task refs to prevent GC before completion


def _broadcast_thread_update() -> None:
    """Fire-and-forget WebSocket broadcast after any thread state change."""
    try:
        from server.ui_server import ws_manager, thread_update_payload, ui_available
        if not ui_available or ws_manager.count == 0:
            return
        loop = asyncio.get_running_loop()
        task = loop.create_task(_do_broadcast())
        _broadcast_tasks.add(task)
        task.add_done_callback(_broadcast_tasks.discard)
    except RuntimeError:
        pass  # no running loop — broadcast not possible from this context
    except Exception:
        pass  # broadcast is best-effort; never break MCP tool execution


async def _do_broadcast() -> None:
    from server.ui_server import ws_manager, thread_update_payload
    payload = await thread_update_payload()
    await ws_manager.broadcast(payload)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NAME_MIN = 3
NAME_MAX = 64
_NAME_RE = re.compile(r"^[a-zA-Z0-9 _-]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_name(name: str) -> None:
    """Raise ToolError if name fails length / character / whitespace rules."""
    if not (NAME_MIN <= len(name) <= NAME_MAX):
        raise ToolError("Thread name must be 3–64 characters")
    if not name.strip():
        raise ToolError("Thread name contains invalid characters")
    if not _NAME_RE.match(name):
        raise ToolError("Thread name contains invalid characters")


def _get_db():
    """Return a DynamoClient configured from server.config."""
    from server.config import config
    from server.storage.dynamo import DynamoClient

    return DynamoClient(
        table_name=config.get("dynamo_table", "agent101"),
        user_id=config.get("user_id", "default"),
        profile=config.get("aws_profile"),
    )


def _get_memory_client():
    """Return an OpenSearchClient configured from server.config."""
    from server.config import config
    from server.storage.opensearch import OpenSearchClient

    host = config.get("opensearch_host")
    if not host:
        raise ToolError("OPENSEARCH_HOST not configured")

    port = int(config.get("opensearch_port", "9200"))
    return OpenSearchClient(
        host=host,
        port=port,
        bedrock_region=config.get("bedrock_region", "us-east-1"),
        profile=config.get("aws_profile"),
    )


def _code_index_header_for_thread(thread_id: str, thread_name: str = "") -> str:
    try:
        from server.tools.hooks import build_code_index_header

        return build_code_index_header(thread_id, thread_name)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def new_thread(name: str) -> dict:
    """
    Create a new named thread.
    Returns the new thread's ID and metadata.

    Args:
        name: Human-readable name for the thread (e.g. "project-alpha", "weekly-review").
              Must be 3–64 characters; alphanumeric, spaces, hyphens, underscores only.
    """
    _validate_name(name)

    db = _get_db()

    # Uniqueness check — query all META items before writing
    existing = db.query_all("THREAD#")
    for item in existing:
        if item.get("SK", "").endswith("#META") and item.get("Name") == name:
            raise ToolError("Thread name already exists")

    thread_id = uuid.uuid4().hex
    sk = f"THREAD#{thread_id}#META"
    now = _now_iso()

    written = db.put_item(sk, {
        "Name": name,
        "Status": "active",
        "LastActivity": now,
        "MessageCount": 0,
    })

    result = {
        "thread_id": thread_id,
        "name": name,
        "created_at": written["CreatedAt"],
    }
    _broadcast_thread_update()
    return result


@mcp.tool()
def switch_thread(thread_id: str) -> dict:
    """
    Atomically switch to an existing thread, making it the active context.
    Uses DynamoDB TransactWriteItems — partial writes fail explicitly.

    Args:
        thread_id: The unique ID of the thread to switch to.

    Returns a dict. If the field ``code_index_header`` is present, prepend its
    value verbatim to your context before continuing — it is the compact code
    index for the thread you just switched into.
    """
    db = _get_db()
    try:
        result = db.switch_thread(thread_id)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            f"SwThread failed — both threads unchanged: {exc}"
        ) from exc
    meta = db.get_thread_meta(thread_id) or {}
    header = _code_index_header_for_thread(thread_id, meta.get("Name", result.get("name", "")))
    if header:
        result = {**result, "code_index_header": header}
    _broadcast_thread_update()
    return result


@mcp.tool()
def switch_thread_by_name(query: str) -> dict:
    """
    Resolve a fuzzy thread-name query and switch to the matched thread.
    Ambiguous matches are returned for Claude to present to the user.

    Args:
        query: Partial or approximate thread name.
    """
    db = _get_db()
    all_items = db.query_all("THREAD#")
    meta_items = [i for i in all_items if i.get("SK", "").endswith("#META")]
    threads = []
    for item in meta_items:
        sk = item.get("SK", "")
        threads.append({
            "thread_id": sk.removeprefix("THREAD#").removesuffix("#META"),
            "name": item.get("Name", ""),
            "status": item.get("Status", "active"),
            "last_activity": item.get("LastActivity", item.get("UpdatedAt", "")),
            "message_count": int(item.get("MessageCount", 0)),
        })

    try:
        resolved = resolve_thread_name(query, threads)
    except ToolError:
        raise
    except Exception as exc:
        # Let McpError propagate with its original error code intact
        raise
    if resolved["status"] == "ambiguous":
        return resolved

    try:
        switched = db.switch_thread(resolved["thread_id"])
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            f"SwThread failed — both threads unchanged: {exc}"
        ) from exc
    header = _code_index_header_for_thread(resolved["thread_id"], resolved.get("name", ""))
    return {
        **switched,
        "name": resolved["name"],
        "message": resolved["message"],
        **({"code_index_header": header} if header else {}),
    }


@mcp.tool()
def kill_thread(thread_id: str) -> dict:
    """
    Close a thread and trigger async Bedrock Opus summarization.
    Returns immediately; summarization is dispatched via the PostToolUse hook.

    Args:
        thread_id: The unique ID of the thread to kill.
    """
    db = _get_db()
    if not db.get_thread_meta(thread_id):
        raise ToolError(f"Thread not found: {thread_id}")

    # Summarization is dispatched by the kill-thread-trigger PostToolUse hook
    # (hooks/kill-thread-trigger.sh → hooks.dispatch_kill_thread_summary).
    # Do NOT also create_task here — that would cause double-summarization.
    _broadcast_thread_update()
    return {
        "status": "killing",
        "thread_id": thread_id,
        "message": "Summarization in progress",
    }


@mcp.tool()
def save_memory(thread_id: str, fact: str, fact_type: str | None = None) -> dict:
    """
    Save a memory fact for a thread, optionally tagged by category.

    Args:
        thread_id: Thread this fact belongs to.
        fact: Compact fact to persist.
        fact_type: Optional category such as "code_index".
    """
    if not fact or not fact.strip():
        raise ToolError("Fact must not be empty")
    metadata = {"type": fact_type} if fact_type else None
    memory_id = _get_memory_client().index_memory(
        thread_id=thread_id,
        fact=fact,
        metadata=metadata,
    )
    return {"status": "saved", "thread_id": thread_id, "memory_id": memory_id, "type": fact_type}


@mcp.tool()
def recall_memory(thread_id: str, query: str, top_k: int = 5, fact_type: str | None = None) -> dict:
    """
    Semantically search thread memory using OpenSearch vector similarity.
    Returns the top-k most relevant memory facts for the given query.

    Args:
        thread_id: The thread to search within.
        query: Natural-language search query.
        top_k: Maximum number of results to return (default: 5).
        fact_type: Optional category filter, e.g. "code_index" to retrieve only
                   structural code facts instead of conversation memory.
    """
    if not query or not query.strip():
        raise ToolError("Query must not be empty")
    if top_k <= 0:
        raise ToolError("top_k must be a positive integer")

    client = _get_memory_client()
    results = client.search_memory(thread_id=thread_id, query=query, k=top_k, type=fact_type)
    return {"results": results}


@mcp.tool()
def list_threads() -> dict:
    """
    List all threads with their status, name, and last-activity timestamp.
    Returns threads sorted by last activity descending.
    """
    db = _get_db()

    all_items = db.query_all("THREAD#")
    meta_items = [i for i in all_items if i.get("SK", "").endswith("#META")]

    threads = []
    for item in meta_items:
        sk = item.get("SK", "")
        thread_id = sk.removeprefix("THREAD#").removesuffix("#META")
        threads.append({
            "thread_id": thread_id,
            "name": item.get("Name", ""),
            "status": item.get("Status", "active"),
            "last_activity": item.get("LastActivity", item.get("UpdatedAt", "")),
            "message_count": int(item.get("MessageCount", 0)),
        })

    threads.sort(key=lambda t: t["last_activity"], reverse=True)
    return {"threads": threads}
