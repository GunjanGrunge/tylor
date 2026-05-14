"""
Tests for Story 2.10: fuzzy thread name matching
Run: pytest server/tools/tests/test_thread_resolver.py -v
"""
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest
from mcp.shared.exceptions import McpError

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))


THREADS = [
    {
        "thread_id": "gemma-v2",
        "name": "Gemma Fine-Tuning v2",
        "status": "active",
        "last_activity": "2026-05-12T10:00:00Z",
        "message_count": 5,
    },
    {
        "thread_id": "eval",
        "name": "Gemma Eval Run",
        "status": "active",
        "last_activity": "2026-05-11T10:00:00Z",
        "message_count": 2,
    },
    {
        "thread_id": "abc",
        "name": "ABC",
        "status": "active",
        "last_activity": "2026-05-10T10:00:00Z",
        "message_count": 1,
    },
]


def test_resolve_thread_name_single_match_uses_extract_with_cutoff():
    from server.tools.thread_resolver import resolve_thread_name

    with patch("server.tools.thread_resolver.process.extract") as extract:
        extract.return_value = [("Gemma Fine-Tuning v2", 90, 0)]
        result = resolve_thread_name("Gemma Fine", THREADS)

    extract.assert_called_once()
    assert extract.call_args.kwargs["score_cutoff"] == 70
    assert result == {
        "status": "resolved",
        "thread_id": "gemma-v2",
        "name": "Gemma Fine-Tuning v2",
        "message": "Switching to thread: Gemma Fine-Tuning v2",
    }


def test_resolve_thread_name_ambiguous_matches_returns_choices():
    from server.tools.thread_resolver import resolve_thread_name

    result = resolve_thread_name("Gemma", THREADS)

    assert result["status"] == "ambiguous"
    assert result["message"] == "Did you mean: [1] Gemma Fine-Tuning v2, [2] Gemma Eval Run?"
    assert [match["thread_id"] for match in result["matches"]] == ["gemma-v2", "eval"]


def test_resolve_thread_name_no_match_raises_invalid_request_mcp_error():
    from server.tools.thread_resolver import resolve_thread_name

    with pytest.raises(McpError) as exc_info:
        resolve_thread_name("Nope", THREADS)

    error = exc_info.value.error
    assert error.code == -32600
    assert "No thread found matching 'Nope'" in error.message
    assert "run list_threads" in error.message


def test_resolve_thread_name_three_character_thread_names_are_matchable():
    from server.tools.thread_resolver import resolve_thread_name

    result = resolve_thread_name("ABC", THREADS)

    assert result["status"] == "resolved"
    assert result["thread_id"] == "abc"
    assert result["name"] == "ABC"


def test_switch_thread_by_name_passes_resolved_thread_id_to_switch_thread():
    import server.tools.tylor as tylor_mod

    mock_db = MagicMock()
    mock_db.query_all.return_value = [
        {
            "SK": "THREAD#gemma-v2#META",
            "Name": "Gemma Fine-Tuning v2",
            "Status": "active",
            "LastActivity": "2026-05-12T10:00:00Z",
            "MessageCount": 5,
        }
    ]
    mock_db.switch_thread.return_value = {
        "thread_id": "gemma-v2",
        "status": "switched",
        "switched_at": "2026-05-12T10:01:00Z",
    }

    with patch.object(tylor_mod, "_get_db", return_value=mock_db):
        result = tylor_mod.switch_thread_by_name("Gemma")

    mock_db.switch_thread.assert_called_once_with("gemma-v2")
    assert result["thread_id"] == "gemma-v2"
    assert result["name"] == "Gemma Fine-Tuning v2"
    assert result["message"] == "Switching to thread: Gemma Fine-Tuning v2"


def test_switch_thread_by_name_ambiguous_match_does_not_switch():
    import server.tools.tylor as tylor_mod

    mock_db = MagicMock()
    mock_db.query_all.return_value = [
        {
            "SK": "THREAD#gemma-v2#META",
            "Name": "Gemma Fine-Tuning v2",
            "Status": "active",
            "LastActivity": "2026-05-12T10:00:00Z",
            "MessageCount": 5,
        },
        {
            "SK": "THREAD#eval#META",
            "Name": "Gemma Eval Run",
            "Status": "active",
            "LastActivity": "2026-05-11T10:00:00Z",
            "MessageCount": 2,
        },
    ]

    with patch.object(tylor_mod, "_get_db", return_value=mock_db):
        result = tylor_mod.switch_thread_by_name("Gemma")

    mock_db.switch_thread.assert_not_called()
    assert result["status"] == "ambiguous"
    assert "Did you mean" in result["message"]


def test_switch_thread_by_name_normalizes_unexpected_switch_failures():
    import server.tools.tylor as tylor_mod
    from mcp.server.fastmcp.exceptions import ToolError

    mock_db = MagicMock()
    mock_db.query_all.return_value = [
        {
            "SK": "THREAD#gemma-v2#META",
            "Name": "Gemma Fine-Tuning v2",
            "Status": "active",
            "LastActivity": "2026-05-12T10:00:00Z",
            "MessageCount": 5,
        }
    ]
    mock_db.switch_thread.side_effect = RuntimeError("dynamo exploded")

    with patch.object(tylor_mod, "_get_db", return_value=mock_db):
        with pytest.raises(ToolError, match="SwThread failed"):
            tylor_mod.switch_thread_by_name("Gemma")
