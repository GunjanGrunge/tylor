"""
Tests for Story 2.6: Model Router 3-Tier Fallback
Run: pytest server/tools/tests/test_router.py -v
"""
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
from mcp.shared.exceptions import McpError

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))


class FakeMessages:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, result=None, error=None):
        self.messages = FakeMessages(result=result, error=error)


class AnthropicStyleError(Exception):
    def __init__(self, error_type: str, message: str = "boom"):
        super().__init__(message)
        self.type = error_type


def test_primary_success_returns_response_as_is_without_platform_route():
    from server.tools.router import ModelRouter

    response = object()
    primary = FakeClient(result=response)
    platform = FakeClient(result={"unused": True})
    router = ModelRouter(primary_client=primary, platform_client=platform)

    request = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 128,
        "messages": [{"role": "user", "content": "hello"}],
    }

    assert router.create_message(**request) is response
    assert primary.messages.calls == [request]
    assert platform.messages.calls == []


def test_rate_limit_error_retries_identical_request_via_platform_route():
    from server.tools.router import ModelRouter

    primary_error = AnthropicStyleError("rate_limit_error", "primary overflow")
    primary = FakeClient(error=primary_error)
    platform_response = {"content": "fallback response"}
    platform = FakeClient(result=platform_response)
    router = ModelRouter(primary_client=primary, platform_client=platform)

    request = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 128,
        "messages": [{"role": "user", "content": "same request"}],
        "temperature": 0,
    }

    assert router.create_message(**request) == platform_response
    assert primary.messages.calls == [request]
    assert platform.messages.calls == [request]


def test_context_length_exceeded_does_not_use_platform_route():
    from server.tools.router import ModelRouter

    primary_error = AnthropicStyleError("context_length_exceeded", "too long")
    primary = FakeClient(error=primary_error)
    platform = FakeClient(result={"unused": True})
    router = ModelRouter(primary_client=primary, platform_client=platform)

    with pytest.raises(AnthropicStyleError, match="too long"):
        router.create_message(model="claude-sonnet-4-6", max_tokens=128, messages=[])

    assert platform.messages.calls == []


def test_non_overflow_primary_error_does_not_use_platform_route():
    from server.tools.router import ModelRouter

    primary_error = AnthropicStyleError("authentication_error", "bad key")
    primary = FakeClient(error=primary_error)
    platform = FakeClient(result={"unused": True})
    router = ModelRouter(primary_client=primary, platform_client=platform)

    with pytest.raises(AnthropicStyleError, match="bad key"):
        router.create_message(model="claude-sonnet-4-6", max_tokens=128, messages=[])

    assert platform.messages.calls == []


def test_exhausted_routes_raise_mcp_internal_error():
    from server.tools.router import ModelRouter

    primary = FakeClient(error=AnthropicStyleError("rate_limit_error", "primary limit"))
    platform = FakeClient(error=RuntimeError("platform unavailable"))
    router = ModelRouter(primary_client=primary, platform_client=platform)

    with pytest.raises(McpError) as exc_info:
        router.create_message(model="claude-sonnet-4-6", max_tokens=128, messages=[])

    error = exc_info.value.error
    assert error.code == -32603
    assert error.message == "All model routes exhausted"


def test_overflow_with_null_platform_key_raises_mcp_error_immediately(monkeypatch):
    import server.config as server_config
    from server.tools.router import ModelRouter

    monkeypatch.setattr(server_config, "config", {"platform_key": None})

    primary = FakeClient(error=AnthropicStyleError("rate_limit_error", "rate limited"))
    router = ModelRouter(primary_client=primary, platform_client=None)

    with pytest.raises(McpError) as exc_info:
        router.create_message(model="claude-sonnet-4-6", max_tokens=128, messages=[])

    error = exc_info.value.error
    assert error.code == -32603
    assert error.message == "All model routes exhausted"


def test_platform_client_cached_after_first_overflow(monkeypatch):
    import server.config as server_config
    from server.tools.router import ModelRouter

    monkeypatch.setattr(
        server_config,
        "config",
        {
            "platform_key": "test-key",
            "platform_base_url": "https://aws-external-anthropic.us-east-1.api.aws",
            "platform_workspace_id": None,
            "bedrock_region": "us-east-1",
        },
    )

    platform_response = {"content": "fallback"}
    primary = FakeClient(error=AnthropicStyleError("rate_limit_error", "rate limited"))
    router = ModelRouter(primary_client=primary, platform_client=None)

    with patch("anthropic.Anthropic") as anthropic_cls:
        mock_client = anthropic_cls.return_value
        mock_client.messages.create.return_value = platform_response
        router.create_message(model="claude-sonnet-4-6", max_tokens=128, messages=[])

    assert router.platform_client is mock_client
    assert anthropic_cls.call_count == 1


def test_platform_base_url_uses_regional_aws_endpoint():
    from server.tools.router import build_platform_base_url

    assert (
        build_platform_base_url("us-east-1")
        == "https://aws-external-anthropic.us-east-1.api.aws"
    )


def test_build_platform_client_uses_key_base_url_and_workspace_header(monkeypatch):
    import server.config as server_config
    from server.tools.router import build_platform_client

    monkeypatch.setattr(
        server_config,
        "config",
        {
            "platform_key": "test-key",
            "platform_base_url": "https://aws-external-anthropic.us-east-1.api.aws",
            "platform_workspace_id": "wrkspc_test",
            "bedrock_region": "us-east-1",
        },
    )

    with patch("anthropic.Anthropic") as anthropic_cls:
        build_platform_client()

    anthropic_cls.assert_called_once_with(
        api_key="test-key",
        base_url="https://aws-external-anthropic.us-east-1.api.aws",
        default_headers={"anthropic-workspace-id": "wrkspc_test"},
    )


def test_build_platform_client_no_workspace_id_sends_no_header(monkeypatch):
    import server.config as server_config
    from server.tools.router import build_platform_client

    monkeypatch.setattr(
        server_config,
        "config",
        {
            "platform_key": "test-key",
            "platform_base_url": "https://aws-external-anthropic.us-east-1.api.aws",
            "platform_workspace_id": None,
            "bedrock_region": "us-east-1",
        },
    )

    with patch("anthropic.Anthropic") as anthropic_cls:
        build_platform_client()

    anthropic_cls.assert_called_once_with(
        api_key="test-key",
        base_url="https://aws-external-anthropic.us-east-1.api.aws",
        default_headers=None,
    )


def test_build_platform_client_raises_when_platform_key_missing(monkeypatch):
    import server.config as server_config
    from server.tools.router import build_platform_client

    monkeypatch.setattr(server_config, "config", {"platform_key": None})

    with pytest.raises(RuntimeError, match="ANTHROPIC_PLATFORM_AWS_API_KEY not configured"):
        build_platform_client()


def test_error_type_string_matching_fallback():
    from server.tools.router import _error_type

    class PlainError(Exception):
        pass

    assert _error_type(PlainError("rate_limit_error in response")) == "rate_limit_error"


def test_error_type_returns_empty_string_for_unknown_error():
    from server.tools.router import _error_type

    class PlainError(Exception):
        pass

    assert _error_type(PlainError("something completely different")) == ""


def test_create_message_convenience_wrapper_success():
    from server.tools.router import create_message

    response = object()
    primary = FakeClient(result=response)
    request = {"model": "claude-sonnet-4-6", "max_tokens": 128, "messages": []}

    assert create_message(primary, **request) is response
    assert primary.messages.calls == [request]
