"""ECC pipeline tools."""
from .._mcp import mcp


@mcp.tool()
def pipeline_builder(name: str, stages: list[str]) -> dict:
    """Plan a pipeline definition from named stages."""
    return {
        "tool": "pipeline_builder",
        "name": name,
        "stages": stages,
        "status": "planned",
    }


@mcp.tool()
def pipeline_run(pipeline_id: str, dry_run: bool = True) -> dict:
    """Plan or request a pipeline run."""
    return {
        "tool": "pipeline_run",
        "pipeline_id": pipeline_id,
        "dry_run": dry_run,
        "status": "planned",
    }
