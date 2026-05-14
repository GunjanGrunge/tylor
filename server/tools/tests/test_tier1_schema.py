"""
Tests for Story 1.4: FastMCP Server Skeleton with Tier 1 Tools
Run: pytest server/tools/tests/test_tier1_schema.py -v
"""
import importlib
import inspect
import sys
import logging
import asyncio
from pathlib import Path
import os

import pytest

# Ensure project root is on path
PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

TIER_1_TOOLS = [
    "new_thread",
    "switch_thread",
    "switch_thread_by_name",
    "kill_thread",
    "save_memory",
    "recall_memory",
    "list_threads",
    "list_personas",
    "spawn_agent",
    "load_skill_tools",
    "list_registry",
    "help_agent101",
    "add_skill",
    "set_sandbox",
    "execute_in_sandbox",
    "execute_with_recovery",
    "start_afk",
    "afk_status",
    "pause_afk",
]


# ---------------------------------------------------------------------------
# AC1: Server imports without error
# ---------------------------------------------------------------------------

def test_main_module_imports_cleanly():
    """server.main must be importable without side effects or crashes."""
    if "server.main" in sys.modules:
        del sys.modules["server.main"]
    mod = importlib.import_module("server.main")
    assert mod is not None


def test_mcp_singleton_name():
    """The FastMCP instance must be named 'agent101'."""
    from server.tools._mcp import mcp
    assert mcp.name == "agent101"


# ---------------------------------------------------------------------------
# AC2: All 8 Tier 1 tools are registered
# ---------------------------------------------------------------------------

def test_all_tier1_tools_registered():
    """All Tier 1 tools must be registered on the mcp instance."""
    import asyncio
    # Ensure startup registration imports every Tier 1 tool module.
    import server.main
    from server.tools._mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    registered = {t.name for t in tools}

    missing = [t for t in TIER_1_TOOLS if t not in registered]
    assert not missing, f"Missing Tier 1 tools: {missing}"


# ---------------------------------------------------------------------------
# AC2: Tool parameter signatures are correct
# ---------------------------------------------------------------------------

def test_new_thread_signature():
    from server.tools.tylor import new_thread
    sig = inspect.signature(new_thread)
    assert "name" in sig.parameters
    assert sig.parameters["name"].annotation in (str, "str")


def test_switch_thread_signature():
    from server.tools.tylor import switch_thread
    sig = inspect.signature(switch_thread)
    assert "thread_id" in sig.parameters
    assert sig.parameters["thread_id"].annotation in (str, "str")


def test_switch_thread_by_name_signature():
    from server.tools.tylor import switch_thread_by_name
    sig = inspect.signature(switch_thread_by_name)
    assert "query" in sig.parameters
    assert sig.parameters["query"].annotation in (str, "str")


def test_kill_thread_is_sync():
    # kill_thread is now sync — summarization dispatched by PostToolUse hook
    from server.tools.tylor import kill_thread
    assert not inspect.iscoroutinefunction(kill_thread)


def test_recall_memory_signature():
    from server.tools.tylor import recall_memory
    sig = inspect.signature(recall_memory)
    assert "thread_id" in sig.parameters
    assert "query" in sig.parameters
    assert "top_k" in sig.parameters
    assert "fact_type" in sig.parameters  # renamed from `type` to avoid shadowing builtin
    # top_k has default of 5
    assert sig.parameters["top_k"].default == 5


def test_save_memory_signature():
    from server.tools.tylor import save_memory
    sig = inspect.signature(save_memory)
    assert "thread_id" in sig.parameters
    assert "fact" in sig.parameters
    assert "fact_type" in sig.parameters  # renamed from `type` to avoid shadowing builtin


def test_spawn_agent_signature():
    from server.tools.agents import spawn_agent
    sig = inspect.signature(spawn_agent)
    assert "thread_id" in sig.parameters
    assert "persona" in sig.parameters
    assert "task" in sig.parameters


def test_list_personas_signature():
    from server.tools.agents import list_personas
    sig = inspect.signature(list_personas)
    assert not sig.parameters


def test_load_skill_tools_signature():
    from server.tools.registry import load_skill_tools
    sig = inspect.signature(load_skill_tools)
    assert "tool_group" in sig.parameters


def test_add_skill_signature():
    from server.tools.skill_installer import add_skill
    sig = inspect.signature(add_skill)
    assert "source_path" in sig.parameters
    assert "overwrite" in sig.parameters


def test_set_sandbox_signature():
    from server.tools.executor import set_sandbox
    sig = inspect.signature(set_sandbox)
    assert "path" in sig.parameters
    assert "thread_id" in sig.parameters
    assert sig.parameters["thread_id"].default is None


def test_execute_in_sandbox_signature():
    from server.tools.executor import execute_in_sandbox
    sig = inspect.signature(execute_in_sandbox)
    assert "command" in sig.parameters
    assert "thread_id" in sig.parameters
    assert "cwd" in sig.parameters
    assert sig.parameters["timeout_seconds"].default == 120


