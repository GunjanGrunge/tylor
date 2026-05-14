#!/usr/bin/env bash
# Tylor installer
# Usage: ./install.sh
# bash 3.2+ compatible (macOS default shell)

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS_FILE="$HOME/.claude/settings.json"
CONFIG_DIR="$HOME/.tylor"
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
header() { echo -e "\n${BOLD}$*${NC}"; }

# ---------------------------------------------------------------------------
# 0. Select storage mode (Project JSON vs Personal DynamoDB)
# ---------------------------------------------------------------------------
select_storage_mode() {
  header "Select storage mode"
  echo "  [1] Project (local JSON) — zero AWS setup, single-machine only"
  echo "  [2] Personal (AWS DynamoDB) — persistent, multi-machine (default)"
  echo ""
  printf "  Choice [2]: "
  read -r choice </dev/tty || choice=""

  mkdir -p "$CONFIG_DIR"

  if [ "$choice" = "1" ]; then
    python3 - <<PYEOF
import json
from pathlib import Path

config_path = Path("$CONFIG_DIR/config.json")
data = {}
if config_path.exists():
    try:
        data = json.loads(config_path.read_text())
    except Exception:
        data = {}

data["storage_mode"] = "project"
data["storage_path"] = "$PLUGIN_DIR/.tylor/threads.json"
config_path.write_text(json.dumps(data, indent=2))
print("  \033[0;32m✓\033[0m  Storage mode: Project (local JSON)")
print(f"     threads.json: $PLUGIN_DIR/.tylor/threads.json")
PYEOF
  else
    python3 - <<PYEOF
import json
from pathlib import Path

config_path = Path("$CONFIG_DIR/config.json")
data = {}
if config_path.exists():
    try:
        data = json.loads(config_path.read_text())
    except Exception:
        data = {}

# Only set if not already configured (idempotent)
if data.get("storage_mode") not in ("personal", "project"):
    data["storage_mode"] = "personal"
    config_path.write_text(json.dumps(data, indent=2))
    print("  \033[0;32m✓\033[0m  Storage mode: Personal (AWS DynamoDB)")
else:
    print(f"     Storage mode already set to '{data['storage_mode']}' — skipping")
PYEOF
  fi
}

