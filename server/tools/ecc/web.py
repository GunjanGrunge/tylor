"""ECC web tools."""
from server.tools._mcp import mcp


@mcp.tool()
def web_scrape(url: str, selector: str | None = None) -> dict:
    """Plan a structured web scrape for a URL and optional selector."""
    return {
        "tool": "web_scrape",
        "url": url,
        "selector": selector,
        "status": "planned",
    }


@mcp.tool()
def web_fetch(url: str) -> dict:
    """Plan a direct web fetch for a URL."""
    return {
        "tool": "web_fetch",
        "url": url,
        "status": "planned",
    }
