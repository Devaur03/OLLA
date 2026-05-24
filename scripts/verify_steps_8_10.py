"""Steps 8-10 verification — run these after server has recovered."""
import json
import sys
import urllib.request
import urllib.error
import asyncio
import asyncpg
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000/api/v1"


def get(path, timeout=15):
    try:
        r = urllib.request.urlopen(f"{BASE}{path}", timeout=timeout)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  ERROR {e.code}: {e.read().decode()[:300]}")
        return None
    except Exception as e:
        print(f"  EXCEPTION {type(e).__name__}: {e}")
        return None


def post(path, data, timeout=30):
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  ERROR {e.code}: {e.read().decode()[:300]}")
        return None
    except Exception as e:
        print(f"  EXCEPTION {type(e).__name__}: {e}")
        return None


def check(condition, msg):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}]: {msg}")
    return condition


# Quick health check first
print("\n=== Health check ===")
h = get("/health", timeout=5)
check(h is not None and h.get("status") == "ok", f"health={h.get('status') if h else 'down'}")


# Step 8: Hybrid retrieval
print("\n=== Step 8: Hybrid retrieval ===")
result = post("/search/hybrid", {"query": "what is a vector database", "mode": "auto"}, timeout=30)
if result:
    check("retrieval_mode" in result, f"has retrieval_mode={result.get('retrieval_mode')}")
    check("query_class" in result, f"has query_class={result.get('query_class')}")
    check("confidence" in result, f"has confidence={result.get('confidence'):.2f}")
    check("from_memory" in result, f"has from_memory={result.get('from_memory')}")
    check("routing_trace" in result, f"has routing_trace len={len(result.get('routing_trace', []))}")
    print(f"  mode={result.get('retrieval_mode')}, class={result.get('query_class')}, "
          f"from_memory={result.get('from_memory')}, conf={result.get('confidence', 0):.2f}")
    print(f"  routing_trace: {result.get('routing_trace', [])[:2]}")
    
    # Second call — cache hit
    print("\n  --- Second hybrid call (expect cache/memory hit) ---")
    result2 = post("/search/hybrid", {"query": "what is a vector database", "mode": "auto"}, timeout=15)
    if result2:
        check(result2.get("from_memory", False), f"from_memory={result2.get('from_memory')} (cache hit)")
        t1 = result.get("processing_time_ms", 9999)
        t2 = result2.get("processing_time_ms", 9999)
        print(f"  first={t1}ms, second={t2}ms")
else:
    print("  SKIP: hybrid failed")

# Recency query
print("\n  --- Recency query ---")
result3 = post("/search/hybrid", {"query": "latest AI news today 2025", "mode": "auto"}, timeout=30)
if result3:
    qclass = result3.get("query_class", "")
    from_mem = result3.get("from_memory", True)
    check(qclass in ("news", "recent", "realtime"), f"query_class={qclass} (expect news/recent/realtime)")
    check(not from_mem, f"from_memory={from_mem} (expect False for recency)")
    print(f"  mode={result3.get('retrieval_mode')}, class={qclass}")
else:
    print("  SKIP: recency hybrid failed")

# Step 9: Feedback
print("\n=== Step 9: Feedback loop + insights ===")
result = post(
    "/feedback",
    {
        "level": "source",
        "feedback_type": "useful",
        "source_url": "https://github.com/pgvector/pgvector",
    },
    timeout=10,
)
if result:
    check(result.get("recorded") is True, f"recorded={result.get('recorded')}")
    effects = result.get("effects", [])
    check(len(effects) > 0, f"effects count={len(effects)}")
    print(f"  effects: {effects}")
else:
    print("  SKIP: feedback failed")

stats = get("/feedback/stats", timeout=10)
if stats:
    total = stats.get("total", 0)
    check(total >= 1, f"feedback total={total}")
    check("by_type" in stats, "has by_type")
    check("best_sources" in stats, "has best_sources")
    print(f"  by_type: {stats.get('by_type', {})}")
    print(f"  best_sources: {[s.get('domain') for s in stats.get('best_sources', [])]}")

# Step 10: Sources + admin
print("\n=== Step 10: Sources + admin endpoints ===")


async def get_result_id():
    conn = await asyncpg.connect("postgresql://postgres:password@localhost:5433/hybriddb")
    rid = await conn.fetchval("SELECT id FROM results LIMIT 1")
    await conn.close()
    return str(rid)


rid = asyncio.run(get_result_id())
print(f"  Using result_id: {rid[:8]}...")

r = get("/sources/recent-queries", timeout=10)
check(r is not None, "GET /sources/recent-queries")
if r:
    print(f"  recent-queries: {len(r) if isinstance(r, list) else r}")

r = get("/sources/trusted-domains", timeout=10)
check(r is not None, "GET /sources/trusted-domains")
if r:
    domains = [d.get("domain") for d in r] if isinstance(r, list) else r
    print(f"  trusted-domains: {domains}")

r = get(f"/sources/{rid}", timeout=10)
check(r is not None, f"GET /sources/{rid[:8]}...")
if r:
    print(f"  source result url: {r.get('url', 'N/A')[:60]}")

r = get("/admin/retention/stats", timeout=10)
check(r is not None, "GET /admin/retention/stats")
if r:
    print(f"  retention stats: {r}")

r = get("/admin/export", timeout=10)
check(r is not None, "GET /admin/export")
if r:
    sections = list(r.keys())
    check("sources" in r and "feedback" in r and "queries" in r, f"export sections={sections}")

print("\n=== Steps 8-10 COMPLETE ===")
