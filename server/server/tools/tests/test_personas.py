"""
Tests for Story 3.1: persona definition files
Run: pytest server/tools/tests/test_personas.py -v
"""
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
PERSONAS_DIR = PLUGIN_DIR / "server" / "personas"

EXPECTED_PERSONAS = {
    "code_agent.md": {"ecc/web", "ecc/data", "ecc/pipeline"},
    "analyst.md": {"ecc/web", "ecc/data", "ecc/diagrams"},
    "ceo.md": {"ecc/presentation", "ecc/web"},
    "cto.md": {"ecc/diagrams", "ecc/pipeline"},
}


def _read_persona(filename: str) -> str:
    return (PERSONAS_DIR / filename).read_text()


def test_required_persona_files_exist():
    for filename in EXPECTED_PERSONAS:
        assert (PERSONAS_DIR / filename).exists(), f"Missing persona {filename}"


def test_each_persona_has_required_sections():
    for filename in EXPECTED_PERSONAS:
        text = _read_persona(filename)
        assert "# " in text
        assert "## Role Description" in text
        assert "## Communication Style" in text
        assert "## ECC Tool Categories" in text


def test_each_persona_declares_expected_ecc_categories():
    for filename, expected_categories in EXPECTED_PERSONAS.items():
        text = _read_persona(filename)
        for category in expected_categories:
            assert f"- `{category}`" in text, f"{filename} missing {category}"


def test_each_persona_has_no_unexpected_ecc_categories():
    allowed = set().union(*EXPECTED_PERSONAS.values())
    for filename in EXPECTED_PERSONAS:
        text = _read_persona(filename)
        declared = {
            line.strip().removeprefix("- `").removesuffix("`")
            for line in text.splitlines()
            if line.strip().startswith("- `ecc/")
        }
        assert declared <= allowed
