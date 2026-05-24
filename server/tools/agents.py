"""server/tools/agents.py — Tier 1 agent orchestration MCP tools."""
from __future__ import annotations
import asyncio
import threading
import uuid
import re

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INVALID_PARAMS

from .personas import list_persona_summaries, load_persona
from ._mcp import mcp
from .harness import run_with_agents
from .registry import detect_registry_skill, load_skill_tools

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


def _ensure_agent_sdk_available() -> None:
    try:
        import claude_agent_sdk  # noqa: F401
    except (ImportError, TypeError):
        raise _invalid_params(
            "Agent SDK not installed — run: pip install claude-agent-sdk"
        )


def _broadcast_agent_payload(payload: dict) -> None:
    try:
        import importlib

        server_pkg = __package__.rsplit(".tools", 1)[0]
        broadcast_from_any_thread = importlib.import_module(
            f"{server_pkg}.ui_server"
        ).broadcast_from_any_thread

        broadcast_from_any_thread(payload)
    except Exception:
        pass


def _record_agent_event(
    db,
    thread_id: str,
    agent_id: str,
    persona: str,
    event_type: str,
    content: str,
) -> dict | None:
    content = content or ""
    event = None
    try:
        if hasattr(db, "put_agent_event"):
            event = db.put_agent_event(
                thread_id=thread_id,
                agent_id=agent_id,
                event_type=event_type,
                content=content,
                persona=persona,
            )
        else:
            from .tylor import _now_iso

            sk = f"THREAD#{thread_id}#AGENT#{agent_id}#EVENT#{_now_iso()}#{uuid.uuid4().hex}"
            event = db.put_item(
                sk,
                {
                    "ThreadId": thread_id,
                    "AgentId": agent_id,
                    "Persona": persona,
                    "Type": "agent_event",
                    "EventType": event_type,
                    "Content": content,
                },
            )
    except Exception:
        event = None

    _broadcast_agent_payload({
        "type": "agent_event",
        "thread_id": thread_id,
        "agent_id": agent_id,
        "persona": persona,
        "event_type": event_type,
        "content": content,
        "timestamp": (event or {}).get("CreatedAt", (event or {}).get("UpdatedAt", "")),
    })
    return event


def _write_agent_state(
    db,
    thread_id: str,
    agent_id: str,
    state: dict,
) -> dict:
    item = db.put_agent_state(thread_id=thread_id, agent_id=agent_id, state=state)
    _broadcast_agent_payload({
        "type": "agent_update",
        "thread_id": thread_id,
        "agent": {
            "agent_id": agent_id,
            "persona": state.get("Persona", ""),
            "status": str(state.get("Status", "unknown")).lower(),
            "task": state.get("Task", ""),
            "tools_loaded": state.get("ToolsLoaded", []),
            "updated_at": item.get("UpdatedAt", item.get("CreatedAt", "")),
        },
    })
    return item


def _load_skill_groups(tool_groups: list[str]) -> list[dict]:
    loaded = []
    for group in tool_groups:
        try:
            loaded.append(load_skill_tools(group))
        except Exception as exc:
            loaded.append({
                "tool_group": group,
                "status": "failed",
                "error": str(exc),
            })
    return loaded


def _auto_load_task_skill(task: str) -> dict:
    try:
        return detect_registry_skill(task, auto_load=True)
    except Exception as exc:
        return {"matched": False, "action": "error", "error": str(exc)}


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
    persona: str,
    role_prompt: str,
    db,
) -> dict:
    """
    Drive the Agent SDK harness synchronously for a persona sub-agent.
    Collects streamed output, persists it, and updates agent state to completed.
    """
    _ensure_agent_sdk_available()

    async def _collect():
        chunks: list[str] = []
        _record_agent_event(db, thread_id, agent_id, persona, "started", f"{persona} started: {task}")
        async for chunk in run_with_agents(
            message=task,
            thread_id=thread_id,
            system_prompt=role_prompt,
        ):
            chunks.append(chunk)
            _record_agent_event(db, thread_id, agent_id, persona, "chunk", chunk)
        return "".join(chunks)

    try:
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
    except Exception as exc:
        message = f"{persona} failed: {exc}"
        _record_agent_event(db, thread_id, agent_id, persona, "error", message)
        _write_agent_state(
            db,
            thread_id,
            agent_id,
            {
                "Status": "failed",
                "Persona": persona,
                "Task": task,
                "Error": str(exc),
            },
        )
        return {"output_sk": None, "output": "", "error": str(exc)}

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
    _write_agent_state(
        db,
        thread_id,
        agent_id,
        {
            "Status": "completed",
            "Persona": persona,
            "Task": task,
        },
    )
    _record_agent_event(db, thread_id, agent_id, persona, "completed", f"{persona} completed.")

    return {"output_sk": output_sk, "output": output}


