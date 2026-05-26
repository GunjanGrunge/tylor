#!/usr/bin/env python3
"""
Tylor installer — patches all Claude clients on Mac / Windows / Linux / WSL.

Clients patched:
  1. Claude Code CLI        → ~/.claude/settings.json
  2. Claude Code VSCode ext → ~/.claude/settings.json  (same file as CLI)
  3. Claude Desktop Mac     → ~/Library/Application Support/Claude/claude_desktop_config.json
  4. Claude Desktop Windows → %APPDATA%/Claude/claude_desktop_config.json
  5. Claude Desktop Linux   → ~/.config/Claude/claude_desktop_config.json
  6. GitHub Copilot CLI     → ~/.copilot/mcp.json
  7. Antigravity            → ~/.gemini/antigravity/mcp_config.json

Usage:
  python3 install.py            # default: project JSON storage
  python3 install.py --dynamo   # use DynamoDB storage
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
SERVER_MAIN = PLUGIN_DIR / "server" / "main.py"
REQUIREMENTS = PLUGIN_DIR / "server" / "requirements.txt"
VENV_DIR = Path.home() / ".tylor" / "venv"

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")


# ── Platform detection ────────────────────────────────────────────────────────

def is_windows() -> bool:
    return platform.system() == "Windows" or "microsoft" in platform.uname().release.lower()

def is_mac() -> bool:
    return platform.system() == "Darwin"

def is_linux() -> bool:
    return platform.system() == "Linux"

def is_wsl() -> bool:
    return is_linux() and "microsoft" in platform.uname().release.lower()


# ── Config file locations ─────────────────────────────────────────────────────

def claude_code_settings() -> Path:
    """Claude Code CLI + VSCode extension — ~/.claude/settings.json on all platforms."""
    return Path.home() / ".claude" / "settings.json"


def claude_desktop_configs() -> list[Path]:
    """All possible Claude Desktop config file locations."""
    candidates = []
    if is_mac():
        candidates.append(
            Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        )
    if is_windows():
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    if is_linux() or is_wsl():
        candidates.append(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")
        # WSL might also access Windows AppData
        if is_wsl():
            try:
                win_appdata = subprocess.check_output(
                    ["cmd.exe", "/c", "echo %APPDATA%"],
                    text=True, stderr=subprocess.DEVNULL
                ).strip()
                if win_appdata:
                    wsl_path = subprocess.check_output(
                        ["wslpath", win_appdata],
                        text=True, stderr=subprocess.DEVNULL
                    ).strip()
                    candidates.append(
                        Path(wsl_path) / "Claude" / "claude_desktop_config.json"
                    )
            except Exception:
                pass
    return [p for p in candidates if p.parent.exists() or p.exists()]

def github_copilot_configs() -> list[Path]:
    """GitHub Copilot CLI config file locations."""
    return [Path.home() / ".copilot" / "mcp.json"]

def antigravity_configs() -> list[Path]:
    """Antigravity agent config file locations."""
    return [Path.home() / ".gemini" / "antigravity" / "mcp_config.json"]

def codex_config() -> Path:
    """Codex CLI / IDE extension config file location."""
    return Path.home() / ".codex" / "config.toml"


# ── Python / venv setup ───────────────────────────────────────────────────────

def find_python() -> str:
    """Find a Python 3.8+ executable."""
    for candidate in ("python3", "python", sys.executable):
        try:
            out = subprocess.check_output(
                [candidate, "-c", "import sys; print(sys.version_info[:2])"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            major, minor = eval(out)
            if (major, minor) >= (3, 8):
                return candidate
        except Exception:
            continue
    return sys.executable


def setup_venv() -> Path:
    """Create venv at ~/.tylor/venv and install deps. Returns python path."""
    header("Setting up Python environment")

    python = find_python()
    py_in_venv = VENV_DIR / ("Scripts" if is_windows() else "bin") / ("python.exe" if is_windows() else "python3")

    if not py_in_venv.exists():
        print(f"  Creating venv at {VENV_DIR} ...")
        subprocess.run([python, "-m", "venv", str(VENV_DIR)], check=True)

    pip = VENV_DIR / ("Scripts" if is_windows() else "bin") / ("pip.exe" if is_windows() else "pip")
    print(f"  Installing dependencies ...")
    result = subprocess.run(
        [str(pip), "install", "-q", "-r", str(REQUIREMENTS)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        fail(f"pip install failed:\n{result.stderr[-500:]}")
        return py_in_venv
    ok(f"Python environment ready ({py_in_venv})")
    return py_in_venv


# ── MCP server entry ──────────────────────────────────────────────────────────

def mcp_server_entry(python_path: Path) -> dict:
    """Build the mcpServers entry for any config file."""
    # Use forward slashes everywhere — works on Mac/Linux/WSL
    # Windows: Claude Desktop accepts forward slashes in JSON
    py   = python_path.as_posix()
    main = SERVER_MAIN.as_posix()
    cwd  = PLUGIN_DIR.as_posix()
    return {
        "command": py,
        "args":    ["-m", "server.main"],
        "env":     {"PYTHONPATH": cwd},
    }


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _toml_inline_table(values: dict[str, str]) -> str:
    pairs = [f"{key} = {_toml_string(value)}" for key, value in values.items()]
    return "{ " + ", ".join(pairs) + " }"


def codex_mcp_server_block(python_path: Path) -> str:
    """Build Codex's TOML MCP server entry for agent101."""
    entry = mcp_server_entry(python_path)
    return "\n".join([
        "[mcp_servers.agent101]",
        'type = "stdio"',
        "enabled = true",
        f"command = {_toml_string(str(entry['command']))}",
        f"args = {_toml_array(list(entry['args']))}",
        f"cwd = {_toml_string(PLUGIN_DIR.as_posix())}",
        f"env = {_toml_inline_table(entry['env'])}",
        "",
    ])


