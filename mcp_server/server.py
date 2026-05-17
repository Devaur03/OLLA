"""
MCP Server for Hybrid Search Agents.

How it works:
- The MCP server exposes two tools: `web_search` and `semantic_search`
- When called by an AI agent, it posts to the local FastAPI server
- The FastAPI server runs the full pipeline and returns JSON
- The MCP server returns the JSON string back to the agent

To use with Claude Desktop:
1. Start the FastAPI server: uvicorn app.main:app --port 8000
2. Run this MCP server: python -m mcp_server.server
3. Add to claude_desktop_config.json:

{
  "mcpServers": {
    "hybrid-search": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/hybrid-search-agents"
    }
  }
}
"""

import asyncio
import json
import logging
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The FastAPI backend URL — must be running before starting this MCP server
BACKEND_URL = "http://localhost:8000/api/v1"

server = Server("hybrid-search-agents")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Declare the tools this MCP server provides."""
    return [
        types.Tool(
            name="web_search",
            description=(
                "Search the web and return clean, chunked, ranked content "
                "suitable for AI agent grounding and RAG pipelines. "
                "Returns structured JSON with title, URL, clean text, "
                "text chunks, and relevance scores for each result."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of web pages to retrieve (1-10)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "chunk_size": {
                        "type": "integer",
                        "description": "Target character size for each text chunk",
                        "default": 500,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="semantic_search",
            description=(
                "Search previously retrieved content using vector similarity. "
                "Finds semantically relevant chunks from the knowledge base "
                "without making new web requests. Fast (<100ms). "
                "Use this when you want to find related content from past searches."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The semantic search query",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of similar chunks to return",
                        "default": 10,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity threshold (0.0–1.0)",
                        "default": 0.6,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str,
    arguments: dict,
) -> list[types.TextContent]:
    """Handle tool calls from AI agents."""

    if name == "web_search":
        return await _handle_web_search(arguments)
    elif name == "semantic_search":
        return await _handle_semantic_search(arguments)
    else:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]


async def _handle_web_search(arguments: dict) -> list[types.TextContent]:
    """Handle web_search tool call."""
    try:
        payload = {
            "query": arguments["query"],
            "max_results": arguments.get("max_results", 5),
            "chunk_size": arguments.get("chunk_size", 500),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/search",
                json=payload,
            )
            response.raise_for_status()

        return [types.TextContent(type="text", text=response.text)]

    except httpx.ConnectError:
        error = {
            "error": "Cannot connect to Hybrid Search backend",
            "detail": f"Is the FastAPI server running at {BACKEND_URL}?",
        }
        return [types.TextContent(type="text", text=json.dumps(error))]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def _handle_semantic_search(arguments: dict) -> list[types.TextContent]:
    """Handle semantic_search tool call."""
    try:
        payload = {
            "query": arguments["query"],
            "top_k": arguments.get("top_k", 10),
            "min_similarity": arguments.get("min_similarity", 0.6),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/search/semantic",
                json=payload,
            )
            response.raise_for_status()

        return [types.TextContent(type="text", text=response.text)]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def main():
    """Run the MCP server over stdio."""
    logger.info("Starting Hybrid Search MCP Server")
    logger.info(f"Backend URL: {BACKEND_URL}")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
