<div align="center">
  <h1>👔 Tylor</h1>
  <p><strong>The Tailor to Your Threads</strong></p>
  <p><em>Give Claude Code persistent memory, laser-focused context, and an autonomous team of specialists.</em></p>
  
  [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
  [![Platform: Windows | macOS | Linux | WSL](https://img.shields.io/badge/Platform-Cross--Platform-success)](#)
  [![Claude Code](https://img.shields.io/badge/Integration-Claude_Code-orange)](#)
</div>

---

Tylor transforms your Claude Code experience from a single-shot terminal interaction into a **persistent, intelligent workspace**. 

Every time you open Claude Code, you normally start from zero. Tylor fixes that. It organizes your work into **threads**—isolated, named workspaces that survive restarts and reboots. It remembers every decision, every line of code, and every discussion, so you never have to repeat yourself.

**No database. No cloud account. No configuration. Just install and go.**

---

## ✨ Features

### 🧠 Persistent Memory
Tylor completely eliminates the "context reset." Shut down your computer, close your terminal, and come back a week later—Claude will pick up exactly where you left off. 

### 🗂️ Context Isolation (Threads)
Work in parallel without context bleed. Discuss frontend components in a `Frontend` thread and database schemas in a `Backend` thread. By isolating context, token usage stays low, and Claude's focus stays incredibly sharp.

### 🤖 Intelligent Orchestration 
You don't need to micromanage. Claude acts as the orchestrator. If you ask it to review architecture, it will dynamically load its `cto` persona. If you ask it to write a PRD, it natively invokes the `bmad` skill framework to get the job done. 

### 🏗️ Autonomous AFK Sandboxing
Declare a sandbox for your thread and let Claude work autonomously. Assign large, complex tasks and let Claude execute them while you step away from the keyboard.

### 📊 Visual Dashboard
Monitor your entire workspace through a beautiful, locally hosted web UI. Track active threads, review past conversations, and watch autonomous agent progress in real-time.

---

## 🚀 Installation

Tylor installs seamlessly into your Claude Code, Claude Desktop, or VSCode Claude extension environment. Requires Python 3.8+.

### Step 1: Clone the Repository

**macOS / Linux / WSL:**
```bash
git clone https://github.com/GunjanGrunge/tylor ~/.claude/plugins/GunjanGrunge/tylor
```

**Windows:**
```powershell
git clone https://github.com/GunjanGrunge/tylor %USERPROFILE%\.claude\plugins\GunjanGrunge\tylor
```

### Step 2: Run the Installer

The installer automatically patches your Claude settings, sets up the Python environment, and configures the MCP server.

**macOS / Linux / WSL:**
```bash
python3 ~/.claude/plugins/GunjanGrunge/tylor/install.py
```

**Windows:**
```powershell
python %USERPROFILE%\.claude\plugins\GunjanGrunge\tylor\install.py
```

### Step 3: Verify

1. Restart your Claude client completely (close the terminal/app and reopen it).
2. Type `/help-agent101` in your Claude prompt.
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

## 🎭 Sub-Agents & Personas

Tylor comes pre-equipped with specialist sub-agents. Claude will **automatically invoke** these personas based on the nature of your query—no manual intervention required.

* **`cto`**: System architecture, tradeoffs, platform strategy, and engineering standards.
* **`code_agent`**: Senior software engineer laser-focused on shipping robust code and tests.
* **`analyst`**: Market research, data synthesis, and technical decision support.
* **`ceo`**: Product strategy, roadmap prioritization, and stakeholder framing.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

<div align="center">
  <p><em>Tylor — Tailoring the future of AI development.</em></p>
</div>
