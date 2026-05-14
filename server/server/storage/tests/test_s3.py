"""
Tests for Story 2.2: S3 Blob Client
Run: pytest server/storage/tests/test_s3.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from mcp.server.fastmcp.exceptions import ToolError
from server.storage.s3 import S3Client, _s3_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_s3_client(mock_s3=None):
    with patch("boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        s3_client = mock_s3 or MagicMock()
        mock_session.client.return_value = s3_client
        client = S3Client(bucket="agent101-blobs-123", user_id="testuser")
        client._s3 = s3_client
        return client, s3_client


# ---------------------------------------------------------------------------
# AC1: put_blob stores at correct path and returns s3:// URI
# ---------------------------------------------------------------------------

def test_put_blob_returns_s3_uri():
    client, s3 = make_s3_client()
    s3.put_object.return_value = {}

    uri = client.put_blob(thread_id="t1", key="summary", content="hello world")

    assert uri == "s3://agent101-blobs-123/testuser/threads/t1/summary"


def test_put_blob_calls_put_object_with_correct_key():
    client, s3 = make_s3_client()
    s3.put_object.return_value = {}

    client.put_blob(thread_id="t1", key="msg_001", content=b"raw bytes")

    s3.put_object.assert_called_once_with(
        Bucket="agent101-blobs-123",
        Key="testuser/threads/t1/msg_001",
        Body=b"raw bytes",
    )


def test_put_blob_encodes_string_to_bytes():
    client, s3 = make_s3_client()
    s3.put_object.return_value = {}

    client.put_blob(thread_id="t1", key="note", content="unicode: 🎉")

    call_kwargs = s3.put_object.call_args.kwargs
    assert isinstance(call_kwargs["Body"], bytes)
    assert "unicode: 🎉".encode("utf-8") == call_kwargs["Body"]


def test_s3_path_embeds_thread_id():
    path = _s3_path("u1", "thread_abc123", "summary")
    assert path == "u1/threads/thread_abc123/summary"
    assert "thread_abc123" in path  # isolation: path encodes thread_id


def test_put_blob_raises_tool_error_on_s3_failure():
    client, s3 = make_s3_client()
    s3.put_object.side_effect = Exception("NoSuchBucket")

    with pytest.raises(ToolError, match="put_blob failed"):
        client.put_blob(thread_id="t1", key="k", content="data")


# ---------------------------------------------------------------------------
# AC2: get_blob returns full content
# ---------------------------------------------------------------------------

def test_get_blob_returns_content():
    client, s3 = make_s3_client()
    mock_body = MagicMock()
    mock_body.read.return_value = b"stored content here"
    s3.get_object.return_value = {"Body": mock_body}

    result = client.get_blob("s3://agent101-blobs-123/testuser/threads/t1/summary")

    assert result == b"stored content here"


def test_get_blob_parses_uri_correctly():
    client, s3 = make_s3_client()
    mock_body = MagicMock()
    mock_body.read.return_value = b"data"
    s3.get_object.return_value = {"Body": mock_body}

    client.get_blob("s3://agent101-blobs-123/testuser/threads/t1/key")

    s3.get_object.assert_called_once_with(
        Bucket="agent101-blobs-123",
        Key="testuser/threads/t1/key",
    )


def test_get_blob_raises_on_invalid_scheme():
    client, s3 = make_s3_client()

    with pytest.raises(ToolError, match="Invalid S3 URI scheme"):
        client.get_blob("https://example.com/file")


def test_get_blob_raises_tool_error_on_s3_failure():
    client, s3 = make_s3_client()
    s3.get_object.side_effect = Exception("NoSuchKey")

    with pytest.raises(ToolError, match="get_blob failed"):
        client.get_blob("s3://bucket/key")
