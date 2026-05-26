"""Tests for Codex installer registration."""
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INSTALL_PATH = ROOT / "install.py"


def _load_installer():
    spec = importlib.util.spec_from_file_location("tylor_install", INSTALL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_requirements_include_claude_agent_sdk():
    requirements = (ROOT / "server" / "requirements.txt").read_text(encoding="utf-8")

    assert "claude-agent-sdk" in requirements


def test_patch_codex_config_creates_agent101_mcp_block(tmp_path):
    installer = _load_installer()
    config_path = tmp_path / ".codex" / "config.toml"
    python_path = tmp_path / "venv" / "Scripts" / "python.exe"

    assert installer.patch_codex_config(config_path, python_path)

    text = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.agent101]" in text
    assert 'type = "stdio"' in text
    assert "enabled = true" in text
    assert f'command = "{python_path.as_posix()}"' in text
    assert 'args = ["-m", "server.main"]' in text
    assert "PYTHONPATH" in text


def test_patch_codex_config_is_idempotent_and_preserves_settings(tmp_path):
    installer = _load_installer()
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join([
            'model = "gpt-5.5"',
            "",
            "[mcp_servers.agent101]",
            'command = "old-python"',
            'args = ["old"]',
            "",
            "[projects.'C:\\\\work']",
            'trust_level = "trusted"',
            "",
        ]),
        encoding="utf-8",
    )
    python_path = tmp_path / "venv" / "bin" / "python3"

    assert installer.patch_codex_config(config_path, python_path)
    assert installer.patch_codex_config(config_path, python_path)

    text = config_path.read_text(encoding="utf-8")
    assert text.count("[mcp_servers.agent101]") == 1
    assert 'model = "gpt-5.5"' in text
    assert "[projects.'C:\\\\work']" in text
    assert "old-python" not in text
    assert f'command = "{python_path.as_posix()}"' in text
