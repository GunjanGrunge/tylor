"""
server/tools/harness.py — Agent SDK orchestration harness.

Spawn-on-need multi-agent system:
- Detects task intent from the user's message + active thread name
- Spawns the right specialist agent(s) automatically
- BMAD workflows injected silently based on thread context
- User just talks — the harness routes to the right expert
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import AsyncIterator

from mcp.server.fastmcp.exceptions import ToolError
from server.tools._mcp import mcp

# ── Intent detection keywords ─────────────────────────────────────────────────

_INTENT_MAP = {
    "code": {
        "keywords": [
            "implement", "code", "build", "fix", "bug", "error", "debug",
            "refactor", "test", "function", "class", "api", "endpoint",
            "feature", "polished", "review code", "lint", "compile",
        ],
        "agent": "code_agent",
    },
    "architecture": {
        "keywords": [
            "design", "architecture", "system", "database", "schema",
            "structure", "pattern", "scalab", "performance", "infrastructure",
            "deploy", "cloud", "microservice", "api design",
        ],
        "agent": "cto",
    },
    "product": {
        "keywords": [
            "prd", "requirements", "user story", "epic", "feature request",
            "prioriti", "roadmap", "product", "stakeholder", "acceptance",
            "business", "market", "user need",
        ],
        "agent": "ceo",
    },
    "analysis": {
        "keywords": [
            "analys", "research", "data", "metric", "insight", "report",
            "trend", "compare", "evaluate", "assess", "review", "audit",
        ],
        "agent": "analyst",
    },
    "planning": {
        "keywords": [
            "plan", "sprint", "story", "estimate", "breakdown", "task",
            "milestone", "timeline", "scope", "backlog",
        ],
        "agent": "analyst",
    },
}

# Thread name → agent team (spawn these agents for this thread type)
_THREAD_TEAMS = {
    "frontend":    ["code_agent"],
    "backend":     ["code_agent", "cto"],
    "api":         ["code_agent", "cto"],
    "prd":         ["ceo", "analyst"],
    "planning":    ["analyst", "ceo"],
    "architecture":["cto", "analyst"],
    "data":        ["analyst", "code_agent"],
    "research":    ["analyst"],
    "design":      ["ceo"],
    "security":    ["cto", "code_agent"],
    "devops":      ["cto", "code_agent"],
    "marketing":   ["ceo", "analyst"],
}

# Thread name → BMAD workflow to silently activate
_THREAD_BMAD = {
    "prd":         "bmad-create-prd",
    "planning":    "bmad-sprint-planning",
    "architecture":"bmad-create-architecture",
    "research":    "bmad-domain-research",
    "design":      "bmad-create-ux-design",
    "epics":       "bmad-create-epics-and-stories",
}


def detect_intent(message: str, thread_name: str = "") -> list[str]:
    """
    Return list of agent names needed for this message + thread context.
    Spawn-on-need: only the agents that match are returned.
    """
    msg_lower = message.lower()
    thread_lower = thread_name.lower()

    agents_needed: set[str] = set()

    # 1. Check thread name for team defaults
    for keyword, team in _THREAD_TEAMS.items():
        if keyword in thread_lower:
            agents_needed.update(team)
            break

    # 2. Detect from message intent
    for intent_data in _INTENT_MAP.values():
        for kw in intent_data["keywords"]:
            if kw in msg_lower:
                agents_needed.add(intent_data["agent"])
                break

    # 3. Default: code_agent if nothing matched
    if not agents_needed:
        agents_needed.add("code_agent")

    return list(agents_needed)


def detect_bmad_workflow(thread_name: str) -> str | None:
    """Return BMAD workflow skill name if thread name matches, else None."""
    tl = thread_name.lower()
    for keyword, workflow in _THREAD_BMAD.items():
        if keyword in tl:
            return workflow
    return None


# ── Agent definitions ─────────────────────────────────────────────────────────

def _get_agent_definitions() -> dict:
    """Build AgentDefinition objects for all specialist agents."""
    try:
        from claude_agent_sdk import AgentDefinition
    except ImportError:
        return {}

    return {
        "code_agent": AgentDefinition(
            description=(
                "Senior software engineer. Handles implementation, debugging, "
                "code review, refactoring, and testing. Reads files, edits code, "
                "runs commands. Use when: build/fix/implement/test/review."
            ),
            prompt=(
                "You are a senior software engineer. You write clean, tested, "
                "production-grade code. You read the codebase before making changes. "
                "You fix bugs systematically. You explain your changes concisely."
            ),
            tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        ),

        "cto": AgentDefinition(
            description=(
                "Technical architect. Handles system design, architecture decisions, "
                "technology choices, database design, API design, scalability. "
                "Use when: design/architecture/system/infrastructure."
            ),
            prompt=(
                "You are a CTO and technical architect. You think in systems. "
                "You make pragmatic technology choices. You design for scalability "
                "and maintainability. You give clear architectural guidance with tradeoffs."
            ),
            tools=["Read", "Glob", "Grep"],
        ),

        "analyst": AgentDefinition(
            description=(
                "Business analyst and researcher. Handles data analysis, market research, "
                "requirements gathering, metrics, insights, reports. "
                "Use when: analyse/research/data/metrics/requirements."
            ),
            prompt=(
                "You are a sharp business analyst. You turn data into insight. "
                "You gather requirements precisely. You ask the right clarifying questions. "
                "You produce structured, actionable analysis."
            ),
            tools=["Read", "Glob", "Grep", "WebSearch"],
        ),

        "ceo": AgentDefinition(
            description=(
                "Product strategist and CEO. Handles product vision, PRD creation, "
                "prioritisation, user stories, roadmaps, stakeholder communication. "
                "Use when: product/prd/roadmap/strategy/prioritise."
            ),
            prompt=(
                "You are a product-focused CEO. You think about user value first. "
                "You write crisp PRDs. You prioritise ruthlessly. "
                "You communicate clearly to both technical and business audiences."
            ),
            tools=["Read", "Glob"],
        ),
    }


# ── Core harness function ─────────────────────────────────────────────────────

async def run_with_agents(
    message: str,
    thread_id: str,
    thread_name: str = "",
    cwd: str | None = None,
) -> AsyncIterator[str]:
    """
    Run a user message through the agent harness:
    1. Detect which agents are needed
    2. Check for BMAD workflow activation
    3. Run via Agent SDK with the right team
    4. Yield streamed output chunks
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        yield "⚠️  Agent SDK not installed. Run: pip install claude-agent-sdk"
        return

    # Detect intent
    needed_agents = detect_intent(message, thread_name)
    bmad_workflow = detect_bmad_workflow(thread_name)
    agent_defs = _get_agent_definitions()

    # Build the active team
    active_agents = {name: agent_defs[name] for name in needed_agents if name in agent_defs}

    # Build system context
    context_parts = [
        f"Active thread: {thread_name}" if thread_name else "",
        f"Working directory: {cwd}" if cwd else "",
        f"Agents active: {', '.join(needed_agents)}",
    ]
    if bmad_workflow:
        context_parts.append(
            f"BMAD workflow detected: {bmad_workflow} — apply this workflow's methodology silently"
        )
    system_context = "\n".join(p for p in context_parts if p)

    full_prompt = f"{system_context}\n\n{message}" if system_context else message

    # Allowed tools: base set + Agent tool if we have subagents
    allowed_tools = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
    if active_agents:
        allowed_tools.append("Agent")

    # Session = thread (Agent SDK session persists context)
    session_id = _load_session_id(thread_id)

    # ── Human-in-the-loop: intercept AskUserQuestion + approval requests ──────
    # When the agent needs input, it calls AskUserQuestion.
    # We surface the question to the user via the MCP response so Claude Code
    # shows it in the terminal and waits for the user's answer.
    # The answer is then injected back into the next query() call.

    pending_questions: list[dict] = []

    async def can_use_tool(ctx) -> object:
        """Intercept tool calls that need human input or approval."""
        try:
            from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
        except ImportError:
            return None  # no SDK permission types — allow all

        tool = getattr(ctx, "tool_name", "") or getattr(ctx, "toolName", "")
        tool_input = getattr(ctx, "tool_input", {}) or getattr(ctx, "input", {}) or {}

        if tool == "AskUserQuestion":
            # Agent wants to ask the user something — collect and surface
            questions = tool_input.get("questions", [])
            pending_questions.extend(questions)
            # Return a marker — caller will see pending_questions and surface them
            return PermissionResultAllow(updated_input=tool_input)

        if tool in ("Bash", "Write", "Edit"):
            # Always allow — agent can execute autonomously
            return PermissionResultAllow(updated_input=tool_input)

        return PermissionResultAllow(updated_input=tool_input)

    options = ClaudeAgentOptions(
        allowed_tools=allowed_tools,
        agents=active_agents if active_agents else None,
        resume=session_id,
        cwd=cwd,
        can_use_tool=can_use_tool,
    )

    # Stream output
    new_session_id: str | None = None
    try:
        async for msg in query(prompt=full_prompt, options=options):

            # Capture session ID on first message
            if hasattr(msg, "subtype") and msg.subtype == "init":
                if hasattr(msg, "session_id"):
                    new_session_id = msg.session_id
                elif hasattr(msg, "data") and isinstance(msg.data, dict):
                    new_session_id = msg.data.get("session_id")

            # Surface any pending questions to the user
            if pending_questions:
                for q in pending_questions:
                    question_text = q.get("question", str(q))
                    yield f"\n❓ **Agent question:** {question_text}\n"
                pending_questions.clear()

            # Yield text content
            if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
                yield msg.content
            elif hasattr(msg, "text") and msg.text:
                yield msg.text

            # Surface subagent activity
            if hasattr(msg, "parent_tool_use_id") and msg.parent_tool_use_id:
                pass  # subagent message — flows through naturally

    except Exception as exc:
        yield f"\n⚠️  Agent error: {exc}"

    # Persist session ID for next message in this thread
    if new_session_id:
        _save_session_id(thread_id, new_session_id)


