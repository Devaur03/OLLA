"""
MCP server — exposes the hybrid-search backend as agent-callable tools.

Tools:
  web_search       — full web crawl: search → fetch → clean → chunk → rank
  semantic_search  — vector similarity over the local knowledge base
  hybrid_search    — confidence-routed retrieval (cache → memory → web)
  submit_feedback  — record feedback on an answer / citation / chunk / source

Each tool is a thin proxy to the running FastAPI backend. The backend must be
up on localhost:8000 before this MCP server starts.
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

# The FastAPI backend URL — must be running before starting this MCP server.
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
                "suitable for AI agent grounding and RAG pipelines. Always "
                "performs a live crawl. Returns structured JSON with title, "
                "URL, clean text, text chunks, and relevance scores. Use this "
                "when you specifically need fresh web results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
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
                "without making new web requests. Fast (<100ms). Use this when "
                "you want related content from past searches."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The semantic search query"},
                    "top_k": {
                        "type": "integer",
                        "description": "Number of similar chunks to return",
                        "default": 10,
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum similarity threshold (0.0-1.0)",
                        "default": 0.6,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="hybrid_search",
            description=(
                "Confidence-routed retrieval — the recommended default tool. "
                "Classifies the query, checks cache and local semantic memory "
                "first, and only crawls the web when memory confidence is low, "
                "the stored content is stale, or the query is recency-sensitive "
                "(news / 'latest'). Returns an answer with citations plus the "
                "retrieval_mode used, a confidence score, and a routing_trace "
                "explaining every decision. Prefer this over web_search unless "
                "you explicitly need a fresh crawl."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The question to answer"},
                    "mode": {
                        "type": "string",
                        "description": (
                            "Retrieval mode. 'auto' lets the router decide; "
                            "'fast' = cache+memory only; 'fresh' = always crawl; "
                            "'hybrid' = memory first, web fallback; "
                            "'deep' = wide web crawl for research."
                        ),
                        "enum": ["auto", "fast", "fresh", "hybrid", "deep"],
                        "default": "auto",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Chunks from memory / results to crawl",
                        "default": 8,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "force_refresh": {
                        "type": "boolean",
                        "description": "Skip cache and memory; always crawl the web",
                        "default": False,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="submit_feedback",
            description=(
                "Record feedback on a retrieval result so future ranking "
                "improves. Feedback can target an answer, a citation, a "
                "specific chunk, or a source domain. Useful feedback boosts a "
                "chunk's usefulness and a domain's trust; negative feedback "
                "lowers them; 'outdated' flags the source for a refresh. "
                "Feedback never edits stored content — only ranking signals."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "description": "What the feedback is attached to",
                        "enum": ["answer", "citation", "chunk", "source"],
                    },
                    "feedback_type": {
                        "type": "string",
                        "description": "The feedback signal",
                        "enum": [
                            "useful",
                            "not_useful",
                            "incorrect",
                            "outdated",
                            "bad_source",
                            "missing_context",
                        ],
                    },
                    "query_id": {
                        "type": "string",
                        "description": "Related query UUID (required for level=answer)",
                    },
                    "result_id": {
                        "type": "string",
                        "description": "Related result UUID (for level=citation/source)",
                    },
                    "chunk_id": {
                        "type": "string",
                        "description": "Related chunk UUID (required for level=chunk)",
                    },
                    "source_url": {
                        "type": "string",
                        "description": "Related source URL (for level=citation/source)",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Optional free-text note",
                    },
                },
                "required": ["level", "feedback_type"],
            },
        ),
        types.Tool(
            name="graph_search",
            description=(
                "Multi-hop knowledge-graph retrieval. Seeds from vector "
                "similarity, then traverses semantic-similarity edges between "
                "stored chunks to surface related context the query did not "
                "name directly. Use for exploratory 'what connects to this' "
                "questions over the local knowledge base."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The graph search query"},
                    "hops": {
                        "type": "integer",
                        "description": "Edges to traverse from each seed (1-4)",
                        "default": 2,
                        "minimum": 1,
                        "maximum": 4,
                    },
                    "seed_k": {
                        "type": "integer",
                        "description": "Seed chunks selected by vector similarity",
                        "default": 5,
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Max chunks to return",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="feedback_stats",
            description=(
                "Read aggregate feedback analytics: total feedback events, "
                "satisfaction rate, a breakdown by type, and the highest- and "
                "lowest-trust source domains. Takes no arguments. Use to gauge "
                "how well the retrieval system is performing over time."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_source",
            description=(
                "Read one stored source back out of the knowledge base by its "
                "result ID — title, URL, cleaned content, chunks, and the "
                "freshness / trust signals attached to it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "result_id": {
                        "type": "string",
                        "description": "The stored result's UUID",
                    },
                },
                "required": ["result_id"],
            },
        ),
        types.Tool(
            name="refresh_source",
            description=(
                "Re-crawl a stored source's URL and replace its cleaned content "
                "and chunks with fresh ones. Use when a source has been flagged "
                "outdated or you need its latest state."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "result_id": {
                        "type": "string",
                        "description": "The stored result's UUID to refresh",
                    },
                },
                "required": ["result_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls from AI agents."""
    handlers = {
        "web_search": _handle_web_search,
        "semantic_search": _handle_semantic_search,
        "hybrid_search": _handle_hybrid_search,
        "submit_feedback": _handle_submit_feedback,
        "graph_search": _handle_graph_search,
        "feedback_stats": _handle_feedback_stats,
        "get_source": _handle_get_source,
        "refresh_source": _handle_refresh_source,
    }
    handler = handlers.get(name)
    if handler is None:
        return _error(f"Unknown tool: {name}")
    return await handler(arguments)


