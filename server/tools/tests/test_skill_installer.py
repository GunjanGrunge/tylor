"""
Tests for Story 4.3: /add-skill command and auto-generated registry entries.
Run: pytest server/tools/tests/test_skill_installer.py -v
"""
import json
from pathlib import Path

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import INVALID_PARAMS

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent


def _write_skill_package(root: Path, name: str = "bmad") -> Path:
    package = root / name
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: Use when user wants to create a PRD, review stories, or run BMAD workflows.\n"
        "---\n\n"
        f"# /{name}\n\n"
        "Use when user wants to create a PRD, review stories, or run BMAD workflows.\n\n"
        "Call `load_skill_tools(\"bmad\")` when this trigger matches.\n",
        encoding="utf-8",
    )
    (package / "notes.md").write_text("extra file", encoding="utf-8")
    return package


def _read_registry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_install_skill_copies_package_and_appends_generated_registry_entry(tmp_path):
    from server.tools.skill_installer import install_skill

    source = _write_skill_package(tmp_path / "source")
    skills_dir = tmp_path / "skills"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text('{"version":"1.0","skills":[]}', encoding="utf-8")

    result = install_skill(
        source_path=source,
        skills_dir=skills_dir,
        registry_path=registry_path,
    )

    target = skills_dir / "bmad"
    assert result["name"] == "bmad"
    assert result["installed_to"] == str(target)
    assert (target / "SKILL.md").exists()
    assert (target / "notes.md").read_text(encoding="utf-8") == "extra file"

    registry = _read_registry(registry_path)
    [entry] = registry["skills"]
    assert entry["name"] == "bmad"
    assert entry["trigger"]
    assert entry["trigger_description"] == entry["trigger"]
    assert {"prd", "review", "stories", "bmad", "workflows"} <= set(entry["keywords"])
    assert entry["tool_count"] == 1
    assert entry["source_path"] == str(source)
    assert entry["installed_date"]


def test_install_skill_requires_skill_markdown(tmp_path):
    from server.tools.skill_installer import install_skill

    source = tmp_path / "empty-skill"
    source.mkdir()

    with pytest.raises(McpError) as excinfo:
        install_skill(
            source_path=source,
            skills_dir=tmp_path / "skills",
            registry_path=tmp_path / "registry.json",
        )

    assert excinfo.value.error.code == INVALID_PARAMS
    assert "SKILL.md not found" in excinfo.value.error.message


def test_install_skill_duplicate_requires_overwrite_confirmation(tmp_path):
    from server.tools.skill_installer import install_skill

    source = _write_skill_package(tmp_path / "source")
    skills_dir = tmp_path / "skills"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "skills": [
                    {
                        "name": "bmad",
                        "trigger": "existing",
                        "trigger_description": "existing",
                        "keywords": ["existing"],
                        "tool_count": 1,
                        "installed_date": "2026-05-12",
                        "source_path": "/old",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(McpError) as excinfo:
        install_skill(
            source_path=source,
            skills_dir=skills_dir,
            registry_path=registry_path,
        )

    assert excinfo.value.error.code == INVALID_PARAMS
    assert "already exists" in excinfo.value.error.message
    assert "overwrite=True" in excinfo.value.error.message

    result = install_skill(
        source_path=source,
        skills_dir=skills_dir,
        registry_path=registry_path,
        overwrite=True,
    )
    assert result["status"] == "installed"
    registry = _read_registry(registry_path)
    assert len(registry["skills"]) == 1
    assert registry["skills"][0]["source_path"] == str(source)


def test_install_skill_preserves_module_and_tools_from_frontmatter(tmp_path):
    from server.tools.skill_installer import install_skill

    package = tmp_path / "source"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\n"
        "name: bmad\n"
        "description: Use when user wants to create a PRD.\n"
        "module: server.tools.ecc.web\n"
        "tools: [\"web_fetch\", \"web_scrape\"]\n"
        "---\n\n"
        "# /bmad\n\n"
        "Call `load_skill_tools(\"bmad\")` when this trigger matches.\n",
        encoding="utf-8",
    )
    skills_dir = tmp_path / "skills"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text('{"version":"1.0","skills":[]}', encoding="utf-8")

    result = install_skill(
        source_path=package,
        skills_dir=skills_dir,
        registry_path=registry_path,
    )

    registry = _read_registry(registry_path)
    entry = registry["skills"][0]
    assert entry["module"] == "server.tools.ecc.web"
    assert entry["tools"] == ["web_fetch", "web_scrape"]
    assert result["name"] == "bmad"


def test_add_skill_slash_command_file_exists_and_mentions_installer():
    path = PLUGIN_DIR / "skills" / "add-skill" / "SKILL.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "name: add-skill" in text
    assert "/add-skill" in text
    assert "server.tools.skill_installer" in text
    assert "overwrite" in text.lower()
    assert "registry.json" in text
