"""
server/tools/hooks.py — Claude Code lifecycle hook helpers.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable

from server.tools.summarizer import summarize_thread
from server.tools.tylor import _get_db, _get_memory_client, _now_iso, list_threads


CODE_INDEX_QUERY = "code index"
CODE_INDEX_MAX_ENTRIES = 30
CODE_INDEX_TOKEN_BUDGET = 150
INDEXABLE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
SKIP_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".env"}
SKIP_NAME_PARTS = {"config", "settings", "requirements", "package-lock"}


def _rough_word_count(text: str) -> int:
    # Approximation only — actual LLM token count is ~1.3–1.5× word count.
    # Used for budget enforcement; keeps header well under the true token limit.
    return len(text.split())


def _code_index_header(thread_name: str, facts: list[dict], max_tokens: int = CODE_INDEX_TOKEN_BUDGET) -> str:
    header = f"[{thread_name or 'Active'} Thread — Code Index]"
    lines = [header]
    used = _rough_word_count(header)
    sorted_facts = sorted(
        facts,
        key=lambda fact: fact.get("last_used_at") or fact.get("created_at") or "",
        reverse=True,
    )
    for fact in sorted_facts:
        content = str(fact.get("content", "")).strip()
        if not content:
            continue
        cost = _rough_word_count(content)
        if used + cost > max_tokens:
            continue  # skip this entry but keep trying smaller ones
        lines.append(content)
        used += cost
    return "\n".join(lines) if len(lines) > 1 else ""


def build_code_index_header(
    thread_id: str,
    thread_name: str,
    memory_client: Any | None = None,
    max_tokens: int = CODE_INDEX_TOKEN_BUDGET,
) -> str:
    """Return compact code-index header for active thread context injection."""
    try:
        memory = memory_client or _get_memory_client()
        facts = memory.search_memory(
            thread_id=thread_id,
            query=CODE_INDEX_QUERY,
            k=CODE_INDEX_MAX_ENTRIES,
            type="code_index",
        )
    except Exception:
        return ""
    return _code_index_header(thread_name, facts, max_tokens=max_tokens)


def _thread_line(thread: dict) -> str:
    return (
        f"- {thread.get('name', '(unnamed)')} "
        f"({thread.get('thread_id')}, {thread.get('status', 'unknown')}, "
        f"{thread.get('message_count', 0)} messages)"
    )


def session_start_message(
    db: Any | None = None,
    list_threads_fn: Callable[[], dict] = list_threads,
    memory_client: Any | None = None,
) -> str:
    """Return active-thread context for Claude Code SessionStart output."""
    db = db or _get_db()
    marker = db.get_current_thread_marker()
    threads = list_threads_fn().get("threads", [])

    if not marker or not marker.get("CurrentThreadId"):
        if not threads:
            return "agent101: No active thread found. Start with /new-thread when ready."
        thread_list = "\n".join(_thread_line(thread) for thread in threads[:5])
        return (
            "agent101 thread context: No active thread marker found.\n"
            "Recent threads:\n"
            f"{thread_list}"
        )

    current_id = marker["CurrentThreadId"]
    current = next((thread for thread in threads if thread.get("thread_id") == current_id), None)
    if not current:
        meta = db.get_thread_meta(current_id) or {}
        current = {
            "thread_id": current_id,
            "name": meta.get("Name", ""),
            "status": meta.get("Status", "unknown"),
            "message_count": meta.get("MessageCount", 0),
        }

    thread_list = "\n".join(_thread_line(thread) for thread in threads[:5])
    code_header = build_code_index_header(
        current_id,
        current.get("name", ""),
        memory_client=memory_client,
    )
    code_block = f"{code_header}\n\n" if code_header else ""
    return (
        f"{code_block}"
        "agent101 active thread context:\n"
        f"Active thread: {_thread_line(current)}\n"
        f"Active since: {marker.get('ActiveAt', 'unknown')}\n"
        "Recent threads:\n"
        f"{thread_list}\n"
        "Acknowledge this active thread before continuing."
    )


def checkpoint_current_thread(
    db: Any | None = None,
    now_fn: Callable[[], str] = _now_iso,
) -> dict:
    """Snapshot current thread metadata with a fresh checkpoint timestamp."""
    db = db or _get_db()
    marker = db.get_current_thread_marker()
    if not marker or not marker.get("CurrentThreadId"):
        return {"status": "skipped", "reason": "no_active_thread"}

    thread_id = marker["CurrentThreadId"]
    meta = db.get_thread_meta(thread_id)
    if not meta:
        return {"status": "skipped", "reason": "active_thread_missing", "thread_id": thread_id}

    now = now_fn()
    updated = dict(meta)
    updated["LastActivity"] = now
    updated["CheckpointAt"] = now
    db.put_item(f"THREAD#{thread_id}#META", updated)
    return {"status": "checkpointed", "thread_id": thread_id}


_THREAD_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{2,64}$")


def dispatch_kill_thread_summary(
    thread_id: str,
    project_root: Path | str | None = None,
    python_executable: str = sys.executable,
) -> dict:
    """Start summarization in a detached process and return immediately."""
    if not _THREAD_ID_RE.match(thread_id or ""):
        return {"status": "skipped", "reason": "invalid_thread_id"}
    root = Path(project_root or Path(__file__).resolve().parents[2])
    subprocess.Popen(
        [
            python_executable,
            "-m",
            "server.tools.hooks",
            "summarize-thread",
            thread_id,
        ],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"status": "dispatched", "thread_id": thread_id}


def _thread_id_from_hook_payload(payload: str) -> str | None:
    if not payload.strip():
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    for path in (
        ("tool_input", "thread_id"),
        ("input", "thread_id"),
        ("thread_id",),
    ):
        value: Any = data
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _file_path_from_hook_payload(payload: str) -> str | None:
    if not payload.strip():
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    for path in (
        ("tool_input", "file_path"),
        ("tool_input", "path"),
        ("input", "file_path"),
        ("input", "path"),
        ("file_path",),
        ("path",),
    ):
        value: Any = data
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, str) and value:
            return value
    return None


_MAX_FILE_BYTES = 512 * 1024  # 512 KB — skip larger files to avoid blocking


def _extract_code_index_fact(file_path: Path, project_root: Path | None = None) -> str | None:
    if file_path.suffix not in INDEXABLE_SUFFIXES:
        return None
    lowered = file_path.name.lower()
    if any(part in lowered for part in SKIP_NAME_PARTS):
        return None
    try:
        if file_path.stat().st_size > _MAX_FILE_BYTES:
            return None
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    # Hooks checked before generic components — use[A-Z] names would match component patterns first
    patterns = [
        (re.compile(r"^\s*export\s+function\s+(use[A-Z][A-Za-z0-9_]*)\b"), "hook"),
        (re.compile(r"^\s*function\s+(use[A-Z][A-Za-z0-9_]*)\b"), "hook"),
        (re.compile(r"^\s*export\s+function\s+([A-Z][A-Za-z0-9_]*)\b"), "component"),
        (re.compile(r"^\s*function\s+([A-Z][A-Za-z0-9_]*)\b"), "component"),
        (re.compile(r"^\s*export\s+const\s+([A-Z][A-Za-z0-9_]*)\b"), "component"),
        (re.compile(r"^\s*const\s+([A-Z][A-Za-z0-9_]*)\b"), "component"),
        (re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\("), "python function"),
        (re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b"), "class"),
    ]
    # Use relative path for portability and token efficiency
    try:
        root = project_root or Path.cwd()
        display_path = file_path.relative_to(root)
    except ValueError:
        display_path = file_path  # fallback to absolute if not under project root

    for line_no, line in enumerate(lines, start=1):
        for pattern, label in patterns:
            match = pattern.search(line)
            if match:
                symbol = match.group(1)
                return f"{symbol}: {display_path}:{line_no} — {label}"
    return None


def index_code_file_for_active_thread(
    file_path: str,
    db: Any | None = None,
    memory_client: Any | None = None,
    project_root: Path | str | None = None,
) -> dict:
    """Index one touched source file as a compact code_index memory fact."""
    path = Path(file_path).expanduser()
    root = Path(project_root).expanduser() if project_root else Path.cwd()
    fact = _extract_code_index_fact(path, project_root=root)
    if not fact:
        return {"status": "skipped", "reason": "no_indexable_symbol"}

    db = db or _get_db()
    marker = db.get_current_thread_marker()
    thread_id = marker.get("CurrentThreadId") if marker else None
    if not thread_id:
        return {"status": "skipped", "reason": "no_active_thread"}

    try:
        memory = memory_client or _get_memory_client()
    except Exception:
        return {"status": "skipped", "reason": "memory_not_configured"}

    try:
        memory_id = memory.index_memory(
            thread_id=thread_id,
            fact=fact,
            metadata={"type": "code_index"},
        )
    except Exception:
        return {"status": "skipped", "reason": "memory_index_failed"}

    return {"status": "indexed", "thread_id": thread_id, "memory_id": memory_id, "fact": fact}


async def _summarize_thread_cli(thread_id: str) -> None:
    await summarize_thread(thread_id, db=_get_db())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="agent101 Claude Code hook helper")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("session-start")
    sub.add_parser("session-checkpoint")
    sub.add_parser("post-tool-use-code-index")
    kill_parser = sub.add_parser("kill-thread-trigger")
    kill_parser.add_argument("thread_id", nargs="?")
    summarize_parser = sub.add_parser("summarize-thread")
    summarize_parser.add_argument("thread_id")

    args = parser.parse_args(argv)

    if args.command == "session-start":
        # Read cwd from Claude Code's stdin JSON payload and persist it
        try:
            raw = sys.stdin.read()
            if raw.strip():
                payload = json.loads(raw)
                cwd = payload.get("cwd") or payload.get("session", {}).get("cwd")
                if cwd:
                    from pathlib import Path as _Path
                    proj_file = _Path.home() / ".tylor" / "current_project.txt"
                    proj_file.parent.mkdir(parents=True, exist_ok=True)
                    proj_file.write_text(cwd)
        except Exception:
            pass
        print(session_start_message())
        return 0
    if args.command == "session-checkpoint":
        print(json.dumps(checkpoint_current_thread()))
        return 0
    if args.command == "post-tool-use-code-index":
        file_path = _file_path_from_hook_payload(sys.stdin.read())
        if not file_path:
            print(json.dumps({"status": "skipped", "reason": "missing_file_path"}))
            return 0
        print(json.dumps(index_code_file_for_active_thread(file_path)))
        return 0
    if args.command == "kill-thread-trigger":
        thread_id = args.thread_id or _thread_id_from_hook_payload(sys.stdin.read())
        if not thread_id:
            print(json.dumps({"status": "skipped", "reason": "missing_thread_id"}))
            return 0
        print(json.dumps(dispatch_kill_thread_summary(thread_id)))
        return 0
    if args.command == "summarize-thread":
        asyncio.run(_summarize_thread_cli(args.thread_id))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
