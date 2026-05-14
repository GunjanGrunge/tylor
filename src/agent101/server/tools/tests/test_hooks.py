"""
Tests for Story 2.8: Claude Code lifecycle hooks
Run: pytest server/tools/tests/test_hooks.py -v
"""
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))


class FakeDynamo:
    CURRENT_THREAD_SK = "THREAD#CURRENT#META"

    def __init__(self):
        self.puts = []
        self.current = {
            "SK": self.CURRENT_THREAD_SK,
            "CurrentThreadId": "t1",
            "ActiveAt": "2026-05-12T00:00:00Z",
        }
        self.meta = {
            "SK": "THREAD#t1#META",
            "Name": "Build hooks",
            "Status": "active",
            "MessageCount": 4,
        }

    def get_current_thread_marker(self):
        return self.current

    def get_thread_meta(self, thread_id):
        return self.meta if thread_id == "t1" else None

    def put_item(self, sk, attributes):
        self.puts.append((sk, attributes))
        return {"SK": sk, **attributes}


def test_session_start_surfaces_active_thread_context():
    from server.tools.hooks import session_start_message

    db = FakeDynamo()

    def fake_list_threads():
        return {
            "threads": [
                {
                    "thread_id": "t1",
                    "name": "Build hooks",
                    "status": "active",
                    "last_activity": "2026-05-12T00:00:00Z",
                    "message_count": 4,
                }
            ]
        }

    message = session_start_message(db=db, list_threads_fn=fake_list_threads)

    assert "agent101 active thread context" in message
    assert "Build hooks" in message
    assert "t1" in message
    assert "Acknowledge this active thread" in message


def test_session_checkpoint_updates_current_thread_meta():
    from server.tools.hooks import checkpoint_current_thread

    db = FakeDynamo()
    result = checkpoint_current_thread(db=db, now_fn=lambda: "2026-05-12T01:02:03Z")

    assert result["status"] == "checkpointed"
    assert result["thread_id"] == "t1"
    assert db.puts == [
        (
            "THREAD#t1#META",
            {
                "SK": "THREAD#t1#META",
                "Name": "Build hooks",
                "Status": "active",
                "MessageCount": 4,
                "LastActivity": "2026-05-12T01:02:03Z",
                "CheckpointAt": "2026-05-12T01:02:03Z",
            },
        )
    ]


def test_kill_thread_trigger_dispatches_background_process_without_waiting():
    from server.tools.hooks import dispatch_kill_thread_summary

    proc = MagicMock()
    with patch("subprocess.Popen", return_value=proc) as popen:
        result = dispatch_kill_thread_summary(
            "t1",
            project_root=PLUGIN_DIR,
            python_executable="python-test",
        )

    assert result == {"status": "dispatched", "thread_id": "t1"}
    args = popen.call_args.args[0]
    assert args[:4] == [
        "python-test",
        "-m",
        "server.tools.hooks",
        "summarize-thread",
    ]
    assert "t1" in args
    assert popen.call_args.kwargs["cwd"] == str(PLUGIN_DIR)
    assert popen.call_args.kwargs["stdout"] == subprocess.DEVNULL


def test_hook_shell_scripts_exist_and_are_executable():
    for rel_path in (
        "hooks/session-start.sh",
        "hooks/session-checkpoint.sh",
        "hooks/kill-thread-trigger.sh",
        "hooks/post-tool-use-code-index.sh",
    ):
        path = PLUGIN_DIR / rel_path
        assert path.exists()
        assert path.stat().st_mode & 0o111
