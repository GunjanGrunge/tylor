"""server/tools/help.py — agent101 capability discovery."""
from __future__ import annotations

from ._mcp import mcp
from . import registry as registry_mod
from .personas import list_persona_summaries


SLASH_COMMANDS = [
    {
        "command": "/new-thread",
        "description": "Create a named thread and switch future work into it.",
    },
    {
        "command": "/switch-thread",
        "description": "List and switch to an existing thread.",
    },
    {
        "command": "/kill-thread",
        "description": "Close a thread and start async summarization.",
    },
    {
        "command": "/list-threads",
        "description": "Show available threads with status and activity.",
    },
    {
        "command": "/recall",
        "description": "Search semantic memory within a thread.",
    },
    {
        "command": "/add-skill",
        "description": "Install a skill package and update registry.json.",
    },
    {
        "command": "/open-threads-ui",
        "description": "Open the local thread visualizer UI when available.",
    },
    {
        "command": "/set-sandbox",
        "description": "Declare or clear filesystem roots for AFK execution.",
    },
    {
        "command": "/afk-status",
        "description": "Report current AFK execution progress for the active thread.",
    },
    {
        "command": "/run",
        "description": "Run a task in the active thread with automatic role and skill routing.",
    },
]

TIER1_TOOLS = [
    {
        "name": "new_thread",
        "description": "Create a new named thread.",
    },
    {
        "name": "switch_thread",
        "description": "Atomically switch to a thread by ID.",
    },
    {
        "name": "switch_thread_by_name",
        "description": "Fuzzy-match a thread name and switch to it.",
    },
    {
        "name": "kill_thread",
        "description": "Close a thread and dispatch async summarization.",
    },
    {
        "name": "recall_memory",
        "description": "Search thread memory using semantic recall.",
    },
    {
        "name": "save_memory",
        "description": "Persist a typed or untyped memory fact for a thread.",
    },
    {
        "name": "list_threads",
        "description": "List threads sorted by recent activity.",
    },
    {
        "name": "list_personas",
        "description": "List available specialist personas.",
    },
    {
        "name": "spawn_agent",
        "description": "Spawn a persona-scoped sub-agent in a thread with live verbose UI streaming.",
    },
    {
        "name": "spawn_agents",
        "description": "Spawn multiple persona-scoped agents in a thread for parallel work.",
    },
    {
        "name": "add_skill",
        "description": "Install a skill package and update registry.json.",
    },
    {
        "name": "load_skill_tools",
        "description": "Lazy-load a registered Tier 2 tool group.",
    },
    {
        "name": "list_registry",
        "description": "List installed skill packages without heavy schemas.",
    },
    {
        "name": "help_agent101",
        "description": "Return a current structured capability index.",
    },
    {
        "name": "set_sandbox",
        "description": "Declare or clear sandbox roots for a thread.",
    },
    {
        "name": "execute_in_sandbox",
        "description": "Run commands only after sandbox roots are configured.",
    },
    {
        "name": "execute_with_recovery",
        "description": "Run sandboxed commands with bounded AFK recovery.",
    },
    {
        "name": "start_afk",
        "description": "Plan and execute an AFK task in the active sandboxed thread.",
    },
    {
        "name": "afk_status",
        "description": "Report AFK progress for the active thread.",
    },
    {
        "name": "pause_afk",
        "description": "Request AFK execution to pause at the next checkpoint.",
    },
    {
        "name": "detect_thread_team",
        "description": "Preview which roles and ECC skill groups match a thread task.",
    },
    {
        "name": "run_in_thread",
        "description": "Run a task through the Agent SDK harness with automatic skill pickup.",
    },
    {
        "name": "list_available_roles",
        "description": "Show the role lenses available to the supervisor harness.",
    },
]


def _registered_skills() -> list[dict]:
    return [
        {
            "name": skill["name"],
            "trigger": skill.get("trigger_description", ""),
        }
        for skill in registry_mod.list_registry()["skills"]
    ]


def _ecc_categories() -> dict[str, list[str]]:
    return {
        category: sorted(tools)
        for category, (_module_path, tools) in registry_mod.ECC_GROUPS.items()
    }


def build_help_index() -> dict:
    """Build a current capability index for `/help-agent101`."""
    return {
        "slash_commands": list(SLASH_COMMANDS),
        "tier1_tools": list(TIER1_TOOLS),
        "registered_skills": _registered_skills(),
        "personas": list_persona_summaries(),
        "ecc_categories": _ecc_categories(),
    }


@mcp.tool()
def help_agent101() -> dict:
    """
    Return a structured listing of agent101 slash commands, Tier 1 tools,
    registered skills, personas, and ECC categories.
    """
    return build_help_index()
