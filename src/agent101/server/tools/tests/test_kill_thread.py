"""
Tests for Story 2.7: kill_thread and async Bedrock summarizer
Run: pytest server/tools/tests/test_kill_thread.py -v
"""
import asyncio
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))


class FakeDynamo:
    def __init__(self):
        self.items = {}
        self.puts = []
        self.messages = [
            {"SK": "THREAD#t1#MSG#001", "Role": "user", "Content": "first"},
            {"SK": "THREAD#t1#MSG#002", "Role": "assistant", "Content": "second"},
        ]

    def get_thread_meta(self, thread_id):
        return {
            "SK": f"THREAD#{thread_id}#META",
            "Name": "Test thread",
            "Status": "active",
            "MessageCount": len(self.messages),
        }

    def query_thread(self, thread_id, sk_prefix):
        if sk_prefix.endswith("#MSG#"):
            return list(self.messages)
        return []

    def put_item(self, sk, attributes):
        item = {"SK": sk, **attributes}
        self.items[sk] = item
        self.puts.append((sk, attributes))
        return item


class FakeBedrock:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        body = MagicMock()
        body.read.return_value = (
            b'{"content":[{"type":"text","text":"' + self.text.encode("utf-8") + b'"}]}'
        )
        return {"body": body}


def test_kill_thread_returns_immediately_without_dispatching_task():
    """kill_thread is now sync; summarization is dispatched by the PostToolUse hook."""
    from server.tools.tylor import kill_thread

    with patch("server.tools.tylor._get_db", return_value=FakeDynamo()):
        result = kill_thread("t1")

    assert result == {
        "status": "killing",
        "thread_id": "t1",
        "message": "Summarization in progress",
    }


def test_summarize_thread_success_writes_summary_and_marks_thread_killed():
    from server.tools.summarizer import summarize_thread

    db = FakeDynamo()
    bedrock = FakeBedrock(text="Permanent summary")

    asyncio.run(
        summarize_thread(
            "t1",
            db=db,
            bedrock_client=bedrock,
            model_id="opus-test",
        )
    )

    summary = db.items["THREAD#t1#SUMMARY"]
    meta = db.items["THREAD#t1#META"]
    assert summary["Summary"] == "Permanent summary"
    assert summary["SummaryType"] == "bedrock_opus"
    assert meta["Status"] == "killed"
    assert bedrock.calls[0]["modelId"] == "opus-test"


def test_summarize_thread_failure_stores_raw_fallback_and_logs_failure():
    from server.tools.summarizer import summarize_thread

    db = FakeDynamo()
    bedrock = FakeBedrock(error=RuntimeError("bedrock down"))

    asyncio.run(
        summarize_thread(
            "t1",
            db=db,
            bedrock_client=bedrock,
            model_id="opus-test",
        )
    )

    summary = db.items["THREAD#t1#SUMMARY"]
    meta = db.items["THREAD#t1#META"]
    failure_logs = [
        item for sk, item in db.items.items()
        if sk.startswith("THREAD#t1#MSG#") and item.get("Role") == "system"
    ]

    assert summary["SummaryType"] == "raw_fallback"
    assert "user: first" in summary["Summary"]
    assert "assistant: second" in summary["Summary"]
    assert "bedrock down" in summary["Error"]
    assert meta["Status"] == "killed"
    assert failure_logs
    assert "bedrock down" in failure_logs[0]["Content"]
