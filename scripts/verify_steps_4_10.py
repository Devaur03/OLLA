"""Run all verification steps 4-10 against running API."""
import json
import sys
import urllib.request
import urllib.error

# Fix Windows encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000/api/v1"


def get(path):
    try:
        r = urllib.request.urlopen(f"{BASE}{path}", timeout=30)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ERROR {e.code}: {body[:300]}")
        return None
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return None


def post(path, data):
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        r = urllib.request.urlopen(req, timeout=30)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ERROR {e.code}: {body[:300]}")
        return None
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return None


def check(condition, msg):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}]: {msg}")
    return condition


# ── Step 3: Swagger ──────────────────────────────────────────────────────────
print("\n=== Step 3: Swagger /docs ===")
try:
    r = urllib.request.urlopen("http://localhost:8000/docs", timeout=5)
    check(r.status == 200, "Swagger page accessible")
except Exception as e:
    check(False, f"Swagger page: {e}")

# ── Step 4: Web search ───────────────────────────────────────────────────────
print("\n=== Step 4: Web search + LLM answer ===")
result = post("/search", {"query": "how does pgvector work", "max_results": 3})
if result:
    check(len(result.get("results", [])) > 0, f"results count={len(result.get('results', []))}")
    check(result.get("total_results", 0) > 0, f"total_results={result.get('total_results')}")
    check(not result.get("degraded", True), f"degraded={result.get('degraded')}")
    answer = result.get("answer", "")
    check(len(answer) > 0, f"answer non-empty (len={len(answer)})")
    print(f"  answer_model: {result.get('answer_model', 'N/A')}")
    if result.get("degraded"):
        print(f"  trace: {result.get('trace', [])}")
    # Save a result_id for step 10
    results = result.get("results", [])
    if results:
        rid = results[0].get("id")
        print(f"  first result_id: {rid}")
        with open("scripts/.result_id.txt", "w") as f:
            f.write(str(rid))
else:
    print("  SKIP: search failed")

# ── Step 5: Persistence ───────────────────────────────────────────────────────
print("\n=== Step 5: Persistence (DB counts) ===")
import asyncio
import asyncpg


async def check_persistence():
    conn = await asyncpg.connect("postgresql://postgres:password@localhost:5433/hybriddb")
    q_count = await conn.fetchval("SELECT count(*) FROM queries")
    r_count = await conn.fetchval("SELECT count(*) FROM results")
    c_count = await conn.fetchval("SELECT count(*) FROM chunks")
    ws_ids = await conn.fetch("SELECT DISTINCT workspace_id FROM results")
    await conn.close()
    check(q_count > 0, f"queries count={q_count}")
    check(r_count > 0, f"results count={r_count}")
    check(c_count > 0, f"chunks count={c_count}")
    for row in ws_ids:
        wid = str(row["workspace_id"])
        check(wid == "00000000-0000-0000-0000-000000000000", f"workspace_id={wid}")


asyncio.run(check_persistence())

# ── Step 6: Embed and store ───────────────────────────────────────────────────
print("\n=== Step 6: Embeddings backfill ===")
result = post("/search/embed-and-store", {})
if result:
    check("processed" in result, f"embed-and-store response: {result}")
    print(f"  processed: {result.get('processed', 'N/A')}")
else:
    print("  SKIP: embed-and-store failed")


async def check_embeddings():
    conn = await asyncpg.connect("postgresql://postgres:password@localhost:5433/hybriddb")
    count = await conn.fetchval("SELECT count(*) FROM chunks WHERE embedding IS NOT NULL")
    await conn.close()
    check(count > 0, f"chunks with embedding={count}")


asyncio.run(check_embeddings())

# ── Step 7: Semantic search ───────────────────────────────────────────────────
print("\n=== Step 7: Semantic search ===")
result = post("/search/semantic", {"query": "vector similarity", "top_k": 5})
if result:
    total = result.get("total_chunks", 0)
    check(total > 0, f"total_chunks={total}")
    if total == 0:
        print("  (Try a query closer to stored content)")
