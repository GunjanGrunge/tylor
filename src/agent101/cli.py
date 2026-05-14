#!/usr/bin/env python3
"""
Agent101 CLI - One-command installation and management for Tylor plugin
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def get_package_root() -> Path:
    """Root of the installed agent101 package (contains server/, hooks/, skills/, ui/)."""
    return Path(__file__).parent


def get_config_dir() -> Path:
    return Path.home() / ".tylor"


def get_claude_settings() -> Path:
    return Path.home() / ".claude" / "settings.json"


def ensure_claude_settings() -> Path:
    settings_file = get_claude_settings()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    if not settings_file.exists():
        settings_file.write_text("{}")
    return settings_file


def install_server_config() -> bool:
    """Patch ~/.claude/settings.json with MCP server + hooks."""
    settings_file = ensure_claude_settings()

    try:
        settings = json.loads(settings_file.read_text())
    except json.JSONDecodeError:
        settings = {}

    package_root = get_package_root()

    # ── MCP server ─────────────────────────────────────────────
    server_script = package_root / "server" / "main.py"
    if not server_script.exists():
        print(f"✗ Server script not found: {server_script}")
        return False

    servers = settings.setdefault("mcpServers", {})
    servers["agent101"] = {
        "command": sys.executable,
        "args": [str(server_script)],
        "cwd": str(package_root),
    }
    print("✓ MCP server registered in settings.json")

    # ── Hooks ──────────────────────────────────────────────────
    hooks_dir = package_root / "hooks"
    hooks = settings.setdefault("hooks", {})

    def _add_hook(event: str, config: dict) -> None:
        existing = hooks.setdefault(event, [])
        cmd = config.get("command")
        if not any(h.get("command") == cmd for h in existing):
            existing.append(config)
            print(f"✓ {event} hook registered")

    _add_hook("SessionStart", {"command": str(hooks_dir / "session-start.sh")})
    _add_hook("Stop",         {"command": str(hooks_dir / "session-checkpoint.sh")})
    _add_hook("PostToolUse",  {"matcher": "kill_thread",
                                "command": str(hooks_dir / "kill-thread-trigger.sh")})
    for matcher in ("Read", "Write", "Edit", "MultiEdit"):
        _add_hook("PostToolUse", {"matcher": matcher,
                                   "command": str(hooks_dir / "post-tool-use-code-index.sh")})

    settings_file.write_text(json.dumps(settings, indent=2))
    return True


def install_storage_config(storage_mode: str = "project") -> None:
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"

    config: dict = {}
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
        except json.JSONDecodeError:
            config = {}

    if storage_mode == "project":
        config["storage_mode"] = "project"
        config["storage_path"] = str(config_dir / "threads.json")
        print("✓ Storage mode: Project (local JSON, zero AWS setup)")
    else:
        config["storage_mode"] = "personal"
        print("✓ Storage mode: Personal (AWS DynamoDB)")
        print("  → Add AWS credentials to:", get_package_root() / "server" / ".env")

    config_file.write_text(json.dumps(config, indent=2))


def install_registry() -> None:
    registry_file = get_package_root() / "registry.json"
    if not registry_file.exists():
        registry_file.write_text('{"version":"1.0","skills":[]}')
        print("✓ Skill registry initialized")


def validate_server() -> bool:
    """Quick smoke-test: can Python import the server module?"""
    package_root = get_package_root()
    server_script = package_root / "server" / "main.py"

    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0,'{package_root}'); "
         f"from agent101.server.tools._mcp import mcp; "
         f"assert mcp.name == 'agent101', mcp.name"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("✓ MCP server validates correctly (name: agent101)")
        return True
    else:
        print(f"✗ Server validation failed: {result.stderr.strip()}")
        return False


def install_command(args: argparse.Namespace) -> None:
    print("\n  Tylor installer\n  " + "─" * 40)

    ok = True
    install_storage_config(args.mode)
    if not install_server_config():
        ok = False
    install_registry()

    if ok and validate_server():
        print("\n  ✓ Tylor installed successfully!")
        print("\n  Next steps:")
        print("  1. Restart Claude Code")
        print("  2. Type /help-agent101 to see all commands")
        if args.mode == "personal":
            print(f"  3. Add AWS credentials: {get_package_root() / 'server' / '.env'}")
            print(f"     (copy from {get_package_root() / 'server' / '.env.example'})")
    else:
        print("\n  ✗ Installation failed — see messages above")
        sys.exit(1)


def run_server() -> None:
    package_root = get_package_root()
    server_script = package_root / "server" / "main.py"
    os.chdir(package_root)
    os.execv(sys.executable, [sys.executable, str(server_script)])


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent101",
        description="Tylor — the tailor to your threads",
    )
    sub = parser.add_subparsers(dest="command")

    install_p = sub.add_parser("install", help="Install the Tylor plugin into Claude Code")
    install_p.add_argument(
        "--mode", choices=["project", "personal"], default="project",
        help="Storage mode: 'project' = local JSON (default), 'personal' = AWS DynamoDB",
    )

    sub.add_parser("run", help="Run the MCP server directly")

    if len(sys.argv) == 1:
        args = parser.parse_args(["install"])
    else:
        args = parser.parse_args()

    if args.command == "install":
        install_command(args)
    elif args.command == "run":
        run_server()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
