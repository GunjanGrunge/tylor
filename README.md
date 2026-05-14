# Tylor — the tailor to your threads

> Claude Code plugin that gives Claude persistent memory, focused context, and a team of specialists — so every session picks up exactly where you left off.

**No database. No cloud account. No configuration. Just install and go.**

> Tylor runs inside Claude Code using Claude itself — no separate AI, no extra API keys needed for core features.

---

## What it does

Every time you open Claude Code, you start from zero. Tylor fixes that.

You work in **threads** — named, persistent conversations that survive restarts, machine reboots, and version updates. Each thread remembers everything: what was built, what was decided, what files were touched. You never re-explain yourself.

When you work inside a thread, Tylor quietly brings in the right help. Discussing a product idea? Claude structures the thinking and drafts the document. Writing code? Claude reads the codebase first, then acts. Need a privacy policy? Claude asks the two questions it actually needs, then writes it — no hallucination, no guessing.

Multiple threads run in parallel. Switch between them instantly. See them all live in the visual dashboard.

---

## What you can do

### Work in threads

```
CT Backend API          → start a new thread for backend work
CT Frontend UI          → separate thread for frontend
CT Product Planning     → planning thread with full product memory
SwThread Backend        → switch back to backend instantly
/list-threads           → see all threads and their status
```

Every thread remembers your full conversation history. When you come back tomorrow, Claude picks up exactly where you left off — no "let me remind you what we were doing."

### Run tasks with a team

```
/run check if the frontend is polished
/run design a cricket coaching app — ask me what you need
/run add a privacy policy to the signup flow
/run we need real-time collaboration — what are my options?
```

Claude figures out what the task needs and handles it. If it needs to research options, it researches. If it needs to read your codebase first, it reads. If it needs to ask you a question before acting, it asks one focused question — not five.

When a task touches multiple areas, Claude coordinates internally. You get a single coherent answer.

### Interactive agents that ask before they act

Claude doesn't guess. When it needs information to do the job right, it asks:

```
❓ What data does your app collect?
❓ Which jurisdictions apply — GDPR, CCPA, or both?
```

You answer, it acts. No hallucinated policies. No invented cricket rules.

### Cross-thread awareness

Claude sees all your open threads. When a conversation starts going somewhere that deserves its own space, it suggests it naturally:

```
"This is growing into frontend territory — 
 you might want a Frontend thread for this work."
```

You decide. Claude never switches threads for you.

### See everything live

```
/open-threads-ui
```

Opens `http://localhost:8765` — a live visual dashboard showing all your threads across projects. See what's active, what's idle, what's archived. Click any thread to read its full history.

### AFK execution

```
/set-sandbox ~/my-project
/run fix all failing tests and make a PR summary
```

Claude works autonomously in your declared project folder. It recovers from errors automatically and logs every decision. Check status anytime with `/afk-status`.

---

## Installation

**Requirements:** Python 3.8+ · Claude Code, Claude Desktop, or VSCode with Claude extension

Works on **macOS, Windows, Linux, and WSL**.

### Step 1 — Clone

```bash
git clone https://github.com/GunjanGrunge/tylor ~/.claude/plugins/GunjanGrunge/tylor
```

### Step 2 — Install

```bash
python3 ~/.claude/plugins/GunjanGrunge/tylor/install.py
```

**Windows:**
```
python %USERPROFILE%\.claude\plugins\GunjanGrunge\tylor\install.py
```

The installer:
- Sets up a Python environment automatically
- Registers Tylor with Claude Code CLI, Claude Desktop, and VSCode — all at once
- No AWS account, no API keys, no configuration needed

### Step 3 — Restart your Claude client

Quit and reopen Claude Code, Claude Desktop, or VSCode.

### Step 4 — Verify

```
/help-agent101
```

If you see the command listing, Tylor is running.

---

## Quick start

```
# Open any project in Claude Code

CT My First Project          ← create your first thread

/run what is in this codebase?    ← Claude reads and summarises

CT Backend                   ← create a backend thread
/run fix the authentication bug

CT Frontend                  ← separate frontend thread
/run the signup form needs improvement

SwThread Backend             ← switch back, full context intact
/run add JWT refresh tokens

/list-threads                ← see all threads
/open-threads-ui             ← open the visual dashboard
```

---

## How threads work

A thread is a persistent, named workspace. Everything you discuss in a thread stays there — decisions, code written, files read, questions answered.

When you switch threads, you switch context. The backend thread doesn't know what the frontend thread discussed. This is intentional — it keeps focus sharp and token usage low.

When you come back to a thread tomorrow, Claude has full memory of it. No re-priming. No "as I mentioned before." Just work.

**Thread status:**
- `active` — currently in use
- `idle` — paused, full memory preserved
- `killed` — archived with an AI-generated summary

---

## Commands

### Thread management

| Command | What it does |
|---|---|
| `CT [name]` or `/new-thread` | Create a new named thread |
| `SwThread [name]` | Switch to a thread — fuzzy matching works |
| `/list-threads` | All threads with status |
| `KillThread [name]` or `/kill-thread` | Archive with summary |
| `/recall [query]` | Search memory across a thread |

### Running tasks

| Command | What it does |
|---|---|
| `/run [task]` | Run any task — Claude handles the rest |
| `/list-available-roles` | See what capabilities are available |

### Autonomous execution

| Command | What it does |
|---|---|
| `/set-sandbox [path]` | Declare the folder Claude can work in |
| `start_afk(task="...")` | Hand off a task, walk away |
| `/afk-status` | Check what's running |

### Visualizer

| Command | What it does |
|---|---|
| `/open-threads-ui` | Open live dashboard at localhost:8765 |

---

## Storage

Everything is stored locally at `~/.tylor/threads.json`.

No database. No cloud. No AWS. A year of heavy daily use fits under 10 MB.

---

## Troubleshooting

**`/help-agent101` not found after restart**
1. Re-run: `python3 ~/.claude/plugins/GunjanGrunge/tylor/install.py`
2. Restart your Claude client completely

**Python not found**
Install Python 3.8+ from [python.org](https://python.org)

**First session is slow**
Normal — first run installs dependencies. Takes ~30 seconds once.

---

## Roadmap

- [ ] Claude Agent SDK migration complete (June 2026)
- [ ] Community skill registry
- [ ] Multi-machine sync (optional)

---

## License

MIT

---

*Named after the tailor who works with threads.*
