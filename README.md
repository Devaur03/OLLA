# Hybrid Search Agents - Complete Progress Walkthrough

This README documents the complete progress of the Hybrid Search Agents project from Phase 1 through Phase 5, including the recent integration of Citation and Credibility services.

---

## Phase 1: Web Retrieval MVP
**Brief Detail**: Building the core search, fetch, clean, chunk, and rank pipeline to create a functional web retrieval API.

### Functionality Explanation
Phase 1 focuses on creating the core synchronous pipeline. It performs an organic search on DuckDuckGo, fetches the content of the top candidate URLs concurrently, extracts clean markdown using the Jina Reader API, cleans the text of boilerplate, chunks it into overlapping pieces for RAG, and ranks the results using a custom TF-IDF and content density heuristic.

### File Update Info
- **`app/services/search_service.py`**: 
  - *Core Functionality*: Uses the `duckduckgo_search` library to fetch organic search results.
  - *Explanation*: It queries DuckDuckGo and returns a list of candidate URLs and titles.
- **`app/services/fetch_service.py`**: 
  - *Core Functionality*: Concurrently fetches content from URLs using `httpx`.
  - *Explanation*: It uses Jina Reader (`https://r.jina.ai/`) to get clean markdown from the target URLs.
- **`app/services/clean_service.py`**: 
  - *Core Functionality*: Aggressively cleans the markdown content.
  - *Explanation*: Removes images, collapses whitespace, removes code blocks and headers to create dense text.
- **`app/services/chunk_service.py`**: 
  - *Core Functionality*: Splits text into overlapping chunks.
  - *Explanation*: Ensures chunks respect paragraph boundaries and overlap by a specified amount.
- **`app/services/rank_service.py`**: 
  - *Core Functionality*: Scores and ranks results.
  - *Explanation*: Uses TF-IDF and title bonuses to score results by relevance to the query.
- **`app/api/routes/search.py`**: 
  - *Core Functionality*: Exposes the `POST /api/v1/search` endpoint.
  - *Explanation*: Orchestrates the services and returns the structured response.

### Output
The output generated in this phase is a structured JSON response containing:
- `query`: The original search query.
- `total_results`: Number of results returned.
- `results`: List of objects containing `rank`, `title`, `url`, `content`, `chunks` (with IDs and text), and `score`.

---

## Phase 2A: PostgreSQL & Vector Search
**Brief Detail**: Adding persistent storage and enabling vector search capabilities using the `pgvector` extension.

### Functionality Explanation
This phase introduces a PostgreSQL database to store search queries, results, and chunks. By using the `pgvector` extension, we enable storage of high-dimensional vector embeddings directly alongside the text chunks, paving the way for hybrid (keyword + semantic) search.

### File Update Info
- **`app/models/db/chunk.py`**: 
  - *Core Functionality*: Defines the database model for a text chunk.
  - *Explanation*: Includes a `vector` column of type `Vector` (from `pgvector`) to store embeddings.
- **`app/db/migrations/`**: 
  - *Core Functionality*: Alembic migrations.
  - *Explanation*: Scripts to create the necessary tables and enable the `pgvector` extension.
- **`app/services/store_service.py`**: 
  - *Core Functionality*: Saves pipeline results to the database.
  - *Explanation*: Inserts queries, associated results, and chunks into Postgres in a non-blocking way.

### Output
The output generated is persistent storage of search sessions. You can query the database to find previously fetched content and their scores.

---

## Phase 2B: Redis Caching
**Brief Detail**: Implementing a Redis-based caching layer to drastically reduce latency for repeated queries.

### Functionality Explanation
To avoid running the expensive fetch-and-clean pipeline for duplicate queries, a Redis cache is introduced. Before executing a search, the system checks if the results for that query are already cached. If so, it returns them immediately, bypassing search engine requests and Jina API calls.

### File Update Info
- **`app/services/cache_service.py`**: 
  - *Core Functionality*: Handles cache operations (GET, SET, EXPIRE).
  - *Explanation*: Connects to Redis and serializes/deserializes search responses.
- **`app/api/routes/search.py`**: 
  - *Core Functionality*: Cache check integration.
  - *Explanation*: Checks for a cache hit at the start of the search route and sets the cache on a miss.

