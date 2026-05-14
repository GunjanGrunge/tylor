"""
server/tools/harness.py — Agent SDK orchestration harness.

5 roles. Claude brings all domain knowledge. No pre-built domain agents.
Cricket coach, legal review, architecture — all Claude, right lens, right tools.
Persistent session memory per thread. Interactive with human-in-the-loop.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

from server.tools._mcp import mcp

# ── 5 roles (lenses, not knowledge bases) ────────────────────────────────────

ROLES = {
    "researcher": {
        "tools": ["WebFetch", "WebSearch", "Read", "Glob", "AskUserQuestion"],
        "lens": (
            "You are in deep research mode. Gather information thoroughly. "
            "Surface options with clear tradeoffs. Ask one focused question at a time. "
            "Never guess — if you need to know something, ask."
        ),
    },
    "implementer": {
        "tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"],
        "lens": (
            "You are in implementation mode. Always read the existing code before changing anything. "
            "Write clean, working code. When prototyping during planning: 50 lines max that proves "
            "the concept. When building for real: production quality. "
            "If you spot issues in adjacent areas (e.g. you're fixing backend but see a frontend bug), "
            "flag them proactively."
        ),
    },
    "reviewer": {
        "tools": ["Read", "Glob", "Grep", "AskUserQuestion"],
        "lens": (
            "You are in review mode. Read everything relevant before giving feedback. "
            "Be specific and actionable — no vague 'improve this'. "
            "Surface risks, gaps, and improvements the user hasn't thought of. "
            "If you spot compliance or legal issues, flag them explicitly."
        ),
    },
    "planner": {
        "tools": ["Read", "Write", "Glob", "AskUserQuestion"],
        "lens": (
            "You are in planning mode. Structure the work clearly. "
            "Ask exactly what you need to know before planning — not after. "
            "Break work into concrete steps. Identify dependencies and risks upfront."
        ),
    },
    "drafter": {
        "tools": ["Read", "Write", "AskUserQuestion"],
        "lens": (
            "You are in drafting mode. Produce polished written output: "
            "specs, docs, policies, PRDs, copy, legal documents. "
            "Ask the minimum necessary questions before drafting. "
            "Ask about: who the audience is, what jurisdiction/context applies, "
            "what decisions are already made. Then produce complete, ready-to-use output."
        ),
    },
}


def _get_bmad_path() -> str | None:
    for p in [
        Path.home() / ".tylor" / "config.json",
    ]:
        if p.exists():
            try:
                cfg = json.loads(p.read_text())
                bmad = cfg.get("bmad_path")
                if bmad and Path(bmad).exists():
                    return bmad
            except Exception:
                pass
    for path in [Path.home() / ".tylor" / "bmad",
                 Path.home() / ".claude" / "plugins" / "bmad"]:
        if path.exists():
            return str(path)
    return None


def _get_all_threads() -> list[dict]:
    """Get all existing threads so Claude knows what's already open."""
    try:
        from server.tools.tylor import _get_db
        db = _get_db()
        threads = db.list_threads()
        return [{"name": t.get("Name", t.get("name", "")),
                 "status": t.get("Status", t.get("status", "")),
                 "id": t.get("thread_id", t.get("id", ""))}
                for t in threads if t.get("Name") or t.get("name")]
    except Exception:
        return []


def build_supervisor_prompt(thread_name: str, cwd: str | None, bmad_path: str | None) -> str:
    context_lines = []
    if thread_name:
        context_lines.append(f"Active thread: {thread_name}")
    if cwd:
        context_lines.append(f"Project: {cwd}")

    # Show all open threads so Claude can reference and suggest new ones
    all_threads = _get_all_threads()
    if all_threads:
        thread_list = ", ".join(
            f"{t['name']} ({t['status']})" for t in all_threads
            if t['name'] != thread_name
        )
        if thread_list:
            context_lines.append(f"Other open threads: {thread_list}")

    if bmad_path:
        context_lines.append(
            f"BMAD methodology available at {bmad_path} — use for structured PRDs, "
            "architecture docs, epics when the task calls for formal structured output."
        )
    context_block = "\n".join(context_lines)

    return f"""You are a proactive supervisor in thread: "{thread_name or 'General'}".
{context_block}

You have access to 5 sub-agent roles via the Agent tool:
- researcher  (WebSearch, WebFetch, Read) — gather info, surface options
- implementer (Read, Write, Edit, Bash)   — build, fix, prototype
- reviewer    (Read, Glob, Grep)          — audit, feedback, risk
- planner     (Read, Write)               — structure, breakdown, roadmap
- drafter     (Read, Write)               — docs, specs, policies, PRDs

YOU provide all domain knowledge. Cricket, legal, medical, finance — you know it all.
Roles are just modes of working, not separate knowledge bases.

## Core behaviours

**Spawn agents when the task has distinct phases or needs focused execution.**
Don't spawn for simple answers — just answer directly.

**Be proactive.** If you notice something the user hasn't asked about:
- Architecture ambiguity → spawn reviewer to map tradeoffs before the user commits
- Implementation unclear → spawn implementer for a quick proof of concept
- Legal/compliance risk → flag it, offer to draft the required document
- Cross-thread issue → "this looks like it affects the frontend too — want me to fix it there?"

**Ask questions before acting, not after.**
Use AskUserQuestion when you need information to proceed correctly.
Ask ONE focused question at a time. Never ask 5 things at once.

**Present decisions as options:**
Format: "Option A: [pros/cons]. Option B: [pros/cons]. I recommend X because Y."
Then ask for the decision.

**Thread memory is your context.**
Reference prior decisions naturally. Never re-ask what's already been answered.

**Cross-thread awareness.**
You can see all open threads. When a conversation spawns work that belongs in a
different thread (e.g. frontend design decisions during a PRD discussion), suggest it:
"This is growing into frontend territory — you may want a Frontend thread for this later."
Never switch threads yourself — just suggest. The user decides.

**Token efficiency.**
Use the minimum context needed. Don't repeat information already in the thread.
Brief sub-agents with only what they need — not the entire conversation history.
"""


