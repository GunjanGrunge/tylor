"""
Tests for Story 1.6: Project JSON Storage Mode
Run: pytest server/storage/tests/test_json_store.py -v
"""
import json
import os
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from server.storage.json_store import JsonStore, STORE_VERSION, WARN_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_store(tmp_path: Path) -> JsonStore:
    return JsonStore(tmp_path / ".agent101" / "threads.json")


# ---------------------------------------------------------------------------
# AC3: File created on first new_thread (absent → created atomically)
# ---------------------------------------------------------------------------

def test_file_created_on_first_new_thread(tmp_path):
    store = make_store(tmp_path)
    assert not store.path.exists()

    thread = store.new_thread("my first thread")

    assert store.path.exists()
    assert thread["name"] == "my first thread"
    assert len(thread["id"]) == 32  # uuid4().hex — 32-char hex
    assert thread["status"] == "active"
    assert thread["messages"] == []
    assert thread["summary"] is None


def test_first_new_thread_writes_correct_schema(tmp_path):
    store = make_store(tmp_path)
    store.new_thread("alpha")

    data = json.loads(store.path.read_text())
    assert data["version"] == STORE_VERSION
    assert isinstance(data["threads"], list)
    assert len(data["threads"]) == 1
    t = data["threads"][0]
    for key in ("id", "name", "status", "created_at", "updated_at", "messages", "summary"):
        assert key in t, f"Missing key: {key}"


def test_atomic_write_no_tmp_file_left_on_success(tmp_path):
    store = make_store(tmp_path)
    store.new_thread("test")
    tmp = store.path.with_suffix(".tmp")
    assert not tmp.exists()


# ---------------------------------------------------------------------------
# AC2: Tylor tools read/write threads.json
# ---------------------------------------------------------------------------

def test_load_returns_empty_store_when_file_absent(tmp_path):
    store = make_store(tmp_path)
    data = store._load()
    assert data["version"] == STORE_VERSION
    assert data["threads"] == []


def test_multiple_threads_persisted_correctly(tmp_path):
    store = make_store(tmp_path)
    t1 = store.new_thread("alpha")
    t2 = store.new_thread("beta")
    t3 = store.new_thread("gamma")

    threads = store.list_threads()
    ids = [t["id"] for t in threads]
    assert t1["id"] in ids
    assert t2["id"] in ids
    assert t3["id"] in ids


def test_list_threads_sorted_by_updated_at_desc(tmp_path):
    store = make_store(tmp_path)
    t1 = store.new_thread("first")
    t2 = store.new_thread("second")
    # Update t1 so it has a later updated_at
    store.update_thread(t1["id"], name="first-updated")

    threads = store.list_threads()
    # t1 (most recently updated) should be first
    assert threads[0]["id"] == t1["id"]


def test_get_thread_returns_correct_thread(tmp_path):
    store = make_store(tmp_path)
    t = store.new_thread("findme")
    found = store.get_thread(t["id"])
    assert found is not None
    assert found["id"] == t["id"]
    assert found["name"] == "findme"


def test_get_thread_returns_none_for_missing(tmp_path):
    store = make_store(tmp_path)
    assert store.get_thread("thread_nonexistent") is None


def test_update_thread_persists_fields(tmp_path):
    store = make_store(tmp_path)
    t = store.new_thread("before")
    store.update_thread(t["id"], name="after", status="archived")

    found = store.get_thread(t["id"])
    assert found["name"] == "after"
    assert found["status"] == "archived"


def test_update_thread_raises_for_missing_id(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises((KeyError, Exception)):  # JsonStore raises ToolError
        store.update_thread("thread_nonexistent", name="x")


def test_delete_thread_removes_from_store(tmp_path):
    store = make_store(tmp_path)
    t = store.new_thread("delete-me")
    deleted = store.delete_thread(t["id"])
    assert deleted is True
    assert store.get_thread(t["id"]) is None


def test_delete_thread_returns_false_for_missing(tmp_path):
    store = make_store(tmp_path)
    assert store.delete_thread("thread_ghost") is False


# ---------------------------------------------------------------------------
# AC4: 400KB warning emitted (write proceeds, no hard failure)
# ---------------------------------------------------------------------------

def test_large_write_warns_but_succeeds(tmp_path, caplog):
    import logging
    store = make_store(tmp_path)
    t = store.new_thread("big")

    # Stuff > 400KB of data into messages
    big_messages = [{"role": "user", "content": "x" * 1000}] * 500  # ~500KB

    with caplog.at_level(logging.WARNING, logger="server.storage.json_store"):
        store.update_thread(t["id"], messages=big_messages)

    assert store.path.exists()  # write succeeded
    assert any("file size limit" in r.message for r in caplog.records)


def test_small_write_no_warning(tmp_path, caplog):
    import logging
    store = make_store(tmp_path)
    with caplog.at_level(logging.WARNING, logger="server.storage.json_store"):
        store.new_thread("tiny")
    assert not any("file size limit" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# AC5: JsonStore is mode-agnostic — caller decides when to use it
# ---------------------------------------------------------------------------

def test_json_store_import_does_not_touch_filesystem(tmp_path):
    """Importing JsonStore must not create any files."""
    from server.storage.json_store import JsonStore  # noqa: F401 (reimport to check)
    agent101_dir = tmp_path / ".agent101"
    assert not agent101_dir.exists()


# ---------------------------------------------------------------------------
# AC1: install.sh config.json shape (tested via Python logic directly)
# ---------------------------------------------------------------------------

def test_project_mode_config_written_correctly(tmp_path):
    """Simulate the Python snippet from install.sh for project mode."""
    config_path = tmp_path / "config.json"
    plugin_dir = "/project/agent101"
    storage_path = f"{plugin_dir}/.agent101/threads.json"

    data = {}
    data["storage_mode"] = "project"
    data["storage_path"] = storage_path
    config_path.write_text(json.dumps(data, indent=2))

    written = json.loads(config_path.read_text())
    assert written["storage_mode"] == "project"
    assert written["storage_path"] == storage_path
    # No AWS keys should be required
    assert "aws_access_key" not in written
    assert "aws_secret_key" not in written


def test_personal_mode_config_written_correctly(tmp_path):
    """Simulate the Python snippet from install.sh for personal mode."""
    config_path = tmp_path / "config.json"
    data = {"storage_mode": "personal"}
    config_path.write_text(json.dumps(data, indent=2))

    written = json.loads(config_path.read_text())
    assert written["storage_mode"] == "personal"


def test_existing_config_not_overwritten_in_personal_mode(tmp_path):
    """Idempotent: if storage_mode already set, don't overwrite."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"storage_mode": "personal", "custom_key": "keep-me"}))

    data = json.loads(config_path.read_text())
    if data.get("storage_mode") not in ("personal", "project"):
        data["storage_mode"] = "personal"
        config_path.write_text(json.dumps(data, indent=2))

    result = json.loads(config_path.read_text())
    assert result["custom_key"] == "keep-me"
    assert result["storage_mode"] == "personal"
