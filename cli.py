#!/usr/bin/env python3
"""
OLLA — OLLA. Smarter Answers. A polished terminal client.

Run it with no arguments for the interactive shell:

    python cli.py

Or use it one-shot, the classic way:

    python cli.py "how does pgvector work"
    python cli.py "RAG pipelines" --max 8
    python cli.py "latest AI news" --hybrid --mode fresh
    python cli.py "vector similarity" --graph
    python cli.py --health
    python cli.py --test-llm
    python cli.py --feedback-stats

Answers are synthesized by the local Ollama model wired into the API. If Ollama
is not running the CLI still shows the retrieved sources.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from rich.box import ROUNDED
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

VERSION = "1.0.0"
NAME = "OLLA"
TAGLINE = "HYBRID SEARCH.   SMARTER ANSWERS."
DEFAULT_HOST = "http://localhost:8000"
DEFAULT_OLLAMA = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:1.5b"

# localhost calls must never traverse a proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

console = Console(highlight=False)

# ASCII wordmark — rendered with a cyan→violet gradient, one colour per letter.
_LOGO = [
    (" ██████ ", "██      ", "██      ", " █████  "),
    ("██    ██", "██      ", "██      ", "██   ██ "),
    ("██    ██", "██      ", "██      ", "███████ "),
    ("██    ██", "██      ", "██      ", "██   ██ "),
    (" ██████ ", "███████ ", "███████ ", "██   ██ "),
]
_LOGO_COLORS = ["bright_cyan", "#3bc9db", "#7c8cf8", "#c084fc"]

QUOTE = ("The best way to predict\nthe future is to build it.", "— Alan Kay")

# Feedback vocabulary — shared by the shell and the --feedback flag.
_FB_TYPES = ["useful", "not_useful", "incorrect", "outdated", "bad_source", "missing_context"]
_FB_LEVELS = ["answer", "citation", "chunk", "source"]


class CLIError(Exception):
    """A recoverable error — printed nicely instead of crashing the shell."""


def _request(host, path, payload=None, method="GET", timeout=180):
    """Call the API. Raises CLIError on any failure so callers can recover."""
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    headers["Connection"] = "close"
    req = urllib.request.Request(host + path, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
            detail = body.get("detail", e.reason)
        except Exception:  # noqa: BLE001
            detail = e.reason
        raise CLIError(f"Error {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise CLIError(
            f"Cannot connect to {host}\n"
            f"Is the server running?  Try:  uvicorn app.main:app --reload\n"
            f"Reason: {e.reason}"
        )
    except Exception as e:  # noqa: BLE001
        raise CLIError(f"Unexpected error: {e}")


def _error_panel(message):
    console.print(
        Panel(
            Text(str(message), style="red"),
            title="[bold red]✗  Something went wrong",
            border_style="red",
            box=ROUNDED,
            padding=(0, 1),
        )
    )


class Settings:
    def __init__(self):
        self.host = DEFAULT_HOST
        self.ollama = DEFAULT_OLLAMA
        self.model = DEFAULT_MODEL
        self.max_results = 5
        self.mode = "auto"
        self.hybrid = False
        self.show_sources = True
        self.as_json = False
        self.last_query_id = None
        self.last_results = []

    def as_table(self):
        t = Table(
            box=ROUNDED,
            border_style="grey42",
            show_header=True,
            header_style="bold cyan",
            title="Current settings",
            title_style="bold",
        )
        t.add_column("Setting", style="bold")
        t.add_column("Value", style="green")
        t.add_column("Change with", style="grey62")
        t.add_row("API host", self.host, "/host <url>")
        t.add_row("retrieval", "hybrid" if self.hybrid else "standard", "/hybrid on|off")
        t.add_row("hybrid mode", self.mode, "/mode <name>")
        t.add_row("max sources", str(self.max_results), "/max <n>")
        t.add_row("show sources", "on" if self.show_sources else "off", "/sources on|off")
        t.add_row("raw JSON", "on" if self.as_json else "off", "/json on|off")
        t.add_row("Ollama host", self.ollama, "/ollama <url>")
        t.add_row("LLM model", self.model, "/model <name>")
        return t


def _probe_health(settings):
    """Best-effort health check; returns the health dict, or None if down."""
    try:
        return _request(settings.host, "/api/v1/health", timeout=4)
    except Exception:  # noqa: BLE001
        return None


def _logo():
    """The OLLA wordmark as a coloured renderable."""
    rows = []
    for row in _LOGO:
        line = Text("  ")
        for idx, seg in enumerate(row):
            line.append(seg, style=f"bold {_LOGO_COLORS[idx]}")
            if idx < len(row) - 1:
                line.append(" ")
        rows.append(line)
    rows.append(Text(""))
    rows.append(Text("  " + TAGLINE, style="bold cyan"))
    return Group(*rows)


def _feature_panel(settings):
    items = [
        ("◆", "magenta", "OLLA Engine", "Graphs · Vectors · Web routing"),
        ("◆", "#7c8cf8", "Built for Developers", "Extensible · Fast · Reliable"),
        ("◆", "cyan", "Local API", settings.host),
        ("◆", "bright_cyan", "Model", settings.model),
    ]
    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="center")
    grid.add_column()
    for icon, color, title, sub in items:
        grid.add_row(
            Text(icon, style=f"bold {color}"),
            Group(Text(title, style="bold white"), Text(sub, style="grey54")),
        )
    return Panel(grid, box=ROUNDED, border_style="grey35", padding=(0, 2), width=48)


def _getting_started_panel():
    grid = Table.grid(padding=(0, 3))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column(style="grey74")
    rows = [
        ("/ask <question>", "ask a question, get an answer"),
        ("/hybrid on|off", "toggle hybrid retrieval"),
        ("/graph <query>", "explore the knowledge graph"),
        ("/feedback", "rate an answer or a source"),
        ("/health", "check the API health"),
        ("/help", "show all commands"),
        ("/exit", "exit the shell"),
    ]
    for c, d in rows:
        grid.add_row(c, d)
    return Panel(
        grid,
        box=ROUNDED,
        border_style="grey35",
        padding=(0, 2),
        width=62,
        title="[bold]🚀  GETTING STARTED",
        title_align="left",
    )


def _status_panel(health):
    grid = Table.grid(padding=(0, 2))
    grid.add_column()
    grid.add_column()
    grid.add_column(justify="right")
    if health:
        comps = health.get("components") or {}
        if comps:
            for name, comp in comps.items():
                st = comp.get("status", "?")
                ok = st in ("ok", "healthy")
                dot = "green" if ok else ("yellow" if st == "slow" else "red")
                grid.add_row(
                    Text("●", style=dot),
                    Text(str(name), style="white"),
                    Text(st.upper(), style="green" if ok else "yellow"),
                )
        else:
            grid.add_row(Text("●", style="green"), Text("API Server"), Text("OK", style="green"))
        border = "grey35"
    else:
        grid.add_row(Text("●", style="red"), Text("API Server"), Text("OFFLINE", style="red"))
        border = "red"
    return Panel(
        grid,
        box=ROUNDED,
        border_style=border,
        padding=(0, 2),
        width=48,
        title="[bold]●  STATUS",
        title_align="left",
    )


def _quote_panel():
    body = Group(
        Text(QUOTE[0], style="italic grey78"),
        Text(QUOTE[1], style="magenta", justify="right"),
    )
    return Panel(
        body,
        box=ROUNDED,
        border_style="grey35",
        padding=(0, 2),
        width=62,
        title="[bold]❝  ETHOS",
        title_align="left",
    )


def render_banner(settings, health=None):
    """OLLA welcome banner — logo, features, getting-started, status, quote."""
    console.print()
    console.print(_logo())
    console.print()
    console.print(
        Columns([_feature_panel(settings), _getting_started_panel()], padding=(0, 2), expand=False)
    )
    console.print(Columns([_status_panel(health), _quote_panel()], padding=(0, 2), expand=False))
    tip = Text.assemble(
        (" 💡 TIP  ", "bold magenta"),
        ("Type ", "grey62"),
        ("/ask", "bold cyan"),
        (" to ask a question, or ", "grey62"),
        ("/help", "bold cyan"),
        (" to see all commands.", "grey62"),
    )
    console.print(Panel(tip, box=ROUNDED, border_style="grey35", padding=(0, 1)))
    console.print()


def _highlight_citations(text):
    """Turn [1] [2] markers into bold cyan."""
    out = Text()
    buf = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "[":
            j = text.find("]", i)
            if j != -1 and text[i + 1 : j].isdigit():
                if buf:
                    out.append(buf)
                    buf = ""
                out.append(text[i : j + 1], style="bold cyan")
                i = j + 1
                continue
        buf += ch
        i += 1
    if buf:
        out.append(buf)
    return out


def _meta_line(pairs):
    """A dim 'key value · key value' status line."""
    t = Text()
    for idx, (key, value, style) in enumerate(pairs):
        if idx:
            t.append("   ·   ", style="grey42")
        if key:
            t.append(f"{key} ", style="grey50")
        t.append(str(value), style=style or "white")
    return t


def _answer_panel(answer, model):
    if answer:
        body = _highlight_citations(answer)
    else:
        body = Text.assemble(
            ("No synthesized answer — the local LLM is not running.\n", "yellow"),
            ("Start it:  ollama serve   &&   ollama pull " + DEFAULT_MODEL, "grey50"),
        )
    title = f"[bold #c084fc]◆  {NAME} ANSWER"
    if model:
        title += f"  [grey50]({model})"
    return Panel(
        body, title=title, title_align="left", border_style="magenta", box=ROUNDED, padding=(1, 2)
    )


def _sources_table(results):
    t = Table(
        box=ROUNDED,
        border_style="grey42",
        show_header=True,
        header_style="bold",
        title="Sources",
        title_style="bold",
        expand=True,
        padding=(0, 1),
    )
    t.add_column("#", style="bold cyan", width=4, justify="right")
    t.add_column("Title", style="bold", ratio=3)
    t.add_column("Score", style="grey62", width=8, justify="right")
    for r in results:
        snippet = (r.get("content") or "").strip().replace("\n", " ")
        cell = Text(str(r.get("title", "untitled")))
        cell.append("\n" + str(r.get("url", "")), style="blue")
        if snippet:
            cell.append("\n" + snippet[:200] + "…", style="grey54")
        score = r.get("score")
        score_s = f"{score:.3f}" if isinstance(score, (int, float)) else "—"
        t.add_row(str(r.get("rank", "?")), cell, score_s)
    return t


def _trace_line(trace):
    t = Text("  pipeline  ", style="grey50")
    for idx, step in enumerate(trace):
        if idx:
            t.append(" → ", style="grey42")
        st = step.get("status", "?")
        color = "green" if st == "success" else "yellow" if st in ("fallback", "skipped") else "red"
        t.append(step.get("stage", "?"), style="white")
        t.append(f":{st}", style=color)
    return t


def cmd_health(settings):
    with console.status("[cyan]checking API health…", spinner="dots"):
        data = _request(settings.host, "/api/v1/health", timeout=20)
    status = data.get("status", "unknown")
    color = "green" if status == "healthy" else "yellow"

    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold")
    t.add_column()
    t.add_column(style="grey50")
    for name, comp in (data.get("components") or {}).items():
        st = comp.get("status", "?")
        c = "green" if st == "ok" else ("yellow" if st == "slow" else "red")
        lat = comp.get("latency_ms")
        lat_s = f"{lat} ms" if lat is not None else ""
        t.add_row(name, Text(st.upper(), style=c), lat_s)

    header = Text.assemble(
        ("API  ", "grey50"),
        (status.upper(), f"bold {color}"),
        (f"   v{data.get('version', '?')}", "grey50"),
    )
    console.print(
        Panel(
            Group(header, Text(""), t),
            title="[bold]API health",
            title_align="left",
            border_style=color,
            box=ROUNDED,
            padding=(1, 2),
        )
    )


def cmd_search(settings, query):
    if settings.hybrid:
        return cmd_hybrid(settings, query)

    with console.status("[cyan]searching…", spinner="dots"):
        data = _request(
            settings.host,
            "/api/v1/search",
            {"query": query, "max_results": settings.max_results},
            "POST",
        )

    settings.last_query_id = data.get("query_id") or data.get("id")
    settings.last_results = data.get("results", []) or []

    if settings.as_json:
        console.print_json(json.dumps(data))
        return

    console.print(Rule(Text(query, style="bold white"), style="orange3"))
    meta = [
        ("", f"{data.get('total_results', 0)} sources", "white"),
        ("", f"{data.get('processing_time_ms', 0)} ms", "white"),
    ]
    if data.get("cache_hit"):
        meta.append(("", "cached", "cyan"))
    if data.get("degraded"):
        meta.append(("", "⚠ degraded", "yellow"))
    console.print(_meta_line(meta))
    console.print()

    console.print(_answer_panel(data.get("answer", ""), data.get("answer_model")))

    results = data.get("results", [])
    if settings.show_sources and results:
        console.print()
        console.print(_sources_table(results))

    trace = data.get("trace", [])
    if trace:
        console.print()
        console.print(_trace_line(trace))
    console.print()


def cmd_hybrid(settings, query):
    with console.status("[cyan]hybrid retrieval — routing query…", spinner="dots"):
        data = _request(
            settings.host,
            "/api/v1/search/hybrid",
            {"query": query, "mode": settings.mode, "max_results": settings.max_results},
            "POST",
        )

    settings.last_query_id = data.get("query_id") or data.get("id")
    settings.last_results = data.get("results", []) or []

    if settings.as_json:
        console.print_json(json.dumps(data))
        return

    rmode = data.get("retrieval_mode", "?")
    qclass = data.get("query_class", "?")
    conf = data.get("confidence", 0.0)
    src = "memory" if data.get("from_memory") else "web"
    conf_c = "green" if conf >= 0.7 else ("yellow" if conf >= 0.4 else "red")

    console.print(Rule(Text(query, style="bold white"), style="orange3"))
    meta = [
        ("mode", rmode.upper(), "bold cyan"),
        ("class", qclass, "white"),
        ("confidence", f"{conf:.2f}", conf_c),
        ("from", src, "white"),
    ]
    if data.get("cache_hit"):
        meta.append(("", "cached", "cyan"))
    if data.get("degraded"):
        meta.append(("", "⚠ degraded", "yellow"))
    console.print(_meta_line(meta))
    console.print()

    console.print(_answer_panel(data.get("answer", ""), data.get("answer_model")))

    results = data.get("results", [])
    if settings.show_sources and results:
        console.print()
        console.print(_sources_table(results))

    trace = data.get("routing_trace", [])
    if trace:
        steps = Group(*[Text("· " + str(s), style="grey62") for s in trace])
        console.print()
        console.print(
            Panel(
                steps,
                title="[bold]Routing",
                title_align="left",
                border_style="grey42",
                box=ROUNDED,
                padding=(0, 2),
            )
        )
    console.print()


def cmd_graph(settings, query):
    with console.status("[cyan]traversing the knowledge graph…", spinner="dots"):
        data = _request(
            settings.host,
            "/api/v1/search/graph",
            {"query": query, "hops": 2, "seed_k": 5, "top_k": 20},
            "POST",
        )

    if settings.as_json:
        console.print_json(json.dumps(data))
        return

    console.print(Rule(Text("Knowledge graph — " + query, style="bold white"), style="orange3"))
    console.print(_meta_line([("", f"{data.get('total_chunks', 0)} chunks", "white")]))
    console.print()

    seeds = data.get("seed_chunks", [])
    conn = data.get("connected_chunks", [])
    if not seeds and not conn:
        console.print(
            Panel(
                Text.assemble(
                    ("No graph results. Build the graph first:\n", "yellow"),
                    ("1) POST /api/v1/search/embed-and-store\n", "grey62"),
                    ("2) POST /api/v1/graph/build", "grey62"),
                ),
                border_style="yellow",
                box=ROUNDED,
                padding=(1, 2),
            )
        )
        console.print()
        return

    blocks = []
    for c in seeds:
        sim = c.get("similarity")
        sim_s = f"  sim {sim:.3f}" if isinstance(sim, (int, float)) else ""
        head = Text.assemble(
            ("SEED  ", "bold cyan"), (str(c.get("title", "chunk")), "bold"), (sim_s, "grey50")
        )
        body = Text((c.get("text") or "")[:240], style="grey62")
        blocks.append(Group(head, body, Text("")))
    for c in conn:
        head = Text.assemble(
            (f"HOP {c.get('hop', 1)}  ", "bold yellow"), (str(c.get("title", "chunk")), "bold")
        )
        body = Text((c.get("text") or "")[:240], style="grey62")
        blocks.append(Group(head, body, Text("")))
    console.print(Panel(Group(*blocks), border_style="grey42", box=ROUNDED, padding=(1, 2)))
    console.print()


def cmd_feedback_stats(settings):
    with console.status("[cyan]loading feedback analytics…", spinner="dots"):
        data = _request(settings.host, "/api/v1/feedback/stats", timeout=20)

    total = data.get("total", 0)
    rate = data.get("satisfaction_rate", 0.0)
    rate_c = "green" if rate >= 0.6 else ("yellow" if rate >= 0.3 else "red")

    header = _meta_line(
        [
            ("", f"{total} events", "white"),
            ("satisfaction", f"{rate:.0%}", rate_c),
        ]
    )

    parts = [header, Text("")]

    by_type = data.get("by_type", {})
    if by_type:
        t = Table.grid(padding=(0, 3))
        t.add_column(style="white")
        t.add_column(style="bold cyan", justify="right")
        for k, v in sorted(by_type.items(), key=lambda kv: -kv[1]):
            t.add_row(k, str(v))
        parts += [Text("By type", style="bold"), t, Text("")]

    def _src_table(label, color, rows):
        t = Table.grid(padding=(0, 3))
        t.add_column(style="white")
        t.add_column(style="grey62", justify="right")
        for s in rows[:5]:
            trust = float(s.get("trust_score", 0) or 0)
            t.add_row(str(s.get("domain", "?")), f"trust {trust:.2f}")
        return Group(Text(label, style=f"bold {color}"), t, Text(""))

    if data.get("best_sources"):
        parts.append(_src_table("Top-trust sources", "green", data["best_sources"]))
    if data.get("worst_sources"):
        parts.append(_src_table("Low-trust sources", "yellow", data["worst_sources"]))

    console.print(
        Panel(
            Group(*parts),
            title="[bold]Feedback analytics",
            title_align="left",
            border_style="cyan",
            box=ROUNDED,
            padding=(1, 2),
        )
    )


def cmd_feedback(settings, args):
    payload = {
        "level": args.level,
        "feedback_type": args.fb_type,
        "query_id": args.query_id,
        "result_id": args.result_id,
        "chunk_id": args.chunk_id,
        "source_url": args.source_url,
        "comment": args.comment,
    }
    data = _request(settings.host, "/api/v1/feedback", payload, "POST")
    lines = [
        Text.assemble(
            ("Feedback recorded  ", "bold green"), (str(data.get("feedback_id", "")), "grey50")
        ),
        Text(f"{args.level} / {args.fb_type}", style="grey62"),
    ]
    for effect in data.get("effects", []):
        lines.append(Text("  · " + str(effect), style="grey62"))
    console.print(Panel(Group(*lines), border_style="green", box=ROUNDED, padding=(1, 2)))


def cmd_test_llm(settings):
    console.print(Rule(Text("LLM diagnostic", style="bold white"), style="orange3"))
    console.print(
        _meta_line(
            [
                ("", settings.ollama, "white"),
                ("model", settings.model, "cyan"),
            ]
        )
    )
    console.print()

    steps = []
    try:
        with console.status("[cyan]contacting Ollama…", spinner="dots"):
            with _OPENER.open(settings.ollama + "/api/tags", timeout=10) as r:
                tags = json.loads(r.read())
        models = [m.get("name", "") for m in tags.get("models", [])]
        steps.append(
            Text.assemble(
                ("  [1] ", "bold green"), (f"Ollama reachable ({len(models)} model(s))", "white")
            )
        )
        base = settings.model.split(":")[0]
        if any(m.split(":")[0] == base for m in models):
            steps.append(
                Text.assemble(
                    ("  [2] ", "bold green"), (f"model '{settings.model}' is available", "white")
                )
            )
        else:
            steps.append(
                Text.assemble(
                    ("  [2] ", "bold red"), (f"model '{settings.model}' NOT found", "white")
                )
            )
            steps.append(Text(f"      available: {', '.join(models) or 'none'}", style="grey50"))
            steps.append(Text(f"      fix:  ollama pull {settings.model}", style="yellow"))
            console.print(Panel(Group(*steps), border_style="red", box=ROUNDED, padding=(1, 2)))
            return
    except Exception as e:  # noqa: BLE001
        steps.append(Text.assemble(("  [1] ", "bold red"), (f"Ollama NOT reachable: {e}", "white")))
        steps.append(Text("      fix:  start the Ollama app or run `ollama serve`", style="yellow"))
        console.print(Panel(Group(*steps), border_style="red", box=ROUNDED, padding=(1, 2)))
        return

    t0 = time.time()
    try:
        with console.status("[cyan]generating a test answer…", spinner="dots"):
            body = json.dumps(
                {
                    "model": settings.model,
                    "prompt": "Reply with exactly: OK",
                    "stream": False,
                    "options": {"num_predict": 10},
                }
            ).encode()
            req = urllib.request.Request(
                settings.ollama + "/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with _OPENER.open(req, timeout=240) as r:
                out = json.loads(r.read())
        dt = time.time() - t0
        reply = (out.get("response") or "").strip()
        steps.append(
            Text.assemble(
                ("  [3] ", "bold green"),
                (f"generation OK in {dt:.1f}s  ", "white"),
                (f"-> {reply[:40]}", "grey50"),
            )
        )
        steps.append(Text(""))
        steps.append(
            Text("  LLM step is working — run a search for synthesized answers.", style="green")
        )
        if dt > 30:
            steps.append(
                Text(
                    "  (first call is slow — the model loads into RAM; later calls are fast)",
                    style="grey50",
                )
            )
        border = "green"
    except Exception as e:  # noqa: BLE001
        steps.append(Text.assemble(("  [3] ", "bold red"), (f"generation failed: {e}", "white")))
        border = "red"
    console.print(Panel(Group(*steps), border_style=border, box=ROUNDED, padding=(1, 2)))


_FB_LABELS = {
    "useful": "the answer was helpful",
    "not_useful": "the answer was not helpful",
    "incorrect": "the answer was wrong",
    "outdated": "the answer was out of date",
    "bad_source": "a cited source was low quality",
    "missing_context": "important context was missing",
}
_FB_SHORTCUTS = {
    "useful": "useful",
    "good": "useful",
    "up": "useful",
    "yes": "useful",
    "not_useful": "not_useful",
    "bad": "not_useful",
    "down": "not_useful",
    "no": "not_useful",
    "incorrect": "incorrect",
    "wrong": "incorrect",
    "outdated": "outdated",
    "stale": "outdated",
    "bad_source": "bad_source",
    "missing_context": "missing_context",
}


def _ask_feedback_type(title):
    """Show the 1-6 rating menu; return a feedback type, or None if cancelled."""
    menu = Table.grid(padding=(0, 3))
    menu.add_column(style="bold cyan", justify="right")
    menu.add_column(style="white")
    for i, key in enumerate(_FB_TYPES, 1):
        menu.add_row(str(i), f"{key}  [grey50]\u2014 {_FB_LABELS[key]}[/]")
    console.print(
        Panel(
            menu,
            title=f"[bold]{title}",
            title_align="left",
            border_style="magenta",
            box=ROUNDED,
            padding=(1, 2),
        )
    )
    try:
        raw = console.input(
            "  pick [bold cyan]1-6[/] (Enter to cancel) [bold cyan]\u276f[/] "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""
    if not raw:
        return None
    key = raw.lower().replace("-", "_")
    if raw.isdigit() and 1 <= int(raw) <= len(_FB_TYPES):
        return _FB_TYPES[int(raw) - 1]
    if key in _FB_TYPES:
        return key
    if key in _FB_SHORTCUTS:
        return _FB_SHORTCUTS[key]
    _error_panel(f"'{raw}' is not a valid choice (pick 1-6)")
    return None


def _ask_comment():
    """Prompt for an optional free-text comment; return it or None."""
    try:
        return (
            console.input(
                "  comment [grey50](optional, Enter to skip)[/] [bold cyan]\u276f[/] "
            ).strip()
            or None
        )
    except (EOFError, KeyboardInterrupt):
        return None


def _show_feedback_result(data, headline, detail):
    lines = [Text(headline, style="bold green"), Text(detail, style="grey62")]
    if data.get("feedback_id"):
        lines.append(Text(f"id {data['feedback_id']}", style="grey50"))
    for effect in data.get("effects", []):
        lines.append(Text("  \u00b7 " + str(effect), style="grey62"))
    console.print(Panel(Group(*lines), border_style="green", box=ROUNDED, padding=(1, 2)))


def _feedback_answer(settings, quick):
    """Rate the synthesized answer of the most recent query."""
    if not settings.last_query_id:
        _error_panel("No recent answer to rate \u2014 run a search first, then use /feedback.")
        return
    fb_type = _FB_SHORTCUTS.get(quick.strip().lower().replace("-", "_")) if quick else None
    if fb_type is None:
        fb_type = _ask_feedback_type("\u25c6  Rate the last answer")
    if fb_type is None:
        console.print("[grey62]  feedback cancelled[/]")
        return
    comment = _ask_comment()
    payload = {
        "level": "answer",
        "feedback_type": fb_type,
        "query_id": settings.last_query_id,
        "result_id": None,
        "chunk_id": None,
        "source_url": None,
        "comment": comment,
    }
    data = _request(settings.host, "/api/v1/feedback", payload, "POST")
    _show_feedback_result(
        data, "\u2713  Thanks \u2014 answer feedback recorded", f"answer \u00b7 {fb_type}"
    )


def _feedback_source(settings):
    """Rate one of the sources / sites used by the most recent search."""
    if not settings.last_results:
        _error_panel("No sources to rate \u2014 run a search first, then use /feedback.")
        return
    listing = Table.grid(padding=(0, 2))
    listing.add_column(style="bold cyan", justify="right")
    listing.add_column()
    for r in settings.last_results:
        cell = Text(str(r.get("title", "untitled")), style="white")
        cell.append("\n" + str(r.get("url", "")), style="blue")
        listing.add_row(str(r.get("rank", "?")), cell)
    console.print(
        Panel(
            listing,
            title="[bold]\u25c6  Which source / site?",
            title_align="left",
            border_style="magenta",
            box=ROUNDED,
            padding=(1, 2),
        )
    )
    try:
        raw = console.input(
            "  pick a source [bold cyan]#[/] (Enter to cancel) [bold cyan]\u276f[/] "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""
    if not raw:
        console.print("[grey62]  feedback cancelled[/]")
        return
    chosen = next((r for r in settings.last_results if str(r.get("rank")) == raw), None)
    if chosen is None:
        _error_panel(f"'{raw}' is not one of the listed sources")
        return
    fb_type = _ask_feedback_type(f"\u25c6  Rate source [{raw}]")
    if fb_type is None:
        console.print("[grey62]  feedback cancelled[/]")
        return
    comment = _ask_comment()
    payload = {
        "level": "source",
        "feedback_type": fb_type,
        "query_id": settings.last_query_id,
        "result_id": None,
        "chunk_id": None,
        "source_url": chosen.get("url"),
        "comment": comment,
    }
    data = _request(settings.host, "/api/v1/feedback", payload, "POST")
    _show_feedback_result(
        data,
        "\u2713  Thanks \u2014 source feedback recorded",
        f"source \u00b7 {fb_type}  \u00b7  {chosen.get('url')}",
    )


def cmd_feedback_shell(settings, arg):
    """Interactive feedback \u2014 rate the last answer, or a source it used."""
    a = arg.strip().lower() if arg else ""
    if a in ("answer", "ans", "a"):
        _feedback_answer(settings, "")
        return
    if a in ("source", "sources", "src", "site", "sites", "s"):
        _feedback_source(settings)
        return
    if a in _FB_SHORTCUTS:  # e.g. `/feedback useful` -> quick answer rating
        _feedback_answer(settings, a)
        return
    if a:
        _error_panel(
            f"Unknown feedback option '{arg}'.  Use /feedback, "
            "/feedback answer, or /feedback source."
        )
        return

    # No argument given -> ask what to rate.
    if not settings.last_results and not settings.last_query_id:
        _error_panel("Nothing to rate yet \u2014 run a search first.")
        return
    choice = Table.grid(padding=(0, 3))
    choice.add_column(style="bold cyan", justify="right")
    choice.add_column(style="white")
    choice.add_row("1", "the answer OLLA gave")
    choice.add_row(
        "2", f"a source / site it used  [grey50]({len(settings.last_results)} available)[/]"
    )
    console.print(
        Panel(
            choice,
            title="[bold]\u25c6  What do you want to rate?",
            title_align="left",
            border_style="magenta",
            box=ROUNDED,
            padding=(1, 2),
        )
    )
    try:
        pick = (
            console.input("  pick [bold cyan]1-2[/] (Enter to cancel) [bold cyan]\u276f[/] ")
            .strip()
            .lower()
        )
    except (EOFError, KeyboardInterrupt):
        pick = ""
    if pick in ("1", "answer", "a"):
        _feedback_answer(settings, "")
    elif pick in ("2", "source", "s"):
        _feedback_source(settings)
    else:
        console.print("[grey62]  feedback cancelled[/]")


def render_help():
    t = Table(
        box=ROUNDED,
        border_style="grey42",
        show_header=True,
        header_style="bold cyan",
        title="OLLA commands",
        title_style="bold",
        expand=True,
    )
    t.add_column("Command", style="bold cyan", no_wrap=True)
    t.add_column("What it does")
    rows = [
        ("/ask <question>", "ask OLLA a question (or just type it)"),
        ("/feedback", "rate the last answer or a source it used"),
        ("/graph <query>", "explore the knowledge graph for a query"),
        ("/hybrid on|off", "toggle confidence-routed hybrid retrieval"),
        ("/mode <name>", "hybrid mode: auto · fast · fresh · hybrid · deep"),
        ("/max <n>", "set how many sources to retrieve"),
        ("/sources on|off", "show or hide the sources table"),
        ("/json on|off", "print raw JSON responses"),
        ("/host <url>", "point at a different API host"),
        ("/ollama <url>", "set the Ollama host"),
        ("/model <name>", "set the LLM model used for diagnostics"),
        ("/health", "check the API and its components"),
        ("/llm", "diagnose the local Ollama LLM"),
        ("/stats", "show aggregate feedback analytics"),
        ("/set", "show all current settings"),
        ("/clear", "clear the screen and redraw the banner"),
        ("/help  or  ?", "show this command reference"),
        ("/exit  or  /quit", "leave the shell"),
    ]
    for cmd, desc in rows:
        t.add_row(cmd, desc)
    console.print(t)


def _toggle(value, default):
    v = value.strip().lower()
    if v in ("on", "true", "yes", "1"):
        return True
    if v in ("off", "false", "no", "0"):
        return False
    return default


def handle_command(line, settings):
    """Process one shell command. Returns False to signal exit."""
    line = line.strip()
    if not line:
        return True

    if not line.startswith("/") and line != "?":
        try:
            cmd_search(settings, line)
        except CLIError as e:
            _error_panel(e)
        return True

    if line == "?":
        cmd, arg = "help", ""
    else:
        parts = line[1:].split(maxsplit=1)
        cmd = (parts[0] if parts else "help").lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

    try:
        if cmd in ("exit", "quit", "q"):
            console.print("[grey62]bye 👋[/]")
            return False
        elif cmd in ("help", "h"):
            render_help()
        elif cmd in ("clear", "cls"):
            console.clear()
            render_banner(settings, _probe_health(settings))
        elif cmd == "set":
            console.print(settings.as_table())
        elif cmd == "ask":
            if not arg:
                _error_panel("Usage: /ask <your question>")
            else:
                cmd_search(settings, arg)
        elif cmd == "feedback":
            cmd_feedback_shell(settings, arg)
        elif cmd == "health":
            cmd_health(settings)
        elif cmd == "llm":
            cmd_test_llm(settings)
        elif cmd == "stats":
            cmd_feedback_stats(settings)
        elif cmd == "graph":
            if not arg:
                _error_panel("Usage: /graph <query>")
            else:
                cmd_graph(settings, arg)
        elif cmd == "hybrid":
            settings.hybrid = _toggle(arg, not settings.hybrid)
            state = "on" if settings.hybrid else "off"
            console.print(f"[green]✓[/] hybrid retrieval [bold]{state}[/]")
        elif cmd == "mode":
            valid = ["auto", "fast", "fresh", "hybrid", "deep"]
            if arg in valid:
                settings.mode = arg
                console.print(f"[green]✓[/] hybrid mode → [bold]{arg}[/]")
            else:
                _error_panel(f"mode must be one of: {', '.join(valid)}")
        elif cmd == "max":
            if arg.isdigit() and int(arg) > 0:
                settings.max_results = int(arg)
                console.print(f"[green]✓[/] max sources → [bold]{arg}[/]")
            else:
                _error_panel("Usage: /max <positive integer>")
        elif cmd == "sources":
            settings.show_sources = _toggle(arg, not settings.show_sources)
            state = "on" if settings.show_sources else "off"
            console.print(f"[green]✓[/] sources display [bold]{state}[/]")
        elif cmd == "json":
            settings.as_json = _toggle(arg, not settings.as_json)
            state = "on" if settings.as_json else "off"
            console.print(f"[green]✓[/] raw JSON output [bold]{state}[/]")
        elif cmd == "host":
            if arg:
                settings.host = arg
                console.print(f"[green]✓[/] API host → [bold]{arg}[/]")
            else:
                _error_panel("Usage: /host <url>")
        elif cmd == "ollama":
            if arg:
                settings.ollama = arg
                console.print(f"[green]✓[/] Ollama host → [bold]{arg}[/]")
            else:
                _error_panel("Usage: /ollama <url>")
        elif cmd == "model":
            if arg:
                settings.model = arg
                console.print(f"[green]✓[/] LLM model → [bold]{arg}[/]")
            else:
                _error_panel("Usage: /model <name>")
        else:
            _error_panel(f"Unknown command: /{cmd}    (try /help)")
    except CLIError as e:
        _error_panel(e)
    return True


def interactive_shell(settings):
    console.clear()
    render_banner(settings, _probe_health(settings))

    while True:
        try:
            tag = "hybrid" if settings.hybrid else "ask"
            prompt = f"\n  [bold #c084fc]{NAME}[/] [grey50]{tag}[/] [bold cyan]❯[/] "
            line = console.input(prompt)
        except (EOFError, KeyboardInterrupt):
            console.print("\n[grey62]bye 👋[/]")
            break
        if not handle_command(line, settings):
            break


def build_parser():
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="OLLA — query the OLLA API and get an "
        "LLM-synthesized answer. Run with no arguments for the "
        "interactive shell.",
    )
    p.add_argument("query", nargs="?", help="the question to ask")
    p.add_argument("--host", default=DEFAULT_HOST, help="API host (default %(default)s)")
    p.add_argument(
        "--max", type=int, default=5, dest="max_results", help="max sources to retrieve (default 5)"
    )
    p.add_argument("--graph", action="store_true", help="query the knowledge graph")
    p.add_argument("--hybrid", action="store_true", help="use confidence-routed hybrid retrieval")
    p.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "fast", "fresh", "hybrid", "deep"],
        help="hybrid retrieval mode (default %(default)s)",
    )
    p.add_argument("--json", action="store_true", dest="as_json", help="raw JSON output")
    p.add_argument("--no-sources", action="store_true", help="answer only, hide sources")
    p.add_argument("--health", action="store_true", help="check API health and exit")
    p.add_argument("--test-llm", action="store_true", help="diagnose the local Ollama LLM and exit")
    p.add_argument(
        "--ollama", default=DEFAULT_OLLAMA, help="Ollama host for --test-llm (default %(default)s)"
    )
    p.add_argument(
        "--model", default=DEFAULT_MODEL, help="Ollama model for --test-llm (default %(default)s)"
    )
    p.add_argument(
        "--feedback", action="store_true", help="submit feedback (requires --level and --type)"
    )
    p.add_argument(
        "--feedback-stats",
        action="store_true",
        dest="feedback_stats",
        help="show aggregate feedback analytics and exit",
    )
    p.add_argument(
        "--level", choices=["answer", "citation", "chunk", "source"], help="feedback level"
    )
    p.add_argument(
        "--type",
        dest="fb_type",
        choices=["useful", "not_useful", "incorrect", "outdated", "bad_source", "missing_context"],
        help="feedback signal",
    )
    p.add_argument("--query-id", dest="query_id", help="related query UUID")
    p.add_argument("--result-id", dest="result_id", help="related result UUID")
    p.add_argument("--chunk-id", dest="chunk_id", help="related chunk UUID")
    p.add_argument("--source-url", dest="source_url", help="related source URL")
    p.add_argument("--comment", help="optional free-text feedback note")
    return p


def main():
    p = build_parser()
    args = p.parse_args()

    settings = Settings()
    settings.host = args.host
    settings.ollama = args.ollama
    settings.model = args.model
    settings.max_results = args.max_results
    settings.mode = args.mode
    settings.hybrid = args.hybrid
    settings.show_sources = not args.no_sources
    settings.as_json = args.as_json

    one_shot = any([args.query, args.health, args.test_llm, args.feedback, args.feedback_stats])
    if not one_shot:
        interactive_shell(settings)
        return

    try:
        if args.test_llm:
            cmd_test_llm(settings)
        elif args.health:
            cmd_health(settings)
        elif args.feedback_stats:
            cmd_feedback_stats(settings)
        elif args.feedback:
            if not args.level or not args.fb_type:
                p.error("--feedback requires both --level and --type")
            cmd_feedback(settings, args)
        elif args.graph:
            cmd_graph(settings, args.query)
        else:
            cmd_search(settings, args.query)
    except CLIError as e:
        _error_panel(e)
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[grey62]interrupted[/]")
        sys.exit(130)


if __name__ == "__main__":
    main()
