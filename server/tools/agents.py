"""server/tools/agents.py — Tier 1 agent orchestration MCP tools."""
from __future__ import annotations
import asyncio
import uuid
import re

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS

from .personas import list_persona_summaries, load_persona
from ._mcp import mcp
from .harness import run_with_agents

_AGENT_ID_RE   = re.compile(r"^[a-zA-Z0-9_-]+$")
_THREAD_ID_RE  = re.compile(r"^[a-f0-9]{32}$")  # uuid4().hex format


def _invalid_params(message: str) -> McpError:
    return McpError(ErrorData(code=INVALID_PARAMS, message=message))


def _get_db():
    from .tylor import _get_db as get_thread_db

    return get_thread_db()


def _get_memory_client():
    from .tylor import _get_memory_client as get_thread_memory_client

    return get_thread_memory_client()


def _ensure_active_thread(db, thread_id: str) -> None:
    meta = db.get_thread_meta(thread_id)
    if not meta:
        raise _invalid_params(f"Thread not found: {thread_id}")

    status = meta.get("Status", meta.get("status", "active"))
    if status != "active":
        raise _invalid_params(f"Thread is not active: {thread_id}")


def _available_personas_message() -> str:
    personas = list_persona_summaries()
    formatted = ", ".join(
        f"{p['name']} ({', '.join(p['ecc_tool_categories'])})"
        for p in personas
    )
    return f"Available personas: {formatted}"


@mcp.tool()
def list_personas() -> dict:
    """
    Return available specialist personas with role summaries and ECC categories.
    """
    return {"personas": list_persona_summaries()}


def _run_persona_agent(
    agent_id: str,
    thread_id: str,
    task: str,
    role_prompt: str,
    db,
) -> dict:
    """
    Drive the Agent SDK harness synchronously for a persona sub-agent.
    Collects streamed output, persists it, and updates agent state to completed.
    """
    # Verify SDK is importable before doing any work
    try:
        import claude_agent_sdk  # noqa: F401
    except (ImportError, TypeError):
        raise _invalid_params(
            "Agent SDK not installed — run: pip install claude-agent-sdk"
        )

    async def _collect():
        chunks: list[str] = []
        async for chunk in run_with_agents(
            message=task,
            thread_id=thread_id,
            system_prompt=role_prompt,
        ):
            chunks.append(chunk)
        return "".join(chunks)

    # Check for a running event loop BEFORE creating any coroutine object so
    # no coroutine is left unawaited if we fall through to the thread-pool path.
    try:
        asyncio.get_running_loop()
        _in_running_loop = True
    except RuntimeError:
        _in_running_loop = False

    if not _in_running_loop:
        output = asyncio.run(_collect())
    else:
        # Already inside a running event loop (e.g. tests or async callers):
        # run in a dedicated thread with its own clean event loop.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            output = pool.submit(lambda: asyncio.run(_collect())).result()

    # Persist output to thread
    try:
        result = persist_agent_output(
            thread_id=thread_id,
            agent_id=agent_id,
            output=output or "(no output)",
            task=task,
        )
        output_sk = result.get("output_sk")
    except Exception:
        output_sk = None

    # Update agent state to completed
    db.put_agent_state(
        thread_id=thread_id,
        agent_id=agent_id,
        state={
            "Status": "completed",
            "Task": task,
        },
    )

    return {"output_sk": output_sk, "output": output}


@mcp.tool()
def spawn_agent(persona: str, thread_id: str, task: str) -> dict:
    """
    Spawn a specialist sub-agent persona within the given thread and execute it.
    The sub-agent is scoped to this thread — no cross-thread bleed.
    Available personas: ceo, cto, analyst, code_agent.

    Args:
        persona: Persona identifier — one of: ceo, cto, analyst, code_agent.
        thread_id: The thread to scope this agent to.
        task: The work the persona should perform inside this thread.
    """
    # Validate SDK availability before writing any state
    try:
        import claude_agent_sdk  # noqa: F401
    except (ImportError, TypeError):
        raise _invalid_params(
            "Agent SDK not installed — run: pip install claude-agent-sdk"
        )

    if not _THREAD_ID_RE.match(thread_id):
        raise _invalid_params(
            f"Invalid thread_id '{thread_id}' — must be a 32-character hex UUID (e.g. uuid4().hex)"
        )
    definition = load_persona(persona)
    if definition is None:
        raise _invalid_params(
            f"Unknown persona: {persona}. {_available_personas_message()}"
        )

    db = _get_db()
    _ensure_active_thread(db, thread_id)

    agent_id = f"agent_{uuid.uuid4().hex}"
    state_item = db.put_agent_state(
        thread_id=thread_id,
        agent_id=agent_id,
        state={
            "Status": "active",
            "Persona": definition.name,
            "Task": task,
            "ToolsLoaded": list(definition.ecc_tool_categories),
        },
    )

    execution = _run_persona_agent(
        agent_id=agent_id,
        thread_id=thread_id,
        task=task,
        role_prompt=definition.role_prompt,
        db=db,
    )

    return {
        "agent_id": agent_id,
        "persona": definition.name,
        "thread_id": thread_id,
        "tools_loaded": list(definition.ecc_tool_categories),
        "task": task,
        "state_sk": state_item["SK"],
        "output_sk": execution.get("output_sk"),
        "status": "completed",
    }


def persist_agent_output(
    thread_id: str,
    agent_id: str,
    output: str,
    task: str | None = None,
    handoff_state: dict | None = None,
) -> dict:
    """
    Persist completed sub-agent output and index it for scoped thread recall.

    This is intentionally an orchestration helper, not a public Tier 1 MCP tool.
    Future sub-agent execution calls this automatically when an agent completes.
    """
    if not _AGENT_ID_RE.match(agent_id or ""):
        raise _invalid_params("Invalid agent_id")
    if not output or not output.strip():
        raise _invalid_params("Agent output must not be empty")

    db = _get_db()
    _ensure_active_thread(db, thread_id)

    output_item = db.put_agent_output(
        thread_id=thread_id,
        agent_id=agent_id,
        output=output,
        task=task,
    )

    handoff_item = None
    if handoff_state is not None:
        handoff_item = db.put_agent_handoff(
            thread_id=thread_id,
            agent_id=agent_id,
            handoff_state=handoff_state,
        )

    memory = _get_memory_client()
    memory_id = memory.index_memory(
        thread_id=thread_id,
        fact=output,
        metadata={
            "source": "agent_output",
            "agent_id": agent_id,
            "agent_output_sk": output_item["SK"],
        },
    )

    return {
        "thread_id": thread_id,
        "agent_id": agent_id,
        "output_sk": output_item["SK"],
        "handoff_sk": handoff_item["SK"] if handoff_item else None,
        "memory_id": memory_id,
    }
