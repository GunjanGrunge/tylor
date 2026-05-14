"""
Tests for Story 3.2: spawn_agent and list_personas tools
Run: pytest server/tools/tests/test_agents.py -v
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import INVALID_PARAMS

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent


class FakeDb:
    def __init__(self, meta: dict | None) -> None:
        self.meta = meta
        self.agent_outputs = []
        self.agent_handoffs = []
        self.agent_states = []

    def get_thread_meta(self, thread_id: str) -> dict | None:
        return self.meta

    def put_agent_output(self, thread_id: str, agent_id: str, output: str, task: str | None = None) -> dict:
        item = {
            "SK": f"THREAD#{thread_id}#AGENT#{agent_id}#OUT#2026-05-12T00:00:00Z",
            "ThreadId": thread_id,
            "AgentId": agent_id,
            "Output": output,
            "Task": task,
        }
        self.agent_outputs.append(item)
        return item

    def put_agent_handoff(self, thread_id: str, agent_id: str, handoff_state: dict) -> dict:
        item = {
            "SK": f"THREAD#{thread_id}#AGENT#{agent_id}#HANDOFF#2026-05-12T00:00:00Z",
            "ThreadId": thread_id,
            "AgentId": agent_id,
            "HandoffState": handoff_state,
        }
        self.agent_handoffs.append(item)
        return item

    def put_agent_state(self, thread_id: str, agent_id: str, state: dict) -> dict:
        item = {
            "SK": f"THREAD#{thread_id}#AGENT#{agent_id}#STATE",
            "ThreadId": thread_id,
            "AgentId": agent_id,
            **state,
        }
        self.agent_states.append(item)
        return item


def test_list_personas_returns_four_personas_with_summaries_and_categories():
    from server.tools.agents import list_personas

    result = list_personas()

    assert set(result.keys()) == {"personas"}
    personas = result["personas"]
    assert {p["name"] for p in personas} == {"analyst", "ceo", "code_agent", "cto"}

    for persona in personas:
        assert persona["role_summary"]
        assert persona["ecc_tool_categories"]
        assert all(c.startswith("ecc/") for c in persona["ecc_tool_categories"])


def test_spawn_agent_initializes_known_persona_in_active_thread_with_scoped_tools():
    from server.tools.agents import spawn_agent

    db = FakeDb({"SK": "THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1#META", "Status": "active"})

    with patch("server.tools.agents._get_db", return_value=db):
        result = spawn_agent(
            persona="code_agent",
            thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",
            task="Implement the next story.",
        )

    assert result["agent_id"].startswith("agent_")
    assert result["persona"] == "code_agent"
    assert result["thread_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"
    assert result["tools_loaded"] == ["ecc/web", "ecc/data", "ecc/pipeline"]
    assert "Senior implementation engineer" in result["role_prompt"]
    assert "Implement the next story." in result["task"]
    assert result["state_sk"].startswith(f"THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1#AGENT#{result['agent_id']}#STATE")
    assert db.agent_states[0]["ThreadId"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"
    assert db.agent_states[0]["Status"] == "active"
    assert db.agent_states[0]["Persona"] == "code_agent"
    assert db.agent_states[0]["ToolsLoaded"] == ["ecc/web", "ecc/data", "ecc/pipeline"]


def test_spawn_agent_keeps_parallel_thread_agents_scoped_to_own_thread():
    from server.tools.agents import spawn_agent

    db_alpha = FakeDb({"SK": "THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2#META", "Status": "active"})
    db_beta = FakeDb({"SK": "THREAD#bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb#META", "Status": "active"})

    with patch("server.tools.agents._get_db", return_value=db_alpha):
        alpha = spawn_agent(
            persona="analyst",
            thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2",
            task="Analyze alpha.",
        )

    with patch("server.tools.agents._get_db", return_value=db_beta):
        beta = spawn_agent(
            persona="cto",
            thread_id="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            task="Analyze beta.",
        )

    assert alpha["thread_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2"
    assert beta["thread_id"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert db_alpha.agent_states[0]["ThreadId"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2"
    assert db_beta.agent_states[0]["ThreadId"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" not in db_alpha.agent_states[0]["SK"]
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2" not in db_beta.agent_states[0]["SK"]


def test_spawn_agent_rejects_inactive_thread():
    from server.tools.agents import spawn_agent

    db = FakeDb({"SK": "THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1#META", "Status": "killed"})

    with pytest.raises(McpError) as excinfo:
        with patch("server.tools.agents._get_db", return_value=db):
            spawn_agent(persona="analyst", thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1", task="Analyze market.")

    assert excinfo.value.error.code == INVALID_PARAMS
    assert "Thread is not active: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1" in excinfo.value.error.message


def test_spawn_agent_unknown_persona_raises_invalid_params_with_persona_list():
    from server.tools.agents import spawn_agent

    with pytest.raises(McpError) as excinfo:
        spawn_agent(persona="designer", thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1", task="Make UI.")

    assert excinfo.value.error.code == INVALID_PARAMS
    message = excinfo.value.error.message
    assert "Unknown persona: designer" in message
    assert "Available personas:" in message
    assert "code_agent" in message
    assert "analyst" in message
    assert "ceo" in message
    assert "cto" in message


def test_spawn_agent_rejects_persona_file_outside_allowlist(tmp_path):
    from server.tools import personas as personas_mod
    from server.tools.agents import spawn_agent

    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "designer.md").write_text(
        "# Designer\n\n"
        "## Role Description\nDesign role.\n\n"
        "## Communication Style\nDirect.\n\n"
        "## ECC Tool Categories\n- `ecc/web`\n",
        encoding="utf-8",
    )

    with patch.object(personas_mod, "PERSONAS_DIR", persona_dir):
        with pytest.raises(McpError) as excinfo:
            spawn_agent(persona="designer", thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1", task="Make UI.")

    assert excinfo.value.error.code == INVALID_PARAMS
    assert "Unknown persona: designer" in excinfo.value.error.message


def test_persist_agent_output_writes_thread_scoped_dynamo_item_and_indexes_memory():
    from server.tools.agents import persist_agent_output

    db = FakeDb({"SK": "THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1#META", "Status": "active"})
    memory = MagicMock()
    memory.index_memory.return_value = "memory-doc-1"

    with patch("server.tools.agents._get_db", return_value=db), patch(
        "server.tools.agents._get_memory_client", return_value=memory
    ):
        result = persist_agent_output(
            thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",
            agent_id="agent_a",
            output="Agent A found the launch risk.",
            task="Assess launch risk.",
        )

    assert result["thread_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"
    assert result["agent_id"] == "agent_a"
    assert result["output_sk"].startswith("THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1#AGENT#agent_a#OUT#")
    assert result["memory_id"] == "memory-doc-1"
    assert db.agent_outputs[0]["ThreadId"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"
    assert db.agent_outputs[0]["Output"] == "Agent A found the launch risk."
    memory.index_memory.assert_called_once_with(
        thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",
        fact="Agent A found the launch risk.",
        metadata={
            "source": "agent_output",
            "agent_id": "agent_a",
            "agent_output_sk": result["output_sk"],
        },
    )


def test_persist_agent_output_preserves_handoff_state_as_distinct_item():
    from server.tools.agents import persist_agent_output

    db = FakeDb({"SK": "THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1#META", "Status": "active"})
    memory = MagicMock()
    memory.index_memory.return_value = "memory-doc-1"
    handoff = {"next_agent": "agent_b", "summary": "Use risk findings in plan."}

    with patch("server.tools.agents._get_db", return_value=db), patch(
        "server.tools.agents._get_memory_client", return_value=memory
    ):
        result = persist_agent_output(
            thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",
            agent_id="agent_a",
            output="Agent A found the launch risk.",
            handoff_state=handoff,
        )

    assert result["handoff_sk"].startswith("THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1#AGENT#agent_a#HANDOFF#")
    assert db.agent_outputs[0]["SK"] != db.agent_handoffs[0]["SK"]
    assert db.agent_handoffs[0]["HandoffState"] == handoff


def test_persist_agent_output_rejects_cross_thread_agent_id():
    from server.tools.agents import persist_agent_output

    db = FakeDb({"SK": "THREAD#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1#META", "Status": "active"})
    with pytest.raises(McpError) as excinfo:
        with patch("server.tools.agents._get_db", return_value=db):
            persist_agent_output(
                thread_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",
                agent_id="THREAD#other#AGENT#agent_a",
                output="bad",
            )

    assert excinfo.value.error.code == INVALID_PARAMS
    assert "Invalid agent_id" in excinfo.value.error.message
