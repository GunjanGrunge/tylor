"""server/tools/executor.py — AFK sandbox declaration and execution guard."""
from __future__ import annotations
import os
import re
import shlex
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

from ._mcp import mcp
from .security import run_bumblebee_security_gate


NO_SANDBOX_MESSAGE = "No sandbox configured — run /set-sandbox <path> first"
DEFAULT_TIMEOUT_SECONDS = 120
TRANSIENT_BACKOFF_SECONDS = (5, 15, 45)
RECOVERY_CAP = 5
SAFE_MODULE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SandboxViolation(ToolError):
    """Raised when a command references a path outside configured sandbox roots."""


def classify_execution_failure(stderr: str) -> str:
    """Classify command stderr for AFK recovery policy."""
    text = (stderr or "").lower()
    transient_markers = (
        "connection reset",
        "connection refused",
        "network",
        "timeout",
        "timed out",
        "temporary",
        "temporarily unavailable",
        "resource busy",
        "file lock",
        "locked",
    )
    if any(marker in text for marker in transient_markers):
        return "transient"
    return "logic"


def _missing_module(stderr: str) -> str | None:
    match = re.search(r"No module named ['\"]([^'\"]+)['\"]", stderr or "")
    module = match.group(1) if match else None
    if not module or not SAFE_MODULE_RE.fullmatch(module):
        return None
    return module


def _get_db():
    from server.tools.tylor import _get_db as get_thread_db

    return get_thread_db()


def _resolve_existing_absolute_path(path: str) -> str:
    expanded = Path(path).expanduser()
    if not expanded.is_absolute() or not expanded.exists():
        raise ToolError("Sandbox path must be absolute and exist")
    return os.path.realpath(expanded)


def _thread_meta(db, thread_id: str) -> dict:
    meta = db.get_thread_meta(thread_id)
    if not meta:
        raise ToolError(f"Thread not found: {thread_id}")
    return meta


def _now_iso() -> str:
    from server.tools.tylor import _now_iso as thread_now

    return thread_now()


def _log_thread_event(db, thread_id: str, event_type: str, attributes: dict) -> None:
    sk = f"THREAD#{thread_id}#MSG#{_now_iso()}#{event_type.upper()}#{uuid.uuid4().hex}"
    db.put_item(sk, {"Role": "system", "Type": event_type, **attributes})


def _write_thread_meta(db, thread_id: str, meta: dict) -> dict:
    updated = dict(meta)
    return db.put_item(f"THREAD#{thread_id}#META", updated)


