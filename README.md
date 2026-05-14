# Tylor — the tailor to your threads

> A Claude Code plugin that eliminates session death.

Tylor gives Claude persistent, isolated named context scopes called **threads** — so every session picks up exactly where you left off, across multiple projects, with zero re-priming.

```
SwThread Backend      → instant context switch, no re-explanation
CT Gemma Fine-Tuning  → new thread, clean slate
/open-threads-ui      → live neural network dashboard of all your work
```

---

## What it does

| Problem | Tylor's answer |
|---|---|
| Every Claude session forgets you | **Persistent threads** — context survives restarts |
| Switching topics loses context | **`SwThread`** — atomic context switch in <2 seconds |
| "Where was that file again?" | **Silent code indexing** — Claude knows `SignIn: src/auth.tsx:89` without scanning |
| Can't see what's running | **Thread Visualizer** at `localhost:8765` — live graph of all threads |
| Need specialists for different tasks | **Personas** — CEO, CTO, Analyst, Code Agent per thread |
| Want Claude to work while you sleep | **AFK mode** — autonomous execution with failure recovery |

---

## Installation

**Requirements:** macOS or Linux, Python 3.11+, Claude Code

### One-line install

```bash
git clone https://github.com/GunjanGrunge/tylor ~/.claude/plugins/tylor
cd ~/.claude/plugins/tylor && ./install.sh
```

The installer will ask you to choose a storage mode:

| Mode | Setup | Best for |
|---|---|---|
| **Project JSON** (recommended) | Zero config | Getting started, single machine |
| **Personal DynamoDB** | AWS credentials required | Multi-machine, production use |

### After install

Open any project in Claude Code and verify:

```
/help-agent101
```

You should see all available commands, skills, and personas.

---

## Quick start

```bash
# Create your first thread
CT My Project

# Switch between threads
SwThread Backend
SwThread Frontend

# See all threads
/list-threads

# Open the visual dashboard
/open-threads-ui
```

---

## Thread Visualizer

The visualizer runs at `http://localhost:8765` — a live neural network graph showing all your threads across projects.

```bash
# Start the visualizer standalone (no Claude Code session required)
python3 -m server.main --ui-only
```

- **Click any node** to see the thread's message history
- **Click a project** to focus that cluster
- Threads update live as you work

![Tylor Thread Visualizer](ui/tylor-logo.svg)

---

## Core commands

### Thread lifecycle

| Command | What it does |
|---|---|
| `CT [name]` or `/new-thread` | Create a new thread |
| `SwThread [name]` | Switch to a thread (fuzzy name matching) |
| `/list-threads` | List all threads with status |
| `KillThread [name]` or `/kill-thread` | Archive a thread with Bedrock Opus summary |
| `/recall [query]` | Semantic search of thread memory |

### Agent personas

```
spawn_agent(persona="cto", thread_id=..., task="Design the API")
```

Available: `ceo`, `cto`, `analyst`, `code_agent`

### AFK execution

```
/set-sandbox ~/my-project
start_afk(task="Fix all failing tests", steps=[...])
```

---

## Project mode vs Personal mode

**Project mode** (local JSON, zero setup):
- Threads stored at `{project}/.tylor/threads.json`
- Portable — travels with your repo
- No AWS required

**Personal mode** (DynamoDB, multi-machine):
- Threads persist across machines and projects
- Requires AWS credentials in `server/.env` (see `server/.env.example`)
- Enables semantic memory search via OpenSearch

Switch modes after install:
```bash
# Migrate from Project to Personal
agent101 config --migrate
```

---

## Configuration

Copy `server/.env.example` to `server/.env` for Personal mode:

```bash
cp server/.env.example server/.env
# Edit server/.env with your AWS credentials
```

---

## Architecture

```
Claude Code (terminal)
  └── Tylor MCP server (FastMCP, stdio transport)
        ├── Thread tools: new_thread, switch_thread, kill_thread, recall_memory
        ├── Agent tools: spawn_agent, list_personas
        ├── Skill tools: load_skill_tools, list_registry, add_skill
        ├── Executor: sandboxed bash + AFK autonomous execution
        └── UI server: aiohttp at localhost:8765

Storage
  ├── Project mode: {project}/.tylor/threads.json
  └── Personal mode: DynamoDB + S3 + OpenSearch (AWS)

Hooks (Claude Code lifecycle)
  ├── SessionStart → surfaces active thread, zero re-priming
  ├── Stop → checkpoints thread state
  └── PostToolUse → code index + kill-thread summarization
```

---

## Roadmap

- [ ] Agent SDK migration (Claude Agent SDK, June 2026)
- [ ] Multi-user thread isolation
- [ ] VSCode extension
- [ ] Community skill registry

---

## License

MIT

---

*Built with Claude Code. Named after the tailor who works with threads.*
