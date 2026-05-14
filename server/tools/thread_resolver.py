"""
server/tools/thread_resolver.py — fuzzy thread-name resolution.
"""
from __future__ import annotations

from typing import Any

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_REQUEST
from rapidfuzz import process

SCORE_CUTOFF = 70


def _invalid_request(message: str) -> McpError:
    return McpError(ErrorData(code=INVALID_REQUEST, message=message))


def _thread_choices(threads: list[dict]) -> dict[str, dict]:
    return {
        thread.get("name", ""): thread
        for thread in threads
        if thread.get("name") and thread.get("thread_id")
    }


def _format_ambiguous(matches: list[dict]) -> str:
    choices = ", ".join(
        f"[{idx}] {match['name']}"
        for idx, match in enumerate(matches, start=1)
    )
    return f"Did you mean: {choices}?"


def resolve_thread_name(
    query: str,
    threads: list[dict[str, Any]],
    score_cutoff: int = SCORE_CUTOFF,
) -> dict:
    """Resolve a fuzzy thread-name query to one thread or ambiguous choices."""
    cleaned = query.strip() if query else ""
    if not cleaned:
        raise _invalid_request("No thread found matching '' - run list_threads to see available threads")

    choices = _thread_choices(threads)
    all_matches = process.extract(
        cleaned,
        choices.keys(),
        score_cutoff=score_cutoff,
        limit=None,
    )
    if not all_matches:
        raise _invalid_request(
            f"No thread found matching '{cleaned}' - run list_threads to see available threads"
        )

    matches = [
        {**choices[name], "score": score}
        for name, score, _index in all_matches
    ]

    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "matches": matches,
            "message": _format_ambiguous(matches),
        }

    thread = choices[all_matches[0][0]]
    return {
        "status": "resolved",
        "thread_id": thread["thread_id"],
        "name": thread["name"],
        "message": f"Switching to thread: {thread['name']}",
    }