def _text(payload: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=payload)]


def _error(message: str, detail: str | None = None) -> list[types.TextContent]:
    err = {"error": message}
    if detail:
        err["detail"] = detail
    return _text(json.dumps(err))


async def _call(
    method: str, path: str, payload: dict | None, timeout: float
) -> list[types.TextContent]:
    """Call the backend (GET or POST) and proxy the response to the agent."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                response = await client.get(f"{BACKEND_URL}{path}")
            else:
                response = await client.post(f"{BACKEND_URL}{path}", json=payload)
            response.raise_for_status()
        return _text(response.text)
    except httpx.ConnectError:
        return _error(
            "Cannot connect to the OLLA backend",
            f"Is the FastAPI server running at {BACKEND_URL}?",
        )
    except httpx.HTTPStatusError as e:
        return _error(
            f"Backend returned HTTP {e.response.status_code}",
            e.response.text[:500],
        )
    except Exception as e:  # noqa: BLE001
        return _error(str(e))


async def _post(path: str, payload: dict, timeout: float) -> list[types.TextContent]:
    """POST to the backend and proxy the response back to the agent."""
    return await _call("POST", path, payload, timeout)


async def _get(path: str, timeout: float) -> list[types.TextContent]:
    """GET from the backend and proxy the response back to the agent."""
    return await _call("GET", path, None, timeout)


async def _handle_web_search(arguments: dict) -> list[types.TextContent]:
    payload = {
        "query": arguments["query"],
        "max_results": arguments.get("max_results", 5),
        "chunk_size": arguments.get("chunk_size", 500),
    }
    return await _post("/search", payload, timeout=60.0)


async def _handle_semantic_search(arguments: dict) -> list[types.TextContent]:
    payload = {
        "query": arguments["query"],
        "top_k": arguments.get("top_k", 10),
        "min_similarity": arguments.get("min_similarity", 0.6),
    }
    return await _post("/search/semantic", payload, timeout=30.0)


async def _handle_hybrid_search(arguments: dict) -> list[types.TextContent]:
    payload = {
        "query": arguments["query"],
        "mode": arguments.get("mode", "auto"),
        "top_k": arguments.get("top_k", 8),
        "force_refresh": arguments.get("force_refresh", False),
    }
    # Hybrid may fall through to a web crawl, so allow the longer timeout.
    return await _post("/search/hybrid", payload, timeout=60.0)


async def _handle_submit_feedback(arguments: dict) -> list[types.TextContent]:
    if "level" not in arguments or "feedback_type" not in arguments:
        return _error("submit_feedback requires 'level' and 'feedback_type'")
    payload = {
        "level": arguments["level"],
        "feedback_type": arguments["feedback_type"],
        "query_id": arguments.get("query_id"),
        "result_id": arguments.get("result_id"),
        "chunk_id": arguments.get("chunk_id"),
        "source_url": arguments.get("source_url"),
        "comment": arguments.get("comment"),
    }
    return await _post("/feedback", payload, timeout=30.0)


async def _handle_graph_search(arguments: dict) -> list[types.TextContent]:
    payload = {
        "query": arguments["query"],
        "hops": arguments.get("hops", 2),
        "seed_k": arguments.get("seed_k", 5),
        "top_k": arguments.get("top_k", 20),
    }
    return await _post("/search/graph", payload, timeout=45.0)


async def _handle_feedback_stats(arguments: dict) -> list[types.TextContent]:
    return await _get("/feedback/stats", timeout=20.0)


async def _handle_get_source(arguments: dict) -> list[types.TextContent]:
    return await _get(f"/sources/{arguments['result_id']}", timeout=20.0)


async def _handle_refresh_source(arguments: dict) -> list[types.TextContent]:
    return await _post(f"/sources/{arguments['result_id']}/refresh", {}, timeout=90.0)


# --- MCP resources --------------------------------------------------------
# Read-only views an agent can browse without calling a tool.
_RESOURCES: dict[str, tuple[str, str, str]] = {
    "hybrid-search://trusted-domains": (
        "/sources/trusted-domains",
        "Trusted domains",
        "Learned per-domain trust ranking",
    ),
    "hybrid-search://recent-queries": (
        "/sources/recent-queries",
        "Recent queries",
        "Recent query history with result counts",
    ),
    "hybrid-search://retrieval-stats": (
        "/feedback/stats",
        "Retrieval stats",
        "Aggregate feedback analytics and source quality",
    ),
}


@server.list_resources()
async def list_resources() -> list[types.Resource]:
    """Declare the read-only resources an agent can browse."""
    return [
        types.Resource(
            uri=uri,
            name=name,
            description=desc,
            mimeType="application/json",
        )
        for uri, (_, name, desc) in _RESOURCES.items()
    ]


@server.read_resource()
async def read_resource(uri) -> str:
    """Resolve a resource URI to JSON by proxying the backing endpoint."""
    entry = _RESOURCES.get(str(uri))
    if not entry:
        return json.dumps({"error": f"Unknown resource: {uri}"})
    result = await _get(entry[0], timeout=20.0)
    return result[0].text if result else "{}"


async def main():
    """Run the MCP server over stdio."""
    logger.info("Starting OLLA MCP Server")
    logger.info("Backend URL: %s", BACKEND_URL)
    logger.info(
        "Tools: web_search, semantic_search, hybrid_search, "
        "submit_feedback, graph_search, feedback_stats, "
        "get_source, refresh_source"
    )
    logger.info("Resources: trusted-domains, recent-queries, retrieval-stats")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
