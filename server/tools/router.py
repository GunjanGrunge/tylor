"""
server/tools/router.py — model routing with transparent overflow fallback.

Routes normal message calls through the primary Claude client. If the primary
route hits a rate limit, retries the identical request through Claude Platform
on AWS. context_length_exceeded is not retried — the identical payload would
fail on the platform route too.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

logger = logging.getLogger(__name__)

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INTERNAL_ERROR

OVERFLOW_ERROR_TYPES = {"rate_limit_error"}
AWS_PLATFORM_BASE_URL_TEMPLATE = "https://aws-external-anthropic.{region}.api.aws"


def _error_type(exc: BaseException) -> str:
    """Extract Anthropic-style error type from SDK or API exceptions."""
    direct_type = getattr(exc, "type", None)
    if isinstance(direct_type, str):
        return direct_type

    error = getattr(exc, "error", None)
    nested_type = getattr(error, "type", None)
    if isinstance(nested_type, str):
        return nested_type
    if isinstance(error, Mapping):
        mapped_type = error.get("type")
        if isinstance(mapped_type, str):
            return mapped_type

    message = str(exc).lower()
    for error_type in OVERFLOW_ERROR_TYPES:
        if error_type in message:
            return error_type
    return ""


def is_overflow_error(exc: BaseException) -> bool:
    """Return True only for errors that should trigger Platform on AWS fallback."""
    return _error_type(exc) in OVERFLOW_ERROR_TYPES


def _internal_error(message: str) -> McpError:
    return McpError(ErrorData(code=INTERNAL_ERROR, message=message))


@dataclass
class ModelRouter:
    """Message router with primary route and Claude Platform on AWS fallback."""

    primary_client: Any
    platform_client: Any | None = None

    def create_message(self, **request: Any) -> Any:
        """
        Create a Claude message through primary route, falling back only for
        rate-limit errors. The fallback receives the identical request kwargs.
        """
        try:
            return self.primary_client.messages.create(**request)
        except Exception as primary_exc:
            if not is_overflow_error(primary_exc):
                raise
            if self.platform_client is None:
                from server.config import config
                if not config.get("platform_key"):
                    logger.warning(
                        "platform_client is null — ANTHROPIC_PLATFORM_AWS_API_KEY not configured; "
                        "overflow fallback unavailable"
                    )
                    raise _internal_error("All model routes exhausted") from primary_exc
            try:
                platform = self.platform_client or build_platform_client()
                self.platform_client = platform
                return platform.messages.create(**request)
            except Exception as platform_exc:
                raise _internal_error("All model routes exhausted") from platform_exc


def build_platform_base_url(region: str) -> str:
    """Build the regional Claude Platform on AWS endpoint."""
    return AWS_PLATFORM_BASE_URL_TEMPLATE.format(region=region)


def build_platform_client() -> Any:
    """Construct an Anthropic SDK client for Claude Platform on AWS."""
    from anthropic import Anthropic
    from server.config import config

    platform_key = config.get("platform_key")
    if not platform_key:
        raise RuntimeError("ANTHROPIC_PLATFORM_AWS_API_KEY not configured")

    base_url = config.get("platform_base_url") or build_platform_base_url(
        config.get("bedrock_region", "us-east-1")
    )
    workspace_id = config.get("platform_workspace_id")
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None

    return Anthropic(
        api_key=platform_key,
        base_url=base_url,
        default_headers=headers,
    )


def create_message(primary_client: Any, **request: Any) -> Any:
    """Convenience wrapper for call sites that do not need a router instance."""
    return ModelRouter(primary_client=primary_client).create_message(**request)