# ---------------------------------------------------------------------------
# 1. Install Python dependencies
# ---------------------------------------------------------------------------
install_deps() {
  header "Installing dependencies"
  if python3 -m pip install -r "$PLUGIN_DIR/server/requirements.txt" --quiet; then
    ok "Dependencies installed"
  else
    fail "Dependency installation failed"
    echo "     Fix: ensure pip is available and you have internet access"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# 2. Patch ~/.claude/settings.json (idempotent)
# ---------------------------------------------------------------------------
patch_settings_json() {
  header "Registering MCP server and hooks in settings.json"

  # Create settings file if absent
  if [ ! -f "$SETTINGS_FILE" ]; then
    mkdir -p "$(dirname "$SETTINGS_FILE")"
    echo '{}' > "$SETTINGS_FILE"
    ok "Created $SETTINGS_FILE"
  fi

  python3 - <<PYEOF
import json, sys
from pathlib import Path

settings_file = Path("$SETTINGS_FILE")
plugin_dir    = "$PLUGIN_DIR"
hooks_dir     = plugin_dir + "/hooks"

data = json.loads(settings_file.read_text() or "{}")

# --- MCP server entry ---
servers = data.setdefault("mcpServers", {})
if "agent101" not in servers:
    servers["agent101"] = {
        "command": "python3",
        "args": ["server/main.py"],
        "cwd": plugin_dir,
    }
    print("  \033[0;32m✓\033[0m  MCP server registered")
else:
    print("     MCP server entry already present — skipping")

# --- Hooks (idempotent: check command before appending) ---
hooks = data.setdefault("hooks", {})

def add_hook(event, entry):
    existing = hooks.setdefault(event, [])
    cmd = entry.get("command")
    if not any(h.get("command") == cmd for h in existing):
        existing.append(entry)
        print(f"  \033[0;32m✓\033[0m  {event} hook registered")
    else:
        print(f"     {event} hook already present — skipping")

add_hook("SessionStart", {"command": hooks_dir + "/session-start.sh"})
add_hook("Stop",         {"command": hooks_dir + "/session-checkpoint.sh"})
add_hook("PostToolUse",  {"matcher": "kill_thread",
                          "command": hooks_dir + "/kill-thread-trigger.sh"})
for matcher in ("Read", "Write", "Edit", "MultiEdit"):
    add_hook("PostToolUse", {"matcher": matcher,
                             "command": hooks_dir + "/post-tool-use-code-index.sh"})

settings_file.write_text(json.dumps(data, indent=2))
PYEOF
}

# ---------------------------------------------------------------------------
# 3. Initialize registry.json
# ---------------------------------------------------------------------------
init_registry() {
  header "Initializing skill registry"
  local registry="$PLUGIN_DIR/registry.json"
  if [ ! -f "$registry" ]; then
    echo '{"version":"1.0","skills":[]}' > "$registry"
    ok "registry.json created"
  else
    ok "registry.json already exists — skipping"
  fi
}

# ---------------------------------------------------------------------------
# 4. Validate MCP server can be imported (stdio transport exits immediately
#    when not connected to Claude Code — import check is the correct gate)
# ---------------------------------------------------------------------------
validate_startup() {
  header "Validating MCP server"

  if python3 -c "
import sys
sys.path.insert(0, '$PLUGIN_DIR')
from server.main import mcp
assert mcp.name == 'agent101', f'Unexpected server name: {mcp.name}'
" 2>/dev/null; then
    ok "MCP server imports and initializes correctly (name: agent101)"
    ok "Claude Code will start it automatically via stdio on next session"
    return 0
  else
    fail "MCP server failed to import"
    echo "     Fix: check Python version (3.11+ required) and run:"
    echo "       python3 -c \"from server.main import mcp; print(mcp.name)\""
    return 1
  fi
}

# ---------------------------------------------------------------------------
# 5. Validate AWS connectivity (advisory — never blocks install)
# ---------------------------------------------------------------------------
validate_aws() {
  python3 "$PLUGIN_DIR/server/validate.py" "$PLUGIN_DIR"
}

# ---------------------------------------------------------------------------
# 6. Provision AWS resources (advisory — never blocks install)
# ---------------------------------------------------------------------------
provision_aws() {
  python3 "$PLUGIN_DIR/server/provision.py" "$PLUGIN_DIR"
}

# ---------------------------------------------------------------------------
# 7. Provision OpenSearch index (advisory — never blocks install)
# ---------------------------------------------------------------------------
provision_opensearch() {
  python3 "$PLUGIN_DIR/server/provision_opensearch.py"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  echo ""
  echo -e "${BOLD}Tylor installer${NC}"
  echo "Plugin directory: $PLUGIN_DIR"

  ERRORS=0

  select_storage_mode
  install_deps   || ERRORS=$((ERRORS + 1))
  patch_settings_json || ERRORS=$((ERRORS + 1))
  init_registry
  validate_startup   || ERRORS=$((ERRORS + 1))

  # AWS steps: skip entirely in Project mode
  STORAGE_MODE="$(python3 -c "
import json, pathlib
cfg = pathlib.Path('$CONFIG_DIR/config.json')
print(json.loads(cfg.read_text()).get('storage_mode','personal') if cfg.exists() else 'personal')
" 2>/dev/null || echo "personal")"

  if [ "$STORAGE_MODE" = "personal" ]; then
    validate_aws
    provision_aws
    provision_opensearch
  else
    warn "Project mode selected — skipping AWS validation and provisioning"
  fi

  echo ""
  if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}Tylor installed ✓${NC}"
    echo ""
    echo "  Next steps:"
    echo "  1. Restart Claude Code to load the MCP server"
    echo "  2. Run Story 1.2 setup to validate AWS credentials (if using Personal mode)"
    echo "  3. Type /help-agent101 in Claude Code to see all available commands"
  else
    echo -e "${RED}${BOLD}Installation completed with $ERRORS error(s) — see messages above${NC}"
    exit 1
  fi
}

main "$@"
