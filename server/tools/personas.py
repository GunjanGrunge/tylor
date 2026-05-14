"""
server/tools/personas.py — persona definition loading for agent orchestration.

Story 3.1 stores personas as structured markdown. This module provides the
deterministic parser used by Story 3.2 MCP tools.
"""
from dataclasses import dataclass
from pathlib import Path


PERSONAS_DIR = Path(__file__).resolve().parents[1] / "personas"
REQUIRED_PERSONAS = ("analyst", "ceo", "code_agent", "cto")


@dataclass(frozen=True)
class PersonaDefinition:
    name: str
    display_name: str
    role_summary: str
    communication_style: str
    ecc_tool_categories: list[str]
    role_prompt: str

    def summary(self) -> dict:
        return {
            "name": self.name,
            "role_summary": self.role_summary,
            "ecc_tool_categories": list(self.ecc_tool_categories),
        }


def _section(lines: list[str], heading: str) -> list[str]:
    start = None
    marker = f"## {heading}"
    for idx, line in enumerate(lines):
        if line.strip() == marker:
            start = idx + 1
            break
    if start is None:
        return []

    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return [line.rstrip() for line in lines[start:end] if line.strip()]


def _parse_ecc_categories(lines: list[str]) -> list[str]:
    categories: list[str] = []
    for line in lines:
        value = line.strip().removeprefix("-").strip().strip("`")
        if value.startswith("ecc/"):
            categories.append(value)
    return categories


def load_persona(name: str) -> PersonaDefinition | None:
    normalized = name.strip().lower().replace("-", "_")
    if normalized not in REQUIRED_PERSONAS:
        return None

    path = PERSONAS_DIR / f"{normalized}.md"
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    display_name = next(
        (line.removeprefix("#").strip() for line in lines if line.startswith("# ")),
        normalized,
    )
    role_lines = _section(lines, "Role Description")
    style_lines = _section(lines, "Communication Style")
    category_lines = _section(lines, "ECC Tool Categories")

    role_summary = " ".join(role_lines).strip()
    communication_style = " ".join(style_lines).strip()
    ecc_tool_categories = _parse_ecc_categories(category_lines)
    role_prompt = (
        f"# {display_name}\n\n"
        f"## Role Description\n{role_summary}\n\n"
        f"## Communication Style\n{communication_style}\n\n"
        "## ECC Tool Categories\n"
        + "\n".join(f"- `{category}`" for category in ecc_tool_categories)
    )

    return PersonaDefinition(
        name=normalized,
        display_name=display_name,
        role_summary=role_summary,
        communication_style=communication_style,
        ecc_tool_categories=ecc_tool_categories,
        role_prompt=role_prompt,
    )


def load_personas() -> list[PersonaDefinition]:
    personas = []
    for name in REQUIRED_PERSONAS:
        persona = load_persona(name)
        if persona is not None:
            personas.append(persona)
    return personas


def list_persona_summaries() -> list[dict]:
    return [persona.summary() for persona in load_personas()]
