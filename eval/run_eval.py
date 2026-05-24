"""
Evaluation runner + benchmark report (Phase 11).

Runs every query in `eval/dataset.py` through three retrieval paths and writes
a markdown benchmark report comparing them:

    web         — POST /search            (always crawls; the baseline)
    hybrid_cold — POST /search/hybrid      (first call — populates memory/cache)
    hybrid_warm — POST /search/hybrid      (second call — should hit cache/memory)

The web → hybrid_warm pair is the "before/after" the plan asks for: it shows
the latency win from cache-first / memory-first routing.

Usage (FastAPI backend must be running on :8000):

    python -m eval.run_eval
    python -m eval.run_eval --host http://localhost:8000 --k 5
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from eval import metrics
from eval.dataset import EVAL_QUERIES, EvalQuery

# localhost calls must never traverse a proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(host: str, path: str, payload: dict, method: str = "POST") -> dict:
    """POST/GET against the API. Raises RuntimeError on any failure."""
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(host + path, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=180) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach {host} ({e.reason})") from e


def _timed(fn) -> tuple[dict | None, float, str | None]:
    """Run `fn`, returning (response, elapsed_ms, error)."""
    start = time.monotonic()
    try:
        resp = fn()
        return resp, (time.monotonic() - start) * 1000.0, None
    except Exception as e:  # noqa: BLE001
        return None, (time.monotonic() - start) * 1000.0, str(e)


def run_query(host: str, q: EvalQuery, k: int) -> dict:
    """Run one query through all three paths and score it."""
    record: dict = {"id": q.id, "query": q.query, "category": q.category,
                    "expected_web_required": q.expected_web_required}

    # --- web baseline -------------------------------------------------
    web, web_ms, web_err = _timed(
        lambda: _request(host, "/api/v1/search", {"query": q.query, "max_results": k})
    )
    record["web"] = _score(web, web_ms, web_err, q, k)

    # --- hybrid cold + warm ------------------------------------------
    hpayload = {"query": q.query, "mode": "auto", "max_results": k}
    cold, cold_ms, cold_err = _timed(
        lambda: _request(host, "/api/v1/search/hybrid", hpayload)
    )
    record["hybrid_cold"] = _score(cold, cold_ms, cold_err, q, k)

    warm, warm_ms, warm_err = _timed(
        lambda: _request(host, "/api/v1/search/hybrid", hpayload)
    )
    record["hybrid_warm"] = _score(warm, warm_ms, warm_err, q, k)

    # classification correctness comes from the hybrid response
    resp = cold or warm
    if resp is not None and "web_required" in resp:
        record["classification_correct"] = (
            bool(resp["web_required"]) == q.expected_web_required
        )
    else:
        record["classification_correct"] = None
    return record


def _score(resp: dict | None, elapsed_ms: float, err: str | None,
           q: EvalQuery, k: int) -> dict:
    """Turn one API response into a per-query metric row."""
    if resp is None:
        return {"ok": False, "error": err, "latency_ms": round(elapsed_ms, 1)}

    results = resp.get("results", []) or []
    urls = [r.get("url", "") for r in results]
    answer = resp.get("answer", "") or ""

    row = {
        "ok": True,
        "latency_ms": round(elapsed_ms, 1),
        "result_count": len(results),
        "has_answer": bool(answer.strip()),
        "citation_support": metrics.citation_support_rate(answer, results),
        "cache_hit": bool(resp.get("cache_hit", False)),
        # hybrid-only fields (absent on /search → default safely)
        "retrieval_mode": resp.get("retrieval_mode"),
        "from_memory": resp.get("from_memory"),
        "confidence": resp.get("confidence"),
    }
    if q.relevant_domains:
        row["precision_at_k"] = metrics.precision_at_k(urls, q.relevant_domains, k)
        row["ndcg_at_k"] = metrics.ndcg_at_k(urls, q.relevant_domains, k)
        row["mrr"] = metrics.mrr(urls, q.relevant_domains)
    return row


# ----------------------------------------------------------- aggregation

def _collect(records: list[dict], path: str, field: str) -> list[float]:
    """All non-None numeric values of `field` from successful `path` rows."""
    out = []
    for r in records:
        row = r.get(path, {})
        if row.get("ok") and row.get(field) is not None:
            out.append(float(row[field]))
    return out


def aggregate(records: list[dict]) -> dict:
    """Build the aggregate stats for every retrieval path."""
    agg: dict = {}
    for path in ("web", "hybrid_cold", "hybrid_warm"):
        oks = [r for r in records if r.get(path, {}).get("ok")]
        lat = _collect(records, path, "latency_ms")
        agg[path] = {
            "runs": len(records),
            "ok": len(oks),
            "latency_mean_ms": metrics.mean(lat),
            "latency_p50_ms": metrics.percentile(lat, 50),
            "latency_p95_ms": metrics.percentile(lat, 95),
            "answer_rate": metrics.mean(
                [1.0 if r[path].get("has_answer") else 0.0 for r in oks]
            ),
            "mean_results": metrics.mean(_collect(records, path, "result_count")),
            "citation_support": metrics.mean(_collect(records, path, "citation_support")),
            "precision_at_k": metrics.mean(_collect(records, path, "precision_at_k")),
            "ndcg_at_k": metrics.mean(_collect(records, path, "ndcg_at_k")),
            "mrr": metrics.mean(_collect(records, path, "mrr")),
        }

    # hybrid-specific signals (from the warm run)
    warm_oks = [r for r in records if r.get("hybrid_warm", {}).get("ok")]
    agg["hybrid_warm"]["from_memory_rate"] = metrics.mean(
        [1.0 if r["hybrid_warm"].get("from_memory") else 0.0 for r in warm_oks]
    )
    modes: dict[str, int] = {}
    for r in warm_oks:
        m = r["hybrid_warm"].get("retrieval_mode") or "?"
        modes[m] = modes.get(m, 0) + 1
    agg["hybrid_warm"]["mode_distribution"] = modes

    cls = [r["classification_correct"] for r in records
           if r.get("classification_correct") is not None]
    agg["classification_accuracy"] = (
        round(sum(1 for c in cls if c) / len(cls), 4) if cls else 0.0
    )

    # headline before/after: web baseline vs warm hybrid
    web_lat = agg["web"]["latency_mean_ms"]
    warm_lat = agg["hybrid_warm"]["latency_mean_ms"]
    agg["latency_speedup"] = round(web_lat / warm_lat, 2) if warm_lat else 0.0
    return agg


# --------------------------------------------------------------- report

def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def write_report(records: list[dict], agg: dict, path: str) -> None:
    """Render the markdown benchmark report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = []
    L.append("# Retrieval Benchmark Report")
    L.append("")
    L.append(f"> Generated {now} · {len(records)} queries · "
             "Phase 11 evaluation harness")
    L.append("")

    L.append("## Headline")
    L.append("")
    L.append(f"- **Latency speedup (web → warm hybrid):** {agg['latency_speedup']}×")
    L.append(f"  ({agg['web']['latency_mean_ms']:.0f} ms → "
             f"{agg['hybrid_warm']['latency_mean_ms']:.0f} ms mean)")
    L.append(f"- **Memory-served rate (warm hybrid):** "
             f"{_pct(agg['hybrid_warm']['from_memory_rate'])} of queries answered "
             "from local memory without a web crawl")
    L.append(f"- **Query classification accuracy:** "
             f"{_pct(agg['classification_accuracy'])}")
    L.append("")

    L.append("## Path comparison")
    L.append("")
    L.append("| Metric | web (baseline) | hybrid cold | hybrid warm |")
    L.append("|---|---|---|---|")
    rows = [
        ("queries ok", "ok"),
        ("latency mean (ms)", "latency_mean_ms"),
        ("latency p50 (ms)", "latency_p50_ms"),
        ("latency p95 (ms)", "latency_p95_ms"),
        ("answer rate", "answer_rate"),
        ("mean results", "mean_results"),
        ("citation support", "citation_support"),
        ("precision@k", "precision_at_k"),
        ("nDCG@k", "ndcg_at_k"),
        ("MRR", "mrr"),
    ]
    for label, key in rows:
        w = agg["web"][key]
        c = agg["hybrid_cold"][key]
        h = agg["hybrid_warm"][key]
        if key in ("answer_rate", "citation_support", "precision_at_k",
                   "ndcg_at_k", "mrr"):
            L.append(f"| {label} | {w:.3f} | {c:.3f} | {h:.3f} |")
        else:
            L.append(f"| {label} | {w} | {c} | {h} |")
    L.append("")

    L.append("## Hybrid routing")
    L.append("")
    L.append("Retrieval mode chosen (warm run):")
    L.append("")
    for mode, n in sorted(agg["hybrid_warm"]["mode_distribution"].items(),
                          key=lambda kv: -kv[1]):
        L.append(f"- `{mode}` — {n}")
    L.append("")

    L.append("## Per-query detail")
    L.append("")
    L.append("| id | category | web ms | warm ms | mode | from memory | "
             "p@k | classified |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in records:
        web = r.get("web", {})
        warm = r.get("hybrid_warm", {})
        p = warm.get("precision_at_k")
        cls = r.get("classification_correct")
        L.append(
            f"| {r['id']} | {r['category']} "
            f"| {web.get('latency_ms', '-')} "
            f"| {warm.get('latency_ms', '-')} "
            f"| {warm.get('retrieval_mode') or '-'} "
            f"| {warm.get('from_memory')} "
            f"| {p if p is not None else '-'} "
            f"| {'✓' if cls else ('✗' if cls is False else '-')} |"
        )
    L.append("")

    failures = [r for r in records
                if not r.get("web", {}).get("ok")
                or not r.get("hybrid_warm", {}).get("ok")]
    if failures:
        L.append("## Failures")
        L.append("")
        for r in failures:
            for path in ("web", "hybrid_cold", "hybrid_warm"):
                row = r.get(path, {})
                if not row.get("ok"):
                    L.append(f"- `{r['id']}` {path}: {row.get('error')}")
        L.append("")

    L.append("---")
    L.append("")
    L.append("Notes: precision@k / nDCG@k / MRR use domain-level relevance "
             "labels from `eval/dataset.py` and are averaged only over labelled "
             "queries. Citation support is a vocabulary-overlap heuristic, not "
             "a factual-entailment check.")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ----------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="Run the retrieval benchmark.")
    p.add_argument("--host", default="http://localhost:8000", help="API host")
    p.add_argument("--k", type=int, default=5, help="results per query")
    p.add_argument("--out", default="eval/benchmark_report.md",
                   help="report output path")
    p.add_argument("--limit", type=int, default=0,
                   help="run only the first N queries (0 = all)")
    args = p.parse_args()

    # fail fast if the backend is unreachable
    try:
        _request(args.host, "/api/v1/health", None, method="GET")
    except RuntimeError as e:
        print(f"  Backend not reachable: {e}", file=sys.stderr)
        print(f"  Start it first:  uvicorn app.main:app --port 8000", file=sys.stderr)
        return 1

    queries = EVAL_QUERIES[: args.limit] if args.limit else EVAL_QUERIES
    print(f"Running {len(queries)} queries against {args.host} ...")
    records = []
    for i, q in enumerate(queries, start=1):
        print(f"  [{i}/{len(queries)}] {q.id}: {q.query}")
        records.append(run_query(args.host, q, args.k))

    agg = aggregate(records)
    write_report(records, agg, args.out)
    print()
    print(f"Latency speedup (web → warm hybrid): {agg['latency_speedup']}x")
    print(f"Memory-served rate: {_pct(agg['hybrid_warm']['from_memory_rate'])}")
    print(f"Classification accuracy: {_pct(agg['classification_accuracy'])}")
    print(f"Report written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
