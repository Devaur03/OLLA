"""
Evaluation dataset (Phase 11).

A small, hand-curated set of queries spanning the categories the router cares
about. Each entry can carry optional `relevant_domains` — if present, the
label-based metrics (precision@k, nDCG@k, MRR) are computed; if absent, only
the label-free metrics run.

`expected_web_required` is the classifier's correct answer for that query, so
the harness can also score classification accuracy.

Keep this list small and high-signal. It is a smoke-level benchmark, not a
research-grade IR test collection.
"""

from dataclasses import dataclass, field


@dataclass
class EvalQuery:
    id: str
    query: str
    category: str                       # evergreen|definition|technical|comparison|recent|news|research
    expected_web_required: bool
    # Optional ground truth: domains that *should* appear in good results.
    relevant_domains: list[str] = field(default_factory=list)


EVAL_QUERIES: list[EvalQuery] = [
    # --- definitions (evergreen — memory should suffice) -----------------
    EvalQuery(
        "def-01", "what is a vector database", "definition", False,
        ["wikipedia.org", "pinecone.io", "cloudflare.com", "ibm.com"],
    ),
    EvalQuery(
        "def-02", "what is retrieval augmented generation", "definition", False,
        ["wikipedia.org", "aws.amazon.com", "nvidia.com", "ibm.com"],
    ),
    EvalQuery(
        "def-03", "what is cosine similarity", "definition", False,
        ["wikipedia.org", "geeksforgeeks.org"],
    ),
    # --- technical / how-to ----------------------------------------------
    EvalQuery(
        "tec-01", "how to install pgvector on postgres", "technical", False,
        ["github.com", "postgresql.org"],
    ),
    EvalQuery(
        "tec-02", "how to chunk documents for RAG pipelines", "technical", False,
        ["github.com", "langchain.com", "pinecone.io"],
    ),
    EvalQuery(
        "tec-03", "how does the pgvector HNSW index work", "technical", False,
        ["github.com", "postgresql.org", "crunchydata.com"],
    ),
    # --- comparisons ------------------------------------------------------
    EvalQuery(
        "cmp-01", "pgvector vs pinecone for semantic search", "comparison", False,
        ["github.com", "pinecone.io"],
    ),
    EvalQuery(
        "cmp-02", "HNSW vs IVFFlat index comparison", "comparison", False,
        ["github.com", "postgresql.org"],
    ),
    # --- evergreen general knowledge -------------------------------------
    EvalQuery(
        "evg-01", "properties of a binary search tree", "evergreen", False,
        ["wikipedia.org", "geeksforgeeks.org"],
    ),
    EvalQuery(
        "evg-02", "how does TF-IDF scoring work", "evergreen", False,
        ["wikipedia.org", "geeksforgeeks.org"],
    ),
    # --- research / deep --------------------------------------------------
    EvalQuery(
        "res-01", "comprehensive overview of reranking models in RAG", "research", False,
    ),
    EvalQuery(
        "res-02", "in-depth analysis of hybrid search architectures", "research", False,
    ),
    # --- recency-sensitive (web required) --------------------------------
    EvalQuery(
        "rec-01", "latest large language model releases", "recent", True,
    ),
    EvalQuery(
        "rec-02", "newest vector database features in 2026", "recent", True,
    ),
    EvalQuery(
        "rec-03", "current state of the art embedding models", "recent", True,
    ),
    # --- news (web required) ---------------------------------------------
    EvalQuery(
        "new-01", "breaking news on AI regulation today", "news", True,
    ),
    EvalQuery(
        "new-02", "recent announcements from the AI industry this week", "news", True,
    ),
]


def by_category() -> dict[str, list[EvalQuery]]:
    """Group the dataset by category."""
    out: dict[str, list[EvalQuery]] = {}
    for q in EVAL_QUERIES:
        out.setdefault(q.category, []).append(q)
    return out
