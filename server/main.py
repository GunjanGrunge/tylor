"""
server/main.py — agent101 FastMCP entry point.

Starts both FastMCP (stdio transport) and the aiohttp Thread Visualizer
server concurrently on a single asyncio event loop.

Can be run as a script: python3 server/main.py (from the plugin root)
or as a module: python3 -m server.main
"""
from __future__ import annotations
import asyncio
import logging
import os
import signal
import sys

# Allow running as a standalone script OR as a module.
# When run as `python3 server/main.py`, __package__ is None and relative
# imports fail. This block ensures the plugin root is on sys.path so that
# `from server.tools...` absolute imports work in both modes.
if __package__ is None or __package__ == "":
    _plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _plugin_root not in sys.path:
        sys.path.insert(0, _plugin_root)

from server.tools._mcp import mcp  # noqa: F401

# Register @mcp.tool() decorators (side effects)
from server.tools import tylor          # noqa: F401
from server.tools import agents         # noqa: F401
from server.tools import registry       # noqa: F401
from server.tools import skill_installer  # noqa: F401
from server.tools import help           # noqa: F401
from server.tools import executor       # noqa: F401
from server.tools import ui             # noqa: F401
from server.tools import harness        # noqa: F401  — Agent SDK orchestration
from server import config               # noqa: F401

logger = logging.getLogger(__name__)


async def _main(ui_only: bool = False) -> None:
    from server.ui_server import start_ui_server

    runner = await start_ui_server()

    from server.ui_server import ui_available
    if not ui_available:
        print(
            "Thread UI could not start (port 8765 in use) — MCP tools unaffected",
            file=sys.stderr,
        )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    if ui_only:
        logger.info("Running in UI-only mode — http://localhost:8765")
        await stop_event.wait()
    else:
        mcp_task = asyncio.create_task(mcp.run_stdio_async())
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            [mcp_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    if runner is not None:
        await runner.cleanup()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ui-only', action='store_true',
                        help='Run only the aiohttp visualizer server (no MCP stdio)')
    args = parser.parse_args()
    asyncio.run(_main(ui_only=args.ui_only))