else:
    print("  SKIP: semantic search failed")

# ── Step 8: Hybrid retrieval ──────────────────────────────────────────────────
print("\n=== Step 8: Hybrid retrieval ===")
result = post("/search/hybrid", {"query": "what is a vector database", "mode": "auto"})
if result:
    check("retrieval_mode" in result, f"has retrieval_mode={result.get('retrieval_mode')}")
    check("query_class" in result, f"has query_class={result.get('query_class')}")
    check("confidence" in result, f"has confidence={result.get('confidence')}")
    check("from_memory" in result, f"has from_memory={result.get('from_memory')}")
    check("routing_trace" in result, f"has routing_trace, len={len(result.get('routing_trace', []))}")
    print(f"  mode={result.get('retrieval_mode')}, class={result.get('query_class')}, "
          f"from_memory={result.get('from_memory')}")
else:
    print("  SKIP: hybrid failed")

# Second hybrid call (cache hit)
print("\n  --- Second hybrid call (expect cache/memory hit) ---")
result2 = post("/search/hybrid", {"query": "what is a vector database", "mode": "auto"})
if result2:
    check(result2.get("from_memory", False), f"from_memory={result2.get('from_memory')} (cache hit)")
    t1 = result.get("processing_time_ms", 9999) if result else 9999
    t2 = result2.get("processing_time_ms", 9999)
    print(f"  first={t1:.0f}ms, second={t2:.0f}ms")

# Recency query
print("\n  --- Recency query ---")
result3 = post("/search/hybrid", {"query": "latest AI news today", "mode": "auto"})
if result3:
    qclass = result3.get("query_class", "")
    from_mem = result3.get("from_memory", True)
    check(qclass in ("news", "recent", "realtime"), f"query_class={qclass} (expect news/recent/realtime)")
    check(not from_mem, f"from_memory={from_mem} (expect False for recency)")

# ── Step 9: Feedback ──────────────────────────────────────────────────────────
print("\n=== Step 9: Feedback loop + insights ===")
result = post(
    "/feedback",
    {
        "level": "source",
        "feedback_type": "useful",
        "source_url": "https://github.com/pgvector/pgvector",
    },
)
if result:
    check(result.get("recorded") is True, f"recorded={result.get('recorded')}")
    effects = result.get("effects", [])
    check(len(effects) > 0, f"effects count={len(effects)}")
else:
    print("  SKIP: feedback failed")

stats = get("/feedback/stats")
if stats:
    total = stats.get("total", 0)
    check(total >= 1, f"feedback total={total}")
    check("by_type" in stats, f"has by_type")
    check("best_sources" in stats, f"has best_sources")
    print(f"  by_type: {stats.get('by_type', {})}")

# ── Step 10: Sources + admin ──────────────────────────────────────────────────
print("\n=== Step 10: Sources + admin endpoints ===")

r = get("/sources/recent-queries")
check(r is not None, "GET /sources/recent-queries")

r = get("/sources/trusted-domains")
check(r is not None, "GET /sources/trusted-domains")

try:
    with open("scripts/.result_id.txt") as f:
        rid = f.read().strip()
    r = get(f"/sources/{rid}")
    check(r is not None, f"GET /sources/{rid}")
except FileNotFoundError:
    print("  SKIP /sources/{id}: no result_id saved (Step 4 may have failed)")

r = get("/admin/retention/stats")
check(r is not None, "GET /admin/retention/stats")
if r:
    print(f"  retention stats: {r}")

r = get("/admin/export")
check(r is not None, "GET /admin/export")
if r:
    sections = list(r.keys())
    check("sources" in r and "feedback" in r and "queries" in r, f"export sections={sections}")

print("\n=== Steps 4-10 complete ===")
