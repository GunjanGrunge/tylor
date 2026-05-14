"""
server/tools/ui.py — MCP tool for opening the Thread Visualizer UI.
FR43: /open-threads-ui skill calls this tool to open localhost:8765.
"""
import webbrowser

from ._mcp import mcp


def _ui_url() -> str:
    from ..ui_server import PORT
    return f"http://localhost:{PORT}"


@mcp.tool()
def open_threads_ui() -> str:
    """
    Open the TYLOR Thread Visualizer in the system default browser.
    Returns a confirmation message, or a warning if the UI server is unavailable.
    """
    from ..ui_server import ui_available

    url = _ui_url()
    if not ui_available:
        return (
            f"Thread UI could not start (port {url.split(':')[-1]} in use) — "
            "MCP tools unaffected. Close the process occupying that port and restart the plugin."
        )

    webbrowser.open(url)
    return f"Thread Visualizer open at {url}"
