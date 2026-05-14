"""
Tests for Story 4.1: ECC tool modules initial five categories.
Run: pytest server/tools/tests/test_ecc_tools.py -v
"""
import asyncio
from pathlib import Path

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import INVALID_PARAMS

PLUGIN_DIR = Path(__file__).parent.parent.parent.parent

EXPECTED_GROUPS = {
    "ecc/web": {"web_scrape", "web_fetch"},
    "ecc/data": {"dataset_manager", "data_clean", "data_transform"},
    "ecc/presentation": {"build_pptx", "build_doc"},
    "ecc/diagrams": {"diagram_gen", "flowchart_gen"},
    "ecc/pipeline": {"pipeline_builder", "pipeline_run"},
}


def _registered_tools() -> set[str]:
    from server.tools._mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    return {tool.name for tool in tools}


@pytest.mark.parametrize("tool_group,expected_tools", EXPECTED_GROUPS.items())
def test_load_skill_tools_registers_ecc_group_tools(tool_group, expected_tools):
    from server.tools.registry import load_skill_tools

    result = load_skill_tools(tool_group)

    assert result == {
        "tool_group": tool_group,
        "status": "loaded",
        "tools": sorted(expected_tools),
    }
    assert expected_tools <= _registered_tools()


def test_load_skill_tools_unknown_category_raises_invalid_params():
    from server.tools.registry import load_skill_tools

    with pytest.raises(McpError) as excinfo:
        load_skill_tools("ecc/unknown")

    assert excinfo.value.error.code == INVALID_PARAMS
    assert excinfo.value.error.message == "Unknown skill category: ecc/unknown"
