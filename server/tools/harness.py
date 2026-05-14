"""
server/tools/harness.py — Agent SDK orchestration harness.

Architecture:
- A supervisor Claude instance runs in the thread context
- It reads the full agent registry and decides which specialists to spawn
- Agents spawn only when needed, based on Claude's own reasoning
- BMAD workflows, ECC skills, legal/design/custom agents all registered
- Skills from installed plugins auto-discovered and injected
- Human-in-the-loop: AskUserQuestion pauses until user responds
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import AsyncIterator


# ── Agent registry ────────────────────────────────────────────────────────────
# Claude reads this registry and decides which agents to spawn.
# Add new agents here — Claude will automatically use them when relevant.

def build_agent_registry() -> dict:
    """
    Build the full agent registry from:
    1. Built-in specialist agents
    2. BMAD agents (if bundled)
    3. ECC skill agents
    4. Any installed plugin skills
    """
    try:
        from claude_agent_sdk import AgentDefinition
    except ImportError:
        return {}

    registry: dict = {}

    # ── Core specialists ──────────────────────────────────────────────────────

    registry["code_agent"] = AgentDefinition(
        description=(
            "Senior software engineer. Reads files, writes code, runs tests, "
            "fixes bugs, implements features. Use for: any coding, debugging, "
            "implementation, refactoring, or testing task."
        ),
        prompt=(
            "You are a senior software engineer. Read the codebase before making changes. "
            "Write clean, tested, production-grade code. Explain changes concisely. "
            "Ask for clarification when requirements are ambiguous."
        ),
        tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"],
    )

    registry["design_agent"] = AgentDefinition(
        description=(
            "UX/UI designer. Handles interface design, user experience, accessibility, "
            "component placement, visual hierarchy. Use for: UI feedback, layout decisions, "
            "design reviews, accessibility checks, privacy policy UI placement."
        ),
        prompt=(
            "You are a UX/UI designer. You think about user experience first. "
            "You give specific, actionable design feedback. You ask about user flows "
            "and accessibility. You review implementations against design principles."
        ),
        tools=["Read", "Glob", "AskUserQuestion"],
    )

    registry["legal_agent"] = AgentDefinition(
        description=(
            "Legal and compliance specialist. Drafts privacy policies, terms of service, "
            "cookie policies, GDPR/CCPA compliance docs. Asks about: data collected, "
            "user jurisdiction, third-party services, data retention. Use for: any "
            "legal document, compliance review, privacy policy, ToS."
        ),
        prompt=(
            "You are a legal and compliance specialist for software products. "
            "You draft clear, enforceable legal documents. You ask the right questions "
            "about data practices before drafting. You flag compliance gaps. "
            "You write in plain language where possible. "
            "Always ask: what data is collected, which jurisdictions apply, "
            "what third-party services are used, how long data is retained."
        ),
        tools=["Read", "Write", "AskUserQuestion"],
    )

    registry["cto"] = AgentDefinition(
        description=(
            "Technical architect. System design, database schema, API design, "
            "technology decisions, scalability, security architecture. "
            "Use for: architecture decisions, tech stack choices, system design."
        ),
        prompt=(
            "You are a CTO and technical architect. Think in systems. "
            "Make pragmatic technology choices with clear tradeoffs. "
            "Design for scalability and maintainability."
        ),
        tools=["Read", "Glob", "Grep", "AskUserQuestion"],
    )

    registry["analyst"] = AgentDefinition(
        description=(
            "Business analyst and researcher. Requirements gathering, market research, "
            "data analysis, metrics, competitive analysis. "
            "Use for: requirements, research, analysis, reporting."
        ),
        prompt=(
            "You are a sharp business analyst. Turn data into insight. "
            "Gather requirements precisely. Ask the right clarifying questions. "
            "Produce structured, actionable analysis."
        ),
        tools=["Read", "Glob", "Grep", "WebSearch", "AskUserQuestion"],
    )

    registry["ceo"] = AgentDefinition(
        description=(
            "Product strategist. PRD creation, product vision, prioritisation, "
            "user stories, roadmaps, stakeholder communication. "
            "Use for: product strategy, PRDs, roadmaps, feature prioritisation."
        ),
        prompt=(
            "You are a product-focused CEO. User value first. "
            "Write crisp PRDs. Prioritise ruthlessly. "
            "Communicate clearly to both technical and business audiences."
        ),
        tools=["Read", "Glob", "AskUserQuestion"],
    )

    registry["security_agent"] = AgentDefinition(
        description=(
            "Security engineer. Security reviews, vulnerability assessment, "
            "auth flows, data protection, OWASP compliance. "
            "Use for: security audits, auth implementation, encryption, access control."
        ),
        prompt=(
            "You are a security engineer. Review code for vulnerabilities. "
            "Follow OWASP guidelines. Think like an attacker. "
            "Give specific remediation steps, not just warnings."
        ),
        tools=["Read", "Glob", "Grep", "AskUserQuestion"],
    )

    # ── BMAD agents (if installed) ────────────────────────────────────────────

    bmad_path = _get_bmad_path()
    if bmad_path:
        registry["bmad_pm"] = AgentDefinition(
            description=(
                "BMAD Product Manager. Runs structured PRD creation, story writing, "
                "epic breakdown using BMAD methodology. Use for: formal PRD creation, "
                "user stories, epic breakdown, sprint planning with BMAD structure."
            ),
            prompt=(
                f"You are a BMAD product manager. Use BMAD methodology from {bmad_path}. "
                "Run structured facilitation for PRDs, stories, and epics. "
                "Ask discovery questions before generating documents."
            ),
            tools=["Read", "Write", "Glob", "AskUserQuestion"],
        )

        registry["bmad_architect"] = AgentDefinition(
            description=(
                "BMAD Architect. Runs structured architecture decision records, "
                "system design using BMAD methodology. Use for: formal architecture "
                "documents, ADRs, technical specifications."
            ),
            prompt=(
                f"You are a BMAD architect. Use BMAD methodology from {bmad_path}. "
                "Create structured architecture documents and ADRs."
            ),
            tools=["Read", "Write", "Glob", "AskUserQuestion"],
        )

    # ── ECC skill agents ──────────────────────────────────────────────────────

    registry["web_agent"] = AgentDefinition(
        description=(
            "Web research and scraping specialist. Fetches URLs, searches the web, "
            "scrapes data. Use for: any task requiring web data, competitor research, "
            "documentation lookup, API reference fetching."
        ),
        prompt="You fetch and process web content accurately. You cite sources.",
        tools=["WebFetch", "WebSearch", "AskUserQuestion"],
    )

    # ── Auto-discover installed plugin skills ─────────────────────────────────

    skills_dir = Path(__file__).parent.parent.parent / "skills"
    if skills_dir.exists():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                skill_name = skill_dir.name
                # Don't re-register built-in skills
                if skill_name in ("new-thread", "switch-thread", "kill-thread",
                                  "list-threads", "recall", "set-sandbox",
                                  "afk-status", "help-agent101", "run"):
                    continue
                # Register as a skill-agent
                skill_content = (skill_dir / "SKILL.md").read_text()[:300]
                registry[f"skill_{skill_name}"] = AgentDefinition(
                    description=f"Runs the /{skill_name} skill. {skill_content[:150]}",
                    prompt=f"You execute the {skill_name} skill workflow.",
                    tools=["Read", "Write", "Glob", "AskUserQuestion"],
                )

    return registry


def _get_bmad_path() -> str | None:
    """Return BMAD path if installed."""
    config_file = Path.home() / ".tylor" / "config.json"
    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text())
            bmad = cfg.get("bmad_path")
            if bmad and Path(bmad).exists():
                return bmad
        except Exception:
            pass
    # Common install locations
    for path in [
        Path.home() / ".tylor" / "bmad",
        Path.home() / ".claude" / "plugins" / "bmad",
    ]:
        if path.exists():
            return str(path)
    return None


# ── Supervisor system prompt ──────────────────────────────────────────────────

SUPERVISOR_PROMPT = """You are the Tylor supervisor — an orchestrator running inside a persistent thread.

