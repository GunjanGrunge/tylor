"""
Tests for Story 5.1: sandbox path declaration.
Run: pytest server/tools/tests/test_executor.py -v
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

_is_windows = sys.platform == "win32"


PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
SKILLS_DIR = PLUGIN_DIR / "skills"


def test_set_sandbox_skill_file_exists_and_mentions_tool():
    path = SKILLS_DIR / "set-sandbox" / "SKILL.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: set-sandbox" in text
    assert "set_sandbox" in text
    assert "clear" in text
    assert "execute_in_sandbox" in text


def test_afk_status_skill_file_exists_and_mentions_tool():
    path = SKILLS_DIR / "afk-status" / "SKILL.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: afk-status" in text
    assert "afk_status" in text
    assert "No AFK session running" in text


def test_set_sandbox_validates_absolute_existing_path(tmp_path):
    from server.tools import executor as executor_mod

    mock_db = MagicMock()
    mock_db.resolve_thread_id.return_value = "t1"
    mock_db.get_thread_meta.return_value = {"SK": "THREAD#t1#META", "sandbox_roots": []}
    mock_db.set_sandbox_roots.return_value = {
        "SK": "THREAD#t1#META",
        "sandbox_roots": [str(tmp_path)],
    }

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        result = executor_mod.set_sandbox(str(tmp_path))

    assert result == {
        "status": "set",
        "thread_id": "t1",
        "sandbox_roots": [str(tmp_path)],
        "message": f"Sandbox set to {tmp_path} — executor will reject any path outside this root",
    }
    mock_db.set_sandbox_roots.assert_called_once_with("t1", [str(tmp_path)])


def test_set_sandbox_rejects_relative_or_missing_paths(tmp_path):
    from server.tools import executor as executor_mod

    with pytest.raises(ToolError, match="Sandbox path must be absolute and exist"):
        executor_mod.set_sandbox("relative/path", thread_id="t1")

    missing = tmp_path / "missing"
    with pytest.raises(ToolError, match="Sandbox path must be absolute and exist"):
        executor_mod.set_sandbox(str(missing), thread_id="t1")


def test_set_sandbox_appends_unique_roots(tmp_path):
    from server.tools import executor as executor_mod

    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()

    mock_db = MagicMock()
    mock_db.resolve_thread_id.return_value = "t1"
    mock_db.get_thread_meta.return_value = {
        "SK": "THREAD#t1#META",
        "sandbox_roots": [str(first)],
    }
    mock_db.set_sandbox_roots.return_value = {
        "SK": "THREAD#t1#META",
        "sandbox_roots": [str(first), str(second)],
    }

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        result = executor_mod.set_sandbox(str(second))

    assert result["sandbox_roots"] == [str(first), str(second)]
    mock_db.set_sandbox_roots.assert_called_once_with("t1", [str(first), str(second)])


def test_set_sandbox_clear_empties_roots():
    from server.tools import executor as executor_mod

    mock_db = MagicMock()
    mock_db.resolve_thread_id.return_value = "t1"
    mock_db.set_sandbox_roots.return_value = {
        "SK": "THREAD#t1#META",
        "sandbox_roots": [],
    }

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        result = executor_mod.set_sandbox("clear")

    assert result == {
        "status": "cleared",
        "thread_id": "t1",
        "sandbox_roots": [],
        "message": "Sandbox cleared — execution tools will refuse all path operations until a new sandbox is set",
    }
    mock_db.set_sandbox_roots.assert_called_once_with("t1", [])


def test_execute_in_sandbox_rejects_when_no_sandbox_configured():
    from server.tools import executor as executor_mod

    mock_db = MagicMock()
    mock_db.resolve_thread_id.return_value = "t1"
    mock_db.get_thread_meta.return_value = {"SK": "THREAD#t1#META", "sandbox_roots": []}

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        with pytest.raises(ToolError, match="No sandbox configured"):
            executor_mod.execute_in_sandbox(command="python3 tests/run.py")


def test_dynamo_set_sandbox_roots_updates_thread_meta():
    from server.tools.tests.test_switch_thread import make_client

    client, table = make_client()
    thread_meta = {
        "PK": "USER#testuser",
        "SK": "THREAD#t1#META",
        "CreatedAt": "2026-05-12T08:00:00Z",
        "UpdatedAt": "2026-05-12T08:00:00Z",
        "Version": 1,
        "Name": "thread-one",
        "sandbox_roots": ["/tmp/old"],
    }
    table.get_item.return_value = {"Item": thread_meta}

    written = client.set_sandbox_roots("t1", ["/tmp/new"])

    assert written["sandbox_roots"] == ["/tmp/new"]
    table.put_item.assert_called_once()
    assert table.put_item.call_args.kwargs["Item"]["sandbox_roots"] == ["/tmp/new"]


def test_executor_tools_registered_as_tier1():
    import asyncio
    import server.main  # noqa: F401
    from server.tools._mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    registered = {tool.name for tool in tools}
    assert {"set_sandbox", "execute_in_sandbox"} <= registered


def _executor_db(thread_id: str, sandbox_roots: list[str]):
    mock_db = MagicMock()
    mock_db.resolve_thread_id.return_value = thread_id
    mock_db.get_thread_meta.return_value = {
        "SK": f"THREAD#{thread_id}#META",
        "sandbox_roots": sandbox_roots,
    }
    return mock_db


def test_execute_in_sandbox_rejects_outside_absolute_path_and_logs(tmp_path):
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", [str(tmp_path)])

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        with pytest.raises(executor_mod.SandboxViolation, match="Path /etc/passwd is outside sandbox"):
            executor_mod.execute_in_sandbox(command="rm -rf /etc/passwd")

    log_call = mock_db.put_item.call_args
    assert log_call.args[0].startswith("THREAD#t1#MSG#")
    assert log_call.args[1]["Type"] == "sandbox_violation"
    assert log_call.args[1]["Command"] == "rm -rf /etc/passwd"
    assert log_call.args[1]["Path"] == "/etc/passwd"


def test_execute_in_sandbox_runs_bumblebee_gate_for_risky_commands(tmp_path):
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", [str(tmp_path)])

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "run_bumblebee_security_gate", return_value=True
    ) as security_gate, patch.object(executor_mod, "_log_thread_event") as log_event:
        executor_mod.execute_in_sandbox(
            command="python3 -m pip install requests",
            cwd=str(tmp_path),
        )

    security_gate.assert_called_once_with("python3 -m pip install requests", str(tmp_path))
    log_event.assert_any_call(
        mock_db,
        "t1",
        "security_gate",
        {
            "Command": "python3 -m pip install requests",
            "Cwd": str(tmp_path),
            "Outcome": "passed",
            "Content": "Bumblebee security gate flagged this command and completed a scan successfully.",
        },
    )


def test_bumblebee_security_gate_missing_cli_suggests_alternatives():
    from server.tools import security as security_mod

    # Patch bumblebee_enabled() directly — it reads from server.config, not os.environ,
    # so patch.dict(os.environ) would have no effect here.
    with patch.object(security_mod, "bumblebee_enabled", return_value=True), \
         patch.object(security_mod, "_bumblebee_path", return_value=None):
        with pytest.raises(ToolError) as excinfo:
            security_mod.run_bumblebee_security_gate("python3 -m pip install requests", "/tmp")

    assert "Bumblebee security gate is enabled by default" in str(excinfo.value)
    assert "Suggested alternatives" in str(excinfo.value)
    assert "BUMBLEBEE_ENABLED=false" in str(excinfo.value)


@pytest.mark.asyncio
async def test_scan_packages_parses_pip_audit_findings_on_nonzero_exit(tmp_path):
    from server.tools import security as security_mod

    async def fake_run_scanner(args, cwd, timeout=60):
        return (
            1,
            '{"dependencies":[{"name":"demo","version":"1.0.0","vulns":[{"id":"PYSEC-1","description":"bad package"}]}]}',
            "",
        )

    def fake_which(name):
        return "pip-audit" if name == "pip-audit" else None

    with patch.object(security_mod.shutil, "which", side_effect=fake_which), \
         patch.object(security_mod, "_run_scanner_async", side_effect=fake_run_scanner):
        findings = await security_mod.scan_packages_async(str(tmp_path))

    assert findings == ["demo==1.0.0 [PYSEC-1]: bad package"]


def test_execute_in_sandbox_rejects_symlink_escape(tmp_path):
    from server.tools import executor as executor_mod

    outside = tmp_path / "outside"
    outside.mkdir()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    target = outside / "secret.txt"
    target.write_text("secret", encoding="utf-8")
    escape = sandbox / "escape"
    try:
        escape.symlink_to(outside, target_is_directory=True)
    except OSError as e:
        pytest.skip(f"Symlink creation requires elevated privileges on this OS: {e}")

    mock_db = _executor_db("t1", [str(sandbox)])

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        with pytest.raises(executor_mod.SandboxViolation, match="outside sandbox"):
            executor_mod.execute_in_sandbox(
                command=f"cat {escape / 'secret.txt'}",
                cwd=str(sandbox),
            )

    assert mock_db.put_item.call_args.args[1]["ResolvedPath"] == str(target.resolve())


def test_execute_in_sandbox_does_not_expand_shell_variables_outside_sandbox(tmp_path):
    from server.tools import executor as executor_mod

    sandbox = tmp_path / "sandbox"
    outside = tmp_path / "outside"
    sandbox.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret", encoding="utf-8")

    mock_db = _executor_db("t1", [str(sandbox)])

    # Pass the outside path as a direct positional argument — the sandbox
    # path-checker scans all absolute path tokens in the command and raises
    # SandboxViolation before any process starts. Using as_posix() for
    # cross-platform shlex compatibility (avoids backslash issues on Windows).
    cmd = f"python3 -c \"import sys; print(open(sys.argv[1]).read())\" {secret.as_posix()}"
    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        with pytest.raises(executor_mod.SandboxViolation, match="outside sandbox"):
            executor_mod.execute_in_sandbox(command=cmd, cwd=str(sandbox))


def test_execute_in_sandbox_runs_valid_command_and_logs_summary(tmp_path):
    from server.tools import executor as executor_mod

    run_py = tmp_path / "run.py"
    run_py.write_text("print('ok')\n", encoding="utf-8")
    mock_db = _executor_db("t1", [str(tmp_path)])

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        result = executor_mod.execute_in_sandbox(
            command=f"python3 {run_py.name}",
            cwd=str(tmp_path),
        )

    assert result["status"] == "completed"
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "ok"
    assert result["stderr"] == ""
    assert result["duration_ms"] >= 0
    log_attrs = mock_db.put_item.call_args.args[1]
    assert log_attrs["Type"] == "sandbox_execution"
    assert log_attrs["Command"] == f"python3 {run_py.name}"
    assert log_attrs["ExitCode"] == 0


def test_execute_in_sandbox_timeout_kills_process_and_returns_partial_output(tmp_path):
    from server.tools import executor as executor_mod

    slow_py = tmp_path / "slow.py"
    slow_py.write_text(
        "import sys, time\n"
        "print('started', flush=True)\n"
        "sys.stdout.flush()\n"
        "time.sleep(5)\n",
        encoding="utf-8",
    )
    mock_db = _executor_db("t1", [str(tmp_path)])

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        result = executor_mod.execute_in_sandbox(
            # -u = unbuffered stdout so partial output is captured before kill
            command=f"python3 -u {slow_py.name}",
            cwd=str(tmp_path),
            timeout_seconds=1,
        )

    assert result["status"] == "timeout"
    assert result["exit_code"] is None
    assert "started" in result["stdout"]
    assert result["message"] == "Command timed out after 1s — partial stdout captured"
    assert mock_db.put_item.call_args.args[1]["Type"] == "sandbox_execution"
    assert mock_db.put_item.call_args.args[1]["Outcome"] == "timeout"


def test_classify_execution_failure_transient_and_logic():
    from server.tools import executor as executor_mod

    assert executor_mod.classify_execution_failure(
        "Connection reset by peer"
    ) == "transient"
    assert executor_mod.classify_execution_failure(
        "ModuleNotFoundError: No module named 'httpx'"
    ) == "logic"
    assert executor_mod.classify_execution_failure("assert 1 == 2") == "logic"


def test_execute_with_recovery_retries_transient_failures_with_backoff():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    attempts = [
        {"status": "completed", "exit_code": 1, "stdout": "", "stderr": "network timeout", "duration_ms": 1},
        {"status": "completed", "exit_code": 1, "stdout": "", "stderr": "temporary failure", "duration_ms": 1},
        {"status": "completed", "exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1},
    ]

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "execute_in_sandbox", side_effect=attempts
    ) as execute, patch.object(executor_mod.time, "sleep") as sleep:
        result = executor_mod.execute_with_recovery("pytest -q", cwd="/tmp")

    assert result["status"] == "recovered"
    assert result["classification"] == "transient"
    assert execute.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [5, 15]
    assert mock_db.put_item.call_args.args[1]["Type"] == "recovery_decision"


def test_execute_with_recovery_autofixes_module_not_found_and_reruns():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    attempts = [
        {
            "status": "completed",
            "exit_code": 1,
            "stdout": "",
            "stderr": "ModuleNotFoundError: No module named 'httpx'",
            "duration_ms": 1,
        },
        {"status": "completed", "exit_code": 0, "stdout": "installed", "stderr": "", "duration_ms": 1},
        {"status": "completed", "exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1},
    ]

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "execute_in_sandbox", side_effect=attempts
    ) as execute:
        result = executor_mod.execute_with_recovery("python3 app.py", cwd="/tmp")

    assert result["status"] == "recovered"
    assert result["classification"] == "logic"
    assert execute.call_args_list[1].kwargs["command"] == "python3 -m pip install httpx"
    assert execute.call_count == 3
    assert (
        mock_db.put_item.call_args.args[1]["Content"]
        == "Failure: ModuleNotFoundError -> Auto-fix: pip install httpx -> Re-run: success"
    )


def test_execute_with_recovery_rejects_unsafe_module_name():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    failed = {
        "status": "completed",
        "exit_code": 1,
        "stdout": "",
        "stderr": "ModuleNotFoundError: No module named 'httpx;touch /tmp/pwned'",
        "duration_ms": 1,
    }

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "execute_in_sandbox", return_value=failed
    ) as execute:
        result = executor_mod.execute_with_recovery("python3 app.py", cwd="/tmp")

    assert result["status"] == "paused"
    assert execute.call_count == 1
    assert result["classification"] == "logic"


def test_execute_with_recovery_exhaustion_writes_decision_log():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    failed = {
        "status": "completed",
        "exit_code": 2,
        "stdout": "",
        "stderr": "pytest failed",
        "duration_ms": 1,
    }

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "execute_in_sandbox", return_value=failed
    ):
        result = executor_mod.execute_with_recovery("pytest -q", cwd="/tmp")

    assert result["status"] == "paused"
    assert result["classification"] == "logic"
    log_attrs = mock_db.put_item.call_args.args[1]
    assert log_attrs["Type"] == "recovery_decision"
    assert log_attrs["OriginalCommand"] == "pytest -q"
    assert log_attrs["RecommendedNextStep"] == "Developer input required before continuing AFK execution."


def test_execute_with_recovery_caps_total_attempts():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    failed = {
        "status": "completed",
        "exit_code": 1,
        "stdout": "",
        "stderr": "network timeout",
        "duration_ms": 1,
    }

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "execute_in_sandbox", return_value=failed
    ), patch.object(executor_mod.time, "sleep"):
        result = executor_mod.execute_with_recovery(
            "pytest -q",
            cwd="/tmp",
            recovery_attempts_used=5,
        )

    assert result["status"] == "paused"
    assert result["message"] == "Recovery cap reached — pausing autonomous execution"
    assert mock_db.put_item.call_args.args[1]["Content"] == "Recovery cap reached — pausing autonomous execution"


def test_start_afk_logs_plan_executes_steps_and_completion_summary():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    attempts = [
        {"status": "completed", "exit_code": 0, "stdout": "one\n", "stderr": "", "duration_ms": 1},
        {"status": "completed", "exit_code": 0, "stdout": "two\n", "stderr": "", "duration_ms": 1},
    ]

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "execute_in_sandbox", side_effect=attempts
    ) as execute:
        result = executor_mod.start_afk(
            task="run the checks",
            steps=["echo one", "echo two"],
            cwd="/tmp",
        )

    assert result["status"] == "completed"
    assert result["message"] == "Task complete — see thread t1 for full execution log"
    assert [call.kwargs["command"] for call in execute.call_args_list] == ["echo one", "echo two"]

    log_items = [call.args[1] for call in mock_db.put_item.call_args_list if "Type" in call.args[1]]
    log_types = [item["Type"] for item in log_items]
    assert log_types.count("afk_plan") == 1
    assert log_types.count("afk_step") == 2
    assert log_types.count("afk_completion") == 1
    completion = [item for item in log_items if item["Type"] == "afk_completion"][0]
    assert completion["TaskDescription"] == "run the checks"
    assert completion["Tests"] == "not_run"
    assert completion["FilesModified"] == []


def test_start_afk_uses_sandbox_root_for_file_summary_when_cwd_omitted(tmp_path):
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", [str(tmp_path)])
    success = {"status": "completed", "exit_code": 0, "stdout": "ok\n", "stderr": "", "duration_ms": 1}
    modified = [{"path": "app.py", "status": "M", "diff_summary": "1 file changed"}]

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "execute_in_sandbox", return_value=success
    ), patch.object(executor_mod, "_files_modified_summary", return_value=modified) as summary:
        result = executor_mod.start_afk(task="ship", steps=["pytest -q"])

    summary.assert_called_once_with(str(tmp_path))
    assert result["files_modified"] == modified


def test_start_afk_background_returns_without_running_steps_inline(tmp_path):
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", [str(tmp_path)])
    mock_thread = MagicMock()

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod.threading, "Thread", return_value=mock_thread
    ), patch.object(executor_mod, "execute_in_sandbox") as execute:
        result = executor_mod.start_afk(
            task="long task",
            steps=["python3 slow.py", "pytest -q"],
            background=True,
        )

    assert result["status"] == "started"
    assert result["current_step"] == "python3 slow.py"
    assert result["steps_total"] == 2
    mock_thread.start.assert_called_once()
    execute.assert_not_called()


def test_start_afk_pauses_at_safe_checkpoint_when_pause_requested():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    active = {"SK": "THREAD#t1#META", "sandbox_roots": ["/tmp"], "afk_session": {"status": "active"}}
    pause_requested = {
        "SK": "THREAD#t1#META",
        "sandbox_roots": ["/tmp"],
        "afk_session": {"status": "pause_requested"},
    }
    mock_db.get_thread_meta.side_effect = [active, active, pause_requested]
    success = {"status": "completed", "exit_code": 0, "stdout": "ok\n", "stderr": "", "duration_ms": 1}

    with patch.object(executor_mod, "_get_db", return_value=mock_db), patch.object(
        executor_mod, "execute_in_sandbox", return_value=success
    ):
        result = executor_mod.start_afk(
            task="run two steps",
            steps=["echo ok", "echo should-not-run"],
            cwd="/tmp",
        )

    assert result["status"] == "paused"
    assert result["current_step"] == "echo should-not-run"
    assert (
        result["message"]
        == "AFK paused — here's where I am: echo should-not-run. Type 'resume' to continue or give new instructions"
    )


def test_pause_afk_marks_session_for_checkpoint_pause():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    mock_db.get_thread_meta.return_value = {
        "SK": "THREAD#t1#META",
        "sandbox_roots": ["/tmp"],
        "afk_session": {
            "status": "active",
            "current_step": "pytest -q",
            "steps_completed": 1,
            "steps_total": 3,
        },
    }

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        result = executor_mod.pause_afk()

    assert result["status"] == "pause_requested"
    assert (
        result["message"]
        == "AFK paused — here's where I am: pytest -q. Type 'resume' to continue or give new instructions"
    )
    written_meta = mock_db.put_item.call_args.args[1]
    assert written_meta["afk_session"]["status"] == "pause_requested"
    assert written_meta["afk_session"]["pause_requested"] is True


def test_afk_status_reports_active_session_and_idle_message():
    from server.tools import executor as executor_mod

    mock_db = _executor_db("t1", ["/tmp"])
    mock_db.get_thread_meta.return_value = {
        "SK": "THREAD#t1#META",
        "sandbox_roots": ["/tmp"],
        "afk_session": {
            "status": "active",
            "task": "ship it",
            "current_step": "pytest -q",
            "steps_completed": 2,
            "steps_total": 4,
            "started_at_monotonic": "2026-05-14T10:00:00Z",  # ISO string, not float
            "last_command_output": "last line",
        },
    }

    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        result = executor_mod.afk_status()

    assert result["status"] == "active"
    assert result["current_step"] == "pytest -q"
    assert result["steps_completed"] == 2
    assert result["steps_total"] == 4
    assert result["elapsed_seconds"] is not None  # just verify it computes without crash
    assert result["last_command_output"] == "last line"

    mock_db.get_thread_meta.return_value = {"SK": "THREAD#t1#META", "sandbox_roots": ["/tmp"]}
    with patch.object(executor_mod, "_get_db", return_value=mock_db):
        idle = executor_mod.afk_status()

    assert idle == {"status": "idle", "message": "No AFK session running"}
