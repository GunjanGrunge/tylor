"""Bumblebee security gate and risky execution guard."""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

from server.config import config

RISKY_COMMAND_PATTERNS = [
    re.compile(r"\b(?:python3\s+-m\s+pip|pip(?:3)?|npm|pnpm|yarn|brew|cargo|gem|composer|apt(?:-get)?|apk)\b.*\binstall\b", re.I),
    re.compile(r"\b(?:code|code-insiders)\b.*\b--install-extension\b", re.I),
    re.compile(r"\bgh\b.*\bextension\s+install\b", re.I),
    re.compile(r"\baz\b.*\bextension\s+add\b", re.I),
    re.compile(r"\b(?:install|upgrade|add)\b.*\b(?:extension|plugin|skill|mcp|package|config)\b", re.I),
    re.compile(r"\b(?:registry\.json|SKILL\.md)\b", re.I),
]
BUMBLEBEE_SCAN_TIMEOUT_SECONDS = 120


def bumblebee_enabled() -> bool:
    return bool(config.get("bumblebee_enabled", False))


def _bumblebee_path() -> str | None:
    path = config.get("bumblebee_path")
    if path:
        expanded = os.path.expanduser(str(path))
        if shutil.which(expanded):
            return expanded
    return shutil.which("bumblebee")


def _should_guard_command(command: str) -> bool:
    for pattern in RISKY_COMMAND_PATTERNS:
        if pattern.search(command):
            return True
    return False


def _parse_bumblebee_output(output: str) -> dict | None:
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _is_risky_scan_result(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("risk") or result.get("risky"):
        return True
    for key in ("findings", "issues", "alerts", "warnings", "violations"):
        value = result.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _bumblebee_alternatives() -> str:
    return (
        "Suggested alternatives:\n"
        "  - Install Bumblebee and ensure it is on your PATH or set BUMBLEBEE_PATH.\n"
        "  - Run `bumblebee scan --json` manually before retrying.\n"
        "  - If you understand the risk, disable the gate with BUMBLEBEE_ENABLED=false.\n"
        "  - Review package metadata and AI/MCP config changes before executing."
    )


def run_bumblebee_security_gate(command: str, cwd: str | None = None) -> bool:
    if not bumblebee_enabled() or not _should_guard_command(command):
        return False

    path = _bumblebee_path()
    if not path:
        raise ToolError(
            "Bumblebee security gate is enabled by default and has flagged this command as potentially risky. "
            "The Bumblebee CLI was not found on this machine. "
            + _bumblebee_alternatives()
        )

    cwd_path = str(Path(cwd or os.getcwd()).expanduser())
    try:
        result = subprocess.run(
            [path, "scan", "--json"],
            cwd=cwd_path,
            capture_output=True,
            text=True,
            timeout=BUMBLEBEE_SCAN_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError as exc:
        raise ToolError(
            "Bumblebee security gate attempted to initiate a check but failed to run. "
            f"Error: {exc}. "
            + _bumblebee_alternatives()
        ) from exc

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        raise ToolError(
            "Bumblebee security gate initiated a scan and blocked execution because the scanner returned a non-zero status. "
            f"stdout: {stdout} stderr: {stderr}\n" + _bumblebee_alternatives()
        )

    parsed = _parse_bumblebee_output(stdout)
    if _is_risky_scan_result(parsed):
        raise ToolError(
            "Bumblebee security gate initiated a scan and blocked execution because the scanner detected risky exposure. "
            f"stdout: {stdout} stderr: {stderr}\n" + _bumblebee_alternatives()
        )

    return True


def validate_skill_package(source_path: str | Path) -> None:
    if not bumblebee_enabled():
        return

    path = Path(source_path).expanduser().resolve()
    if not path.exists():
        raise ToolError(f"Skill package path does not exist: {source_path}")

    bumblebee = _bumblebee_path()
    if not bumblebee:
        raise ToolError(
            "Bumblebee security gate is enabled but the bumblebee CLI was not found. "
            "Install Bumblebee or disable the gate by setting BUMBLEBEE_ENABLED=false."
        )

    try:
        result = subprocess.run(
            [bumblebee, "scan", "--json"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=BUMBLEBEE_SCAN_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError as exc:
        raise ToolError(f"Bumblebee security gate failed to run on skill package: {exc}") from exc

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        raise ToolError(
            "Bumblebee security gate blocked skill installation because the scanner returned a non-zero status. "
            f"stdout: {stdout} stderr: {stderr}"
        )

    parsed = _parse_bumblebee_output(stdout)
    if _is_risky_scan_result(parsed):
        raise ToolError(
            "Bumblebee security gate blocked skill installation because the scan detected risky exposure. "
            f"stdout: {stdout} stderr: {stderr}"
        )
