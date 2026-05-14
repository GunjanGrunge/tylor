"""
Tests for Story 4.2: two-tier manifest and skill registry client.
Run: pytest server/tools/tests/test_registry_client.py -v
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent


def _write_registry(path: Path, skills: list[dict]) -> None:
    path.write_text(
        json.dumps({"version": "1.0", "skills": skills}, indent=2),
        encoding="utf-8",
    )


def test_list_registry_returns_lightweight_skill_index(tmp_path):
    from server.tools import registry as registry_mod

    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        [
            {
                "name": "bmad",
                "trigger_description": "BMad story workflows",
                "keywords": ["story", "review"],
                "tool_count": 2,
                "installed_date": "2026-05-13",
                "module": "server.tools.ecc.web",
                "tools": ["web_fetch", "web_scrape"],
                "schemas": [{"name": "too-heavy"}],
            }
        ],
    )

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path):
        result = registry_mod.list_registry()

    assert result == {
        "skills": [
            {
                "name": "bmad",
                "trigger_description": "BMad story workflows",
                "keywords": ["story", "review"],
                "tool_count": 2,
            }
        ]
    }
    assert "schemas" not in result["skills"][0]
    assert "module" not in result["skills"][0]
    assert "tools" not in result["skills"][0]


def test_load_skill_tools_loads_registry_backed_group_without_restart(tmp_path):
    from server.tools import registry as registry_mod
    from server.tools._mcp import mcp

    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        [
            {
                "name": "bmad",
                "trigger_description": "BMad story workflows",
                "keywords": ["story"],
                "tool_count": 2,
                "module": "server.tools.ecc.web",
                "tools": ["web_fetch", "web_scrape"],
            }
        ],
    )

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path):
        result = registry_mod.load_skill_tools("bmad")

    assert result == {
        "tool_group": "bmad",
        "status": "loaded",
        "tools": ["web_fetch", "web_scrape"],
    }
    tool_names = {tool.name for tool in __import__("asyncio").run(mcp.list_tools())}
    assert {"web_fetch", "web_scrape"} <= tool_names


def test_startup_manifest_is_tier1_only_and_lists_under_100ms():
    code = """
import asyncio, json, time
import server.main
from server.tools._mcp import mcp
start = time.perf_counter()
tools = asyncio.run(mcp.list_tools())
elapsed_ms = (time.perf_counter() - start) * 1000
print(json.dumps({"elapsed_ms": elapsed_ms, "tools": sorted(t.name for t in tools)}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PLUGIN_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    tier2_tools = {
        "web_scrape",
        "web_fetch",
        "dataset_manager",
        "data_clean",
        "data_transform",
        "build_pptx",
        "build_doc",
        "diagram_gen",
        "flowchart_gen",
        "pipeline_builder",
        "pipeline_run",
    }
    assert payload["elapsed_ms"] < 100
    assert tier2_tools.isdisjoint(payload["tools"])


def test_detect_registry_skill_match_surfaces_agent101_suggestion(tmp_path):
    from server.tools import registry as registry_mod

    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        [
            {
                "name": "bmad",
                "trigger_description": "Use when user wants to create a PRD or draft requirements.",
                "keywords": ["prd", "requirements"],
                "tool_count": 2,
                "module": "server.tools.ecc.web",
                "tools": ["web_fetch", "web_scrape"],
            }
        ],
    )

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path):
        result = registry_mod.detect_registry_skill("let's draft a PRD for this idea")

    assert result == {
        "matched": True,
        "skill": "bmad",
        "action": "suggest",
        "message": "You have BMAD in agent101 — want me to use it?",
        "thread_persistence": True,
    }


def test_auto_load_matching_registry_skill_loads_tools(tmp_path):
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
        result = registry_mod.detect_registry_skill(
            "let's draft a PRD for this idea",
            auto_load=True,
        )

    assert result["matched"] is True
    assert result["action"] == "loaded"
    assert result["skill"] == "bmad"
    assert result["loaded"]["tools"] == ["web_fetch", "web_scrape"]
    assert result["thread_persistence"] is True


def test_auto_load_matching_registry_skill_without_tools_falls_back_to_suggestion(tmp_path):
    from server.tools import registry as registry_mod

    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        [
            {
                "name": "bmad",
                "trigger_description": "Use when user wants to create a PRD.",
                "keywords": ["prd"],
                "tool_count": 1,
                "source_path": "/local/skills/bmad",
            }
        ],
    )

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path), patch(
        "server.tools.registry.importlib.import_module"
    ) as import_module:
        result = registry_mod.detect_registry_skill(
            "let's draft a PRD for this idea",
            auto_load=True,
        )

    assert result == {
        "matched": True,
        "skill": "bmad",
        "action": "suggest",
        "message": "You have BMAD in agent101 — want me to use it?",
        "thread_persistence": True,
    }
    import_module.assert_not_called()


def test_non_matching_registry_skill_does_not_load_schemas(tmp_path):
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

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path), patch(
        "server.tools.registry.importlib.import_module"
    ) as import_module:
        result = registry_mod.detect_registry_skill("show my active threads", auto_load=True)

    assert result == {"matched": False, "action": "none"}
    import_module.assert_not_called()


def test_generic_trigger_words_do_not_match_registry_skill(tmp_path):
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

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path), patch(
        "server.tools.registry.importlib.import_module"
    ) as import_module:
        result = registry_mod.detect_registry_skill(
            "create a new thread for billing",
            auto_load=True,
        )

    assert result == {"matched": False, "action": "none"}
    import_module.assert_not_called()


def test_explicit_native_slash_skill_is_not_thread_persistent(tmp_path):
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

    with patch.object(registry_mod, "REGISTRY_PATH", registry_path), patch(
        "server.tools.registry.importlib.import_module"
    ) as import_module:
        result = registry_mod.detect_registry_skill("/bmad create a PRD")

    assert result == {
        "matched": True,
        "skill": "bmad",
        "action": "claude_native",
        "thread_persistence": False,
    }
    import_module.assert_not_called()
