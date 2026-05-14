"""
Tests for Story 2.5: recall_memory tool.
Run: pytest server/tools/tests/test_recall_memory.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from mcp.server.fastmcp.exceptions import ToolError
from server.tools.tylor import recall_memory


def test_recall_memory_calls_search_memory_with_top_k():
    mock_client = MagicMock()
    mock_client.search_memory.return_value = [{"id": "doc1"}]

    with patch("server.tools.tylor._get_memory_client", return_value=mock_client):
        result = recall_memory(thread_id="t1", query="find relevant facts", top_k=3)

    mock_client.search_memory.assert_called_once_with(
        thread_id="t1",
        query="find relevant facts",
        k=3,
        type=None,
    )
    assert result == {"results": [{"id": "doc1"}]}


def test_recall_memory_returns_empty_list_when_no_results():
    mock_client = MagicMock()
    mock_client.search_memory.return_value = []

    with patch("server.tools.tylor._get_memory_client", return_value=mock_client):
        result = recall_memory(thread_id="t1", query="missing facts")

    assert result == {"results": []}


def test_recall_memory_raises_on_empty_query():
    with pytest.raises(ToolError, match="Query must not be empty"):
        recall_memory(thread_id="t1", query="   ")


def test_recall_memory_propagates_opensearch_errors():
    mock_client = MagicMock()
    mock_client.search_memory.side_effect = ToolError("search failed")

    with patch("server.tools.tylor._get_memory_client", return_value=mock_client):
        with pytest.raises(ToolError, match="search failed"):
            recall_memory(thread_id="t1", query="search")
