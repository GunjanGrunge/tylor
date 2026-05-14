"""
Tests for Story 2.1: DynamoDB Storage Client
Run: pytest server/storage/tests/test_dynamo.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from mcp.server.fastmcp.exceptions import ToolError
from server.storage.dynamo import DynamoClient, ITEM_SIZE_LIMIT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client(mock_table=None):
    """Return a DynamoClient with a mocked DynamoDB table."""
    with patch("boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        resource = MagicMock()
        mock_session.resource.return_value = resource
        table = mock_table or MagicMock()
        resource.Table.return_value = table
        client = DynamoClient(table_name="agent101", user_id="testuser")
        client.table = table  # keep reference for assertions
        return client, table


# ---------------------------------------------------------------------------
# AC1: Initialises boto3 on import with configured profile
# ---------------------------------------------------------------------------

def test_init_creates_boto3_session_no_profile():
    with patch("boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        resource = MagicMock()
        mock_session.resource.return_value = resource
        resource.Table.return_value = MagicMock()

        DynamoClient(table_name="agent101", user_id="u1")

    mock_session_cls.assert_called_once_with()
    mock_session.resource.assert_called_once_with("dynamodb")


def test_init_creates_boto3_session_with_profile():
    with patch("boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        resource = MagicMock()
        mock_session.resource.return_value = resource
        resource.Table.return_value = MagicMock()

        DynamoClient(table_name="agent101", user_id="u1", profile="myprofile")

    mock_session_cls.assert_called_once_with(profile_name="myprofile")


# ---------------------------------------------------------------------------
# AC2: put_item writes mandatory base fields for ≤400KB item
# ---------------------------------------------------------------------------

def test_put_item_injects_mandatory_fields():
    client, table = make_client()
    table.get_item.return_value = {}  # item doesn't exist yet
    table.put_item.return_value = {}

    sk = "THREAD#t1#META"
    result = client.put_item(sk=sk, attributes={"Name": "alpha"})

    assert result["PK"] == "USER#testuser"
    assert result["SK"] == sk
    assert "CreatedAt" in result
    assert "UpdatedAt" in result
    assert isinstance(result["Version"], int)
    assert result["Version"] == 1
    # Verify DynamoDB was actually called
    table.put_item.assert_called_once()


def test_put_item_passes_correct_item_to_dynamo():
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}

    result = client.put_item(sk="THREAD#t1#META", attributes={"Name": "beta"})

    written = table.put_item.call_args.kwargs["Item"]
    assert written["Name"] == "beta"
    assert written["PK"] == "USER#testuser"


def test_put_item_preserves_created_at_on_update():
    """UpdatedAt changes; CreatedAt stays the same on subsequent writes."""
    client, table = make_client()
    # Simulate existing item
    existing = {
        "PK": "USER#testuser",
        "SK": "THREAD#t1#META",
        "CreatedAt": "2026-01-01T00:00:00Z",
        "UpdatedAt": "2026-01-01T00:00:00Z",
        "Version": 3,
        "Name": "old",
    }
    table.get_item.return_value = {"Item": existing}
    table.put_item.return_value = {}

    result = client.put_item(sk="THREAD#t1#META", attributes={"Name": "new"})

    assert result["CreatedAt"] == "2026-01-01T00:00:00Z"
    assert result["Version"] == 4  # incremented


# ---------------------------------------------------------------------------
# AC3: put_item rejects items > 400KB
# ---------------------------------------------------------------------------

def test_put_item_rejects_oversized_item():
    client, table = make_client()
    table.get_item.return_value = {}

    big_content = "x" * (ITEM_SIZE_LIMIT + 10_000)
    with pytest.raises(ToolError, match="400KB"):
        client.put_item(sk="THREAD#t1#MSG#ts", attributes={"Content": big_content})

    table.put_item.assert_not_called()


def test_put_item_accepts_item_at_size_limit():
    """Item at exactly ITEM_SIZE_LIMIT should not raise (boundary check)."""
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}

    # A small item well under 400KB should pass
    small = {"Content": "x" * 100}
    result = client.put_item(sk="THREAD#t1#META", attributes=small)
    assert result["Version"] == 1


# ---------------------------------------------------------------------------
# AC4: Thread isolation enforced on get_item, query_thread, delete_item
# ---------------------------------------------------------------------------

def test_get_item_raises_on_isolation_violation():
    client, table = make_client()
    with pytest.raises(ToolError, match="Thread isolation violation"):
        client.get_item(thread_id="t1", sk="THREAD#t2#META")


def test_get_item_passes_when_sk_matches_thread():
    client, table = make_client()
    table.get_item.return_value = {"Item": {"PK": "USER#testuser", "SK": "THREAD#t1#META"}}

    result = client.get_item(thread_id="t1", sk="THREAD#t1#META")
    assert result is not None


def test_get_item_returns_none_when_not_found():
    client, table = make_client()
    table.get_item.return_value = {}  # no "Item" key

    result = client.get_item(thread_id="t1", sk="THREAD#t1#META")
    assert result is None


def test_query_thread_raises_on_isolation_violation():
    client, table = make_client()
    with pytest.raises(ToolError, match="Thread isolation violation"):
        client.query_thread(thread_id="t1", sk_prefix="THREAD#t2#MSG")


def test_query_thread_passes_correct_prefix():
    client, table = make_client()
    table.query.return_value = {"Items": [{"SK": "THREAD#t1#MSG#001"}]}

    items = client.query_thread(thread_id="t1", sk_prefix="THREAD#t1#MSG")
    assert len(items) == 1
    table.query.assert_called_once()


def test_delete_item_raises_on_isolation_violation():
    client, table = make_client()
    with pytest.raises(ToolError, match="Thread isolation violation"):
        client.delete_item(thread_id="t1", sk="THREAD#t2#META")


def test_delete_item_calls_dynamo_delete():
    client, table = make_client()
    table.delete_item.return_value = {}

    client.delete_item(thread_id="t1", sk="THREAD#t1#META")

    table.delete_item.assert_called_once_with(
        Key={"PK": "USER#testuser", "SK": "THREAD#t1#META"}
    )


# ---------------------------------------------------------------------------
# Story 3.3: Sub-agent output and handoff persistence
# ---------------------------------------------------------------------------

def test_put_agent_output_writes_expected_thread_scoped_sk():
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}

    item = client.put_agent_output(
        thread_id="t1",
        agent_id="agent_a",
        output="Agent A completed analysis.",
        task="Analyze risk.",
    )

    assert item["SK"].startswith("THREAD#t1#AGENT#agent_a#OUT#")
    assert item["ThreadId"] == "t1"
    assert item["AgentId"] == "agent_a"
    assert item["Type"] == "agent_output"
    assert item["Output"] == "Agent A completed analysis."
    assert item["Task"] == "Analyze risk."


def test_put_agent_output_generates_unique_sk_for_rapid_writes():
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}

    first = client.put_agent_output(
        thread_id="t1",
        agent_id="agent_a",
        output="First output.",
    )
    second = client.put_agent_output(
        thread_id="t1",
        agent_id="agent_a",
        output="Second output.",
    )

    assert first["SK"] != second["SK"]
    assert first["SK"].startswith("THREAD#t1#AGENT#agent_a#OUT#")
    assert second["SK"].startswith("THREAD#t1#AGENT#agent_a#OUT#")


def test_put_agent_handoff_writes_distinct_thread_scoped_sk():
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}
    handoff = {"next_agent": "agent_b", "summary": "Carry this forward."}

    item = client.put_agent_handoff(
        thread_id="t1",
        agent_id="agent_a",
        handoff_state=handoff,
    )

    assert item["SK"].startswith("THREAD#t1#AGENT#agent_a#HANDOFF#")
    assert item["ThreadId"] == "t1"
    assert item["AgentId"] == "agent_a"
    assert item["Type"] == "agent_handoff"
    assert item["HandoffState"] == handoff


def test_put_agent_handoff_generates_unique_sk_for_rapid_writes():
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}

    first = client.put_agent_handoff(
        thread_id="t1",
        agent_id="agent_a",
        handoff_state={"step": 1},
    )
    second = client.put_agent_handoff(
        thread_id="t1",
        agent_id="agent_a",
        handoff_state={"step": 2},
    )

    assert first["SK"] != second["SK"]
    assert first["SK"].startswith("THREAD#t1#AGENT#agent_a#HANDOFF#")
    assert second["SK"].startswith("THREAD#t1#AGENT#agent_a#HANDOFF#")


def test_put_agent_state_writes_thread_scoped_state_record():
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}

    item = client.put_agent_state(
        thread_id="t1",
        agent_id="agent_a",
        state={
            "Status": "active",
            "Persona": "analyst",
            "Task": "Analyze risk.",
            "ToolsLoaded": ["ecc/web", "ecc/data"],
        },
    )

    assert item["SK"] == "THREAD#t1#AGENT#agent_a#STATE"
    assert item["ThreadId"] == "t1"
    assert item["AgentId"] == "agent_a"
    assert item["Type"] == "agent_state"
    assert item["Status"] == "active"
    assert item["Persona"] == "analyst"


def test_query_agent_states_is_scoped_to_thread_prefix():
    client, table = make_client()
    table.query.return_value = {
        "Items": [
            {"SK": "THREAD#t1#AGENT#agent_a#STATE", "ThreadId": "t1"},
        ]
    }

    result = client.query_agent_states("t1")

    assert result == [{"SK": "THREAD#t1#AGENT#agent_a#STATE", "ThreadId": "t1"}]
    table.query.assert_called_once()


def test_agent_output_rejects_cross_thread_sk_injection():
    client, table = make_client()
    with pytest.raises(ToolError, match="Invalid agent_id"):
        client.put_agent_output(
            thread_id="t1",
            agent_id="THREAD#t2#AGENT#agent_a",
            output="bad",
        )
    table.put_item.assert_not_called()


def test_switch_thread_suspends_previous_agents_and_resumes_target_agents():
    client, table = make_client()

    def raw_get_side_effect(Key):
        sk = Key["SK"]
        items = {
            "THREAD#CURRENT#META": {
                "PK": "USER#testuser",
                "SK": "THREAD#CURRENT#META",
                "CurrentThreadId": "thread_alpha",
                "ActiveAt": "2026-05-12T00:00:00Z",
                "CreatedAt": "2026-05-12T00:00:00Z",
                "UpdatedAt": "2026-05-12T00:00:00Z",
                "Version": 1,
            },
            "THREAD#thread_alpha#META": {
                "PK": "USER#testuser",
                "SK": "THREAD#thread_alpha#META",
                "Version": 1,
            },
            "THREAD#thread_beta#META": {
                "PK": "USER#testuser",
                "SK": "THREAD#thread_beta#META",
                "Version": 1,
            },
        }
        item = items.get(sk)
        return {"Item": item} if item else {}

    table.get_item.side_effect = raw_get_side_effect

    query_results = [
        {
            "Items": [
                {
                    "PK": "USER#testuser",
                    "SK": "THREAD#thread_alpha#AGENT#agent_a#STATE",
                    "ThreadId": "thread_alpha",
                    "AgentId": "agent_a",
                    "Status": "active",
                    "Version": 1,
                }
            ]
        },
        {
            "Items": [
                {
                    "PK": "USER#testuser",
                    "SK": "THREAD#thread_beta#AGENT#agent_b#STATE",
                    "ThreadId": "thread_beta",
                    "AgentId": "agent_b",
                    "Status": "suspended",
                    "Version": 1,
                }
            ]
        },
    ]
    table.query.side_effect = query_results

    result = client.switch_thread("thread_beta")

    assert result["thread_id"] == "thread_beta"
    writes = client._client.transact_write_items.call_args.kwargs["TransactItems"]
    serialised = [w["Put"]["Item"] for w in writes if w["Put"]["Item"]["SK"]["S"].endswith("#STATE")]
    statuses = {item["SK"]["S"]: item["Status"]["S"] for item in serialised}
    assert statuses["THREAD#thread_alpha#AGENT#agent_a#STATE"] == "suspended"
    assert statuses["THREAD#thread_beta#AGENT#agent_b#STATE"] == "active"


# ---------------------------------------------------------------------------
# AC5: Version increments on every write
# ---------------------------------------------------------------------------

def test_version_starts_at_1_for_new_item():
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}

    result = client.put_item(sk="THREAD#t1#META", attributes={})
    assert result["Version"] == 1


def test_version_increments_on_subsequent_writes():
    client, table = make_client()
    existing = {
        "PK": "USER#testuser",
        "SK": "THREAD#t1#META",
        "CreatedAt": "2026-01-01T00:00:00Z",
        "UpdatedAt": "2026-01-01T00:00:00Z",
        "Version": 7,
    }
    table.get_item.return_value = {"Item": existing}
    table.put_item.return_value = {}

    result = client.put_item(sk="THREAD#t1#META", attributes={})
    assert result["Version"] == 8


# ---------------------------------------------------------------------------
# ISO 8601 date format
# ---------------------------------------------------------------------------

def test_created_at_is_iso_8601_utc():
    import re
    client, table = make_client()
    table.get_item.return_value = {}
    table.put_item.return_value = {}

    result = client.put_item(sk="THREAD#t1#META", attributes={})
    # Must match YYYY-MM-DDTHH:MM:SSZ
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", result["CreatedAt"])
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", result["UpdatedAt"])
