# Tylor — the tailor to your threads

> A Claude Code plugin that eliminates session death.

Tylor gives Claude persistent, isolated named context scopes called **threads** — so every session picks up exactly where you left off, across multiple projects, with zero re-priming.

```
CT Backend API        → new thread, clean slate
SwThread Backend      → instant context switch, no re-explanation
/open-threads-ui      → live neural network dashboard of all your work
```

No database. No cloud account. No configuration. Just install and go.

> **Tylor runs inside Claude Code using Claude itself** — no separate AI, no extra API keys. It gives Claude the memory and tools it was missing.

---

## What it does

| Problem | Tylor's answer |
|---|---|
| Every Claude session forgets you | **Persistent threads** — context survives restarts, machine reboots, and version updates |
| Switching topics loses context | **`SwThread`** — atomic context switch in under 2 seconds |
| "Where was that file again?" | **Silent code indexing** — Claude navigates directly to the right file and line without re-scanning |
| Can't see what's running | **Thread Visualizer** at `localhost:8765` — live neural network graph of all threads |
| Need specialists for different tasks | **Personas** — CEO, CTO, Analyst, Code Agent per thread |
| Want Claude to work while you sleep | **AFK mode** — autonomous execution with automatic failure recovery |

---

## Installation

**Requirements:** Python 3.8+ · One of: Claude Code CLI, Claude Desktop, or VSCode with Claude extension

Works on **macOS, Windows, Linux, and WSL**.

### Step 1 — Clone the repo

```bash
git clone https://github.com/GunjanGrunge/tylor ~/.claude/plugins/GunjanGrunge/tylor
```

### Step 2 — Run the installer

```bash
python3 ~/.claude/plugins/GunjanGrunge/tylor/install.py
```

The installer automatically:
- Creates a Python virtual environment at `~/.tylor/venv`
- Installs all dependencies
- Patches **Claude Code CLI** (`~/.claude/settings.json`)
- Patches **Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json` on Mac, `%APPDATA%\Claude\` on Windows)
- VSCode extension uses the same config as Claude Code CLI — no extra step needed

You should see:
```
  ✓ Python environment ready
  ✓ Storage mode: Project (local JSON, no AWS needed)
  ✓ Patched ~/.claude/settings.json
  ✓ Patched ~/Library/Application Support/Claude/claude_desktop_config.json
  ✓ MCP server validates correctly (name: agent101)
  ✓ Tylor installed successfully!
```

### Step 3 — Restart your Claude client

Quit and reopen Claude Code, Claude Desktop, or VSCode.

### Step 4 — Verify

Type in any Claude session:

```
/help-agent101
```

You should see the full command listing. If you see it — Tylor is running.

---

## Troubleshooting

**`/help-agent101` not found after restart**

1. Re-run the installer: `python3 ~/.claude/plugins/GunjanGrunge/tylor/install.py`
2. Restart your Claude client completely
3. Check the MCP server is listed in your client's settings under MCP servers

**Python not found**

Tylor requires Python 3.8+. Check: `python3 --version`
If missing, install from [python.org](https://python.org) and restart your terminal.

**Windows: use `python` instead of `python3`**

```
python %USERPROFILE%\.claude\plugins\GunjanGrunge\tylor\install.py
```

**First session takes longer**

Normal — first run installs Python dependencies. Subsequent starts are instant.

---

## Quick start

```
# Create your first thread
CT My Project

# Create domain-specific threads
CT Backend API
CT Frontend UI
CT PRD Planning

# Switch between threads instantly — no re-priming
SwThread Backend
SwThread Frontend

# See all threads
/list-threads

# Open the live visual dashboard
/open-threads-ui
```

---

## Thread Visualizer

Open `http://localhost:8765` in your browser — a live neural network graph of all your threads across projects.

- **Click any thread node** → message history panel slides in
- **Click a project hub** → focuses that project's cluster
- Threads update live as you work
- Drag nodes to rearrange

---

## Core commands

### Thread lifecycle

| Command | What it does |
|---|---|
| `CT [name]` or `/new-thread` | Create a new named thread |
| `SwThread [name]` | Switch to a thread — fuzzy name matching |
| `/list-threads` | List all threads with status and message count |
| `KillThread [name]` or `/kill-thread` | Archive a thread with an AI-generated summary |
| `/recall [query]` | Search thread memory |

### Silent code indexing

Every time Claude reads or writes a file, Tylor silently records key symbols:

```
SignIn: src/components/auth/SignIn.tsx:89
useAuth: src/hooks/auth.ts:12
```

Next session, Claude goes directly to the right file — no codebase scanning.

### Agent personas

Spawn a specialist inside the active thread:

```
spawn_agent(persona="cto", thread_id=..., task="Design the database schema")
```

| Persona | Role |
|---|---|
| `ceo` | Strategy, prioritisation |
| `cto` | Architecture, system design |
| `analyst` | Research, data analysis |
| `code_agent` | Implementation, debugging |

### AFK execution

```
/set-sandbox ~/my-project
start_afk(task="Refactor the auth module and make the tests pass")
```

Claude executes autonomously, recovers from failures, and logs every decision to the thread.

---

## Storage

Threads are stored as a local JSON file at `~/.tylor/threads.json`.

**No database. No AWS. No cloud account required.**

A year of heavy daily use (50 threads, 10,000 messages) fits comfortably under 10 MB.

---

## Architecture

```
Claude Code (terminal)
  └── Tylor MCP server (Python · FastMCP · stdio)
        ├── Thread tools:  new_thread, switch_thread, kill_thread, recall_memory
        ├── Agent tools:   spawn_agent, list_personas
        ├── Executor:      sandboxed bash + AFK autonomous execution
        └── UI server:     aiohttp at localhost:8765

Storage: ~/.tylor/threads.json (local JSON, zero config)

Hooks (Claude Code lifecycle)
  ├── SessionStart  → injects active thread context (zero re-priming)
  ├── Stop          → checkpoints thread state
  └── PostToolUse   → silent code indexing on file reads/writes
```

---

## Roadmap

- [ ] Claude Agent SDK migration (June 2026)
- [ ] ECC skill implementations (web scrape, diagrams, pipelines)
- [ ] Community skill registry
- [ ] Multi-machine sync (optional DynamoDB for power users)

---

## License

MIT

---

*Built with Claude Code. Named after the tailor who works with threads.*
