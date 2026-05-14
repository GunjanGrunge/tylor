"""Development mock server for the Thread Visualizer UI."""
import asyncio
import itertools

from server import ui_server


MOCK_THREADS = [
    {
        "id": "thread-active",
        "title": "Story 6.4 Detail Panel",
        "status": "active",
        "created_at": "2026-05-13T20:35:00Z",
        "message_count": 18,
    },
    {
        "id": "thread-router",
        "title": "Model Router Fallback",
        "status": "running",
        "created_at": "2026-05-13T19:18:00Z",
        "message_count": 42,
    },
    {
        "id": "thread-hooks",
        "title": "Claude Hooks + Code Index",
        "status": "awaiting",
        "created_at": "2026-05-13T18:44:00Z",
        "message_count": 27,
    },
    {
        "id": "thread-ui",
        "title": "Thread Visualizer UI",
        "status": "idle",
        "created_at": "2026-05-13T17:10:00Z",
        "message_count": 13,
    },
    {
        "id": "thread-old",
        "title": "Archived Spike",
        "status": "killed",
        "created_at": "2026-05-12T16:00:00Z",
        "message_count": 6,
    },
]

MOCK_MESSAGES = {
    "thread-active": [
        {
            "role": "user",
            "content": "Open the thread detail panel.",
            "timestamp": "2026-05-13T20:35:00Z",
        },
        {
            "role": "assistant",
            "content": "Rendering thread metadata, messages, and agent state.",
            "timestamp": "2026-05-13T20:36:00Z",
        },
    ],
    "thread-router": [
        {
            "role": "assistant",
            "content": "Primary model failed; falling back to lower tier.",
            "timestamp": "2026-05-13T19:21:00Z",
        },
    ],
}


def _mock_threads() -> list[dict]:
    return MOCK_THREADS


def _mock_messages(thread_id: str, limit: int = 50) -> list[dict]:
    return MOCK_MESSAGES.get(thread_id, [])[-limit:]


async def main() -> None:
    ui_server._fetch_threads = _mock_threads
    ui_server._fetch_messages = _mock_messages

    runner = await ui_server.start_ui_server()
    if runner is None:
        print("mock thread UI server: port 8765 is already in use", flush=True)
        return

    print("mock thread UI server running at http://localhost:8765", flush=True)
    cycle = itertools.cycle(
        [
            ("thread-router", "running"),
            ("thread-router", "awaiting"),
            ("thread-hooks", "running"),
            ("thread-hooks", "idle"),
        ]
    )

    try:
        while True:
            target, status = next(cycle)
            for thread in MOCK_THREADS:
                if thread["id"] == target:
                    thread["status"] = status
                    thread["message_count"] += 1
            await ui_server.ws_manager.broadcast({"type": "thread_update", "threads": MOCK_THREADS})
            await asyncio.sleep(3)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