### Output
- **Cache Hit**: Instantaneous response (under 50ms) returning identical structured JSON.
- **Logs**: `Cache HIT for 'query'` or `Cache MISS for 'query'`.

---

## Phase 3: Local Embeddings & Semantic Search
**Brief Detail**: Generating text embeddings locally and implementing semantic search endpoints.

### Functionality Explanation
This phase removes reliance on external embedding APIs by using a local model (`BAAI/bge-small-en-v1.5`). It adds endpoints to generate embeddings for stored chunks and to perform purely semantic vector searches using cosine similarity in PostgreSQL.

### File Update Info
- **`app/services/embed_service.py`**: 
  - *Core Functionality*: Generates embeddings using a local transformer model.
  - *Explanation*: Downloads and caches the model, then converts text strings into 384-dimensional vectors.
- **`app/api/routes/search.py`**: 
  - *Core Functionality*: Added endpoints `/embed-and-store` and `/semantic`.
  - *Explanation*: `/embed-and-store` processes chunks without embeddings, and `/semantic` finds chunks similar to a query vector.

### Output
- **`/api/v1/search/embed-and-store`**: Returns a message like `{"message":"Processed X chunks","processed":X}`.
- **`/api/v1/search/semantic`**: Returns a list of chunks ordered by similarity score.

---

## Phase 4: Model Context Protocol (MCP) Server
**Brief Detail**: Exposing the search pipeline as an MCP server for AI clients like Claude.

### Functionality Explanation
The Model Context Protocol allows AI assistants to use external tools. This phase creates an MCP server that exposes our search engine as a tool. When an AI agent needs to search the web, it can call our local server to get the top results.

### File Update Info
- **`mcp_server/server.py`**: 
  - *Core Functionality*: Implements the MCP server.
  - *Explanation*: Defines a `web_search` tool that calls our internal FastAPI endpoints over HTTP and returns the results to the MCP client.

### Output
The output is an active MCP server running on stdio that can be added to Claude Desktop's configuration file, enabling Claude to use the search tool.

---

## Phase 5: Production Docker Stack
**Brief Detail**: Containerizing the application for reliable production deployment.

### Functionality Explanation
To ensure consistent behavior across environments and simplify deployment, the entire stack (FastAPI, Postgres, Redis) is containerized using Docker and orchestrated with Docker Compose.

### File Update Info
- **`docker/Dockerfile`**: 
  - *Core Functionality*: Builds the API container.
  - *Explanation*: Installs system dependencies, Python packages (including CPU-only PyTorch), and sets up the Uvicorn production server.
- **`docker/docker-compose.yml`**: 
  - *Core Functionality*: Orchestrates the services.
  - *Explanation*: Defines the `api`, `db` (Postgres with pgvector), and `cache` (Redis) services, setting up networks, volumes, and health checks.

### Output
A running stack of 3 containers that communicate with each other. Health checks ensure the stack is only marked ready when all services are responsive.

---

## Bonus: Citation and Credibility Integration
**Brief Detail**: Enhancing responses with domain credibility scoring and structured citations.

### Functionality Explanation
This phase fulfills a key plan gap by adding a `CredibilityService` that adjusts the ranking score of results based on domain authority (e.g., official docs get a higher weight than random blogs). It also adds a `CitationService` that produces both a Markdown summary of sources and a detailed JSON list of citations with auto-generated access dates.

### File Update Info
- **`app/services/credibility_service.py`**: 
  - *Core Functionality*: Returns a credibility score (0.0–1.0) based on domain matching.
  - *Explanation*: Contains a dictionary of known high-authority domains.
- **`app/services/citation_service.py`**: 
  - *Core Functionality*: Generates APA-style and Markdown citations.
  - *Explanation*: Iterates over final search results and builds citation strings.
- **`app/models/response.py`**: 
  - *Core Functionality*: Updated `SearchResponse` model.
  - *Explanation*: Added `citations_markdown` and `citations_json` fields.
- **`app/api/routes/search.py`**: 
  - *Core Functionality*: Pipeline integration.
  - *Explanation*: Calls credibility service during ranking step and citation service before returning the response.

### Output
The final `SearchResponse` JSON now includes:
- `citations_markdown`: A generated string listing sources with relevance and retrieved date.
- `citations_json`: A list of objects containing rank, title, url, score, retrieved_date, APA format string, and markdown link.
