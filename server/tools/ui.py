"""
server/tools/ui.py — MCP tool for opening the Thread Visualizer UI.
FR43: /open-threads-ui skill calls this tool to open localhost:8765.
"""
import webbrowser

from ._mcp import mcp


def _ui_url() -> str:
    from ..ui_server import PORT
    return f"http://localhost:{PORT}"


def _open_ui_browser() -> str:
    """
    Open the Thread Visualizer in the default browser.
    Always opens if ui_available; returns a status string.
    """
    from ..ui_server import ui_available, PORT, PORT_RANGE
    url = f"http://localhost:{PORT}"
    if not ui_available:
        return (
            f"Thread Visualizer could not start — all ports "
            f"{PORT_RANGE[0]}–{PORT_RANGE[1]-1} were in use. "
            "MCP tools are unaffected. Free a port and restart the plugin."
        )
    webbrowser.open(url)
    return f"Thread Visualizer open at {url}"


@mcp.tool()
def open_threads_ui() -> str:
    """
    Open the TYLOR Thread Visualizer in the system default browser.
    Returns a confirmation message, or a warning if the UI server is unavailable.
    """
    return _open_ui_browser()
