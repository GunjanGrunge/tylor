"""
Isolation gate test for Story 2.4.
Run: pytest server/tests/test_isolation.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from agent101.server.storage.dynamo import DynamoClient


def test_switch_thread_does_not_touch_message_items():
    """Zero message bleed: switch_thread only updates marker and thread metadata."""
    with patch("boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        resource = MagicMock()
        mock_session.resource.return_value = resource
        table = MagicMock()
        resource.Table.return_value = table

        client = DynamoClient(table_name="agent101", user_id="testuser")
        client.table = table

        items = {
            "THREAD#CURRENT#META": {
                "PK": "USER#testuser",
                "SK": "THREAD#CURRENT#META",
                "CreatedAt": "2026-05-12T07:00:00Z",
                "UpdatedAt": "2026-05-12T07:00:00Z",
                "Version": 1,
                "CurrentThreadId": "t1",
                "ActiveAt": "2026-05-12T07:00:00Z",
            },
            "THREAD#t1#META": {
                "PK": "USER#testuser",
                "SK": "THREAD#t1#META",
                "CreatedAt": "2026-05-12T06:00:00Z",
                "UpdatedAt": "2026-05-12T06:00:00Z",
                "Version": 1,
                "Name": "thread-one",
            },
            "THREAD#t2#META": {
                "PK": "USER#testuser",
                "SK": "THREAD#t2#META",
                "CreatedAt": "2026-05-12T06:10:00Z",
                "UpdatedAt": "2026-05-12T06:10:00Z",
                "Version": 1,
                "Name": "thread-two",
            },
            "THREAD#t1#MSG#0001": {
                "PK": "USER#testuser",
                "SK": "THREAD#t1#MSG#0001",
                "Content": "message from thread one",
            },
            "THREAD#t2#MSG#0001": {
                "PK": "USER#testuser",
                "SK": "THREAD#t2#MSG#0001",
                "Content": "message from thread two",
            },
        }

        def get_item_side_effect(Key):
            sk = Key["SK"]
            item = items.get(sk)
            return {"Item": item} if item else {}

        table.get_item.side_effect = get_item_side_effect

        def transact_write_side_effect(TransactItems):
            for op in TransactItems:
                put = op.get("Put")
                if put:
                    item = put["Item"]
                    sk = item["SK"]["S"]
                    items[sk] = {k: list(v.values())[0] for k, v in item.items()}
            return {}

        client._client.transact_write_items.side_effect = transact_write_side_effect

        client.switch_thread("t2")

    assert items["THREAD#t1#MSG#0001"]["Content"] == "message from thread one"
    assert items["THREAD#t2#MSG#0001"]["Content"] == "message from thread two"
    assert items["THREAD#CURRENT#META"]["CurrentThreadId"] == "t2"
    assert items["THREAD#t2#META"]["LastActivity"]
    assert items["THREAD#t1#META"]["LastActivity"]
