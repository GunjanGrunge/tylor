"""
Tests for Story 2.2: OpenSearch Vector Client
Run: pytest server/storage/tests/test_opensearch.py -v
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from mcp.server.fastmcp.exceptions import ToolError
from server.storage.opensearch import OpenSearchClient, INDEX, TITAN_MODEL, VECTOR_DIM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_EMBEDDING = [0.1] * VECTOR_DIM


def make_os_client():
    """Return OpenSearchClient with mocked OpenSearch + Bedrock."""
    with (
        patch("server.storage.opensearch.OpenSearch") as mock_os_cls,
        patch("boto3.Session") as mock_session_cls,
    ):
        mock_os = MagicMock()
        mock_os_cls.return_value = mock_os

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_bedrock = MagicMock()
        mock_session.client.return_value = mock_bedrock

        client = OpenSearchClient(host="localhost", port=9200)
        client._os = mock_os
        client._bedrock = mock_bedrock
        return client, mock_os, mock_bedrock


def _mock_embed(mock_bedrock):
    """Configure mock_bedrock to return a valid 1536-dim embedding."""
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({"embedding": FAKE_EMBEDDING}).encode()
    mock_bedrock.invoke_model.return_value = {"body": mock_body}


# ---------------------------------------------------------------------------
# AC3: index_memory embeds via Titan and writes to agent-memories
# ---------------------------------------------------------------------------

def test_index_memory_calls_bedrock_with_correct_model():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.index.return_value = {"result": "created"}

    client.index_memory(thread_id="t1", fact="The project uses FastMCP v1.")

    call_kwargs = mock_bedrock.invoke_model.call_args.kwargs
    assert call_kwargs["modelId"] == TITAN_MODEL
    body = json.loads(call_kwargs["body"])
    assert body["inputText"] == "The project uses FastMCP v1."


def test_index_memory_writes_to_agent_memories_index():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.index.return_value = {"result": "created"}

    client.index_memory(thread_id="t1", fact="fact text")

    call_kwargs = mock_os.index.call_args.kwargs
    assert call_kwargs["index"] == INDEX  # "agent-memories"


def test_index_memory_stores_thread_id_and_content():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.index.return_value = {"result": "created"}

    client.index_memory(thread_id="t1", fact="important fact", metadata={"source": "user"})

    doc = mock_os.index.call_args.kwargs["body"]
    assert doc["thread_id"] == "t1"
    assert doc["content"] == "important fact"
    assert doc["source"] == "user"
    assert len(doc["embedding"]) == VECTOR_DIM


def test_index_memory_returns_doc_id():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.index.return_value = {"result": "created"}

    doc_id = client.index_memory(thread_id="t1", fact="fact")
    assert isinstance(doc_id, str)
    assert len(doc_id) == 32  # uuid4().hex


def test_index_memory_raises_tool_error_on_bedrock_failure():
    client, mock_os, mock_bedrock = make_os_client()
    mock_bedrock.invoke_model.side_effect = Exception("Bedrock throttled")

    with pytest.raises(ToolError, match="embedding failed"):
        client.index_memory(thread_id="t1", fact="fact")

    mock_os.index.assert_not_called()


def test_index_memory_raises_tool_error_on_opensearch_failure():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.index.side_effect = Exception("connection refused")

    with pytest.raises(ToolError, match="index_memory failed"):
        client.index_memory(thread_id="t1", fact="fact")


# ---------------------------------------------------------------------------
# AC4: search_memory returns thread-scoped results
# ---------------------------------------------------------------------------

def test_search_memory_query_includes_thread_id_filter():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.search.return_value = {"hits": {"hits": []}}

    client.search_memory(thread_id="t1", query="project name")

    os_query = mock_os.search.call_args.kwargs["body"]
    bool_query = os_query["query"]["bool"]
    filters = bool_query["must"]
    term_filters = [f for f in filters if "term" in f]
    assert any(f["term"].get("thread_id") == "t1" for f in term_filters)


def test_search_memory_query_includes_type_filter_when_provided():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.search.return_value = {"hits": {"hits": []}}

    client.search_memory(thread_id="t1", query="SignIn", type="code_index")

    os_query = mock_os.search.call_args.kwargs["body"]
    filters = os_query["query"]["bool"]["must"]
    assert any(f.get("term", {}).get("type") == "code_index" for f in filters)


def test_search_memory_returns_correct_shape():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "abc123",
                    "_score": 0.95,
                    "_source": {
                        "thread_id": "t1",
                        "content": "FastMCP is great",
                        "created_at": "2026-05-12T10:00:00Z",
                    },
                }
            ]
        }
    }

    results = client.search_memory(thread_id="t1", query="MCP")

    assert len(results) == 1
    r = results[0]
    assert r["id"] == "abc123"
    assert r["content"] == "FastMCP is great"
    assert r["thread_id"] == "t1"
    assert r["score"] == 0.95


def test_search_memory_filters_out_wrong_thread_results(caplog):
    """Defence-in-depth: results with wrong thread_id are dropped at client layer."""
    import logging

    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "doc1",
                    "_score": 0.9,
                    "_source": {
                        "thread_id": "t2",  # wrong thread
                        "content": "other thread fact",
                        "created_at": "2026-05-12T10:00:00Z",
                    },
                },
                {
                    "_id": "doc2",
                    "_score": 0.8,
                    "_source": {
                        "thread_id": "t1",  # correct
                        "content": "correct fact",
                        "created_at": "2026-05-12T10:00:00Z",
                    },
                },
            ]
        }
    }

    with caplog.at_level(logging.WARNING, logger="server.storage.opensearch"):
        results = client.search_memory(thread_id="t1", query="something")

    assert len(results) == 1
    assert results[0]["content"] == "correct fact"
    assert any("wrong thread_id" in r.message for r in caplog.records)


def test_search_memory_uses_k_parameter():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.search.return_value = {"hits": {"hits": []}}

    client.search_memory(thread_id="t1", query="q", k=10)

    os_query = mock_os.search.call_args.kwargs["body"]
    assert os_query["size"] == 10
    knn_field = os_query["query"]["bool"]["must"][0]["knn"]["embedding"]
    assert knn_field["k"] == 10


# ---------------------------------------------------------------------------
# AC5: Empty thread returns empty list
# ---------------------------------------------------------------------------

def test_search_memory_returns_empty_list_for_empty_thread():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.search.return_value = {"hits": {"hits": []}}

    results = client.search_memory(thread_id="t1", query="anything")

    assert results == []


def test_search_memory_raises_tool_error_on_opensearch_failure():
    client, mock_os, mock_bedrock = make_os_client()
    _mock_embed(mock_bedrock)
    mock_os.search.side_effect = Exception("index not found")

    with pytest.raises(ToolError, match="search_memory failed"):
        client.search_memory(thread_id="t1", query="q")


# ---------------------------------------------------------------------------
# Embedding dimension validation
# ---------------------------------------------------------------------------

def test_embed_raises_on_wrong_dimension():
    client, mock_os, mock_bedrock = make_os_client()
    # Return wrong-dimension embedding
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({"embedding": [0.1] * 768}).encode()
    mock_bedrock.invoke_model.return_value = {"body": mock_body}

    with pytest.raises(ToolError, match="dimension"):
        client.index_memory(thread_id="t1", fact="fact")
