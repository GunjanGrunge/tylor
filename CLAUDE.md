# agent101 — Claude Code Plugin (TYLOR Thread Manager)

## Project Overview

agent101 is a Claude Code plugin — Personal Cognitive Infrastructure — that eliminates session death by giving Claude persistent, isolated, named context scopes called **threads**. Built as a FastMCP Python server with a local Thread Visualizer UI.

## Architecture

```
Claude Code (terminal)
  └── FastMCP server (server/main.py, stdio transport)
        ├── Tier 1 tools: new_thread, switch_thread, kill_thread, list_threads, recall_memory
        ├── Tier 2 tools (lazy): ECC skill modules (ecc/*/tools.py)
        ├── aiohttp UI server (localhost:8765) — Thread Visualizer
        └── Storage: DynamoDB single-table (Personal) or local JSON (Project mode)

Claude Code hooks (hooks/)
  ├── session-start.sh    → surfaces active thread context on session open
  ├── session-checkpoint.sh → checkpoints thread state on Stop
  └── kill-thread-trigger.sh → dispatches Bedrock Opus summarization on KillThread

Thread Visualizer (ui/)
  └── D3.js force graph, glassmorphism bubbles, silk SVG bezier curves, Vanta.js bg
```

## Directory Structure

```
agent101/
├── server/                    # FastMCP Python server
│   ├── main.py                # Entry point — co-starts FastMCP + aiohttp
│   ├── config.py              # pydantic-settings (reads .env)
│   ├── ui_server.py           # aiohttp web server (localhost:8765)
│   ├── tools/                 # MCP tool modules
│   │   ├── tylor.py           # Thread lifecycle tools (new/switch/kill/recall/list)
│   │   ├── ui.py              # open_threads_ui tool
│   │   ├── agents.py          # spawn_agent, list_personas
│   │   ├── registry.py        # load_skill_tools, list_registry
│   │   ├── executor.py        # sandboxed bash execution
│   │   └── router.py          # 3-tier model router
│   ├── storage/               # Storage clients
│   │   ├── dynamo.py          # DynamoDB single-table client
│   │   ├── json_store.py      # Project JSON mode (zero-infra)
│   │   ├── s3.py              # S3 blob storage (>400KB)
│   │   └── opensearch.py      # Vector search (Titan Embeddings v2)
│   └── personas/              # Agent persona definitions
├── ui/                        # Thread Visualizer (served by aiohttp)
│   └── index.html             # D3.js force graph + WebSocket client
├── hooks/                     # Claude Code lifecycle hook scripts
├── skills/                    # Claude Code slash commands
│   ├── new-thread/
│   ├── switch-thread/
│   ├── kill-thread/
│   ├── list-threads/
│   ├── recall/
│   ├── add-skill/
│   └── help-agent101/
├── ecc/                       # ECC tool modules (lazy-loaded Tier 2)
│   ├── web/, data/, presentation/, diagrams/, pipeline/
├── install.sh                 # One-command install
├── registry.json              # Installed skill index
└── pytest.ini                 # Test config (asyncio_mode = auto)
```

## Starting the Server

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m server.main    # starts FastMCP on stdio + aiohttp on :8765
```

## Environment Setup

Copy `.env` to `server/.env`. Required keys:
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `DYNAMO_TABLE` (default: agent101)
- `OPENSEARCH_HOST`, `OPENSEARCH_PORT`
- `BEDROCK_REGION` (default: us-east-1)

## Storage Modes

- **Project mode** (default): threads stored at `{cwd}/.agent101/threads.json` — zero AWS required
- **Personal mode**: DynamoDB-backed, cross-project, cross-machine

## Key Conventions

- All MCP tools use explicit `thread_id` parameter — never hidden server-side state
- All errors raised as `McpError` — never return error dicts
- DynamoDB items include mandatory fields: `PK`, `SK`, `CreatedAt`, `UpdatedAt`, `Version`
- MCP tool names: `verb_noun` snake_case — immutable once registered
- Status colors in UI: cyan=active, amber=awaiting, purple=running, dim=idle

## Running Tests

```bash
python3 -m pytest server/tests/ -v
```