# ── Hooks entries ─────────────────────────────────────────────────────────────

def hooks_entries() -> dict:
    """Build the hooks section. Shell scripts on Mac/Linux, Python on Windows."""
    hooks_dir = PLUGIN_DIR / "hooks"
    if is_windows():
        # Windows: run hooks as Python scripts (no bash)
        py = (VENV_DIR / "Scripts" / "python.exe").as_posix()
        server_dir = (PLUGIN_DIR / "server").as_posix()
        def win_hook(cmd: str) -> str:
            return f"{py} -c \"import sys; sys.path.insert(0,'{server_dir}'); from server.tools.hooks import main; sys.argv=['hooks','{cmd}']; main()\""
        return {
            "SessionStart": [{"type": "command", "command": win_hook("session-start")}],
            "Stop":         [{"type": "command", "command": win_hook("session-checkpoint")}],
            "PostToolUse":  [
                {"matcher": "kill_thread",
                 "hooks": [{"type": "command", "command": win_hook("kill-thread-trigger")}]},
                {"matcher": "Read|Write|Edit|MultiEdit",
                 "hooks": [{"type": "command", "command": win_hook("post-tool-use-code-index")}]}
            ],
        }
    else:
        def sh(name: str) -> str:
            return (hooks_dir / name).as_posix()
        return {
            "SessionStart": [{"type": "command", "command": sh("session-start.sh")}],
            "Stop":         [{"type": "command", "command": sh("session-checkpoint.sh")}],
            "PostToolUse":  [
                {"matcher": "kill_thread",
                 "hooks": [{"type": "command", "command": sh("kill-thread-trigger.sh")}]},
                {"matcher": "Read|Write|Edit|MultiEdit",
                 "hooks": [{"type": "command", "command": sh("post-tool-use-code-index.sh")}]}
            ],
        }


# ── Patch a single config file ────────────────────────────────────────────────

