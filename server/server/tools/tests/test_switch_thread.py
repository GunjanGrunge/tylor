"""
Tests for Story 2.4: switch_thread tool and DynamoDB atomic write helper.
Run: pytest server/tools/tests/test_switch_thread.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from mcp.server.fastmcp.exceptions import ToolError
from server.storage.dynamo import DynamoClient
from server.tools.tylor import switch_thread


def make_client(mock_table=None):
    with patch("boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        resource = MagicMock()
        mock_session.resource.return_value = resource
        table = mock_table or MagicMock()
        resource.Table.return_value = table
        client = DynamoClient(table_name="agent101", user_id="testuser")
        client.table = table
        return client, table


def test_switch_thread_tool_calls_dynamo_switch():
    mock_db = MagicMock()
    with patch("server.tools.tylor._get_db", return_value=mock_db):
        mock_db.switch_thread.return_value = {
            "thread_id": "t2",
            "status": "switched",
            "switched_at": "2026-05-12T10:00:00Z",
        }

        result = switch_thread("t2")

    mock_db.switch_thread.assert_called_once_with("t2")
    assert result["thread_id"] == "t2"


def test_switch_thread_includes_code_index_header_when_available():
    mock_db = MagicMock()
    mock_db.switch_thread.return_value = {
        "thread_id": "t2",
        "status": "switched",
        "switched_at": "2026-05-12T10:00:00Z",
        "name": "Frontend",
    }
    mock_db.get_thread_meta.return_value = {"Name": "Frontend"}

    with patch("server.tools.tylor._get_db", return_value=mock_db), patch(
        "server.tools.hooks.build_code_index_header",
        return_value="[Frontend Thread — Code Index]\nSignIn: ui/auth.tsx:42",
    ):
        result = switch_thread("t2")

    assert result["code_index_header"].startswith("[Frontend Thread")


def test_dynamo_client_switch_thread_raises_when_target_missing():
    client, table = make_client()
    table.get_item.return_value = {}

    with pytest.raises(ToolError, match="Thread not found: missing"): 
        client.switch_thread("missing")

    assert not client._client.transact_write_items.called


def test_dynamo_client_switch_thread_writes_marker_and_target_meta():
    client, table = make_client()
    target_meta = {
        "PK": "USER#testuser",
        "SK": "THREAD#t2#META",
        "CreatedAt": "2026-05-12T08:00:00Z",
        "UpdatedAt": "2026-05-12T08:00:00Z",
        "Version": 1,
        "Name": "thread-two",
    }
    current_marker = {
        "PK": "USER#testuser",
        "SK": "THREAD#CURRENT#META",
        "CreatedAt": "2026-05-12T07:00:00Z",
        "UpdatedAt": "2026-05-12T07:00:00Z",
        "Version": 1,
        "CurrentThreadId": "t1",
        "ActiveAt": "2026-05-12T07:00:00Z",
    }

    def get_item_side_effect(Key):
        if Key["SK"] == "THREAD#CURRENT#META":
            return {"Item": current_marker}
        if Key["SK"] == "THREAD#t2#META":
            return {"Item": target_meta}
        return {}

    table.get_item.side_effect = get_item_side_effect
    client._client.transact_write_items.return_value = {}

    result = client.switch_thread("t2")

    assert result["thread_id"] == "t2"
    client._client.transact_write_items.assert_called_once()

    transact_items = client._client.transact_write_items.call_args.kwargs["TransactItems"]
    sks = [item["Put"]["Item"]["SK"]["S"] for item in transact_items]
    assert "THREAD#CURRENT#META" in sks
    assert "THREAD#t2#META" in sks
    assert len(sks) >= 2  # marker + target, previous meta optional depending on current state


def test_dynamo_client_switch_thread_transaction_uses_metric_shape():
    client, table = make_client()
    target_meta = {
        "PK": "USER#testuser",
        "SK": "THREAD#t2#META",
        "CreatedAt": "2026-05-12T08:00:00Z",
        "UpdatedAt": "2026-05-12T08:00:00Z",
        "Version": 1,
        "Name": "thread-two",
    }
    current_marker = {
        "PK": "USER#testuser",
        "SK": "THREAD#CURRENT#META",
        "CreatedAt": "2026-05-12T07:00:00Z",
        "UpdatedAt": "2026-05-12T07:00:00Z",
        "Version": 1,
        "CurrentThreadId": "t1",
        "ActiveAt": "2026-05-12T07:00:00Z",
    }
    previous_meta = {
        "PK": "USER#testuser",
        "SK": "THREAD#t1#META",
        "CreatedAt": "2026-05-12T06:00:00Z",
        "UpdatedAt": "2026-05-12T06:00:00Z",
        "Version": 2,
        "Name": "thread-one",
    }

    def get_item_side_effect(Key):
        if Key["SK"] == "THREAD#CURRENT#META":
            return {"Item": current_marker}
        if Key["SK"] == "THREAD#t2#META":
            return {"Item": target_meta}
        if Key["SK"] == "THREAD#t1#META":
            return {"Item": previous_meta}
        return {}

    table.get_item.side_effect = get_item_side_effect
    client._client.transact_write_items.return_value = {}

    client.switch_thread("t2")

    transact_items = client._client.transact_write_items.call_args.kwargs["TransactItems"]
    assert any(item["Put"]["Item"]["SK"]["S"] == "THREAD#t1#META" for item in transact_items)
    assert any(item["Put"]["Item"]["SK"]["S"] == "THREAD#CURRENT#META" for item in transact_items)
    assert any(item["Put"]["Item"]["SK"]["S"] == "THREAD#t2#META" for item in transact_items)
