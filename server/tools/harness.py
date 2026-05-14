"""
server/tools/harness.py — Agent SDK orchestration harness.

The harness gives Claude a team of ROLES with TOOLS.
Claude brings ALL domain knowledge itself — no cricket agent, no legal agent,
no pre-built persona for every use case needed.

The supervisor Claude reads the task, picks the right role + tools,
and spawns sub-agents with that role framing. Sub-agents are Claude
with a focused lens — not separate knowledge bases.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

from server.tools._mcp import mcp


# ── Roles registry ────────────────────────────────────────────────────────────
# These are LENSES, not knowledge bases. Claude already knows everything.
# A role just focuses Claude on the right mode of thinking + tool access.

ROLES = {
    "researcher": {
        "tools": ["WebFetch", "WebSearch", "Read", "Glob", "AskUserQuestion"],
        "lens": "You are in research mode. Gather information, surface options, present tradeoffs. Ask one focused question at a time.",
    },
    "implementer": {
        "tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"],
        "lens": "You are in implementation mode. Read the codebase first. Write clean, working code. Show the minimal proof of concept that proves the idea.",
    },
    "reviewer": {
        "tools": ["Read", "Glob", "Grep", "AskUserQuestion"],
        "lens": "You are in review mode. Read everything relevant. Give specific, actionable feedback. Identify gaps, risks, and improvements.",
    },
    "planner": {
        "tools": ["Read", "Write", "Glob", "AskUserQuestion"],
        "lens": "You are in planning mode. Structure the work. Break it into clear steps. Ask clarifying questions before planning, not after.",
    },
    "drafter": {
        "tools": ["Read", "Write", "AskUserQuestion"],
        "lens": "You are in drafting mode. Produce well-structured written output — specs, docs, policies, PRDs, copy. Ask what you need to know before drafting.",
    },
}


def _get_bmad_path() -> str | None:
    config_file = Path.home() / ".tylor" / "config.json"
    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text())
            p = cfg.get("bmad_path")
            if p and Path(p).exists():
                return p
        except Exception:
            pass
    for path in [Path.home() / ".tylor" / "bmad",
                 Path.home() / ".claude" / "plugins" / "bmad"]:
        if path.exists():
            return str(path)
    return None


# ── Supervisor prompt ─────────────────────────────────────────────────────────

def build_supervisor_prompt(thread_name: str, cwd: str | None, bmad_path: str | None) -> str:
    bmad_line = (
        f"\nBMAD structured methodology available at {bmad_path} — use it for "
        "PRDs, architecture docs, epics when structured output would help."
        if bmad_path else ""
    )

    return f"""You are a proactive supervisor working in the thread: "{thread_name or 'General'}".
{bmad_line}

You have access to sub-agents via the Agent tool. Each sub-agent is YOU with a focused role.
You do NOT need pre-built agents for specific domains — you already know everything.
A cricket coach asking about an app gets the same Claude that knows cricket AND software.

## When to spawn sub-agents

Spawn when the task genuinely benefits from parallel or sequential focused work:
- Complex task with distinct phases (research → plan → implement → review)
- Task needs both broad thinking AND detailed execution at the same time
- Output quality improves with role separation (drafter + reviewer)

Do NOT spawn for simple tasks — just answer directly.

## How to spawn

Pick a role from: researcher, implementer, reviewer, planner, drafter.
Brief the sub-agent with ALL context it needs — don't make it start cold.
Pass prior decisions, constraints, and relevant thread history.

## Proactive behaviour

If you notice the conversation needs something the user hasn't asked for yet:
- Architecture ambiguity → spawn reviewer to map tradeoffs: "Option A vs B — your call"
- Implementation unclear → spawn implementer for a 50-line proof of concept
- Document needed → spawn drafter to produce it

Present these proactively, briefly. "Here's what the architect found — your call."

## Decision pattern

Present options as: "[Option A]: pros/cons. [Option B]: pros/cons. My recommendation: X because Y."
Then ask ONE question to get the decision.

## Memory

Everything in this thread is your context. Reference prior decisions naturally.
Don't re-ask what's already been answered.
"""


# ── Agent definitions ─────────────────────────────────────────────────────────

def build_agent_registry() -> dict:
    try:
        from claude_agent_sdk import AgentDefinition
    except ImportError:
        return {}

    registry = {}
    for role_name, role in ROLES.items():
        registry[role_name] = AgentDefinition(
            description=f"{role_name.capitalize()} role: {role['lens'][:120]}",
            prompt=role["lens"],
            tools=role["tools"],
        )
    return registry


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
        from claude_agent_sdk import query, ClaudeAgentOptions, PermissionResultAllow
    except ImportError:
        yield "⚠️  Agent SDK not installed. Run: pip install claude-agent-sdk"
        return

    bmad_path = _get_bmad_path()
    system_prompt = build_supervisor_prompt(thread_name, cwd, bmad_path)
    agent_registry = build_agent_registry()

    pending_questions: list[str] = []

    async def can_use_tool(ctx):
        tool = getattr(ctx, "tool_name", "") or getattr(ctx, "toolName", "")
        tool_input = getattr(ctx, "tool_input", {}) or {}
        if tool == "AskUserQuestion":
            for q in tool_input.get("questions", []):
                q_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
                pending_questions.append(q_text)
        return PermissionResultAllow(updated_input=tool_input)

    session_id = _load_session_id(thread_id)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep",
                        "WebFetch", "WebSearch", "AskUserQuestion", "Agent"],
        agents=agent_registry,
        resume=session_id,
        cwd=cwd,
        can_use_tool=can_use_tool,
    )

    new_session_id: str | None = None
    try:
        async for msg in query(prompt=message, options=options):

            if hasattr(msg, "subtype") and msg.subtype == "init":
                sid = getattr(msg, "session_id", None) or (
                    (msg.data or {}).get("session_id") if hasattr(msg, "data") else None
                )
                if sid:
                    new_session_id = sid

            if pending_questions:
                for q in pending_questions:
                    yield f"\n❓ **{q}**\n"
                pending_questions.clear()

            content = getattr(msg, "content", None) or getattr(msg, "text", None)
            if isinstance(content, str) and content:
                yield content

    except Exception as exc:
        yield f"\n⚠️  Error: {exc}"

    if new_session_id:
        _save_session_id(thread_id, new_session_id)


# ── MCP tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def run_in_thread(thread_id: str, message: str, cwd: str | None = None) -> str:
    """
    Run a task in a thread. Claude uses its own knowledge for any domain —
    cricket, legal, medical, architecture, whatever. No pre-built agents needed.
    The harness provides focused roles (researcher, implementer, planner, etc.)
    and Claude picks the right one(s) for the task.

    Args:
        thread_id: Active thread ID.
        message: What you want done.
        cwd: Project directory (optional).
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
    List the roles the supervisor can assign to sub-agents.
    Claude picks roles based on the task — you don't need to specify.
    """
    return {
        "roles": {name: role["lens"] for name, role in ROLES.items()},
        "note": (
            "These are lenses, not knowledge bases. Claude already knows everything. "
            "A role just focuses Claude on the right mode (research vs implement vs review). "
            "No cricket agent needed — Claude knows cricket."
        ),
        "bmad_available": _get_bmad_path() is not None,
    }
