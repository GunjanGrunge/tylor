"""
Tests for Story 4.5: /help-agent101 slash command.
Run: pytest server/tools/tests/test_help_agent101.py -v
"""
import json
from pathlib import Path
from unittest.mock import patch


PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
SKILLS_DIR = PLUGIN_DIR / "skills"


def _write_registry(path: Path, skills: list[dict]) -> None:
    path.write_text(
        json.dumps({"version": "1.0", "skills": skills}, indent=2),
        encoding="utf-8",
    )


def test_help_agent101_skill_file_exists_and_describes_live_help_tool():
    path = SKILLS_DIR / "help-agent101" / "SKILL.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: help-agent101" in text
    assert "help_agent101" in text
    assert "list_registry" in text
    assert "list_personas" in text


def test_help_index_lists_commands_tools_registry_personas_and_ecc(tmp_path):
    from server.tools import help as help_mod
    from server.tools import registry as registry_mod

    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        [
            {
                "name": "bmad",
                "trigger_description": "Use when user wants to create a PRD.",
                "keywords": ["prd"],
                "tool_count": 2,
                "module": "server.tools.ecc.web",
                "tools": ["web_fetch", "web_scrape"],
            }
        ],
    )

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path):
        result = help_mod.build_help_index()

    assert {command["command"] for command in result["slash_commands"]} >= {
        "/new-thread",
        "/switch-thread",
        "/kill-thread",
        "/list-threads",
        "/recall",
        "/add-skill",
        "/open-threads-ui",
        "/set-sandbox",
        "/afk-status",
    }
    assert {tool["name"] for tool in result["tier1_tools"]} >= {
        "new_thread",
        "switch_thread",
        "switch_thread_by_name",
        "kill_thread",
        "recall_memory",
        "list_threads",
        "list_personas",
        "spawn_agent",
        "spawn_agents",
        "load_skill_tools",
        "list_registry",
        "help_agent101",
        "set_sandbox",
        "execute_in_sandbox",
        "execute_with_recovery",
        "start_afk",
        "afk_status",
        "pause_afk",
    }
    assert result["registered_skills"] == [
        {
            "name": "bmad",
            "trigger": "Use when user wants to create a PRD.",
        }
    ]
    assert {persona["name"] for persona in result["personas"]} == {
        "analyst",
        "ceo",
        "code_agent",
        "cto",
    }
    assert result["ecc_categories"]["ecc/web"] == ["web_fetch", "web_scrape"]
    assert result["ecc_categories"]["ecc/pipeline"] == [
        "pipeline_builder",
        "pipeline_run",
    ]


def test_help_agent101_reads_registry_fresh_each_invocation(tmp_path):
    from server.tools import help as help_mod
    from server.tools import registry as registry_mod

    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        [
            {
                "name": "alpha",
                "trigger_description": "Use for alpha workflows.",
                "keywords": ["alpha"],
                "tool_count": 1,
            }
        ],
    )

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path):
        first = help_mod.help_agent101()
        _write_registry(
            registry_path,
            [
                {
                    "name": "beta",
                    "trigger_description": "Use for beta workflows.",
                    "keywords": ["beta"],
                    "tool_count": 1,
                }
            ],
        )
        second = help_mod.help_agent101()

    assert first["registered_skills"] == [
        {"name": "alpha", "trigger": "Use for alpha workflows."}
    ]
    assert second["registered_skills"] == [
        {"name": "beta", "trigger": "Use for beta workflows."}
    ]


def test_help_agent101_registered_as_tier1_tool():
    import asyncio
    import server.main  # noqa: F401
    from server.tools._mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    assert "help_agent101" in {tool.name for tool in tools}
