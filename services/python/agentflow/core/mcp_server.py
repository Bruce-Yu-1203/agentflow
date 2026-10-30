"""Local MCP endpoint for approved knowledge diagnostics."""

from typing import Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from agentflow.core.knowledge import KnowledgeStore


def build_mcp_server(get_knowledge: Callable[[], KnowledgeStore]) -> FastMCP:
    server = FastMCP("AgentFlow Knowledge")

    @server.tool(name="search_knowledge_base", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
    async def search_knowledge_base(query: str, top_k: int = 5) -> dict:
        """Search approved knowledge and return source metadata."""
        return {"results": await get_knowledge().search(query, top_k)}

    @server.tool(name="knowledge_stats", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
    async def knowledge_stats() -> dict:
        """Return the number of indexed knowledge chunks."""
        return {"total_chunks": await get_knowledge().count()}

    return server
