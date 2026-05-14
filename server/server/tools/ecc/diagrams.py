"""ECC diagram tools."""
from .._mcp import mcp


@mcp.tool()
def diagram_gen(kind: str, description: str) -> dict:
    """Plan a diagram from a kind and description."""
    return {
        "tool": "diagram_gen",
        "kind": kind,
        "description": description,
        "status": "planned",
    }


@mcp.tool()
def flowchart_gen(steps: list[str]) -> dict:
    """Plan a flowchart from ordered steps."""
    return {
        "tool": "flowchart_gen",
        "steps": steps,
        "status": "planned",
    }
