"""
Tests for Story 2.9: thread management slash-command skill files
Run: pytest server/tools/tests/test_thread_command_skills.py -v
"""
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent
SKILLS_DIR = PLUGIN_DIR / "skills"


COMMANDS = {
    "new-thread": ["new_thread", "prompt", "thread name", "Created thread", "recovery"],
    "switch-thread": ["list_threads", "switch_thread", "selection", "Switched", "recovery"],
    "kill-thread": ["kill_thread", "Summarization in progress", "Killing", "recovery"],
    "list-threads": ["list_threads", "Active", "message_count", "recovery"],
    "recall": ["recall_memory", "query", "results", "recovery"],
}


def _read_skill(command: str) -> str:
    return (SKILLS_DIR / command / "SKILL.md").read_text()


def test_all_thread_command_skill_files_exist():
    for command in COMMANDS:
        path = SKILLS_DIR / command / "SKILL.md"
        assert path.exists(), f"Missing {path}"


def test_skill_files_have_frontmatter_name_and_description():
    for command in COMMANDS:
        text = _read_skill(command)
        assert text.startswith("---\n")
        assert f"name: {command}" in text
        assert "description:" in text


def test_skill_files_reference_required_tools_and_confirmations():
    for command, required_phrases in COMMANDS.items():
        text = _read_skill(command)
        for phrase in required_phrases:
            assert phrase in text, f"{command} missing {phrase!r}"


def test_switch_thread_requires_listing_before_switching():
    text = _read_skill("switch-thread")
    assert text.index("list_threads") < text.index("switch_thread")


def test_error_handling_mentions_failed_operation_and_next_steps():
    for command in COMMANDS:
        text = _read_skill(command).lower()
        assert "failed operation" in text
        assert "recovery steps" in text
