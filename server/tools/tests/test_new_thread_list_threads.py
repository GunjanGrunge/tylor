"""
Tests for Story 2.3: new_thread & list_threads tools
Run: pytest server/tools/tests/test_new_thread_list_threads.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from mcp.server.fastmcp.exceptions import ToolError
# Import the tool functions directly for unit testing
import server.tools.tylor as tylor_mod
from server.tools.tylor import _validate_name, new_thread, list_threads


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_mock(existing_items=None):
    """Return a mock DynamoClient."""
    mock_db = MagicMock()
    mock_db.query_all.return_value = existing_items or []
    mock_db.put_item.side_effect = lambda sk, attrs: {
        **attrs, "PK": "USER#default", "SK": sk,
        "CreatedAt": "2026-05-12T10:00:00Z",
        "UpdatedAt": "2026-05-12T10:00:00Z",
        "Version": 1,
    }
    return mock_db


def _call_new_thread(name: str, existing_items=None):
    """Call new_thread with a mocked DynamoClient."""
    mock_db = _make_db_mock(existing_items)
    with patch.object(tylor_mod, "_get_db", return_value=mock_db):
        return new_thread(name), mock_db


def _call_list_threads(items=None):
    """Call list_threads with a mocked DynamoClient."""
    mock_db = _make_db_mock(items)
    with patch.object(tylor_mod, "_get_db", return_value=mock_db):
        return list_threads(), mock_db


# ---------------------------------------------------------------------------
# AC4: Name length validation
# ---------------------------------------------------------------------------

def test_new_thread_rejects_name_too_short():
    with pytest.raises(ToolError, match="3–64 characters"):
        new_thread("ab")


def test_new_thread_rejects_name_too_long():
    with pytest.raises(ToolError, match="3–64 characters"):
        new_thread("x" * 65)


def test_new_thread_accepts_name_at_min_length():
    result, db = _call_new_thread("abc")
    assert result["name"] == "abc"
    db.put_item.assert_called_once()


def test_new_thread_accepts_name_at_max_length():
    result, db = _call_new_thread("x" * 64)
    assert result["name"] == "x" * 64


# ---------------------------------------------------------------------------
# AC5: Character and whitespace validation
# ---------------------------------------------------------------------------

def test_new_thread_rejects_whitespace_only():
    with pytest.raises(ToolError, match="invalid characters"):
        new_thread("   ")


def test_new_thread_rejects_only_spaces_exact_min():
    with pytest.raises(ToolError, match="invalid characters"):
        new_thread("   ")  # 3 spaces


def test_new_thread_rejects_special_characters():
    with pytest.raises(ToolError, match="invalid characters"):
        new_thread("bad@name!")


def test_new_thread_rejects_slash_characters():
    with pytest.raises(ToolError, match="invalid characters"):
        new_thread("my/thread")


def test_new_thread_accepts_hyphens_underscores_spaces():
    result, _ = _call_new_thread("my-thread_name test")
    assert result["name"] == "my-thread_name test"


def test_new_thread_accepts_alphanumeric():
    result, _ = _call_new_thread("Project123")
    assert result["name"] == "Project123"


# ---------------------------------------------------------------------------
# AC3: Duplicate name
# ---------------------------------------------------------------------------

def test_new_thread_rejects_duplicate_name():
    existing = [
        {
            "SK": "THREAD#abc123#META",
            "Name": "my-project",
            "Status": "active",
        }
    ]
    with pytest.raises(ToolError, match="already exists"):
        _call_new_thread("my-project", existing_items=existing)


def test_new_thread_allows_different_name_when_others_exist():
    existing = [
        {
            "SK": "THREAD#abc123#META",
            "Name": "other-project",
            "Status": "active",
        }
    ]
    result, db = _call_new_thread("new-project", existing_items=existing)
    assert result["name"] == "new-project"
    db.put_item.assert_called_once()


# ---------------------------------------------------------------------------
# AC1: new_thread returns correct shape
# ---------------------------------------------------------------------------

def test_new_thread_returns_thread_id_name_created_at():
    result, _ = _call_new_thread("alpha")
    assert "thread_id" in result
    assert "name" in result
    assert "created_at" in result


def test_new_thread_thread_id_is_hex_32chars():
    result, _ = _call_new_thread("beta")
    assert len(result["thread_id"]) == 32
    assert all(c in "0123456789abcdef" for c in result["thread_id"])


def test_new_thread_writes_correct_sk():
    result, db = _call_new_thread("gamma")
    thread_id = result["thread_id"]
    call_sk = db.put_item.call_args.args[0]
    assert call_sk == f"THREAD#{thread_id}#META"


def test_new_thread_writes_status_active():
    result, db = _call_new_thread("delta")
    attrs = db.put_item.call_args.args[1]
    assert attrs["Status"] == "active"
    assert attrs["MessageCount"] == 0


def test_new_thread_uniqueness_check_before_write():
    """query_all must be called before put_item."""
    mock_db = _make_db_mock()
    call_order = []
    mock_db.query_all.side_effect = lambda *a, **kw: call_order.append("query") or []
    mock_db.put_item.side_effect = lambda sk, attrs: call_order.append("write") or {
        **attrs, "SK": sk, "CreatedAt": "2026-05-12T10:00:00Z",
        "UpdatedAt": "2026-05-12T10:00:00Z", "Version": 1,
    }

    with patch.object(tylor_mod, "_get_db", return_value=mock_db):
        new_thread("epsilon")

    assert call_order.index("query") < call_order.index("write")


# ---------------------------------------------------------------------------
# AC2: list_threads returns sorted threads
# ---------------------------------------------------------------------------

def test_list_threads_returns_empty_when_no_threads():
    result, _ = _call_list_threads([])
    assert result == {"threads": []}


def test_list_threads_returns_correct_shape():
    items = [
        {
            "SK": "THREAD#abc123#META",
            "Name": "project-a",
            "Status": "active",
            "LastActivity": "2026-05-12T10:00:00Z",
            "MessageCount": 3,
        }
    ]
    result, _ = _call_list_threads(items)
    threads = result["threads"]
    assert len(threads) == 1
    t = threads[0]
    assert t["thread_id"] == "abc123"
    assert t["name"] == "project-a"
    assert t["status"] == "active"
    assert t["last_activity"] == "2026-05-12T10:00:00Z"
    assert t["message_count"] == 3


def test_list_threads_sorted_by_last_activity_descending():
    items = [
        {
            "SK": "THREAD#aaa#META",
            "Name": "old",
            "Status": "active",
            "LastActivity": "2026-05-10T10:00:00Z",
            "MessageCount": 1,
        },
        {
            "SK": "THREAD#bbb#META",
            "Name": "new",
            "Status": "active",
            "LastActivity": "2026-05-12T10:00:00Z",
            "MessageCount": 5,
        },
        {
            "SK": "THREAD#ccc#META",
            "Name": "middle",
            "Status": "active",
            "LastActivity": "2026-05-11T10:00:00Z",
            "MessageCount": 2,
        },
    ]
    result, _ = _call_list_threads(items)
    activities = [t["last_activity"] for t in result["threads"]]
    assert activities == sorted(activities, reverse=True)
    assert result["threads"][0]["name"] == "new"


def test_list_threads_excludes_non_meta_items():
    items = [
        {
            "SK": "THREAD#abc123#META",
            "Name": "real-thread",
            "Status": "active",
            "LastActivity": "2026-05-12T10:00:00Z",
            "MessageCount": 0,
        },
        {
            "SK": "THREAD#abc123#MSG#2026-05-12T10:00:00Z",
            "Content": "a message",
        },
    ]
    result, _ = _call_list_threads(items)
    assert len(result["threads"]) == 1
    assert result["threads"][0]["name"] == "real-thread"


def test_list_threads_thread_id_extracted_correctly():
    items = [
        {
            "SK": "THREAD#deadbeef1234567890abcdef12345678#META",
            "Name": "extract-test",
            "Status": "active",
            "LastActivity": "2026-05-12T10:00:00Z",
            "MessageCount": 0,
        }
    ]
    result, _ = _call_list_threads(items)
    assert result["threads"][0]["thread_id"] == "deadbeef1234567890abcdef12345678"


# ---------------------------------------------------------------------------
# query_all on DynamoClient
# ---------------------------------------------------------------------------

def test_query_all_method_exists_on_dynamo_client():
    from server.storage.dynamo import DynamoClient
    assert hasattr(DynamoClient, "query_all")


def test_query_all_no_thread_isolation_check():
    """query_all must NOT call _assert_thread_isolation."""
    from server.storage.dynamo import DynamoClient
    import inspect
    source = inspect.getsource(DynamoClient.query_all)
    assert "_assert_thread_isolation" not in source
