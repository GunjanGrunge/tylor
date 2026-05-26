"""Tests for Story 3.5 — spawn_agent wired to Agent SDK harness."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.shared.exceptions import McpError


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_fake_db(thread_status: str = "active"):
    db = MagicMock()
    db.resolve_thread_id = lambda tid: tid
    db.get_thread_meta.return_value = {"Status": thread_status}
    db.put_agent_state.return_value = {"SK": "THREAD#abc#AGENT#agent_xyz#STATE"}
    db.put_agent_output.return_value = {"SK": "THREAD#abc#AGENT#agent_xyz#OUT#2026-01-01"}
    db.put_agent_handoff.return_value = {"SK": "THREAD#abc#AGENT#agent_xyz#HANDOFF#2026-01-01"}
    return db


VALID_THREAD_ID = "a" * 32


# ── AC4: SDK not installed → McpError before any DB write ────────────────────

def test_spawn_agent_raises_when_sdk_missing(monkeypatch):
    """AC4: McpError raised when claude_agent_sdk is not importable."""
    # Hide the SDK
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)

    from server.tools.agents import spawn_agent

    with patch("server.tools.agents._get_db", return_value=_make_fake_db()):
        with pytest.raises(McpError) as exc_info:
            spawn_agent(persona="code_agent", thread_id=VALID_THREAD_ID, task="do stuff")
    assert "Agent SDK not installed" in str(exc_info.value)


# ── AC1: run_with_agents called with persona role_prompt as system_prompt ────

@pytest.mark.asyncio
async def test_spawn_agent_calls_harness_with_persona_prompt():
    """AC1: run_with_agents invoked with system_prompt=persona.role_prompt."""
    fake_db = _make_fake_db()

    async def fake_run(message, thread_id, thread_name="", cwd=None, system_prompt=None):
        # Capture args for assertion
        fake_run.captured_system_prompt = system_prompt
        fake_run.captured_message = message
        yield "task output"

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock()}), \
         patch("server.tools.agents._get_db", return_value=fake_db), \
         patch("server.tools.agents.run_with_agents", side_effect=fake_run), \
         patch("server.tools.agents.persist_agent_output", return_value={"output_sk": "SK1", "memory_id": "m1"}):

        from server.tools.agents import spawn_agent, load_persona
        persona_def = load_persona("code_agent")

        result = spawn_agent(persona="code_agent", thread_id=VALID_THREAD_ID, task="build the thing", wait_for_completion=True)

    assert fake_run.captured_system_prompt == persona_def.role_prompt
    assert fake_run.captured_message == "build the thing"
    assert result["status"] == "completed"


# ── AC2: persist_agent_output called after harness completes ─────────────────

@pytest.mark.asyncio
async def test_spawn_agent_persists_output():
    """AC2: persist_agent_output called with collected output text."""
    fake_db = _make_fake_db()

    async def fake_run(message, thread_id, thread_name="", cwd=None, system_prompt=None):
        yield "chunk one "
        yield "chunk two"

    persist_mock = MagicMock(return_value={"output_sk": "OUT_SK", "memory_id": "m2"})

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock()}), \
         patch("server.tools.agents._get_db", return_value=fake_db), \
         patch("server.tools.agents.run_with_agents", side_effect=fake_run), \
         patch("server.tools.agents.persist_agent_output", persist_mock):

        from server.tools.agents import spawn_agent
        spawn_agent(persona="code_agent", thread_id=VALID_THREAD_ID, task="analyse data", wait_for_completion=True)

    persist_mock.assert_called_once()
    call_kwargs = persist_mock.call_args
    output_arg = call_kwargs[0][2] if call_kwargs[0] else call_kwargs[1].get("output")
    assert "chunk one" in output_arg
    assert "chunk two" in output_arg


# ── AC3: agent state updated to completed ────────────────────────────────────

@pytest.mark.asyncio
async def test_spawn_agent_marks_state_completed():
    """AC3: DB state record updated to Status=completed after harness run."""
    fake_db = _make_fake_db()

    async def fake_run(message, thread_id, thread_name="", cwd=None, system_prompt=None):
        yield "done"

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock()}), \
         patch("server.tools.agents._get_db", return_value=fake_db), \
         patch("server.tools.agents.run_with_agents", side_effect=fake_run), \
         patch("server.tools.agents.persist_agent_output", return_value={"output_sk": "SK", "memory_id": "m"}):

        from server.tools.agents import spawn_agent
        spawn_agent(persona="code_agent", thread_id=VALID_THREAD_ID, task="review code", wait_for_completion=True)

    # put_agent_state called twice: once for "active", once for "completed"
    calls = fake_db.put_agent_state.call_args_list
    assert len(calls) == 2
    final_state = calls[1][1]["state"] if calls[1][1] else calls[1][0][2]
    assert final_state["Status"] == "completed"


# ── AC5: persona system_prompt passed to ClaudeAgentOptions ──────────────────

@pytest.mark.asyncio
async def test_run_with_agents_uses_override_system_prompt():
    """AC5: run_with_agents passes system_prompt override to ClaudeAgentOptions."""
    mock_sdk = MagicMock()
    captured = {}

    async def fake_query(prompt, options):
        captured["system_prompt"] = options.system_prompt
        return
        yield  # make it an async generator

    mock_sdk.query = fake_query
    mock_sdk.ClaudeAgentOptions = MagicMock(side_effect=lambda **kw: MagicMock(**kw))

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        from importlib import reload
        import server.tools.harness as harness_mod
        reload(harness_mod)

        chunks = []
        async for chunk in harness_mod.run_with_agents(
            message="test",
            thread_id=VALID_THREAD_ID,
            system_prompt="CUSTOM PERSONA PROMPT",
        ):
            chunks.append(chunk)

    mock_sdk.ClaudeAgentOptions.assert_called_once()
    call_kwargs = mock_sdk.ClaudeAgentOptions.call_args[1]
    assert call_kwargs["system_prompt"] == "CUSTOM PERSONA PROMPT"


# ── AC6: return dict includes output_sk and status ───────────────────────────

@pytest.mark.asyncio
async def test_spawn_agent_return_includes_output_sk_and_status():
    """AC6: return dict has output_sk and status fields."""
    fake_db = _make_fake_db()

    async def fake_run(message, thread_id, thread_name="", cwd=None, system_prompt=None):
        yield "result"

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock()}), \
         patch("server.tools.agents._get_db", return_value=fake_db), \
         patch("server.tools.agents.run_with_agents", side_effect=fake_run), \
         patch("server.tools.agents.persist_agent_output", return_value={"output_sk": "THE_SK", "memory_id": "m"}):

        from server.tools.agents import spawn_agent
        result = spawn_agent(persona="analyst", thread_id=VALID_THREAD_ID, task="crunch numbers", wait_for_completion=True)

    assert "output_sk" in result
    assert result["output_sk"] == "THE_SK"
    assert result["status"] == "completed"
    assert "agent_id" in result
    assert "persona" in result
    assert "thread_id" in result


@pytest.mark.asyncio
async def test_spawn_agent_persists_verbose_events_for_started_chunks_and_completed():
    fake_db = _make_fake_db()

    async def fake_run(message, thread_id, thread_name="", cwd=None, system_prompt=None):
        yield "first verbose chunk"
        yield "\n$ Bash {\"command\":\"pytest -q\"}\n"

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock()}), \
         patch("server.tools.agents._get_db", return_value=fake_db), \
         patch("server.tools.agents.run_with_agents", side_effect=fake_run), \
         patch("server.tools.agents.persist_agent_output", return_value={"output_sk": "THE_SK", "memory_id": "m"}):

        from server.tools.agents import spawn_agent
        result = spawn_agent(
            persona="code_agent",
            thread_id=VALID_THREAD_ID,
            task="run tests verbosely",
            wait_for_completion=True,
        )

    events = [call.kwargs for call in fake_db.put_agent_event.call_args_list]
    event_types = [event["event_type"] for event in events]
    contents = [event["content"] for event in events]

    assert result["status"] == "completed"
    assert event_types == ["started", "chunk", "chunk", "completed"]
    assert "first verbose chunk" in contents
    assert any("\n$ Bash" in content for content in contents)


def test_detect_thread_team_previews_roles_and_ecc_skill():
    from server.tools.harness import detect_thread_team

    result = detect_thread_team(
        thread_id=VALID_THREAD_ID,
        message="review the architecture and create a flowchart diagram",
    )

    assert result["thread_id"] == VALID_THREAD_ID
    assert "reviewer" in result["roles"]
    assert "planner" in result["roles"]
    assert {"tool_group": "ecc/diagrams", "action": "suggest"} in result["ecc_groups"]


def test_save_session_id_is_cross_platform(tmp_path, monkeypatch):
    from server.tools import harness as harness_mod

    session_file = tmp_path / "sessions.json"
    monkeypatch.setattr(harness_mod, "_sessions_file", lambda: session_file)

    harness_mod._save_session_id("thread-a", "session-a")
    harness_mod._save_session_id("thread-b", "session-b")

    assert json.loads(session_file.read_text(encoding="utf-8")) == {
        "thread-a": "session-a",
        "thread-b": "session-b",
    }


@pytest.mark.asyncio
async def test_run_with_agents_reports_failed_summary_on_sdk_error():
    mock_sdk = MagicMock()

    async def fake_query(prompt, options):
        raise RuntimeError("sdk exploded")
        yield

    mock_sdk.query = fake_query
    mock_sdk.ClaudeAgentOptions = MagicMock(side_effect=lambda **kw: MagicMock(**kw))

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        from importlib import reload
        import server.tools.harness as harness_mod
        reload(harness_mod)

        chunks = []
        async for chunk in harness_mod.run_with_agents(
            message="test",
            thread_id=VALID_THREAD_ID,
        ):
            chunks.append(chunk)

    output = "".join(chunks)
    assert "sdk exploded" in output
    assert "[supervisor] failed" in output


def test_spawn_agent_marks_failed_when_output_persistence_fails():
    fake_db = _make_fake_db()

    async def fake_run(message, thread_id, thread_name="", cwd=None, system_prompt=None):
        yield "result"

    with patch.dict(sys.modules, {"claude_agent_sdk": MagicMock()}), \
         patch("server.tools.agents._get_db", return_value=fake_db), \
         patch("server.tools.agents.run_with_agents", side_effect=fake_run), \
         patch("server.tools.agents.persist_agent_output", side_effect=RuntimeError("db down")):

        from server.tools.agents import spawn_agent
        result = spawn_agent(
            persona="analyst",
            thread_id=VALID_THREAD_ID,
            task="crunch numbers",
            wait_for_completion=True,
        )

    final_state = fake_db.put_agent_state.call_args_list[-1].kwargs["state"]
    assert result["status"] == "failed"
    assert result["output_sk"] is None
    assert final_state["Status"] == "failed"
    assert "db down" in final_state["Error"]


@pytest.mark.asyncio
async def test_run_with_agents_wires_auto_spawn_agent_tool():
    """The supervisor harness exposes Agent and reports sub-agent starts."""
    mock_sdk = MagicMock()
    captured = {}

    async def fake_query(prompt, options):
        captured["allowed_tools"] = options.allowed_tools
        captured["agents"] = options.agents
        yield SimpleNamespace(
            content=[
                SimpleNamespace(
                    name="Agent",
                    input={
                        "subagent_type": "reviewer",
                        "description": "review the harness code",
                    },
                )
            ]
        )

    def fake_agent_definition(**kwargs):
        return SimpleNamespace(**kwargs)

    mock_sdk.query = fake_query
    mock_sdk.ClaudeAgentOptions = MagicMock(side_effect=lambda **kw: SimpleNamespace(**kw))
    mock_sdk.AgentDefinition = MagicMock(side_effect=fake_agent_definition)

    with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
        from importlib import reload
        import server.tools.harness as harness_mod
        reload(harness_mod)

        chunks = []
        async for chunk in harness_mod.run_with_agents(
            message="review the harness code",
            thread_id=VALID_THREAD_ID,
        ):
            chunks.append(chunk)

    output = "".join(chunks)
    assert "Agent" in captured["allowed_tools"]
    assert {"researcher", "implementer", "reviewer", "planner", "drafter"} <= set(captured["agents"])
    assert "[agent: reviewer #1] starting" in output
    assert "[supervisor] complete" in output
    assert "1 agent ran" in output
