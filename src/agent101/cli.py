#!/usr/bin/env python3
"""
Agent101 CLI - One-command installation and management for Tylor plugin
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

def get_package_root():
    """Get the root directory of the agent101 package"""
    return Path(__file__).parent

def get_config_dir():
    """Get the user config directory"""
    return Path.home() / ".tylor"

def get_claude_settings():
    """Get Claude Code settings file path"""
    return Path.home() / ".claude" / "settings.json"

def ensure_claude_settings():
    """Ensure Claude settings file exists"""
    settings_file = get_claude_settings()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    if not settings_file.exists():
        settings_file.write_text("{}")
    return settings_file

def install_server_config(storage_mode="project"):
    """Install MCP server configuration"""
    settings_file = ensure_claude_settings()

    # Read existing settings
    settings = json.loads(settings_file.read_text())

    # Get package root and server script path
    package_root = get_package_root()
    server_script = package_root / "src" / "agent101" / "server" / "main.py"

    # Register MCP server
    servers = settings.setdefault("mcpServers", {})
    if "agent101" not in servers:
        servers["agent101"] = {
            "command": sys.executable,
            "args": [str(server_script)],
            "cwd": str(package_root),
        }
        print("✓ MCP server registered")

    # Register hooks
    hooks_dir = package_root / "hooks"
    hooks = settings.setdefault("hooks", {})

    hook_configs = [
        ("SessionStart", {"command": str(hooks_dir / "session-start.sh")}),
        ("Stop", {"command": str(hooks_dir / "session-checkpoint.sh")}),
        ("PostToolUse", {"matcher": "kill_thread", "command": str(hooks_dir / "kill-thread-trigger.sh")}),
    ]

    # Add file operation hooks
    for matcher in ("Read", "Write", "Edit", "MultiEdit"):
        hook_configs.append(("PostToolUse", {"matcher": matcher, "command": str(hooks_dir / "post-tool-use-code-index.sh")}))

    for event, config in hook_configs:
        existing = hooks.setdefault(event, [])
        cmd = config.get("command")
        if not any(h.get("command") == cmd for h in existing):
            existing.append(config)
            print(f"✓ {event} hook registered")

    # Write back settings
    settings_file.write_text(json.dumps(settings, indent=2))

def install_storage_config(storage_mode="project"):
    """Install storage configuration"""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "config.json"
    config = {}

    if config_file.exists():
        config = json.loads(config_file.read_text())

    if storage_mode == "project":
        package_root = get_package_root()
        config["storage_mode"] = "project"
        config["storage_path"] = str(package_root / ".tylor" / "threads.json")
        print("✓ Storage mode: Project (local JSON)")
    else:
        config["storage_mode"] = "personal"
        print("✓ Storage mode: Personal (AWS DynamoDB)")

    config_file.write_text(json.dumps(config, indent=2))

def install_registry():
    """Install skill registry"""
    package_root = get_package_root()
    registry_file = package_root / "registry.json"

    if not registry_file.exists():
        registry_file.write_text('{"version":"1.0","skills":[]}')
        print("✓ Skill registry initialized")

def validate_server():
    """Validate MCP server can be imported"""
    try:
        package_root = get_package_root()
        server_main = package_root / "src" / "agent101" / "server" / "main.py"

        # Add package root to Python path
        sys.path.insert(0, str(package_root))

        # Import and validate server
        from agent101.server.main import mcp

        if mcp.name == "agent101":
            print("✓ MCP server validates correctly")
            return True
        else:
            print(f"✗ Unexpected server name: {mcp.name}")
            return False

    except Exception as e:
        print(f"✗ Server validation failed: {e}")
        return False

def run_server():
    """Run the MCP server"""
    package_root = get_package_root()
    server_script = package_root / "src" / "agent101" / "server" / "main.py"

    print(f"Starting Agent101 server from {server_script}")
    os.chdir(package_root)

    # Run the server
    subprocess.run([sys.executable, str(server_script)], check=True)

def install_command(args):
    """Handle installation"""
    print("Agent101 Installer")
    print("=" * 20)

    storage_mode = args.mode

    # Install storage config
    install_storage_config(storage_mode)

    # Install MCP server config
    install_server_config()

    # Install registry
    install_registry()

    # Validate server
    if validate_server():
        print("\n✓ Agent101 installed successfully!")
        print("\nNext steps:")
        print("1. Restart Claude Code")
        print("2. Type /help-agent101 to see available commands")
        if storage_mode == "personal":
            print("3. Configure AWS credentials for persistence")
    else:
        print("\n✗ Installation failed - server validation error")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Agent101 - Tylor Plugin Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Install command
    install_parser = subparsers.add_parser("install", help="Install Agent101 plugin")
    install_parser.add_argument("--mode", choices=["project", "personal"],
                               default="project",
                               help="Storage mode (default: project)")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run the MCP server")

    # Default to install if no command given
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