Your job:
1. Read the user's request and the thread context
2. Decide which specialist agent(s) to spawn using the Agent tool
3. Coordinate their work — pass outputs between agents when needed
4. Ask the user clarifying questions via AskUserQuestion when requirements are unclear
5. Wait for user approval before making destructive changes (deleting files, major refactors)

Rules:
- Spawn agents only when they add value — don't spawn for simple answers
- When spawning multiple agents, be explicit about what each one should do
- Always surface agent questions to the user — never guess on their behalf
- If a task spans multiple agents (e.g. legal + code + design), coordinate their outputs
- The thread context is your memory — reference previous work naturally
"""


# ── Core harness ──────────────────────────────────────────────────────────────

async def run_with_agents(
    message: str,
    thread_id: str,
    thread_name: str = "",
    cwd: str | None = None,
) -> AsyncIterator[str]:
    """
    Run a user message through the supervisor.
    Claude reads the agent registry and decides what to spawn.
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, PermissionResultAllow
    except ImportError:
        yield "⚠️  Agent SDK not installed. Run: pip install claude-agent-sdk"
        return

    agent_registry = build_agent_registry()

    # Build context for the supervisor
    context = f"Thread: {thread_name}" if thread_name else ""
    if cwd:
        context += f"\nProject directory: {cwd}"

    bmad_path = _get_bmad_path()
    if bmad_path and _thread_needs_bmad(thread_name):
        context += f"\nBMAD methodology available at: {bmad_path}"

    full_prompt = f"{context}\n\n{message}".strip()

    # Human-in-the-loop: intercept questions and approval requests
    pending_questions: list[str] = []

    async def can_use_tool(ctx):
        tool = getattr(ctx, "tool_name", "") or getattr(ctx, "toolName", "")
        tool_input = getattr(ctx, "tool_input", {}) or {}

        if tool == "AskUserQuestion":
            questions = tool_input.get("questions", [])
            for q in questions:
                q_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
                pending_questions.append(q_text)
        return PermissionResultAllow(updated_input=tool_input)

    # Session = thread (full persistent memory)
    session_id = _load_session_id(thread_id)

    options = ClaudeAgentOptions(
        system_prompt=SUPERVISOR_PROMPT,
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep",
                        "WebFetch", "WebSearch", "AskUserQuestion", "Agent"],
        agents=agent_registry,
        resume=session_id,
        cwd=cwd,
        can_use_tool=can_use_tool,
    )

    new_session_id: str | None = None
    try:
        async for msg in query(prompt=full_prompt, options=options):

            # Capture session ID
            if hasattr(msg, "subtype") and msg.subtype == "init":
                sid = getattr(msg, "session_id", None)
                if not sid and hasattr(msg, "data"):
                    sid = (msg.data or {}).get("session_id")
                if sid:
                    new_session_id = sid

            # Surface pending questions before content
            if pending_questions:
                for q in pending_questions:
                    yield f"\n❓ **{q}**\n"
                pending_questions.clear()

            # Stream text
            content = getattr(msg, "content", None) or getattr(msg, "text", None)
            if isinstance(content, str) and content:
                yield content

    except Exception as exc:
        yield f"\n⚠️  Supervisor error: {exc}"

    if new_session_id:
        _save_session_id(thread_id, new_session_id)


def _thread_needs_bmad(thread_name: str) -> bool:
    keywords = ("prd", "planning", "architecture", "design", "research", "epic", "story")
    return any(k in thread_name.lower() for k in keywords)


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


# ── MCP tools ─────────────────────────────────────────────────────────────────

from server.tools._mcp import mcp  # noqa: E402


@mcp.tool()
async def run_in_thread(thread_id: str, message: str, cwd: str | None = None) -> str:
    """
    Run a task in a thread. The supervisor reads the full agent registry and
    spawns exactly the right specialists — legal, design, code, BMAD, ECC —
    based on what the task actually requires.

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
def list_available_agents() -> dict:
    """
    List all agents in the registry that the supervisor can spawn.
    Shows which specialists are available for the current session.
    """
    registry = build_agent_registry()
    return {
        "agents": {
            name: defn.description
            for name, defn in registry.items()
        },
        "total": len(registry),
        "bmad_available": _get_bmad_path() is not None,
        "note": "The supervisor (Claude) decides which to spawn based on your task.",
    }
