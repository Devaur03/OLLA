"""
Dashboard route — serves a self-contained HTML UI at /dashboard.
No build step, no separate frontend project. Plain HTML + vanilla JS.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Hybrid Search — Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0f1117;
      --surface: #1a1d27;
      --surface2: #22263a;
      --border: #2e3250;
      --accent: #7c6af7;
      --accent2: #56c2e6;
      --text: #e8eaf6;
      --muted: #8b90b4;
      --ok: #4ade80;
      --warn: #facc15;
      --err: #f87171;
      --radius: 10px;
      --font: 'Inter', system-ui, sans-serif;
    }
    body { background: var(--bg); color: var(--text); font-family: var(--font);
           min-height: 100vh; display: flex; flex-direction: column; }
    header { background: var(--surface); border-bottom: 1px solid var(--border);
             padding: 14px 28px; display: flex; align-items: center; gap: 14px; }
    header h1 { font-size: 1.1rem; font-weight: 600; letter-spacing: -.3px; }
    header span { font-size: .75rem; color: var(--muted); }
    .pill { display:inline-block; padding: 2px 10px; border-radius: 20px;
            font-size: .7rem; font-weight: 600; text-transform: uppercase; }
    .pill-ok  { background: #14532d; color: var(--ok); }
    .pill-deg { background: #713f12; color: var(--warn); }
    .pill-err { background: #7f1d1d; color: var(--err); }

    main { display: grid; grid-template-columns: 1fr 340px; gap: 20px;
           padding: 24px 28px; flex: 1; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; } }

    .panel { background: var(--surface); border: 1px solid var(--border);
             border-radius: var(--radius); padding: 20px; }
    .panel-title { font-size: .8rem; font-weight: 600; text-transform: uppercase;
                   letter-spacing: .08em; color: var(--muted); margin-bottom: 14px; }

    /* Search form */
    .search-form { display: flex; gap: 10px; margin-bottom: 20px; }
    .search-input { flex: 1; background: var(--surface2); border: 1px solid var(--border);
                    border-radius: 8px; padding: 10px 14px; color: var(--text);
                    font-size: .95rem; outline: none; transition: border .15s; }
    .search-input:focus { border-color: var(--accent); }
    .btn { background: var(--accent); border: none; border-radius: 8px; color: #fff;
           font-weight: 600; font-size: .9rem; padding: 10px 20px; cursor: pointer;
           transition: opacity .15s; white-space: nowrap; }
    .btn:hover { opacity: .85; }
    .btn:disabled { opacity: .45; cursor: not-allowed; }
    .btn-sm { padding: 6px 12px; font-size: .78rem; }
    .btn-ghost { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }

    /* Options row */
    .opts { display: flex; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
    .opt-group label { font-size: .72rem; color: var(--muted); display: block; margin-bottom: 3px; }
    .opt-group input[type=number] { background: var(--surface2); border: 1px solid var(--border);
      border-radius: 6px; color: var(--text); padding: 5px 8px; width: 70px; font-size: .85rem; }
    .opt-group input[type=checkbox] { accent-color: var(--accent); }

    /* Status bar */
    #status { font-size: .82rem; color: var(--muted); margin-bottom: 14px; min-height: 1.2em; }

    /* Result cards */
    .result-card { background: var(--surface2); border: 1px solid var(--border);
                   border-radius: var(--radius); padding: 16px; margin-bottom: 14px; }
    .result-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
    .rank-badge { background: var(--accent); color: #fff; border-radius: 6px;
                  font-size: .72rem; font-weight: 700; padding: 2px 8px; white-space: nowrap; }
    .score-badge { background: var(--surface); border: 1px solid var(--border);
                   color: var(--muted); border-radius: 6px; font-size: .72rem;
                   padding: 2px 8px; white-space: nowrap; }
    .result-title { font-size: .92rem; font-weight: 600; }
    .result-url { font-size: .72rem; color: var(--accent2); text-decoration: none;
                  display: block; margin: 3px 0 8px; word-break: break-all; }
    .result-url:hover { text-decoration: underline; }
    .result-content { font-size: .82rem; color: var(--muted); line-height: 1.5;
                      max-height: 120px; overflow: hidden; position: relative; }
    .result-content::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0;
                              height: 40px; background: linear-gradient(transparent, var(--surface2)); }
    .result-meta { display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
    .meta-tag { font-size: .7rem; color: var(--muted); background: var(--surface);
                border: 1px solid var(--border); border-radius: 4px; padding: 2px 7px; }
    .curl-box { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
                padding: 8px 12px; font-family: monospace; font-size: .75rem; color: var(--accent2);
                margin-top: 10px; cursor: pointer; word-break: break-all; }
    .curl-box:hover { border-color: var(--accent); }

    /* Citations */
    .citation-block { background: var(--surface2); border: 1px solid var(--border);
                      border-radius: var(--radius); padding: 14px; margin-top: 16px; }
    .citation-block pre { font-size: .75rem; color: var(--muted); white-space: pre-wrap;
                          word-break: break-word; font-family: monospace; }

    /* Sidebar */
    .sidebar { display: flex; flex-direction: column; gap: 18px; }

    /* Health panel */
    .health-row { display: flex; justify-content: space-between; align-items: center;
                  padding: 8px 0; border-bottom: 1px solid var(--border); }
    .health-row:last-child { border-bottom: none; }
    .health-label { font-size: .83rem; }
    .health-latency { font-size: .75rem; color: var(--muted); }

    /* History */
    .history-item { display: flex; justify-content: space-between; align-items: center;
                    padding: 7px 0; border-bottom: 1px solid var(--border); cursor: pointer; }
    .history-item:last-child { border-bottom: none; }
    .history-query { font-size: .83rem; white-space: nowrap; overflow: hidden;
                     text-overflow: ellipsis; max-width: 180px; }
    .history-time { font-size: .7rem; color: var(--muted); white-space: nowrap; }
    .history-item:hover .history-query { color: var(--accent); }

    /* Loader */
    .loader { display: inline-block; width: 16px; height: 16px;
              border: 2px solid var(--border); border-top-color: var(--accent);
              border-radius: 50%; animation: spin .7s linear infinite; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* Embed progress */
    #embed-progress { font-size: .82rem; color: var(--muted); margin-top: 8px; }
    .empty-state { text-align: center; padding: 40px 0; color: var(--muted); font-size: .9rem; }
  </style>
</head>
<body>

<header>
  <h1>⚡ Hybrid Search</h1>
  <span>for Agents</span>
  <div style="flex:1"></div>
  <span id="overall-status"></span>
  <button class="btn btn-sm btn-ghost" onclick="refreshHealth()">↻ Health</button>
</header>

<main>
  <!-- Left column: search + results -->
  <div>
    <div class="search-form">
      <input id="query-input" class="search-input" type="text"
             placeholder="Ask anything — e.g. how does pgvector work"
             onkeydown="if(event.key==='Enter') doSearch()" />
      <button class="btn" id="search-btn" onclick="doSearch()">Search</button>
      <button class="btn btn-ghost" onclick="doSemantic()">Semantic</button>
    </div>

    <div class="opts">
      <div class="opt-group">
        <label>Max results</label>
        <input type="number" id="opt-max" value="5" min="1" max="10" />
      </div>
      <div class="opt-group">
        <label>Min score</label>
        <input type="number" id="opt-score" value="0" min="0" max="1" step="0.05" style="width:80px"/>
      </div>
      <div class="opt-group" style="display:flex;align-items:center;gap:6px;margin-top:16px">
        <input type="checkbox" id="opt-semantic-fallback" />
        <label style="margin:0;font-size:.82rem;color:var(--text)">auto semantic after web</label>
      </div>
    </div>

    <div id="status"></div>
    <div id="results-container"></div>
  </div>

  <!-- Right column: sidebar -->
  <div class="sidebar">
    <!-- Health panel -->
    <div class="panel">
      <div class="panel-title">System health</div>
      <div id="health-detail">
        <div style="color:var(--muted);font-size:.83rem">Loading...</div>
      </div>
      <div style="margin-top:12px">
        <button class="btn btn-sm btn-ghost" style="width:100%" onclick="triggerEmbedStore()">
          ↳ Backfill embeddings
        </button>
        <div id="embed-progress"></div>
      </div>
    </div>

    <!-- Search history -->
    <div class="panel">
      <div class="panel-title">Recent searches</div>
      <div id="history-list"><div class="empty-state">No searches yet</div></div>
    </div>
  </div>
</main>

<script>
const API = '/api/v1';
let history = [];

// ── Health ────────────────────────────────────────────────────────────────────
async function refreshHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const d = await r.json();
    renderHealth(d);
  } catch(e) {
    document.getElementById('health-detail').innerHTML =
      `<div style="color:var(--err);font-size:.83rem">Cannot reach API — is the server running?</div>`;
  }
}

function renderHealth(d) {
  const overall = d.status === 'ok' ? 'pill-ok' : 'pill-deg';
  document.getElementById('overall-status').innerHTML =
    `<span class="pill ${overall}">${d.status}</span>`;

  const comps = d.components || {};
  const rows = Object.entries(comps).map(([name, info]) => {
    const cls = info.status === 'ok' ? 'pill-ok' : info.status === 'slow' ? 'pill-deg' : 'pill-err';
    const lat = info.latency_ms != null ? `<span class="health-latency">${info.latency_ms}ms</span>` : '';
    return `<div class="health-row">
      <span class="health-label">${name}</span>
      <div style="display:flex;align-items:center;gap:8px">
        ${lat}
        <span class="pill ${cls}">${info.status}</span>
      </div>
    </div>`;
  }).join('');

  document.getElementById('health-detail').innerHTML = rows ||
    `<div style="color:var(--muted);font-size:.83rem">v${d.version}</div>`;
}

// ── Search ────────────────────────────────────────────────────────────────────
async function doSearch() {
  const query = document.getElementById('query-input').value.trim();
  if (!query) return;
  setStatus('<span class="loader"></span> Searching the web...');
  setBtn(true);

  try {
    const body = {
      query,
      max_results: parseInt(document.getElementById('opt-max').value) || 5,
      min_score: parseFloat(document.getElementById('opt-score').value) || 0,
    };
    const r = await fetch(`${API}/search`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok) { setStatus(`<span style="color:var(--err)">${d.detail || 'Search failed'}</span>`); return; }

    addHistory(query, d.processing_time_ms, d.total_results);
    renderResults(d, query, body);
    setStatus(`Found <b>${d.total_results}</b> results in ${d.processing_time_ms}ms
      ${d.cache_hit ? '&nbsp;<span class="pill pill-ok">cache hit</span>' : ''}`);
  } catch(e) {
    setStatus(`<span style="color:var(--err)">Network error — is the server running?</span>`);
  } finally {
    setBtn(false);
  }
}

async function doSemantic() {
  const query = document.getElementById('query-input').value.trim();
  if (!query) return;
  setStatus('<span class="loader"></span> Running semantic search...');
  setBtn(true);

  try {
    const r = await fetch(`${API}/search/semantic`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ query, top_k: 10, min_similarity: 0.5 }),
    });
    const d = await r.json();
    if (!r.ok) { setStatus(`<span style="color:var(--err)">${d.detail || 'Semantic search failed'}</span>`); return; }
    renderSemanticResults(d);
    setStatus(`Found <b>${d.total_chunks}</b> semantic chunks`);
  } catch(e) {
    setStatus(`<span style="color:var(--err)">Network error</span>`);
  } finally {
    setBtn(false);
  }
}

// ── Render results ────────────────────────────────────────────────────────────
function renderResults(d, query, reqBody) {
  if (!d.results || d.results.length === 0) {
    document.getElementById('results-container').innerHTML =
      `<div class="empty-state">No results found. Try a different query or lower the min score.</div>`;
    return;
  }

  const curlCmd = `curl -s -X POST http://localhost:8000/api/v1/search \\\\\\n  -H "Content-Type: application/json" \\\\\\n  -d '${JSON.stringify(reqBody)}'`;

  const cards = d.results.map(r => `
    <div class="result-card">
      <div class="result-header">
        <span class="rank-badge">#${r.rank}</span>
        <span class="score-badge">score ${r.score.toFixed(3)}</span>
        <span class="result-title">${escHtml(r.title)}</span>
      </div>
      <a class="result-url" href="${escHtml(r.url)}" target="_blank">${escHtml(r.url)}</a>
      <div class="result-content">${escHtml(r.content.slice(0, 400))}</div>
      <div class="result-meta">
        <span class="meta-tag">${r.char_count.toLocaleString()} chars</span>
        <span class="meta-tag">${r.chunk_count} chunks</span>
      </div>
    </div>
  `).join('');

  const citations = d.citations_markdown ? `
    <div class="citation-block">
      <div class="panel-title" style="margin-bottom:8px">Citations</div>
      <pre>${escHtml(d.citations_markdown)}</pre>
    </div>` : '';

  const curlSection = `
    <div style="margin-top:16px">
      <div class="panel-title">Copy curl command</div>
      <div class="curl-box" title="Click to copy" onclick="copyText(this, \`${curlCmd}\`)">
        ${escHtml(`curl -X POST /api/v1/search -d '${JSON.stringify(reqBody)}'`)}
      </div>
    </div>`;

  document.getElementById('results-container').innerHTML = cards + citations + curlSection;
}

function renderSemanticResults(d) {
  if (!d.chunks || d.chunks.length === 0) {
    document.getElementById('results-container').innerHTML =
      `<div class="empty-state">No semantic matches found. Run a web search first, then backfill embeddings.</div>`;
    return;
  }
  const cards = d.chunks.map((c, i) => `
    <div class="result-card">
      <div class="result-header">
        <span class="rank-badge">#${i+1}</span>
        <span class="score-badge">sim ${c.similarity.toFixed(3)}</span>
        <span class="result-title">${escHtml(c.title)}</span>
      </div>
      <a class="result-url" href="${escHtml(c.url)}" target="_blank">${escHtml(c.url)}</a>
      <div class="result-content">${escHtml(c.text)}</div>
      <div class="result-meta">
        <span class="meta-tag">${c.char_count} chars</span>
      </div>
    </div>
  `).join('');
  document.getElementById('results-container').innerHTML = cards;
}

// ── Embed backfill ────────────────────────────────────────────────────────────
async function triggerEmbedStore() {
  document.getElementById('embed-progress').innerHTML =
    '<span class="loader"></span> Generating embeddings for stored chunks...';
  try {
    const r = await fetch(`${API}/search/embed-and-store`, { method: 'POST' });
    const d = await r.json();
    document.getElementById('embed-progress').innerHTML =
      `<span style="color:var(--ok)">✓ ${d.message} (${d.processed} chunks)</span>`;
  } catch(e) {
    document.getElementById('embed-progress').innerHTML =
      `<span style="color:var(--err)">Failed — is the server running?</span>`;
  }
}

// ── History ───────────────────────────────────────────────────────────────────
function addHistory(query, ms, count) {
  history.unshift({ query, ms, count, time: new Date().toLocaleTimeString() });
  if (history.length > 20) history.pop();
  renderHistory();
}

function renderHistory() {
  if (history.length === 0) {
    document.getElementById('history-list').innerHTML =
      '<div class="empty-state">No searches yet</div>';
    return;
  }
  document.getElementById('history-list').innerHTML = history.map(h => `
    <div class="history-item" onclick="rerun('${escAttr(h.query)}')">
      <span class="history-query" title="${escAttr(h.query)}">${escHtml(h.query)}</span>
      <span class="history-time">${h.time} · ${h.count} results</span>
    </div>
  `).join('');
}

function rerun(query) {
  document.getElementById('query-input').value = query;
  doSearch();
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function setStatus(html) { document.getElementById('status').innerHTML = html; }
function setBtn(disabled) {
  document.getElementById('search-btn').disabled = disabled;
}
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}
function escAttr(s) { return String(s).replace(/'/g, "\\'"); }
async function copyText(el, text) {
  await navigator.clipboard.writeText(text.replace(/\\\\\\n/g, ' '));
  const orig = el.style.borderColor;
  el.style.borderColor = 'var(--ok)';
  setTimeout(() => el.style.borderColor = orig, 800);
}

// ── Init ──────────────────────────────────────────────────────────────────────
refreshHealth();
setInterval(refreshHealth, 30_000);
document.getElementById('query-input').focus();
</script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Serve the web dashboard UI."""
    return HTMLResponse(content=_DASHBOARD_HTML)