def patch_config(config_path: Path, python_path: Path, is_desktop: bool = False) -> bool:
    """
    Patch an existing Claude config file with Tylor's MCP server + hooks.
    Creates the file if it doesn't exist.
    Returns True on success.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if config_path.exists():
        try:
            settings = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warn(f"Could not parse {config_path} — will overwrite")
            settings = {}

    # MCP server
    servers = settings.setdefault("mcpServers", {})
    servers["agent101"] = mcp_server_entry(python_path)

    # Hooks — Claude Desktop doesn't support hooks, only Claude Code CLI/VSCode
    if not is_desktop:
        new_hooks = hooks_entries()
        existing_hooks = settings.setdefault("hooks", {})
        for event, entries in new_hooks.items():
            event_list = existing_hooks.setdefault(event, [])
            for entry in entries:
                cmd = entry.get("command", "")
                if not any(e.get("command") == cmd for e in event_list):
                    event_list.append(entry)

    # Write atomically
    tmp = config_path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        os.replace(tmp, config_path)
        return True
    except OSError as e:
        fail(f"Could not write {config_path}: {e}")
        tmp.unlink(missing_ok=True)
        return False


_CODEX_AGENT101_BLOCK_RE = re.compile(
    r"(?ms)^\[mcp_servers\.agent101\]\n.*?(?=^\[|\Z)"
)


def patch_codex_config(config_path: Path, python_path: Path) -> bool:
    """
    Patch Codex's TOML config with the agent101 MCP server.
    Preserves unrelated user settings and replaces only the agent101 MCP block.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    current = ""
    if config_path.exists():
        try:
            current = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            fail(f"Could not read {config_path}: {exc}")
            return False

    block = codex_mcp_server_block(python_path)
    if _CODEX_AGENT101_BLOCK_RE.search(current):
        updated = _CODEX_AGENT101_BLOCK_RE.sub(block, current).rstrip() + "\n"
    else:
        updated = current.rstrip()
        updated = (updated + "\n\n" if updated else "") + block

    tmp = config_path.with_suffix(".tmp")
    try:
        tmp.write_text(updated, encoding="utf-8")
        os.replace(tmp, config_path)
        return True
    except OSError as exc:
        fail(f"Could not write {config_path}: {exc}")
        tmp.unlink(missing_ok=True)
        return False


# ── Validate server starts ────────────────────────────────────────────────────

def validate(python_path: Path) -> bool:
    result = subprocess.run(
        [str(python_path), "-c",
         f"import sys; sys.path.insert(0,{str(PLUGIN_DIR)!r}); "
         f"from server.tools._mcp import mcp; assert mcp.name=='agent101'"],
        capture_output=True, text=True, cwd=str(PLUGIN_DIR)
    )
    if result.returncode == 0:
        ok("MCP server validates correctly (name: agent101)")
        return True
    fail(f"Server validation failed: {result.stderr.strip()[-300:]}")
    return False


# ── Storage config ────────────────────────────────────────────────────────────