def _stdout_summary(result: dict, limit: int = 1000) -> str:
    text = (result.get("stdout") or result.get("stderr") or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _default_afk_steps(task: str) -> list[str]:
    return [
        f"printf '%s\\n' {shlex.quote('AFK task accepted: ' + task)}",
        "pytest -q",
    ]


def _pause_message(current_step: str) -> str:
    return (
        f"AFK paused — here's where I am: {current_step}. "
        "Type 'resume' to continue or give new instructions"
    )


def _afk_session(meta: dict) -> dict | None:
    session = meta.get("afk_session")
    return dict(session) if isinstance(session, dict) else None


def _is_pause_requested(meta: dict) -> bool:
    session = _afk_session(meta)
    return bool(
        session
        and (
            session.get("pause_requested") is True
            or session.get("status") == "pause_requested"
        )
    )


def _files_modified_summary(cwd: str | None) -> list[dict]:
    if not cwd:
        return []
    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if status.returncode != 0:
        return []
    changed = []
    for line in status.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        path_for_diff = path.split(" -> ")[-1]
        file_diff = subprocess.run(
            ["git", "diff", "--stat", "--", path_for_diff],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        changed.append({
            "path": path,
            "status": line[:2].strip(),
            "diff_summary": file_diff.stdout.strip(),
        })
    return changed


def _test_state(outcomes: list[dict]) -> str:
    testish = [
        outcome
        for outcome in outcomes
        if "test" in outcome.get("command", "").lower()
        or "pytest" in outcome.get("command", "").lower()
    ]
    if not testish:
        return "not_run"
    return "passing" if all(outcome.get("exit_code") == 0 for outcome in testish) else "failing"


def _recovery_log(
    db,
    thread_id: str,
    command: str,
    result: dict,
    classification: str,
    attempts: list[dict],
    content: str,
    recommended_next_step: str | None = None,
) -> None:
    attributes = {
        "OriginalCommand": command,
        "ExitCode": result.get("exit_code"),
        "Classification": classification,
        "Attempts": attempts,
        "CommandsRun": [attempt.get("command") for attempt in attempts if attempt.get("command")],
        "FilesModified": [],
        "Content": content,
    }
    if recommended_next_step:
        attributes["RecommendedNextStep"] = recommended_next_step
    _log_thread_event(db, thread_id, "recovery_decision", attributes)


def _real_roots(raw_roots: list[str]) -> list[str]:
    return [os.path.realpath(Path(root).expanduser()) for root in raw_roots]


def _is_inside_roots(path: str, roots: list[str]) -> bool:
    real_path = os.path.realpath(path)
    for root in roots:
        try:
            if os.path.commonpath([real_path, root]) == root:
                return True
        except ValueError:
            continue
    return False


def _candidate_paths(command: str, cwd: str) -> list[tuple[str, str]]:
    candidates = [(cwd, cwd)]
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ToolError(f"Invalid command syntax: {exc}") from exc
    for token in tokens:
        # Extract value from --flag=value or -f/value forms
        raw = token
        if "=" in token and token.startswith("-"):
            raw = token.split("=", 1)[1]
        elif token.startswith("-") and not token.startswith("--") and len(token) > 2 and "/" in token:
            raw = token[2:]  # -o/path/to/file
        elif token.startswith("-") and "=" not in token and "/" not in token:
            continue  # pure flag like -v, --verbose
        path = Path(raw).expanduser()
        if path.is_absolute():
            candidates.append((raw, str(path)))
            continue
        relative = Path(cwd) / path
        # Include bare filenames resolved relative to cwd (even if they don't exist yet)
        candidates.append((raw, str(relative)))
    return candidates


def _raise_violation(db, thread_id: str, command: str, display_path: str, resolved_path: str) -> None:
    message = f"Path {display_path} is outside sandbox — operation rejected"
    _log_thread_event(
        db,
        thread_id,
        "sandbox_violation",
        {
            "Command": command,
            "Path": display_path,
            "ResolvedPath": resolved_path,
            "Content": message,
        },
    )
    raise SandboxViolation(message)


def _validate_command_paths(
    db,
    thread_id: str,
    command: str,
    cwd: str,
    roots: list[str],
) -> None:
    for display_path, path in _candidate_paths(command, cwd):
        resolved = os.path.realpath(path)
        if not _is_inside_roots(resolved, roots):
            _raise_violation(db, thread_id, command, display_path, resolved)


def _terminate_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return


@mcp.tool()
def set_sandbox(path: str, thread_id: str | None = None) -> dict:
    """
    Add or clear sandbox roots for a thread.

    Args:
        path: Absolute existing path to allow, or "clear" to remove all roots.
        thread_id: Optional thread id. Defaults to the active current thread.
    """
    db = _get_db()
    resolved_thread_id = db.resolve_thread_id(thread_id)

    if path.strip().lower() == "clear":
        item = db.set_sandbox_roots(resolved_thread_id, [])
        return {
            "status": "cleared",
            "thread_id": resolved_thread_id,
            "sandbox_roots": list(item.get("sandbox_roots", [])),
            "message": (
                "Sandbox cleared — execution tools will refuse all path operations "
                "until a new sandbox is set"
            ),
        }

    root = _resolve_existing_absolute_path(path)
    meta = _thread_meta(db, resolved_thread_id)
    roots = list(meta.get("sandbox_roots", []))
    if root not in roots:
        roots.append(root)

    item = db.set_sandbox_roots(resolved_thread_id, roots)
    return {
        "status": "set",
        "thread_id": resolved_thread_id,
        "sandbox_roots": list(item.get("sandbox_roots", [])),
        "message": f"Sandbox set to {path} — executor will reject any path outside this root",
    }


@mcp.tool()
def execute_in_sandbox(
    command: str,
    thread_id: str | None = None,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """
    Execute a command inside declared sandbox roots.
    Story 5.1 only implements the no-sandbox guard; Story 5.2 adds execution.
    """
    db = _get_db()
    resolved_thread_id = db.resolve_thread_id(thread_id)
    meta = _thread_meta(db, resolved_thread_id)
    sandbox_roots = list(meta.get("sandbox_roots", []))
    if not sandbox_roots:
        raise ToolError(NO_SANDBOX_MESSAGE)

    roots = _real_roots(sandbox_roots)
    workdir = os.path.realpath(Path(cwd).expanduser()) if cwd else roots[0]
    if not _is_inside_roots(workdir, roots):
        _raise_violation(db, resolved_thread_id, command, cwd or workdir, workdir)
    _validate_command_paths(db, resolved_thread_id, command, workdir, roots)

    checked = run_bumblebee_security_gate(command, workdir)
    if checked:
        _log_thread_event(
            db,
            resolved_thread_id,
            "security_gate",
            {
                "Command": command,
                "Cwd": workdir,
                "Outcome": "passed",
                "Content": "Bumblebee security gate flagged this command and completed a scan successfully.",
            },
        )

    start = time.monotonic()
    try:
        args = shlex.split(command)
    except ValueError as exc:
        raise ToolError(f"Invalid command syntax: {exc}") from exc
    if not args:
        raise ToolError("Command must not be empty")

    process = subprocess.Popen(
        args,
        cwd=workdir,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        duration_ms = int((time.monotonic() - start) * 1000)
        result = {
            "status": "completed",
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
        }
        _log_thread_event(
            db,
            resolved_thread_id,
            "sandbox_execution",
            {
                "Command": command,
                "Cwd": workdir,
                "ExitCode": process.returncode,
                "Outcome": "success" if process.returncode == 0 else "failed",
                "DurationMs": duration_ms,
                "Content": f"Command `{command}` exited {process.returncode}",
            },
        )
        return result
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        duration_ms = int((time.monotonic() - start) * 1000)
        message = f"Command timed out after {timeout_seconds}s — partial stdout captured"
        _log_thread_event(
            db,
            resolved_thread_id,
            "sandbox_execution",
            {
                "Command": command,
                "Cwd": workdir,
                "ExitCode": None,
                "Outcome": "timeout",
                "DurationMs": duration_ms,
                "Content": message,
            },
        )
        return {
            "status": "timeout",
            "exit_code": None,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "message": message,
        }


@mcp.tool()
def execute_with_recovery(
    command: str,
    thread_id: str | None = None,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    recovery_attempts_used: int = 0,
) -> dict:
    """
    Execute a sandboxed command and apply bounded AFK failure recovery.

    Retries transient failures with 5s, 15s, 45s backoff. For fixable import
    failures, installs the missing module once and re-runs the original command.
    """
    db = _get_db()
    resolved_thread_id = db.resolve_thread_id(thread_id)
    if recovery_attempts_used >= RECOVERY_CAP:
        message = "Recovery cap reached — pausing autonomous execution"
        _log_thread_event(
            db,
            resolved_thread_id,
            "recovery_decision",
            {
                "OriginalCommand": command,
                "ExitCode": None,
                "Classification": "cap_reached",
                "Attempts": [],
                "CommandsRun": [],
                "FilesModified": [],
                "RecommendedNextStep": "Developer input required before continuing AFK execution.",
                "Content": message,
            },
        )
        return {"status": "paused", "message": message}

    attempts: list[dict] = []
    result = execute_in_sandbox(
        command=command,
        thread_id=resolved_thread_id,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )
    attempts.append({"command": command, "outcome": result.get("status"), "exit_code": result.get("exit_code")})
    if result.get("exit_code") == 0:
        return {"status": "success", "result": result, "attempts": attempts}

    classification = classify_execution_failure(result.get("stderr", ""))
    used = recovery_attempts_used

    if classification == "transient":
        current = result
        for backoff in TRANSIENT_BACKOFF_SECONDS:
            if used >= RECOVERY_CAP:
                break
            used += 1
            time.sleep(backoff)
            current = execute_in_sandbox(
                command=command,
                thread_id=resolved_thread_id,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
            )
            attempts.append({
                "command": command,
                "strategy": f"transient_retry_after_{backoff}s",
                "outcome": current.get("status"),
                "exit_code": current.get("exit_code"),
            })
            if current.get("exit_code") == 0:
                _recovery_log(
                    db,
                    resolved_thread_id,
                    command,
                    result,
                    classification,
                    attempts,
                    "Transient failure recovered after retry.",
                )
                return {
                    "status": "recovered",
                    "classification": classification,
                    "result": current,
                    "attempts": attempts,
                }
        result = current

    module = _missing_module(result.get("stderr", ""))
    if classification == "logic" and module and used < RECOVERY_CAP:
        fix_command = f"python3 -m pip install {module}"
        used += 1
        fix = execute_in_sandbox(
            command=fix_command,
            thread_id=resolved_thread_id,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
        attempts.append({
            "command": fix_command,
            "strategy": "install_missing_module",
            "outcome": fix.get("status"),
            "exit_code": fix.get("exit_code"),
        })
        if fix.get("exit_code") == 0 and used < RECOVERY_CAP:
            used += 1
            rerun = execute_in_sandbox(
                command=command,
                thread_id=resolved_thread_id,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
            )
            attempts.append({
                "command": command,
                "strategy": "rerun_after_fix",
                "outcome": rerun.get("status"),
                "exit_code": rerun.get("exit_code"),
            })
            if rerun.get("exit_code") == 0:
                content = (
                    f"Failure: ModuleNotFoundError -> Auto-fix: pip install {module} "
                    "-> Re-run: success"
                )
                _recovery_log(db, resolved_thread_id, command, result, classification, attempts, content)
                return {
                    "status": "recovered",
                    "classification": classification,
                    "result": rerun,
                    "attempts": attempts,
                }
            result = rerun

    message = (
        "Recovery cap reached — pausing autonomous execution"
        if used >= RECOVERY_CAP
        else "Recovery exhausted — pausing autonomous execution"
    )
    _recovery_log(
        db,
        resolved_thread_id,
        command,
        result,
        classification,
        attempts,
        message,
        recommended_next_step="Developer input required before continuing AFK execution.",
    )
    return {
        "status": "paused",
        "classification": classification,
        "message": message,
        "attempts": attempts,
    }


@mcp.tool()
def start_afk(
    task: str,
    steps: list[str] | None = None,
    thread_id: str | None = None,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    background: bool = False,
) -> dict:
    """
    Start an AFK task: persist a plan, execute each command in the sandbox, and
    write step and completion events to the active thread.
    """
    db = _get_db()
    resolved_thread_id = db.resolve_thread_id(thread_id)
    meta = _thread_meta(db, resolved_thread_id)
    sandbox_roots = list(meta.get("sandbox_roots", []))
    if not sandbox_roots:
        raise ToolError(NO_SANDBOX_MESSAGE)

    planned_steps = list(steps) if steps else _default_afk_steps(task)
    if not planned_steps:
        raise ToolError("AFK task requires at least one execution step")
    effective_cwd = cwd or sandbox_roots[0]

    session = {
        "id": uuid.uuid4().hex,
        "status": "active",
        "task": task,
        "steps": planned_steps,
        "steps_completed": 0,
        "steps_total": len(planned_steps),
        "current_step": planned_steps[0],
        "last_command_output": "",
        "started_at": _now_iso(),
        "started_at_monotonic": _now_iso(),
        "pause_requested": False,
    }
    meta["afk_session"] = session
    _write_thread_meta(db, resolved_thread_id, meta)
    _log_thread_event(
        db,
        resolved_thread_id,
        "afk_plan",
        {
            "TaskDescription": task,
            "Steps": planned_steps,
            "Content": "AFK execution plan:\n"
            + "\n".join(f"{index}. {step}" for index, step in enumerate(planned_steps, start=1)),
        },
    )

    if background:
        worker = threading.Thread(
            target=_run_afk_background,
            args=(resolved_thread_id, task, planned_steps, effective_cwd, timeout_seconds),
            daemon=True,
        )
        worker.start()
        return {
            "status": "started",
            "thread_id": resolved_thread_id,
            "steps_total": len(planned_steps),
            "current_step": planned_steps[0],
            "message": f"AFK started — see thread {resolved_thread_id} for progress",
        }

    return _run_afk_steps(
        db=db,
        resolved_thread_id=resolved_thread_id,
        meta=meta,
        task=task,
        planned_steps=planned_steps,
        effective_cwd=effective_cwd,
        timeout_seconds=timeout_seconds,
        session=session,
    )


def _run_afk_background(
    resolved_thread_id: str,
    task: str,
    planned_steps: list[str],
    effective_cwd: str,
    timeout_seconds: int,
) -> None:
    db = _get_db()
    meta = _thread_meta(db, resolved_thread_id)
    session = _afk_session(meta) or {
        "id": uuid.uuid4().hex,
        "status": "active",
        "task": task,
        "steps": planned_steps,
        "steps_completed": 0,
        "steps_total": len(planned_steps),
        "current_step": planned_steps[0],
        "last_command_output": "",
        "started_at": _now_iso(),
        "started_at_monotonic": _now_iso(),
        "pause_requested": False,
    }
    _run_afk_steps(
        db=db,
        resolved_thread_id=resolved_thread_id,
        meta=meta,
        task=task,
        planned_steps=planned_steps,
        effective_cwd=effective_cwd,
        timeout_seconds=timeout_seconds,
        session=session,
    )


def _run_afk_steps(
    db,
    resolved_thread_id: str,
    meta: dict,
    task: str,
    planned_steps: list[str],
    effective_cwd: str,
    timeout_seconds: int,
    session: dict,
) -> dict:
    outcomes: list[dict] = []
    for index, command in enumerate(planned_steps, start=1):
        checkpoint_meta = _thread_meta(db, resolved_thread_id)
        if _is_pause_requested(checkpoint_meta):
            session.update({
                "status": "paused",
                "current_step": command,
                "pause_requested": False,
            })
            checkpoint_meta["afk_session"] = session
            _write_thread_meta(db, resolved_thread_id, checkpoint_meta)
            return {
                "status": "paused",
                "thread_id": resolved_thread_id,
                "current_step": command,
                "steps_completed": session["steps_completed"],
                "steps_total": session["steps_total"],
                "message": _pause_message(command),
            }

        session["current_step"] = command
        meta["afk_session"] = session
        _write_thread_meta(db, resolved_thread_id, meta)
        result = execute_in_sandbox(
            command=command,
            thread_id=resolved_thread_id,
            cwd=effective_cwd,
            timeout_seconds=timeout_seconds,
        )
        outcome = {
            "step": index,
            "command": command,
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
            "stdout_summary": _stdout_summary(result),
        }
        outcomes.append(outcome)
        session.update({
            "steps_completed": index,
            "last_command_output": outcome["stdout_summary"],
        })
        meta = _thread_meta(db, resolved_thread_id)
        if _is_pause_requested(meta):
            next_step = planned_steps[index] if index < len(planned_steps) else command
            session.update({
                "status": "paused",
                "current_step": next_step,
                "pause_requested": False,
            })
            meta["afk_session"] = session
            _write_thread_meta(db, resolved_thread_id, meta)
            return {
                "status": "paused",
                "thread_id": resolved_thread_id,
                "current_step": next_step,
                "steps_completed": session["steps_completed"],
                "steps_total": session["steps_total"],
                "message": _pause_message(next_step),
            }
        meta["afk_session"] = session
        _write_thread_meta(db, resolved_thread_id, meta)
        _log_thread_event(
            db,
            resolved_thread_id,
            "afk_step",
            {
                "Step": index,
                "Command": command,
                "Outcome": "success" if result.get("exit_code") == 0 else "failed",
                "ExitCode": result.get("exit_code"),
                "StdoutSummary": outcome["stdout_summary"],
                "Content": f"AFK step {index}/{len(planned_steps)} `{command}` exited {result.get('exit_code')}",
            },
        )

        checkpoint_meta = _thread_meta(db, resolved_thread_id)
        if _is_pause_requested(checkpoint_meta) and index < len(planned_steps):
            next_step = planned_steps[index]
            session.update({
                "status": "paused",
                "current_step": next_step,
                "pause_requested": False,
            })
            checkpoint_meta["afk_session"] = session
            _write_thread_meta(db, resolved_thread_id, checkpoint_meta)
            return {
                "status": "paused",
                "thread_id": resolved_thread_id,
                "current_step": next_step,
                "steps_completed": session["steps_completed"],
                "steps_total": session["steps_total"],
                "message": _pause_message(next_step),
            }

        if result.get("exit_code") != 0:
            session["status"] = "failed"
            meta["afk_session"] = session
            _write_thread_meta(db, resolved_thread_id, meta)
            _log_thread_event(
                db,
                resolved_thread_id,
                "afk_completion",
                {
                    "TaskDescription": task,
                    "StepsExecuted": outcomes,
                    "FilesModified": _files_modified_summary(effective_cwd),
                    "Tests": _test_state(outcomes),
                    "Content": f"AFK task failed at step {index}: {command}",
                },
            )
            return {
                "status": "failed",
                "thread_id": resolved_thread_id,
                "failed_step": command,
                "steps_executed": outcomes,
            }

    files_modified = _files_modified_summary(effective_cwd)
    tests = _test_state(outcomes)
    session.update({
        "status": "completed",
        "current_step": planned_steps[-1],
        "files_modified": files_modified,
        "tests": tests,
    })
    meta["afk_session"] = session
    _log_thread_event(
        db,
        resolved_thread_id,
        "afk_completion",
        {
            "TaskDescription": task,
            "StepsExecuted": outcomes,
            "FilesModified": files_modified,
            "Tests": tests,
            "Content": f"AFK task complete: {task}",
        },
    )
    _write_thread_meta(db, resolved_thread_id, meta)
    return {
        "status": "completed",
        "thread_id": resolved_thread_id,
        "steps_executed": outcomes,
        "files_modified": files_modified,
        "tests": tests,
        "message": f"Task complete — see thread {resolved_thread_id} for full execution log",
    }


@mcp.tool()
def pause_afk(thread_id: str | None = None) -> dict:
    """
    Request an active AFK session to pause after the current command finishes.
    """
    db = _get_db()
    resolved_thread_id = db.resolve_thread_id(thread_id)
    meta = _thread_meta(db, resolved_thread_id)
    session = _afk_session(meta)
    if not session or session.get("status") not in {"active", "pause_requested"}:
        return {"status": "idle", "message": "No AFK session running"}

    session["status"] = "pause_requested"
    session["pause_requested"] = True
    meta["afk_session"] = session
    _write_thread_meta(db, resolved_thread_id, meta)
    current_step = session.get("current_step") or "next checkpoint"
    return {
        "status": "pause_requested",
        "thread_id": resolved_thread_id,
        "current_step": current_step,
        "message": _pause_message(current_step),
    }


@mcp.tool()
def afk_status(thread_id: str | None = None) -> dict:
    """
    Return current AFK progress for `/afk-status`.
    """
    db = _get_db()
    resolved_thread_id = db.resolve_thread_id(thread_id)
    meta = _thread_meta(db, resolved_thread_id)
    session = _afk_session(meta)
    if not session or session.get("status") not in {"active", "pause_requested", "paused"}:
        return {"status": "idle", "message": "No AFK session running"}

    started_iso = session.get("started_at_monotonic") or session.get("started_at")
    try:
        from datetime import datetime, timezone
        started_dt = datetime.fromisoformat(started_iso.replace("Z", "+00:00"))
        elapsed = int((datetime.now(timezone.utc) - started_dt).total_seconds())
    except Exception:
        elapsed = None
    return {
        "status": session.get("status"),
        "thread_id": resolved_thread_id,
        "task": session.get("task"),
        "current_step": session.get("current_step"),
        "steps_completed": session.get("steps_completed", 0),
        "steps_total": session.get("steps_total", 0),
        "elapsed_seconds": elapsed,
        "last_command_output": session.get("last_command_output", ""),
    }
