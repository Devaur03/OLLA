"""Steps 8 and 10 verification — using stored queries to avoid web crawl."""
import json
import sys
import urllib.request
import urllib.error
import asyncio
import asyncpg

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


# Step 8: Hybrid retrieval using a KNOWN query (pgvector — stored in memory)
print("\n=== Step 8: Hybrid retrieval ===")
print("  Query: 'how does pgvector work' (expected to come from memory)")
result = post("/search/hybrid", {"query": "how does pgvector work", "mode": "auto"}, timeout=60)
if result:
    check("retrieval_mode" in result, f"has retrieval_mode={result.get('retrieval_mode')}")
    check("query_class" in result, f"has query_class={result.get('query_class')}")
    check("confidence" in result, f"has confidence={result.get('confidence', 0):.2f}")
    check("from_memory" in result, f"has from_memory={result.get('from_memory')}")
    check("routing_trace" in result, f"has routing_trace len={len(result.get('routing_trace', []))}")
    print(f"  mode={result.get('retrieval_mode')}, class={result.get('query_class')}, "
          f"from_memory={result.get('from_memory')}, conf={result.get('confidence', 0):.2f}")
    print(f"  routing_trace:")
    for t in result.get("routing_trace", []):
        print(f"    - {t}")
    
    # Second call — should be cache hit
    print("\n  --- Second hybrid call (expect cache/memory hit) ---")
    result2 = post("/search/hybrid", {"query": "how does pgvector work", "mode": "auto"}, timeout=30)
    if result2:
        check(result2.get("from_memory", False), f"from_memory={result2.get('from_memory')} (cache hit)")
        t1 = result.get("processing_time_ms", 9999)
        t2 = result2.get("processing_time_ms", 9999)
        print(f"  first={t1}ms, second={t2}ms")
        if t1 > t2:
            check(True, f"second call faster ({t2}ms < {t1}ms)")
        else:
            print(f"  Note: second call not faster (both from memory, similar time)")
else:
    print("  SKIP: hybrid failed")


# Step 10 remaining: trusted-domains, sources/{id}, admin/export
print("\n=== Step 10: Remaining endpoints ===")


async def get_result_id():
    conn = await asyncpg.connect("postgresql://postgres:password@localhost:5433/hybriddb")
    rid = await conn.fetchval("SELECT id FROM results LIMIT 1")
    await conn.close()
    return str(rid)


rid = asyncio.run(get_result_id())
print(f"  Using result_id: {rid[:8]}...")

r = get("/sources/trusted-domains", timeout=10)
check(r is not None, "GET /sources/trusted-domains")
if r:
    domains = r.get("domains", r) if isinstance(r, dict) else r
    print(f"  trusted-domains: {domains}")

r = get(f"/sources/{rid}", timeout=10)
check(r is not None, f"GET /sources/{rid[:8]}...")
if r:
    print(f"  source url: {r.get('url', r.get('result', {}).get('url', 'N/A'))[:60]}")

r = get("/admin/retention/stats", timeout=10)
check(r is not None, "GET /admin/retention/stats")
if r:
    print(f"  retention stats: {r}")

r = get("/admin/export", timeout=15)
check(r is not None, "GET /admin/export")
if r:
    sections = list(r.keys())
    check("sources" in r and "feedback" in r and "queries" in r, f"export sections={sections}")

print("\n=== Steps 8+10 COMPLETE ===")
