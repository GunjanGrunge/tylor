# Tylor — the tailor to your threads

> Claude Code plugin that gives Claude persistent memory, focused context, and a team of specialists — so every session picks up exactly where you left off.

**No database. No cloud account. No configuration. Just install and go.**

---

## What it does

Every time you open Claude Code, you start from zero. Tylor fixes that.

You work in **threads** — named, persistent workspaces that survive restarts and reboots. Each thread remembers everything: what was built, what was decided, what was discussed. You never re-explain yourself.

When you work inside a thread, Tylor quietly brings in the right help. Discussing a product idea? The right thinking mode activates and structures the work. Writing code? The codebase gets read first, then acted on. Need a privacy policy? Two questions get asked, then a complete policy gets written — no hallucination, no guessing.

Multiple threads run in parallel. Switch between them instantly. See them all live in the visual dashboard.

---

## Installation

**Requirements:** Python 3.8+ · Claude Code, Claude Desktop, or VSCode with Claude extension

Works on **macOS, Windows, Linux, and WSL**.

### Step 1 — Clone

```bash
git clone https://github.com/GunjanGrunge/tylor ~/.claude/plugins/GunjanGrunge/tylor
```

**Windows:**
```
git clone https://github.com/GunjanGrunge/tylor %USERPROFILE%\.claude\plugins\GunjanGrunge\tylor
```

### Step 2 — Install

```bash
python3 ~/.claude/plugins/GunjanGrunge/tylor/install.py
```

**Windows:**
```
python %USERPROFILE%\.claude\plugins\GunjanGrunge\tylor\install.py
```

The installer sets up everything automatically — no AWS account, no API keys, no manual configuration needed.

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
CT My First Project          ← create your first thread

/run what is in this codebase?   ← Claude reads and summarises

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

## Commands

### Thread management

| Command | What it does |
|---|---|
| `CT [name]` | Create a new named thread |
| `/new-thread [name]` | Same as CT |
| `SwThread [name]` | Switch to a thread — fuzzy matching works, exact name not required |
| `/switch-thread [name]` | Same as SwThread |
| `/list-threads` | Show all threads with status |
| `KillThread [name]` | Archive a thread with an AI-generated summary |
| `/kill-thread [name]` | Same as KillThread |
| `/recall [query]` | Search memory within the active thread |

### Running tasks

| Command | What it does |
|---|---|
| `/run [task]` | Run any task — Claude handles the rest |
| `/list-available-roles` | Show what specialist modes are available |

### Autonomous execution

| Command | What it does |
|---|---|
| `/set-sandbox [path]` | Declare the folder Claude can work in autonomously |
| `/afk-status` | Check what autonomous tasks are running |

### Visualizer

| Command | What it does |
|---|---|
| `/open-threads-ui` | Open live dashboard at localhost:8765 |

---

## How threads work

A thread is a persistent, named workspace. Everything you discuss in a thread stays there — decisions, code written, files read, questions answered.

When you switch threads, you switch context. The backend thread doesn't know what the frontend thread discussed. This keeps focus sharp and token usage low.

When you come back to a thread tomorrow, Claude has full memory of it. No re-priming. No "as I mentioned before." Just work.

**Thread status:**
- `active` — currently in use
- `idle` — paused, full memory preserved
- `killed` — archived with an AI-generated summary

---

## Running tasks with `/run`

`/run` is the main way to delegate work to Claude. You describe what you need, and Claude figures out the best approach.

```
/run check if the frontend is polished
/run design a cricket coaching app — ask me what you need
/run add a privacy policy to the signup flow
/run we need real-time collaboration — what are my options?
/run create a PRD for the new onboarding flow
/run review this code for security issues
```

Claude doesn't guess. When it needs information to do the job right, it asks one focused question at a time:

```
❓ What data does your app collect?
❓ Which jurisdictions apply — GDPR, CCPA, or both?
```

You answer, it acts.

---

## Working with multiple threads

Tylor is designed for parallel work across multiple threads:

```
CT Backend API
CT Frontend UI
CT Product Planning
CT Legal Review

SwThread Backend     ← focus on backend
/run implement the search endpoint

SwThread Frontend    ← switch to frontend
/run the search results page needs a loading state

SwThread Legal       ← switch to legal
/run draft a GDPR-compliant privacy policy

/list-threads        ← see all four threads, all their context preserved
```

---

## Cross-thread awareness

Claude sees all your open threads. When a conversation starts going somewhere that deserves its own space, it suggests it:

```
"This is growing into frontend territory — 
 you might want a Frontend thread for this work."
```

You decide. Claude never switches threads for you.

---

## Visual dashboard

```
/open-threads-ui
```

Opens `http://localhost:8765` — a live visual dashboard showing all your threads. See what's active, what's idle, what's archived. Click any thread to read its full conversation history and summary.

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

**Port 8765 already in use**
Tylor will automatically try ports 8766–8774. The dashboard link in `/open-threads-ui` will reflect the actual port.

**Thread context feels stale**
Use `/recall [topic]` to surface relevant prior decisions from the thread.

---

## License

MIT — see [LICENSE](LICENSE)

---

*Named after the tailor who works with threads.*
