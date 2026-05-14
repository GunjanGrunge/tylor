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
| "Where was that file again?" | **Silent code indexing** — Claude navigates directly to the right file and line |
| Can't see what's running | **Thread Visualizer** at `localhost:8765` — live neural network graph of all threads |
| Need specialists for different tasks | **Personas** — CEO, CTO, Analyst, Code Agent per thread |
| Want Claude to work while you sleep | **AFK mode** — autonomous execution with failure recovery |

---

## Installation

**Requirements:** [Claude Code](https://claude.ai/code) · Python 3.8+

---

### Install via Claude Code (recommended)

In Claude Code, run:

```
/plugins install GunjanGrunge/tylor
```

Claude Code handles everything — downloads the plugin, registers the MCP server, and wires up lifecycle hooks automatically.

On first use, it will create a Python virtual environment at `~/.tylor/venv` and install dependencies. This takes ~30 seconds once.

---

### Verify

After install, restart Claude Code and run:

```
/help-agent101
```

You should see a full listing of commands, skills, and agent personas.

---

### Troubleshooting

**`/help-agent101` not found**
The plugin may not have loaded. Try:
1. Restart Claude Code completely
2. Run `/plugins install GunjanGrunge/tylor` again

**Python not found / server fails to start**
Tylor requires Python 3.8+. Check with:
```bash
python3 --version
```
If Python is not on your PATH, install it from [python.org](https://python.org).

---

## Storage modes

Tylor supports two storage modes selected at install time.

### Project mode (default — zero setup)

```bash
agent101 install --mode project
```

- Threads stored locally at `~/.tylor/threads.json`
- No AWS account needed
- Works immediately after install
- Best for: getting started, single machine

### Personal mode (multi-machine)

```bash
agent101 install --mode personal
```

- Threads stored in AWS DynamoDB — persist across machines and projects
- Enables semantic memory search via OpenSearch
- Requires AWS credentials

**Setup for Personal mode:**

1. Copy the credentials template:
   ```bash
   # Find where Tylor is installed:
   python3 -c "import agent101; print(agent101.__file__)"
   # Copy .env.example from that directory's server/ folder:
   cp /path/to/agent101/server/.env.example /path/to/agent101/server/.env
   ```

2. Edit `server/.env` with your AWS credentials:
   ```
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your_key
   AWS_SECRET_ACCESS_KEY=your_secret
   DYNAMO_TABLE=agent101
   ```

3. Re-run the installer:
   ```bash
   agent101 install --mode personal
   ```

---

## Quick start

Once installed, open any project in Claude Code:

```bash
# Create your first thread for this project
CT My Project

# Create domain-specific threads
CT Backend API
CT Frontend UI
CT PRD Planning

# Switch between threads instantly (no re-priming)
SwThread Backend
SwThread Frontend

# List all threads with status
/list-threads

# Open the live visual dashboard
/open-threads-ui
```

---

## Thread Visualizer

Open `http://localhost:8765` in your browser — a live neural network graph showing all your threads across projects.

```bash
# Start the visualizer standalone (without a Claude Code session)
agent101 run --ui-only
```

- **Click any thread node** to open its message history panel
- **Click a project hub** to focus that project's cluster
- New threads appear live as you create them

---

## Core commands

### Thread lifecycle

| Command | What it does |
|---|---|
| `CT [name]` or `/new-thread` | Create a new named thread |
| `SwThread [name]` | Switch to a thread — fuzzy name matching |
| `/list-threads` | List all threads with status and message count |
| `KillThread [name]` or `/kill-thread` | Archive a thread with an AI-generated summary |
| `/recall [query]` | Semantic search across thread memory |

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
start_afk(task="Refactor the auth module and make tests pass")
```

Claude executes inside the declared sandbox, recovers from failures automatically, and logs every decision to the thread.

---

## Architecture

```
Claude Code (terminal)
  └── Tylor MCP server (FastMCP, stdio transport)
        ├── Thread tools:  new_thread, switch_thread, kill_thread, recall_memory
        ├── Agent tools:   spawn_agent, list_personas
        ├── Skill tools:   load_skill_tools, list_registry, add_skill
        ├── Executor:      sandboxed bash + AFK autonomous execution
        └── UI server:     aiohttp at localhost:8765

Storage
  ├── Project mode:  ~/.tylor/threads.json
  └── Personal mode: DynamoDB + S3 + OpenSearch (AWS)

Hooks (Claude Code lifecycle)
  ├── SessionStart  → injects active thread context, zero re-priming
  ├── Stop          → checkpoints thread state on every turn
  └── PostToolUse   → code index (file reads/writes) + kill-thread summarization
```

---

## Roadmap

- [ ] Claude Agent SDK migration (June 2026)
- [ ] Multi-user thread isolation
- [ ] VSCode extension
- [ ] Community skill registry

---

## License

MIT

---

*Built with Claude Code. Named after the tailor who works with threads.*
