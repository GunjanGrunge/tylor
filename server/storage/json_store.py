"""
server/storage/json_store.py — Local JSON storage for agent101 threads.

Zero-infra default: all state lives in ~/.tylor/threads.json.
No database, no cloud account, no configuration required.
All writes are atomic (write-to-tmp then os.replace).

This is the default storage backend. DynamoDB is optional for multi-machine sync.
"""
from __future__ import annotations
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

STORE_VERSION = "1.0"
WARN_THRESHOLD = 400 * 1024  # 400 KB

_EMPTY_STORE: dict = {"version": STORE_VERSION, "threads": [], "current_thread_id": None}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_store_path() -> Path:
    return Path.home() / ".tylor" / "threads.json"


class JsonStore:
    """
    Local JSON storage implementing the same interface as DynamoClient
    so tools can use either backend transparently via _get_db().

    Thread data structure:
      {id, name, status, created_at, updated_at, messages[], summary,
       sandbox_roots[], current: bool, agent_states{}, agent_outputs[]}
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _default_store_path()

    # ── Internal load/save ─────────────────────────────────────────────

    def _load(self) -> dict:
        import copy
        if not self.path.exists():
            return copy.deepcopy(_EMPTY_STORE)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            data.setdefault("threads", [])
            data.setdefault("current_thread_id", None)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load %s: %s", self.path, exc)
            import copy
            return copy.deepcopy(_EMPTY_STORE)

    # Public alias — tests call store.load()
    def load(self) -> dict:
        return self._load()

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(data, indent=2, ensure_ascii=False)
        if len(raw.encode()) > WARN_THRESHOLD:
            logger.warning(
                "Thread store approaching file size limit (%d KB)",
                len(raw.encode()) // 1024,
            )
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(raw, encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def _find(self, data: dict, thread_id: str) -> dict | None:
        for t in data["threads"]:
            if t["id"] == thread_id:
                return t
        return None

    def _require(self, data: dict, thread_id: str) -> dict:
        t = self._find(data, thread_id)
        if t is None:
            raise KeyError(f"Thread not found: {thread_id}")
        return t

    # ── Thread CRUD (high-level API used by JsonStore tests) ───────────

    def new_thread(self, name: str) -> dict:
        data = self._load()
        now = _now_iso()
        thread: dict = {
            "id": f"thread_{uuid.uuid4().hex}",
            "name": name, "status": "active",
            "created_at": now, "updated_at": now,
            "messages": [], "summary": None,
            "sandbox_roots": [], "agent_states": {}, "agent_outputs": [], "agent_events": [],
        }
        data["threads"].append(thread)
        self._save(data)
        return thread

    def get_thread(self, thread_id: str) -> dict | None:
        return self._find(self._load(), thread_id)

    def update_thread(self, thread_id: str, **fields) -> dict:
        data = self._load()
        t = self._require(data, thread_id)
        fields["updated_at"] = _now_iso()
        t.update(fields)
        self._save(data)
        return t

    def delete_thread(self, thread_id: str) -> bool:
        data = self._load()
        before = len(data["threads"])
        data["threads"] = [t for t in data["threads"] if t["id"] != thread_id]
        if len(data["threads"]) == before:
            return False
        self._save(data)
        return True

    def list_threads(self) -> list:
        data = self._load()
        return sorted(data["threads"], key=lambda t: t.get("updated_at", ""), reverse=True)

    # ── DynamoClient-compatible interface ──────────────────────────────
    # All tool code calls these methods via _get_db(). Keeping the same
    # signatures means zero changes needed in tools/*.py

    def put_item(self, sk: str, attributes: dict) -> dict:
        """Store a raw item by SK. Used for messages, summaries, events."""
        data = self._load()
        now = _now_iso()
        item = dict(attributes)
        item["SK"] = sk
        item.setdefault("CreatedAt", now)
        item["UpdatedAt"] = now

        # Route by SK pattern
        if "#META" in sk:
            thread_id = sk.split("#")[1] if sk.startswith("THREAD#") else None
            if thread_id and thread_id != "CURRENT":
                existing = self._find(data, thread_id)
                if existing:
                    existing.update({
                        "name": item.get("Name", existing.get("name", "")),
                        "status": item.get("Status", existing.get("status", "active")).lower(),
                        "updated_at": now,
                        **({"project": item["Project"]} if item.get("Project") else {}),
                    })
                    if "Summary" in item:
                        existing["summary"] = item["Summary"]
                    self._save(data)
                    return item
                else:
                    thread = {
                        "id": thread_id, "name": item.get("Name", ""),
                        "status": item.get("Status", "active").lower(),
                        "project": item.get("Project", ""),
                        "created_at": item.get("CreatedAt", now),
                        "updated_at": now, "messages": [], "summary": None,
                        "sandbox_roots": [], "agent_states": {}, "agent_outputs": [], "agent_events": [],
                    }
                    data["threads"].append(thread)
                    self._save(data)
                    return item
            elif thread_id == "CURRENT":
                data["current_thread_id"] = item.get("CurrentThreadId")
                data["current_thread_active_at"] = item.get("ActiveAt", now)
                self._save(data)
                return item
        elif "#MSG#" in sk or "#SUMMARY_FAILURE" in sk or "#RECOVERY" in sk or "#SANDBOX" in sk:
            parts = sk.split("#")
            if len(parts) >= 2:
                thread_id = parts[1]
                t = self._find(data, thread_id)
                if t:
                    t.setdefault("messages", [])
                    item["SK"] = sk
                    t["messages"].append(item)
                    t["updated_at"] = now
                    self._save(data)
            return item
        elif "#SUMMARY" in sk and "#SUMMARY_FAILURE" not in sk:
            parts = sk.split("#")
            thread_id = parts[1] if len(parts) >= 2 else None
            if thread_id:
                t = self._find(data, thread_id)
                if t:
                    t["summary"] = item.get("Summary", "")
                    t["summary_type"] = item.get("SummaryType", "")
                    t["updated_at"] = now
                    self._save(data)
            return item

        # Fallback: store in misc bucket
        data.setdefault("misc", [])
        data["misc"].append(item)
        self._save(data)
        return item

    def get_item(self, thread_id: str, sk: str) -> dict | None:
        data = self._load()
        t = self._find(data, thread_id)
        if not t:
            return None
        for msg in t.get("messages", []):
            if msg.get("SK") == sk:
                return msg
        return None

    def query_all(self, sk_prefix: str) -> list:
        """Return all items whose SK starts with sk_prefix."""
        data = self._load()
        results = []
        # Thread META items
        if sk_prefix.startswith("THREAD#"):
            parts = sk_prefix.split("#")
            if len(parts) >= 2 and parts[1]:
                thread_id = parts[1]
                t = self._find(data, thread_id)
                if t:
                    results.extend(self._thread_to_items(t))
            else:
                # All threads
                for t in data["threads"]:
                    results.extend(self._thread_to_items(t))
        return results

    def _thread_to_items(self, t: dict) -> list:
        """Convert thread dict to DynamoDB-style item list."""
        items = [{
            "SK": f"THREAD#{t['id']}#META",
            "Name": t.get("name", ""),
            "Status": t.get("status", "active").capitalize(),
            "LastActivity": t.get("updated_at", ""),
            "MessageCount": len(t.get("messages", [])),
            "CreatedAt": t.get("created_at", ""),
            "UpdatedAt": t.get("updated_at", ""),
            "Project": t.get("project", ""),
        }]
        for msg in t.get("messages", []):
            items.append(msg)
        for event in t.get("agent_events", []):
            items.append(event)
        return items

    def query_thread(self, thread_id: str, sk_prefix: str) -> list:
        data = self._load()
        t = self._find(data, thread_id)
        if not t:
            return []
        return [m for m in t.get("messages", []) if m.get("SK", "").startswith(sk_prefix)]

    def get_thread_meta(self, thread_id: str) -> dict | None:
        data = self._load()
        t = self._find(data, thread_id)
        if not t:
            return None
        return {
            "SK": f"THREAD#{thread_id}#META",
            "Name": t.get("name", ""),
            "Status": t.get("status", "active").capitalize(),
            "LastActivity": t.get("updated_at", ""),
            "MessageCount": len(t.get("messages", [])),
            "CreatedAt": t.get("created_at", ""),
            "UpdatedAt": t.get("updated_at", ""),
        }

    def get_current_thread_marker(self) -> dict | None:
        data = self._load()
        tid = data.get("current_thread_id")
        if not tid:
            return None
        return {
            "CurrentThreadId": tid,
            "ActiveAt": data.get("current_thread_active_at", ""),
        }

    def resolve_thread_id(self, thread_id: str | None = None) -> str:
        if thread_id:
            return thread_id
        data = self._load()
        tid = data.get("current_thread_id")
        if not tid:
            raise ToolError("No active thread — create one with CT [name]")
        return tid

    def switch_thread(self, thread_id: str) -> dict:
        """Make thread_id the active thread. Atomic in JSON via single save."""
        data = self._load()
        t = self._find(data, thread_id)
        if not t:
            raise ToolError(f"Thread not found: {thread_id}")
        old_id = data.get("current_thread_id")
        if old_id and old_id != thread_id:
            old = self._find(data, old_id)
            if old:
                old["updated_at"] = _now_iso()
        data["current_thread_id"] = thread_id
        data["current_thread_active_at"] = _now_iso()
        t["updated_at"] = _now_iso()
        self._save(data)
        return {"status": "switched", "thread_id": thread_id, "switched_at": _now_iso()}

    def set_sandbox_roots(self, thread_id: str, sandbox_roots: list) -> dict:
        data = self._load()
        t = self._require(data, thread_id)
        t["sandbox_roots"] = sandbox_roots
        t["updated_at"] = _now_iso()
        self._save(data)
        return {"thread_id": thread_id, "sandbox_roots": sandbox_roots}

    # ── Agent state (stub — works for single-machine use) ──────────────

    def put_agent_output(self, thread_id: str, agent_id: str, output: str, task: str | None = None) -> dict:
        data = self._load()
        t = self._require(data, thread_id)
        now = _now_iso()
        item = {"SK": f"THREAD#{thread_id}#AGENT#{agent_id}#OUT#{now}", "ThreadId": thread_id, "AgentId": agent_id, "Output": output, "Task": task}
        t.setdefault("agent_outputs", []).append(item)
        t["updated_at"] = now
        self._save(data)
        return item

    def put_agent_event(
        self,
        thread_id: str,
        agent_id: str,
        event_type: str,
        content: str,
        persona: str | None = None,
    ) -> dict:
        data = self._load()
        t = self._require(data, thread_id)
        now = _now_iso()
        item = {
            "SK": f"THREAD#{thread_id}#AGENT#{agent_id}#EVENT#{now}#{uuid.uuid4().hex}",
            "ThreadId": thread_id,
            "AgentId": agent_id,
            "Type": "agent_event",
            "EventType": event_type,
            "Content": content,
            "CreatedAt": now,
        }
        if persona:
            item["Persona"] = persona
        t.setdefault("agent_events", []).append(item)
        t["updated_at"] = now
        self._save(data)
        return item

    def put_agent_handoff(self, thread_id: str, agent_id: str, handoff_state: dict) -> dict:
        data = self._load()
        t = self._require(data, thread_id)
        now = _now_iso()
        item = {"SK": f"THREAD#{thread_id}#AGENT#{agent_id}#HANDOFF#{now}", "ThreadId": thread_id, "AgentId": agent_id, "HandoffState": handoff_state}
        t.setdefault("agent_outputs", []).append(item)
        t["updated_at"] = now
        self._save(data)
        return item

    def put_agent_state(self, thread_id: str, agent_id: str, state: dict) -> dict:
        data = self._load()
        t = self._require(data, thread_id)
        t.setdefault("agent_states", {})[agent_id] = {**state, "UpdatedAt": _now_iso()}
        t["updated_at"] = _now_iso()
        self._save(data)
        sk = f"THREAD#{thread_id}#AGENT#{agent_id}#STATE"
        return {"SK": sk, "ThreadId": thread_id, "AgentId": agent_id, **state}

    def query_agent_states(self, thread_id: str) -> list:
        data = self._load()
        t = self._find(data, thread_id)
        if not t:
            return []
        return [{"AgentId": aid, **s} for aid, s in t.get("agent_states", {}).items()]

    def query_agent_events(self, thread_id: str, agent_id: str | None = None) -> list:
        data = self._load()
        t = self._find(data, thread_id)
        if not t:
            return []
        events = list(t.get("agent_events", []))
        if agent_id:
            events = [e for e in events if e.get("AgentId") == agent_id]
        return sorted(events, key=lambda e: e.get("SK", ""))