@mcp.tool()
def spawn_agent(persona: str, thread_id: str, task: str, wait_for_completion: bool = False) -> dict:
    """
    Spawn a specialist sub-agent persona within the given thread and execute it.
    The sub-agent is scoped to this thread — no cross-thread bleed.
    Available personas: ceo, cto, analyst, code_agent.

    Args:
        persona: Persona identifier — one of: ceo, cto, analyst, code_agent.
        thread_id: The thread to scope this agent to.
        task: The work the persona should perform inside this thread.
    """
    if not _THREAD_ID_RE.match(thread_id):
        raise _invalid_params(
            f"Invalid thread_id '{thread_id}' — must be a 32-character hex UUID (e.g. uuid4().hex)"
        )
    definition = load_persona(persona)
    if definition is None:
        raise _invalid_params(
            f"Unknown persona: {persona}. {_available_personas_message()}"
        )
    _ensure_agent_sdk_available()

    db = _get_db()
    _ensure_active_thread(db, thread_id)

    persona_skill_loads = _load_skill_groups(list(definition.ecc_tool_categories))
    task_skill = _auto_load_task_skill(task)

    agent_id = f"agent_{uuid.uuid4().hex}"
    state_item = _write_agent_state(
        db,
        thread_id,
        agent_id,
        {
            "Status": "active",
                "Persona": definition.name,
                "Task": task,
                "ToolsLoaded": list(definition.ecc_tool_categories),
                "SkillLoads": persona_skill_loads,
                "TaskSkill": task_skill,
            },
    )

    execution: dict = {"output_sk": None}
    if wait_for_completion:
        execution = _run_persona_agent(
            agent_id=agent_id,
            thread_id=thread_id,
            task=task,
            persona=definition.name,
            role_prompt=definition.role_prompt,
            db=db,
        )
    else:
        worker = threading.Thread(
            target=_run_persona_agent,
            kwargs={
                "agent_id": agent_id,
                "thread_id": thread_id,
                "task": task,
                "persona": definition.name,
                "role_prompt": definition.role_prompt,
                "db": db,
            },
            name=f"agent101-{agent_id}",
            daemon=True,
        )
        worker.start()

    return {
        "agent_id": agent_id,
        "persona": definition.name,
        "thread_id": thread_id,
        "tools_loaded": list(definition.ecc_tool_categories),
        "role_prompt": definition.role_prompt,
        "task": task,
        "state_sk": state_item["SK"],
        "output_sk": execution.get("output_sk"),
        "status": "completed" if wait_for_completion else "running",
        "streaming": not wait_for_completion,
        "skill_loads": persona_skill_loads,
        "task_skill": task_skill,
    }


@mcp.tool()
def spawn_agents(thread_id: str, agents: list[dict], wait_for_completion: bool = False) -> dict:
    """
    Spawn multiple persona agents for the same thread.

    Each entry in agents must include:
      {"persona": "analyst|ceo|cto|code_agent", "task": "..."}
    """
    if not agents:
        raise _invalid_params("agents must contain at least one agent spec")

    spawned = []
    for spec in agents:
        if not isinstance(spec, dict):
            raise _invalid_params("Each agent spec must be an object")
        spawned.append(spawn_agent(
            persona=str(spec.get("persona", "")),
            thread_id=thread_id,
            task=str(spec.get("task", "")),
            wait_for_completion=wait_for_completion,
        ))
    return {"thread_id": thread_id, "agents": spawned}


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
