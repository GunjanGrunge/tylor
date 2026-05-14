"""ECC presentation tools."""
from server.tools._mcp import mcp


@mcp.tool()
def build_pptx(title: str, outline: list[str]) -> dict:
    """Plan a presentation deck from a title and outline."""
    return {
        "tool": "build_pptx",
        "title": title,
        "outline": outline,
        "status": "planned",
    }


@mcp.tool()
def build_doc(title: str, sections: list[str]) -> dict:
    """Plan a document from a title and section list."""
    return {
        "tool": "build_doc",
        "title": title,
        "sections": sections,
        "status": "planned",
    }
