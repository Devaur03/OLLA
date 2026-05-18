#!/usr/bin/env python3
"""
hybrid-search CLI -- query the Hybrid Search API from your terminal.

Usage:
  hybrid-search "how does pgvector work"
  hybrid-search "RAG pipelines" --top 5 --semantic
  hybrid-search "vector similarity" --json
  hybrid-search --health
"""

import argparse
import json
import sys
import urllib.request
import urllib.error


DEFAULT_HOST = "http://localhost:8000"

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_CYAN  = "\033[36m"
_GREEN = "\033[32m"
_YELLOW= "\033[33m"
_RED   = "\033[31m"
_BLUE  = "\033[34m"


def _c(text, *codes):
    """Apply ANSI colour codes when stdout is a TTY."""
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + str(text) + _RESET


def _post(host, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        host + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        print("\n  Error {}: {}".format(e.code, body.get("detail", e.reason)), file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(
            "\n  Cannot connect to {}\n"
            "  Is the server running? Try: make dev\n"
            "  Reason: {}".format(host, e.reason),
            file=sys.stderr,
        )
        sys.exit(1)


def _get(host, path):
    req = urllib.request.Request(host + path)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        print(
            "\n  Cannot connect to {}\n"
            "  Is the server running? Try: make dev\n"
            "  Reason: {}".format(host, e.reason),
            file=sys.stderr,
        )
        sys.exit(1)


# --- Formatters ---------------------------------------------------------------

def print_health(data):
    status = data.get("status", "?")
    color = _GREEN if status == "ok" else _YELLOW
    print("\n  {} -- {}".format(_c("System Health", _BOLD), _c(status.upper(), color, _BOLD)))
    for name, info in data.get("components", {}).items():
        s = info.get("status", "?")
        lat = "  {}ms".format(info["latency_ms"]) if "latency_ms" in info else ""
        sc = _GREEN if s == "ok" else (_YELLOW if s == "slow" else _RED)
        print("    {:12s} {}{}".format(name, _c(s, sc), _c(lat, _DIM)))
    print()


def print_results(data):
    query = data.get("query", "")
    total = data.get("total_results", 0)
    ms = data.get("processing_time_ms", 0)
    cache = "  " + _c("(cached)", _GREEN) if data.get("cache_hit") else ""

    print("\n  {}".format(_c(query, _BOLD, _CYAN)))
    print("  {}\n".format(_c("{} results * {}ms{}".format(total, ms, cache), _DIM)))

    for r in data.get("results", []):
        filled = int(r["score"] * 10)
        score_bar = "#" * filled + "." * (10 - filled)
        print("  {}  {}".format(_c("#" + str(r["rank"]), _BOLD), _c(r["title"], _BOLD)))
        print("      {}".format(_c(r["url"], _CYAN)))
        print("      {} {}  {}".format(
            _c(score_bar, _GREEN),
            _c(str(round(r["score"], 3)), _DIM),
            _c("{} chars * {} chunks".format(r["char_count"], r["chunk_count"]), _DIM),
        ))
        snippet = r.get("content", "")[:200].replace("\n", " ")
        ellipsis = "..." if len(r.get("content", "")) > 200 else ""
        print("      {}".format(_c(snippet + ellipsis, _DIM)))
        print()

    if data.get("citations_markdown"):
        print(_c("  Citations", _BOLD))
        for line in data["citations_markdown"].splitlines()[:6]:
            print("  {}".format(_c(line, _DIM)))
        print()


def print_semantic(data):
    total = data.get("total_chunks", 0)
    print("\n  {}".format(_c(data.get("query", ""), _BOLD, _CYAN)))
    print("  {}\n".format(_c("{} semantic chunks".format(total), _DIM)))

    for i, c in enumerate(data.get("chunks", []), 1):
        sim = c.get("similarity", 0)
        filled = int(sim * 10)
        bar = "#" * filled + "." * (10 - filled)
        print("  {}  {}".format(_c("#" + str(i), _BOLD), _c(c["title"], _BOLD)))
        print("      {}".format(_c(c["url"], _CYAN)))
        print("      {} {}".format(_c(bar, _BLUE), _c(str(round(sim, 3)), _DIM)))
        snippet = c.get("text", "")[:200].replace("\n", " ")
        print("      {}".format(_c(snippet + "...", _DIM)))
        print()


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="hybrid-search",
        description="Query the Hybrid Search API from your terminal.",
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--top", "-n", type=int, default=5, metavar="N",
                        help="Number of results (default: 5)")
    parser.add_argument("--semantic", "-s", action="store_true",
                        help="Use semantic (vector) search instead of web search")
    parser.add_argument("--min-score", type=float, default=0.0, metavar="SCORE",
                        help="Minimum relevance score 0-1 (default: 0)")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="Output raw JSON")
    parser.add_argument("--health", action="store_true",
                        help="Check system health and exit")
    parser.add_argument("--host", default=DEFAULT_HOST, metavar="URL",
                        help="API base URL (default: {})".format(DEFAULT_HOST))

    args = parser.parse_args()

    if args.health:
        data = _get(args.host, "/api/v1/health")
        if args.as_json:
            print(json.dumps(data, indent=2))
        else:
            print_health(data)
        sys.exit(0)

    if not args.query:
        parser.print_help()
        sys.exit(1)

    if args.semantic:
        payload = {"query": args.query, "top_k": args.top, "min_similarity": args.min_score}
        data = _post(args.host, "/api/v1/search/semantic", payload)
        if args.as_json:
            print(json.dumps(data, indent=2))
        else:
            print_semantic(data)
    else:
        payload = {"query": args.query, "max_results": args.top, "min_score": args.min_score}
        data = _post(args.host, "/api/v1/search", payload)
        if args.as_json:
            print(json.dumps(data, indent=2))
        else:
            print_results(data)


if __name__ == "__main__":
    main()
