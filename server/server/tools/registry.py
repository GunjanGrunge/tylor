"""
server/tools/registry.py — Tier 1 skill registry MCP tools.
FR36-FR39: load_skill_tools, list_registry.

Story 4.1 implements built-in ECC category loading. Story 4.2 expands this
to the full registry client for external skill groups.
"""
from __future__ import annotations
import importlib
import json
import re
from pathlib import Path

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS

from ._mcp import mcp

PLUGIN_DIR = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PLUGIN_DIR / "registry.json"

ECC_GROUPS = {
    "ecc/web": ("server.tools.ecc.web", ["web_scrape", "web_fetch"]),
    "ecc/data": ("server.tools.ecc.data", ["dataset_manager", "data_clean", "data_transform"]),
    "ecc/presentation": ("server.tools.ecc.presentation", ["build_pptx", "build_doc"]),
    "ecc/diagrams": ("server.tools.ecc.diagrams", ["diagram_gen", "flowchart_gen"]),
    "ecc/pipeline": ("server.tools.ecc.pipeline", ["pipeline_builder", "pipeline_run"]),
}


def _invalid_category(tool_group: str) -> McpError:
    return McpError(
        ErrorData(
            code=INVALID_PARAMS,
            message=f"Unknown skill category: {tool_group}",
        )
    )


def _read_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"version": "1.0", "skills": []}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _registry_skills() -> list[dict]:
    data = _read_registry()
    return data.get("skills", [])


def _find_registry_skill(name: str) -> dict | None:
    normalized = name.strip().lower()
    for skill in _registry_skills():
        if skill.get("name", "").strip().lower() == normalized:
            return skill
    return None


def _task_tokens(task: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", task.lower()))


def _skill_keyword_tokens(skill: dict) -> set[str]:
    tokens: set[str] = set()
    for keyword in skill.get("keywords") or []:
        if isinstance(keyword, str):
            tokens.update(_task_tokens(keyword))
    return tokens


def _native_slash_skill(task: str) -> str | None:
    stripped = task.strip()
    if not stripped.startswith("/"):
        return None
    command = stripped.split(maxsplit=1)[0][1:].lower()
    return command or None


def _suggestion(skill_name: str) -> dict:
    return {
        "matched": True,
        "skill": skill_name,
        "action": "suggest",
        "message": f"You have {skill_name.upper()} in agent101 — want me to use it?",
        "thread_persistence": True,
    }


import re as _re
_SAFE_MODULE_RE = _re.compile(r'^server\.tools\.[a-z0-9_.]+$')


def _load_module_group(tool_group: str, module_path: str, tools: list[str]) -> dict:
    if not _SAFE_MODULE_RE.match(module_path):
        from mcp.server.fastmcp.exceptions import ToolError
        raise ToolError(
            f"Unsafe module path '{module_path}' — must match server.tools.<name>"
        )
    importlib.import_module(module_path)
    return {
        "tool_group": tool_group,
        "status": "loaded",
        "tools": sorted(tools),
    }


@mcp.tool()
def load_skill_tools(tool_group: str) -> dict:
    """
    Lazy-load a Tier 2 tool group into the active session manifest.
    Use when a task matches a specific skill category.
    Available groups: ecc/web, ecc/data, ecc/presentation, ecc/diagrams, ecc/pipeline.

    Args:
        tool_group: The tool group path to load (e.g. "ecc/web", "ecc/data").
    """
    if tool_group in ECC_GROUPS:
        module_path, tools = ECC_GROUPS[tool_group]
        return _load_module_group(tool_group, module_path, tools)

    skill = _find_registry_skill(tool_group)
    if not skill:
        raise _invalid_category(tool_group)

    module_path = skill.get("module")
    tools = skill.get("tools", [])
    if not module_path or not tools:
        raise _invalid_category(tool_group)

    return _load_module_group(tool_group, module_path, tools)


def detect_registry_skill(task: str, auto_load: bool = False) -> dict:
    """
    Detect whether a user task matches an installed agent101 registry skill.
    Non-matches never import Tier 2 modules, keeping the startup manifest lean.

    Args:
        task: User task text to evaluate against registry trigger metadata.
        auto_load: When true, load the matched registry skill's Tier 2 tools.
    """
    native_command = _native_slash_skill(task)
    if native_command and _find_registry_skill(native_command):
        return {
            "matched": True,
            "skill": native_command,
            "action": "claude_native",
            "thread_persistence": False,
        }

    tokens = _task_tokens(task)
    for skill in _registry_skills():
        name = skill.get("name", "").strip()
        if not name or not tokens.intersection(_skill_keyword_tokens(skill)):
            continue

        if auto_load and skill.get("module") and skill.get("tools"):
            return {
                "matched": True,
                "skill": name,
                "action": "loaded",
                "loaded": load_skill_tools(name),
                "thread_persistence": True,
            }

        return _suggestion(name)

    return {"matched": False, "action": "none"}


@mcp.tool()
def list_registry() -> dict:
    """
    List all installed skills from registry.json with their trigger descriptions.
    Returns skills sorted by install date descending.
    """
    skills = sorted(
        _registry_skills(),
        key=lambda skill: skill.get("installed_date", ""),
        reverse=True,
    )
    return {
        "skills": [
            {
                "name": skill.get("name", ""),
                "trigger_description": skill.get(
                    "trigger_description",
                    skill.get("trigger", ""),
                ),
                "keywords": list(skill.get("keywords", [])),
                "tool_count": int(skill.get("tool_count", 0)),
            }
            for skill in skills
        ]
    }
