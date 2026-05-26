<div align="center">
  <img src="assets/tylor_logo.png" alt="Tylor Logo" width="150">
  <h1>Tylor</h1>
  <p><strong>The Tailor to Your Threads</strong></p>
  <p><em>Give Claude Code persistent memory, laser-focused context, and an autonomous team of specialists.</em></p>
  
  [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
  [![Platform: Windows | macOS | Linux | WSL](https://img.shields.io/badge/Platform-Cross--Platform-success)](#)
  [![Claude Code](https://img.shields.io/badge/Integration-Claude_Code-orange)](#)
  [![GitHub Copilot](https://img.shields.io/badge/Integration-GitHub_Copilot-blue)](#)
  [![Codex](https://img.shields.io/badge/Integration-Codex-black)](#)
  [![Antigravity](https://img.shields.io/badge/Integration-Antigravity-blueviolet)](#)
</div>

---

Tylor transforms your Claude Code experience from a single-shot terminal interaction into a **persistent, intelligent workspace**. 

Every time you open Claude Code, you normally start from zero. Tylor fixes that. It organizes your work into **threads**—isolated, named workspaces that survive restarts and reboots. It remembers every decision, every line of code, and every discussion, so you never have to repeat yourself.

**No database. No cloud account. No configuration. Just install and go.**

---

## 🎨 How It Works

<div align="center">
  <img src="assets/tylor_threads_concept.png" alt="Tylor Threads Architecture" width="800">
  <p><em>Tylor weaves parallel, persistent memory threads and orchestrates specialist sub-agents.</em></p>
</div>

---

## ✨ Features

### 🧠 Persistent Memory
Tylor completely eliminates the "context reset." Shut down your computer, close your terminal, and come back a week later—Claude will pick up exactly where you left off. 

### 🗂️ Context Isolation (Threads)
Work in parallel without context bleed. Discuss frontend components in a `Frontend` thread and database schemas in a `Backend` thread. By isolating context, token usage stays low, and Claude's focus stays incredibly sharp.

### 🤖 Intelligent Orchestration 
You don't need to micromanage. Claude acts as the orchestrator. If you ask it to review architecture, it will dynamically load its `cto` persona. If you ask it to write a PRD, it natively invokes the `bmad` skill framework to get the job done. 

### 🔌 Infinite Extensibility (Lazy-Loading)
Tylor is built on a production-hardened ADK-pattern harness. You can register hundreds of domain-specific ECC skills (like `ecc/web`, `ecc/data`) via the `/add-skill` command. Tylor **lazy-loads** only the tools required for the current prompt, giving you massive capability scaling without ever blowing up Claude's token context window.

### 🏗️ Autonomous AFK Sandboxing
Declare a sandbox for your thread and let Claude work autonomously. Assign large, complex tasks and let Claude execute them while you step away from the keyboard.

### 📊 Visual Dashboard
Monitor your entire workspace through a beautiful, locally hosted web UI. Track active threads, review past conversations, and watch autonomous agent progress in real-time.

---

## 🚀 Installation

Tylor installs seamlessly into your Claude Code, Claude Desktop, Codex, GitHub Copilot, Antigravity, or VSCode Claude extension environment. Requires Python 3.8+.

### ⚡ Option 1: The One-Line Installer (Recommended)

If you have Node.js installed, you can configure Tylor instantly across all your clients without manually cloning the repository. Simply run:

```bash
npx tylor-mcp
```

### 💻 Option 2: Manual Git Clone

**macOS / Linux / WSL:**
```bash
git clone https://github.com/GunjanGrunge/tylor ~/.claude/plugins/GunjanGrunge/tylor
python3 ~/.claude/plugins/GunjanGrunge/tylor/install.py
```

**Windows:**
```powershell
git clone https://github.com/GunjanGrunge/tylor %USERPROFILE%\.claude\plugins\GunjanGrunge\tylor
python %USERPROFILE%\.claude\plugins\GunjanGrunge\tylor\install.py
```

### Step 3: Verify

1. Restart your Claude, Codex, GitHub Copilot, or Antigravity client completely (close the terminal/app and reopen it).
2. Type `/help-agent101` in your prompt (or use Copilot Chat / `/mcp show`).
3. If you see the capability index, Tylor is fully operational!

---

## 🕹️ Quick Start

Creating your first persistent workflow is incredibly simple:

```text
/new-thread Authentication   ← Create a persistent workspace
/run we need to implement JWT based authentication

/new-thread Dashboard UI     ← Create an isolated UI thread
/run build a react dashboard with a sidebar

/switch-thread Authentication ← Instantly switch context back to Auth
/run add refresh token logic

/list-threads                ← View your workspace status
/open-threads-ui             ← Launch the visual dashboard
```

---

## 🛠️ Command Reference

Tylor exposes a suite of powerful commands directly within Claude:

| Command | Description |
|---|---|
| `/new-thread <name>` | Create a named thread and seamlessly switch future work into it. |
| `/switch-thread <name>` | Switch context to an existing thread (fuzzy matching supported). |
| `/list-threads` | Show all available threads alongside their status and activity. |
| `/kill-thread <name>` | Close a thread and dispatch asynchronous summarization. |
| `/recall` | Search through the deep semantic memory of your active thread. |
| `/add-skill` | Install a new skill package dynamically. |
| `/open-threads-ui` | Open the live, local thread visualizer UI in your browser. |
| `/set-sandbox <path>` | Declare specific filesystem roots for secure, autonomous execution. |
| `/afk-status` | Get real-time progress reports on current autonomous background tasks. |

> **Pro Tip:** You can also use shorthand aliases like `CT <name>` to create a thread or `SwThread <name>` to switch.

---

## 🔒 Bumblebee Security Gate

Tylor now includes a default, plugin-wide security gate powered by Bumblebee. When a risky command is detected—especially package installs, extension installs, skill/package additions, or MCP config changes—Tylor will initiate a read-only Bumblebee scan before the command runs.

- Enabled by default for any command pattern that looks like `pip install`, `npm install`, editor/extension installs, or skill/config setup.
- If Bumblebee is missing, Tylor will flag the command and surface clear guidance instead of executing it blindly.
- If Bumblebee detects risk, execution is blocked and the user sees actionable alternatives.

Suggested responses from the gate include:

- Install Bumblebee or set `BUMBLEBEE_PATH` if the CLI is not found.
- Run `bumblebee scan --json` manually before retrying.
- Disable the gate temporarily with `BUMBLEBEE_ENABLED=false` only if you understand the risk.
- Review package metadata, MCP config changes, and AI tool integrations before proceeding.

This layer applies across the plugin, regardless of which thread or persona is active.

---

## 🎭 Sub-Agents & Personas

Tylor comes pre-equipped with specialist sub-agents. The harness will **automatically invoke** these personas based on the nature of your query—no manual intervention required.

* **`cto`**: System architecture, tradeoffs, platform strategy, and engineering standards.
* **`code_agent`**: Senior software engineer laser-focused on shipping robust code and tests.
* **`analyst`**: Market research, data synthesis, and technical decision support.
* **`ceo`**: Product strategy, roadmap prioritization, and stakeholder framing.

### Codex users

The installer patches `~/.codex/config.toml` with an `agent101` stdio MCP server entry. Tylor installs its Python dependencies, including `claude-agent-sdk`, into `~/.tylor/venv`; Codex acts as the MCP client, while Tylor's internal orchestration harness uses the Agent SDK runtime to spawn role agents.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

<div align="center">
  <p><em>Tylor — Tailoring the future of AI development.</em></p>
</div>
