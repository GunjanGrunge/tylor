"""
server/storage/json_store.py — Project (local JSON) storage for agent101 threads.
Zero-infra path: all state is stored in {cwd}/.agent101/threads.json.

Used when config.json has storage_mode: "project".
All writes are atomic (write-to-tmp then os.replace).
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STORE_VERSION = "1.0"
WARN_THRESHOLD = 400 * 1024  # 400 KB

_EMPTY_STORE: dict = {"version": STORE_VERSION, "threads": []}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JsonStore:
    """
    Reads and writes threads from a local JSON file.
    All mutations are atomic: written to a .tmp file then os.replace'd.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    # ------------------------------------------------------------------
    # Low-level load / save
    # ------------------------------------------------------------------

    def load(self) -> dict:
        """Load the store. Returns an empty store if the file is absent."""
        if not self.path.exists():
            return {"version": STORE_VERSION, "threads": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if "threads" not in data:
                data["threads"] = []
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load %s: %s — starting with empty store", self.path, exc)
            return {"version": STORE_VERSION, "threads": []}

    def save(self, data: dict) -> None:
        """Atomic write: serialise to .tmp then os.replace."""
        raw = json.dumps(data, indent=2, ensure_ascii=False)
        size = len(raw.encode("utf-8"))

        if size > WARN_THRESHOLD:
            logger.warning(
                "Thread content approaching file size limit (%d KB) — "
                "consider Personal (DynamoDB) mode",
                size // 1024,
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(raw, encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------
    # Thread operations
    # ------------------------------------------------------------------

    def new_thread(self, name: str) -> dict:
        """Create a new thread, persist, and return the thread dict."""
        data = self.load()
        now = _now_iso()
        thread: dict = {
            "id": f"thread_{uuid.uuid4().hex}",
            "name": name,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "messages": [],
            "summary": None,
        }
        data["threads"].append(thread)
        self.save(data)
        return thread

    def get_thread(self, thread_id: str) -> dict | None:
        """Return thread dict by ID, or None if not found."""
        data = self.load()
        for t in data["threads"]:
            if t["id"] == thread_id:
                return t
        return None

    def update_thread(self, thread_id: str, **fields) -> dict:
        """
        Update fields on an existing thread.
        Always sets `updated_at` to now.
        Raises KeyError if thread_id not found.
        """
        data = self.load()
        for t in data["threads"]:
            if t["id"] == thread_id:
                fields["updated_at"] = _now_iso()
                t.update(fields)
                self.save(data)
                return t
        raise KeyError(f"Thread '{thread_id}' not found")

    def delete_thread(self, thread_id: str) -> bool:
        """
        Remove a thread. Returns True if deleted, False if not found.
        """
        data = self.load()
        before = len(data["threads"])
        data["threads"] = [t for t in data["threads"] if t["id"] != thread_id]
        if len(data["threads"]) == before:
            return False
        self.save(data)
        return True

    def list_threads(self) -> list:
        """Return all threads sorted by updated_at descending."""
        data = self.load()
        return sorted(
            data["threads"],
            key=lambda t: t.get("updated_at", ""),
            reverse=True,
        )