def build_agent_registry() -> dict:
    try:
        from claude_agent_sdk import AgentDefinition
    except ImportError:
        return {}

    return {
        name: AgentDefinition(
            description=f"{name}: {role['lens'][:100]}",
            prompt=role["lens"],
            tools=role["tools"],
        )
        for name, role in ROLES.items()
    }


# ── Session persistence ───────────────────────────────────────────────────────

def _sessions_file() -> Path:
    return Path.home() / ".tylor" / "sessions.json"


def _load_session_id(thread_id: str) -> str | None:
    f = _sessions_file()
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text()).get(thread_id)
    except Exception:
        return None


def _save_session_id(thread_id: str, session_id: str) -> None:
    f = _sessions_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if f.exists():
        try:
            data = json.loads(f.read_text())
        except Exception:
            pass
    data[thread_id] = session_id
    f.write_text(json.dumps(data, indent=2))


# ── Core harness ──────────────────────────────────────────────────────────────

async def run_with_agents(
    message: str,
    thread_id: str,
    thread_name: str = "",
    cwd: str | None = None,
) -> AsyncIterator[str]:
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        yield "⚠️  Agent SDK not installed. Run: pip install claude-agent-sdk"
        return

    bmad_path = _get_bmad_path()
    system_prompt = build_supervisor_prompt(thread_name, cwd, bmad_path)
    agent_registry = build_agent_registry()

    session_id = _load_session_id(thread_id)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=[
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
            "WebFetch", "WebSearch", "AskUserQuestion", "Agent",
        ],
        agents=agent_registry,
        resume=session_id,
        cwd=cwd,
    )

    new_session_id: str | None = None
    try:
        async for msg in query(prompt=message, options=options):
            # Capture session ID from ResultMessage (end of run)
            sid = getattr(msg, "session_id", None)
            if sid:
                new_session_id = sid

            # Stream text content from AssistantMessage
            # content is List[TextBlock | ToolUseBlock | ...] or str
            content = getattr(msg, "content", None) or getattr(msg, "text", None)
            if isinstance(content, str) and content:
                yield content
            elif isinstance(content, list):
                for block in content:
                    text = getattr(block, "text", None)
                    if isinstance(text, str) and text:
                        yield text

    except Exception as exc:
        yield f"\n⚠️  Error: {exc}"

    if new_session_id:
        _save_session_id(thread_id, new_session_id)


# ── MCP tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def run_in_thread(thread_id: str, message: str, cwd: str | None = None) -> str:
    """
    Run a task in a thread using the agent harness.

    Claude uses its own knowledge for any domain. The harness provides
    5 roles (researcher, implementer, reviewer, planner, drafter) and
    Claude picks the right one(s) based on the task.

    Persistent memory: each thread has its own session — full conversation
    history preserved across sessions. Agents are interactive and ask
    focused questions when they need information to proceed.

    Args:
        thread_id: Active thread ID.
        message: What you want done.
        cwd: Project directory (optional, defaults to current).
    """
    thread_name = ""
    try:
        from server.tools.tylor import _get_db
        meta = _get_db().get_thread_meta(thread_id)
        thread_name = (meta or {}).get("Name", "")
    except Exception:
        pass

    chunks: list[str] = []
    async for chunk in run_with_agents(message, thread_id, thread_name, cwd):
        chunks.append(chunk)
    return "".join(chunks) or "(no output)"


@mcp.tool()
def list_available_roles() -> dict:
    """
    Show the 5 roles the supervisor can assign to sub-agents.
    Claude picks the right role(s) — you never need to specify.
    """
    return {
        "roles": {name: role["lens"][:120] for name, role in ROLES.items()},
        "how_it_works": (
            "Roles are lenses. Claude brings all domain knowledge. "
            "No pre-built agents for cricket, legal, medical, etc. needed. "
            "Claude IS the expert. Roles just focus it: research vs implement vs review."
        ),
        "memory": (
            "Each thread has a persistent Agent SDK session. "
            "Full conversation history saved automatically. "
            "SwThread resumes the session — zero re-priming."
        ),
        "bmad": f"BMAD available: {_get_bmad_path() is not None}",
    }
