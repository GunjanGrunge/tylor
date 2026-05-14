"""Tests for Story 2.11: thread-scoped code index."""
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_save_memory_stores_typed_code_index_fact():
    from server.tools.tylor import save_memory

    memory = MagicMock()
    memory.index_memory.return_value = "doc-1"

    with patch("server.tools.tylor._get_memory_client", return_value=memory):
        result = save_memory(
            thread_id="t1",
            fact="SignIn: ui/auth.tsx:42 — login form component",
            fact_type="code_index",
        )

    memory.index_memory.assert_called_once_with(
        thread_id="t1",
        fact="SignIn: ui/auth.tsx:42 — login form component",
        metadata={"type": "code_index"},
    )
    assert result == {"status": "saved", "thread_id": "t1", "memory_id": "doc-1", "type": "code_index"}


def test_recall_memory_filters_by_type_at_storage_layer():
    from server.tools.tylor import recall_memory

    memory = MagicMock()
    memory.search_memory.return_value = [{"content": "SignIn: ui/auth.tsx:42"}]

    with patch("server.tools.tylor._get_memory_client", return_value=memory):
        result = recall_memory(thread_id="t1", query="SignIn", fact_type="code_index")

    # storage layer receives `type=` (its own parameter name)
    memory.search_memory.assert_called_once_with(
        thread_id="t1",
        query="SignIn",
        k=5,
        type="code_index",
    )
    assert result["results"][0]["content"].startswith("SignIn")


def test_code_index_header_injected_on_session_start_with_budget():
    from server.tools.hooks import session_start_message

    db = MagicMock()
    db.get_current_thread_marker.return_value = {
        "CurrentThreadId": "t1",
        "ActiveAt": "2026-05-13T00:00:00Z",
    }
    db.get_thread_meta.return_value = {"Name": "Frontend", "Status": "active", "MessageCount": 3}
    memory = MagicMock()
    memory.search_memory.return_value = [
        {"content": f"Symbol{i}: src/file{i}.tsx:{i} — component", "created_at": f"2026-05-13T00:00:{i:02d}Z"}
        for i in range(30)
    ]

    def list_threads():
        return {"threads": [{"thread_id": "t1", "name": "Frontend", "status": "active", "message_count": 3}]}

    message = session_start_message(db=db, list_threads_fn=list_threads, memory_client=memory)

    assert "[Frontend Thread — Code Index]" in message
    header = message.split("agent101 active thread context:", 1)[0]
    assert len(header.split()) <= 150
    # storage layer receives `type=`
    memory.search_memory.assert_called_once_with(
        thread_id="t1",
        query="code index",
        k=30,
        type="code_index",
    )


def test_post_tool_use_indexes_read_file_symbol(tmp_path):
    from server.tools.hooks import index_code_file_for_active_thread

    source = tmp_path / "SignIn.tsx"
    source.write_text("export function SignIn() {\n  return <form />\n}\n", encoding="utf-8")
    db = MagicMock()
    db.get_current_thread_marker.return_value = {"CurrentThreadId": "t1"}
    memory = MagicMock()
    memory.index_memory.return_value = "doc-1"

    result = index_code_file_for_active_thread(str(source), db=db, memory_client=memory,
                                               project_root=tmp_path)

    assert result["status"] == "indexed"
    fact = memory.index_memory.call_args.kwargs["fact"]
    assert fact.startswith("SignIn:")
    # path should be relative (just the filename when project_root=tmp_path)
    assert "SignIn.tsx:1" in fact
    assert len(fact.split()) <= 30
    assert memory.index_memory.call_args.kwargs["metadata"]["type"] == "code_index"


def test_post_tool_use_skips_config_files(tmp_path):
    from server.tools.hooks import index_code_file_for_active_thread

    config = tmp_path / "vite.config.ts"
    config.write_text("export default {}\n", encoding="utf-8")

    result = index_code_file_for_active_thread(str(config), db=MagicMock(), memory_client=MagicMock())

    assert result == {"status": "skipped", "reason": "no_indexable_symbol"}