def _bundle_bmad() -> None:
    """
    Clone or update BMAD into ~/.tylor/bmad so the harness can use its
    workflows silently. BMAD is never exposed directly to the user —
    the harness activates it based on thread context.
    """
    import subprocess
    bmad_dir = Path.home() / ".tylor" / "bmad"
    bmad_repo = "https://github.com/bmadcode/BMAD-METHOD"

    if bmad_dir.exists():
        # Already installed — pull latest silently
        result = subprocess.run(
            ["git", "-C", str(bmad_dir), "pull", "--quiet"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            ok("BMAD updated")
        else:
            warn("BMAD update skipped (no internet or git not available)")
    else:
        # First install — try to clone
        result = subprocess.run(
            ["git", "clone", "--quiet", "--depth=1", bmad_repo, str(bmad_dir)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            ok(f"BMAD bundled at {bmad_dir}")
        else:
            warn("BMAD not available (no internet or git not found) — harness will work without it")
            return

    # Point harness to BMAD location via config
    config_file = Path.home() / ".tylor" / "config.json"
    try:
        import json
        cfg = json.loads(config_file.read_text()) if config_file.exists() else {}
        cfg["bmad_path"] = bmad_dir.as_posix()
        config_file.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


def configure_storage(use_dynamo: bool) -> None:
    config_dir = Path.home() / ".tylor"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    cfg_file = config_dir / "config.json"
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text())
        except Exception:
            cfg = {}
    if use_dynamo:
        cfg["storage_mode"] = "personal"
        ok("Storage mode: Personal (AWS DynamoDB)")
    else:
        cfg["storage_mode"] = "project"
        cfg["storage_path"] = (config_dir / "threads.json").as_posix()
        ok("Storage mode: Project (local JSON, no AWS needed)")
    cfg_file.write_text(json.dumps(cfg, indent=2))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    use_dynamo = "--dynamo" in sys.argv

    print(f"\n{BOLD}  Tylor installer{RESET}")
    print(f"  {'─' * 50}")
    print(f"  Platform : {platform.system()} {'(WSL)' if is_wsl() else ''}")
    print(f"  Plugin   : {PLUGIN_DIR}")

    # Step 1: Python venv
    python_path = setup_venv()

    # Step 2: Storage config
    header("Configuring storage")
    configure_storage(use_dynamo)

    # Step 3: Patch Claude Code CLI + VSCode (same settings.json)
    header("Patching Claude Code CLI / VSCode extension")
    cli_path = claude_code_settings()
    if patch_config(cli_path, python_path, is_desktop=False):
        ok(f"Patched {cli_path}")
    else:
        fail(f"Failed to patch {cli_path}")

    # Step 4: Patch Claude Desktop (all locations that exist)
    header("Patching Claude Desktop")
    desktop_configs = claude_desktop_configs()
    if not desktop_configs:
        warn("Claude Desktop config not found — skipping (install Claude Desktop first if needed)")
    for cfg_path in desktop_configs:
        # Desktop config may not exist yet — create it
        if patch_config(cfg_path, python_path, is_desktop=True):
            ok(f"Patched {cfg_path}")
        else:
            fail(f"Failed to patch {cfg_path}")

    # Step 5: Patch GitHub Copilot
    header("Patching GitHub Copilot CLI")
    copilot_configs = github_copilot_configs()
    for cfg_path in copilot_configs:
        if patch_config(cfg_path, python_path, is_desktop=True):
            ok(f"Patched {cfg_path}")
        else:
            fail(f"Failed to patch {cfg_path}")

    # Step 6: Patch Antigravity
    header("Patching Antigravity")
    antigravity_cfgs = antigravity_configs()
    for cfg_path in antigravity_cfgs:
        if patch_config(cfg_path, python_path, is_desktop=True):
            ok(f"Patched {cfg_path}")
        else:
            fail(f"Failed to patch {cfg_path}")

    # Step 7: Patch Codex
    header("Patching Codex")
    codex_path = codex_config()
    if patch_codex_config(codex_path, python_path):
        ok(f"Patched {codex_path}")
    else:
        fail(f"Failed to patch {codex_path}")

    # Step 8: Bundle BMAD silently
    header("Bundling BMAD (silent)")
    _bundle_bmad()

    # Step 9: Validate
    header("Validating")
    validate(python_path)

    # Step 10: Done
    print(f"\n{BOLD}{GREEN}  ✓ Tylor installed successfully!{RESET}\n")
    print("  Next steps:")
    print("  1. Restart Claude Code / Claude Desktop / VSCode / Codex")
    print("  2. Type /help-agent101 to see all commands")
    if use_dynamo:
        print(f"  3. Add AWS credentials to {PLUGIN_DIR / 'server' / '.env'}")
    print()


if __name__ == "__main__":
    main()
