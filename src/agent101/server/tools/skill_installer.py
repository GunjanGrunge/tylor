"""Skill package installer for the /add-skill command."""
from __future__ import annotations
import json
import re
import shutil
import argparse
from datetime import datetime, timezone
from pathlib import Path

from mcp.shared.exceptions import McpError
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ErrorData, INVALID_PARAMS

from ._mcp import mcp

PLUGIN_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SKILLS_DIR = PLUGIN_DIR / "skills"
DEFAULT_REGISTRY_PATH = PLUGIN_DIR / "registry.json"

_STOPWORDS = {
    "and",
    "for",
    "the",
    "this",
    "that",
    "use",
    "user",
    "when",
    "wants",
    "with",
}


def _invalid_params(message: str) -> McpError:
    return McpError(ErrorData(code=INVALID_PARAMS, message=message))


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_registry(path: Path) -> dict:
    if not path.exists():
        return {"version": "1.0", "skills": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_registry(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _parse_frontmatter_value(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value.strip("'\"")


def _frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    data = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = _parse_frontmatter_value(value)
    return data


def _skill_name(source_path: Path, metadata: dict, explicit_name: str | None) -> str:
    raw = explicit_name or metadata.get("name") or source_path.name
    name = raw.strip().lower().replace(" ", "-").replace("_", "-")
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", name):
        raise _invalid_params(f"Invalid skill name: {raw}")
    return name


def _trigger_description(text: str, metadata: dict) -> str:
    description = metadata.get("description", "").strip()
    if description:
        return description
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("use when"):
            return line
    return "No trigger description provided."


def _keywords(name: str, trigger: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", f"{name} {trigger}".lower())
    seen = set()
    keywords = []
    for word in words:
        if len(word) < 3 or word in _STOPWORDS or word in seen:
            continue
        seen.add(word)
        keywords.append(word)
    return keywords


def _tool_count(text: str) -> int:
    tool_refs = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]+)\(", text))
    return len(tool_refs)


def _copy_skill(source_path: Path, target_path: Path, overwrite: bool) -> None:
    if target_path.exists():
        if not overwrite:
            raise _invalid_params(
                f"Skill '{target_path.name}' already exists; rerun with overwrite=True to replace it."
            )
        shutil.rmtree(target_path)
    shutil.copytree(source_path, target_path)


def install_skill(
    source_path: str | Path,
    name: str | None = None,
    overwrite: bool = False,
    skills_dir: str | Path = DEFAULT_SKILLS_DIR,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict:
    """Copy a skill package and upsert its generated registry entry."""
    source = Path(source_path).expanduser().resolve()
    skill_file = source / "SKILL.md"
    if not skill_file.exists():
        raise _invalid_params(f"SKILL.md not found in {source}")

    text = skill_file.read_text(encoding="utf-8")
    metadata = _frontmatter(text)
    skill_name = _skill_name(source, metadata, name)
    trigger = _trigger_description(text, metadata)
    target = Path(skills_dir) / skill_name
    registry = _read_registry(Path(registry_path))
    skills = list(registry.get("skills", []))
    exists = any(entry.get("name") == skill_name for entry in skills)

    if exists and not overwrite:
        raise _invalid_params(
            f"Skill '{skill_name}' already exists in registry.json; rerun with overwrite=True to replace it."
        )

    _copy_skill(source, target, overwrite=overwrite)

    module = metadata.get("module")
    tools = metadata.get("tools")
    if isinstance(tools, str):
        tools = [tools]
    if tools is not None and not isinstance(tools, list):
        raise _invalid_params("Invalid tools metadata in SKILL.md; use a comma-separated list or JSON array.")

    entry = {
        "name": skill_name,
        "trigger": trigger,
        "trigger_description": trigger,
        "keywords": _keywords(skill_name, trigger),
        "tool_count": _tool_count(text),
        "installed_date": _now_date(),
        "source_path": str(source),
    }
    if module:
        entry["module"] = str(module)
    if tools:
        entry["tools"] = [str(tool).strip() for tool in tools if str(tool).strip()]

    registry["skills"] = [entry for entry in skills if entry.get("name") != skill_name]
    registry["skills"].append(entry)
    _write_registry(Path(registry_path), registry)

    return {
        "status": "installed",
        "name": skill_name,
        "installed_to": str(target),
        "registry_path": str(registry_path),
    }


@mcp.tool()
def add_skill(
    source_path: str,
    name: str | None = None,
    overwrite: bool = False,
) -> dict:
    """
    Install an agent101 skill package and update registry.json.

    Args:
        source_path: Local path to a skill package directory containing SKILL.md.
        name: Optional skill name override.
        overwrite: Replace an existing installed skill if present.
    """
    try:
        return install_skill(
            source_path=source_path,
            name=name,
            overwrite=overwrite,
        )
    except McpError:
        raise
    except Exception as exc:
        raise ToolError(f"add_skill failed: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Install an agent101 skill package.")
    parser.add_argument("source_path")
    parser.add_argument("--name")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    result = install_skill(
        source_path=args.source_path,
        name=args.name,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
