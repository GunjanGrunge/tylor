# Tylor — the tailor to your threads

> A Claude Code plugin that eliminates session death.

Tylor gives Claude persistent, isolated named context scopes called **threads** — so every session picks up exactly where you left off, across multiple projects, with zero re-priming.

```
CT Backend API        → new thread, clean slate
SwThread Backend      → instant context switch, no re-explanation
/open-threads-ui      → live neural network dashboard of all your work
```

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

**Requirements:** [Claude Code](https://claude.ai/code) · Python 3.8+

### Step 1 — Clone the plugin

```bash
git clone https://github.com/GunjanGrunge/tylor ~/.claude/plugins/GunjanGrunge/tylor
```

Claude Code automatically discovers plugins placed in `~/.claude/plugins/`. No marketplace registration needed.

On first use, it creates a Python virtual environment at `~/.tylor/venv` and installs dependencies. This takes about 30 seconds and only happens once.

### Step 2 — Restart Claude Code

Quit and reopen Claude Code to load the new MCP server.

### Step 3 — Verify

Open any project and run:

```
/help-agent101
```

You should see the full command listing. If you see it — Tylor is running.

---

## Troubleshooting

### `/help-agent101` not found after restart

The MCP server may not have started. Check:

1. Restart Claude Code completely (quit, reopen)
2. Confirm the plugin was cloned: `ls ~/.claude/plugins/GunjanGrunge/tylor`
3. Check the MCP server is listed: go to Claude Code settings → MCP servers → confirm `agent101` appears
4. If missing, re-clone: `git clone https://github.com/GunjanGrunge/tylor ~/.claude/plugins/GunjanGrunge/tylor`

### Python not found / server fails to start

Tylor requires Python 3.8+. Verify:

```bash
python3 --version
```

If Python is missing, install it from [python.org](https://python.org) and restart your terminal before reopening Claude Code.

### First session takes longer than expected

Normal — the first run installs Python dependencies into `~/.tylor/venv`. Subsequent starts are instant.

---

## Quick start

Once installed, open any project in Claude Code:

```
# Create your first thread
CT My Project

# Create domain-specific threads for a real project
CT Backend API
CT Frontend UI
CT PRD Planning

# Switch between threads instantly — no re-priming
SwThread Backend
SwThread Frontend

# List all threads with status
/list-threads

# Open the live visual dashboard
/open-threads-ui
```

---

## Thread Visualizer

Open `http://localhost:8765` in your browser for a live neural network graph showing all your threads across projects.

- **Click any thread node** → opens message history panel
- **Click a project hub** → focuses that project's cluster
- Threads update live as you work
- Drag nodes to rearrange

To start the visualizer without a full Claude Code session:

```bash
# From the plugin directory
python3 server/main.py --ui-only
```

---

## Core commands

### Thread lifecycle

| Command | What it does |
|---|---|
| `CT [name]` or `/new-thread` | Create a new named thread |
| `SwThread [name]` | Switch to a thread — supports fuzzy name matching |
| `/list-threads` | List all threads with status and message count |
| `KillThread [name]` or `/kill-thread` | Archive a thread with an AI-generated summary |
| `/recall [query]` | Semantic search across thread memory |

### Code indexing (automatic)

Every time Claude reads or writes a file, Tylor silently indexes key symbols:

```
SignIn: src/components/auth/SignIn.tsx:89 — component
useAuth: src/hooks/auth.ts:12 — hook
```

On the next session, Claude navigates directly to the right file — no codebase scanning.

### Agent personas

Spawn a specialist inside the active thread:

```
spawn_agent(persona="cto", thread_id=..., task="Design the database schema")
```

| Persona | Specialisation |
|---|---|
| `ceo` | Strategy, prioritisation, stakeholder communication |
| `cto` | Architecture, technical decisions, system design |
| `analyst` | Research, data analysis, market insights |
| `code_agent` | Implementation, debugging, code review |

### AFK autonomous execution

Let Claude work while you're away:

```
/set-sandbox ~/my-project
start_afk(task="Refactor the auth module and make the tests pass")
```

Claude executes inside the declared sandbox, recovers from failures automatically, and logs every decision to the active thread. Check progress anytime:

```
/afk-status
```

---

## Storage modes

### Project mode (default — zero setup)

Threads are stored locally at `~/.tylor/threads.json`. No cloud account needed. Works immediately after install. Best for single machines and getting started.

### Personal mode (multi-machine with AWS)

Threads stored in AWS DynamoDB — persist across machines and projects. Enables semantic memory search via OpenSearch.

**Setup:**

1. Copy the credentials template from the plugin directory:
   ```bash
   cp ~/.claude/plugins/cache/GunjanGrunge/tylor/*/server/.env.example \
      ~/.claude/plugins/cache/GunjanGrunge/tylor/*/server/.env
   ```

2. Edit `server/.env`:
   ```
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your_key
   AWS_SECRET_ACCESS_KEY=your_secret
   DYNAMO_TABLE=agent101
   ```

3. Restart Claude Code.

---

## Architecture

```
Claude Code (terminal)
  └── Tylor MCP server (Python · FastMCP · stdio)
        ├── Thread tools:  new_thread, switch_thread, kill_thread, recall_memory
        ├── Agent tools:   spawn_agent, list_personas
        ├── Skill tools:   load_skill_tools, list_registry, add_skill
        ├── Executor:      sandboxed bash + AFK autonomous execution
        └── UI server:     aiohttp at localhost:8765

Storage
  ├── Project mode:  ~/.tylor/threads.json  (default, zero config)
  └── Personal mode: DynamoDB + S3 + OpenSearch (AWS)

Hooks (Claude Code lifecycle)
  ├── SessionStart  → injects active thread context (zero re-priming)
  ├── Stop          → checkpoints thread state on every turn
  └── PostToolUse   → code index on file reads/writes + kill-thread summarization
```

---

## Roadmap

- [ ] Claude Agent SDK migration (June 2026)
- [ ] Multi-user thread isolation
- [ ] Community skill registry
- [ ] VSCode extension

---

## License

MIT

---

*Built with Claude Code. Named after the tailor who works with threads.*
