"""Shared FastMCP singleton — imported by all tool modules to register @mcp.tool() decorators."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent101")
