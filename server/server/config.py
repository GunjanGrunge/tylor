"""
server/config.py — Agent101 server configuration.
Reads AWS profile, Bedrock region, and Platform on AWS key.
Resolution order: env var → ~/.agent101/config.json → .env file → defaults.
Warns on missing optional config; never crashes on startup.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv optional at import time; already in requirements.txt

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".agent101" / "config.json"


def _load_file_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("~/.agent101/config.json is not a JSON object — ignoring")
                return {}
            return data
        except (json.JSONDecodeError, OSError):
            logger.warning("~/.agent101/config.json is malformed — ignoring")
    return {}


def _load() -> dict:
    file_cfg = _load_file_config()

    def _get(env_key: str, file_key: str | None = None, default: str | None = None) -> str | None:
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val or None
        return file_cfg.get(file_key or env_key) or default

    def _get_any(env_keys: tuple[str, ...], default: str | None = None) -> str | None:
        for env_key in env_keys:
            env_val = os.environ.get(env_key)
            if env_val is not None:
                return env_val or None
            file_val = file_cfg.get(env_key)
            if file_val:
                return file_val
        return default

    cfg = {
        "aws_profile":    _get("AWS_PROFILE"),
        "bedrock_region": _get("BEDROCK_REGION", default="us-east-1"),
        "bedrock_opus_model": _get(
            "BEDROCK_OPUS_MODEL",
            default="us.anthropic.claude-opus-4-7-20251101-v1:0",
        ),
        "platform_key":   _get_any(("ANTHROPIC_PLATFORM_AWS_API_KEY", "ANTHROPIC_AWS_API_KEY")),
        "platform_base_url": _get("ANTHROPIC_AWS_BASE_URL"),
        "platform_workspace_id": _get("ANTHROPIC_AWS_WORKSPACE_ID"),
        "dynamo_table":   _get("DYNAMO_TABLE", default="agent101"),
        "s3_bucket":      _get("S3_BUCKET"),
        "opensearch_host": _get("OPENSEARCH_HOST"),
        "opensearch_port": _get("OPENSEARCH_PORT", default="9200"),
    }

    # Warn on optional keys that affect runtime features
    if not cfg["platform_key"]:
        logger.warning(
            "ANTHROPIC_PLATFORM_AWS_API_KEY/ANTHROPIC_AWS_API_KEY not set — "
            "token overflow fallback to Claude Platform on AWS is disabled"
        )
    if not cfg["opensearch_host"]:
        logger.warning(
            "OPENSEARCH_HOST not set — "
            "semantic memory recall (recall_memory) will be unavailable until configured"
        )

    return cfg


config = _load()
