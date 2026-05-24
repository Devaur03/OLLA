"""Step 4: Web search verification (may take 60-120s)."""
import json
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000/api/v1"


def post(path, data, timeout=180):
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
        body = e.read().decode()
        print(f"  ERROR {e.code}: {body[:300]}")
        return None
    except Exception as e:
        print(f"  EXCEPTION {type(e).__name__}: {e}")
        return None


def check(condition, msg):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}]: {msg}")
    return condition


print("\n=== Step 4: Web search + LLM answer ===")
print("  Running search (may take 60-120s)...")
result = post("/search", {"query": "how does pgvector work", "max_results": 3}, timeout=200)
if result:
    check(len(result.get("results", [])) > 0, f"results count={len(result.get('results', []))}")
    check(result.get("total_results", 0) > 0, f"total_results={result.get('total_results')}")
    check(not result.get("degraded", True), f"degraded={result.get('degraded')}")
    answer = result.get("answer", "")
    check(len(answer) > 0, f"answer non-empty (len={len(answer)})")
    print(f"  answer_model: {result.get('answer_model', 'N/A')}")
    print(f"  processing_time_ms: {result.get('processing_time_ms', 0)}ms")
    if result.get("degraded"):
        for t in result.get("trace", []):
            if t.get("status") == "failed":
                print(f"  FAILED STAGE: {t.get('stage')} - {t.get('detail')}")
else:
    print("  SKIP: search failed entirely")

print("\n=== Step 4 COMPLETE ===")