def test_execute_with_recovery_signature():
    from server.tools.executor import execute_with_recovery
    sig = inspect.signature(execute_with_recovery)
    assert "command" in sig.parameters
    assert "thread_id" in sig.parameters
    assert "cwd" in sig.parameters
    assert "timeout_seconds" in sig.parameters
    assert "recovery_attempts_used" in sig.parameters


def test_afk_tool_signatures():
    from server.tools.executor import afk_status, pause_afk, start_afk

    start_sig = inspect.signature(start_afk)
    assert "task" in start_sig.parameters
    assert "steps" in start_sig.parameters
    assert "thread_id" in start_sig.parameters
    assert "cwd" in start_sig.parameters
    assert "background" in start_sig.parameters

    status_sig = inspect.signature(afk_status)
    assert "thread_id" in status_sig.parameters

    pause_sig = inspect.signature(pause_afk)
    assert "thread_id" in pause_sig.parameters


# ---------------------------------------------------------------------------
# AC2: Tools raise McpError (not crash) when called without storage
# ---------------------------------------------------------------------------

def test_kill_thread_raises_tool_error():
    import asyncio
    from unittest.mock import MagicMock, patch
    from mcp.server.fastmcp.exceptions import ToolError
    from server.tools.tylor import kill_thread
    mock_db = MagicMock()
    mock_db.get_thread_meta.return_value = None
    with pytest.raises(ToolError):
        with patch("server.tools.tylor._get_db", return_value=mock_db):
            asyncio.run(kill_thread(thread_id="t123"))


def test_new_thread_validates_short_name():
    # Story 2.3: new_thread is implemented — validates input before any DB write
    from mcp.server.fastmcp.exceptions import ToolError
    from server.tools.tylor import new_thread
    with pytest.raises(ToolError, match="3\u201364 characters"):
        new_thread(name="ab")  # too short


def test_list_threads_returns_dict():
    # Story 2.3: list_threads is implemented — returns {threads: []} when DB is mocked empty
    import server.tools.tylor as tylor_mod
    from unittest.mock import MagicMock, patch
    mock_db = MagicMock()
    mock_db.query_all.return_value = []
    with patch.object(tylor_mod, "_get_db", return_value=mock_db):
        from server.tools.tylor import list_threads
        result = list_threads()
    assert "threads" in result


def test_list_registry_returns_dict():
    from server.tools.registry import list_registry
    assert "skills" in list_registry()


# ---------------------------------------------------------------------------
# AC3: config.py warns on missing optional keys without crashing
# ---------------------------------------------------------------------------

def test_config_loads_without_crash():
    """config.py must be importable without crashing regardless of env state."""
    if "server.config" in sys.modules:
        del sys.modules["server.config"]
    mod = importlib.import_module("server.config")
    assert hasattr(mod, "config")
    assert isinstance(mod.config, dict)


def test_config_warns_on_missing_platform_key(caplog):
    """Missing Platform on AWS API key must emit a warning."""
    env_backup = os.environ.pop("ANTHROPIC_PLATFORM_AWS_API_KEY", None)
    aws_env_backup = os.environ.pop("ANTHROPIC_AWS_API_KEY", None)
    try:
        os.environ["ANTHROPIC_PLATFORM_AWS_API_KEY"] = ""
        os.environ["ANTHROPIC_AWS_API_KEY"] = ""
        if "server.config" in sys.modules:
            del sys.modules["server.config"]
        with caplog.at_level(logging.WARNING, logger="server.config"):
            importlib.import_module("server.config")
        assert any("ANTHROPIC_PLATFORM_AWS_API_KEY" in r.message for r in caplog.records)
    finally:
        os.environ.pop("ANTHROPIC_PLATFORM_AWS_API_KEY", None)
        os.environ.pop("ANTHROPIC_AWS_API_KEY", None)
        if env_backup is not None:
            os.environ["ANTHROPIC_PLATFORM_AWS_API_KEY"] = env_backup
        if aws_env_backup is not None:
            os.environ["ANTHROPIC_AWS_API_KEY"] = aws_env_backup


def test_config_bedrock_region_defaults_to_us_east_1():
    """Bedrock region must default to us-east-1 when not set."""
    env_backup = os.environ.pop("BEDROCK_REGION", None)
    try:
        if "server.config" in sys.modules:
            del sys.modules["server.config"]
        mod = importlib.import_module("server.config")
        assert mod.config["bedrock_region"] == "us-east-1"
    finally:
        if env_backup is not None:
            os.environ["BEDROCK_REGION"] = env_backup


def test_config_reads_aws_profile_from_env():
    """AWS_PROFILE env var must be reflected in config."""
    os.environ["AWS_PROFILE"] = "agent101-test"
    try:
        if "server.config" in sys.modules:
            del sys.modules["server.config"]
        mod = importlib.import_module("server.config")
        assert mod.config["aws_profile"] == "agent101-test"
    finally:
        del os.environ["AWS_PROFILE"]