# ── Session persistence ───────────────────────────────────────────────────────

def _sessions_file() -> Path:
    return Path.home() / ".tylor" / "sessions.json"


def _load_session_id(thread_id: str) -> str | None:
    import json
    f = _sessions_file()
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text())
        return data.get(thread_id)
    except Exception:
        return None


def _save_session_id(thread_id: str, session_id: str) -> None:
    import json
    f = _sessions_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if f.exists():
        try:
            data = json.loads(f.read_text())
        except Exception:
            data = {}
    data[thread_id] = session_id
    f.write_text(json.dumps(data, indent=2))


# ── MCP tool exposed to Claude Code ──────────────────────────────────────────

@mcp.tool()
async def run_in_thread(thread_id: str, message: str, cwd: str | None = None) -> str:
    """
    Run a message in a thread using the agent harness.
    Automatically spawns the right specialist agents based on:
    - The thread name (e.g. 'Frontend' → code agent)
    - The message content (e.g. 'fix the bug' → code agent)
    - BMAD workflows activated silently by thread context

    Args:
        thread_id: The active thread ID.
        message: What you want the agent team to do.
        cwd: Optional working directory (defaults to current project).
    """
    # Get thread name from storage
    thread_name = ""
    try:
        from server.tools.tylor import _get_db
        db = _get_db()
        meta = db.get_thread_meta(thread_id)
        thread_name = meta.get("Name", "") if meta else ""
    except Exception:
        pass

    chunks: list[str] = []
    async for chunk in run_with_agents(message, thread_id, thread_name, cwd):
        chunks.append(chunk)

    return "".join(chunks) or "(no output)"


@mcp.tool()
def detect_thread_team(thread_id: str, message: str = "") -> dict:
    """
    Preview which agents would be activated for a thread + message.
    Useful for understanding what team is working on a task.

    Args:
        thread_id: The thread to check.
        message: Optional message to test intent detection.
    """
    thread_name = ""
    try:
        from server.tools.tylor import _get_db
        db = _get_db()
        meta = db.get_thread_meta(thread_id)
        thread_name = meta.get("Name", "") if meta else ""
    except Exception:
        pass

    agents = detect_intent(message, thread_name)
    bmad = detect_bmad_workflow(thread_name)
    session = _load_session_id(thread_id)

    return {
        "thread_name":   thread_name,
        "agents_active": agents,
        "bmad_workflow": bmad,
        "has_session":   session is not None,
        "message":       f"Team: {', '.join(agents)}" + (f" + BMAD:{bmad}" if bmad else ""),
    }
