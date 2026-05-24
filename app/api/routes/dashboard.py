"""
Dashboard route — self-contained HTML UI at /dashboard.

Tab 1: Search    — query + results browser + system health + recent history
Tab 2: Billing   — plan info, usage bar, upgrade options, API key management
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>OLLA — Dashboard</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1117;--surface:#1a1d27;--surface2:#22263a;--border:#2e3250;
--accent:#7c6af7;--accent2:#56c2e6;--text:#e8eaf6;--muted:#8b90b4;
--ok:#4ade80;--warn:#facc15;--err:#f87171;--radius:10px;
--font:'Inter',system-ui,sans-serif}
body{background:var(--bg);color:var(--text);font-family:var(--font);
min-height:100vh;display:flex;flex-direction:column}
header{background:var(--surface);border-bottom:1px solid var(--border);
padding:14px 28px;display:flex;align-items:center;gap:14px}
header h1{font-size:1.1rem;font-weight:600;letter-spacing:-.3px}
.pill{display:inline-block;padding:2px 10px;border-radius:20px;
font-size:.7rem;font-weight:600;text-transform:uppercase}
.pill-ok{background:#14532d;color:var(--ok)}
.pill-deg{background:#713f12;color:var(--warn)}
.pill-err{background:#7f1d1d;color:var(--err)}
.pill-plan{background:#312e81;color:#a5b4fc}
.tabs{display:flex;background:var(--surface);border-bottom:1px solid var(--border);padding:0 28px}
.tab-btn{background:none;border:none;color:var(--muted);font-size:.9rem;font-weight:500;
padding:12px 20px;cursor:pointer;border-bottom:2px solid transparent;transition:color .15s,border-color .15s}
.tab-btn.active{color:var(--text);border-bottom-color:var(--accent)}
.tab-btn:hover{color:var(--text)}
.tab-content{display:none;flex:1}
.tab-content.active{display:block}
.page-grid{display:grid;grid-template-columns:1fr 340px;gap:20px;padding:24px 28px}
@media(max-width:900px){.page-grid{grid-template-columns:1fr}}
.panel{background:var(--surface);border:1px solid var(--border);
border-radius:var(--radius);padding:20px}
.panel-title{font-size:.8rem;font-weight:600;text-transform:uppercase;
letter-spacing:.08em;color:var(--muted);margin-bottom:14px}
.section-gap{margin-bottom:20px}
.btn{background:var(--accent);border:none;border-radius:8px;color:#fff;
font-weight:600;font-size:.9rem;padding:10px 20px;cursor:pointer;
transition:opacity .15s;white-space:nowrap}
.btn:hover{opacity:.85}
.btn:disabled{opacity:.45;cursor:not-allowed}
.btn-sm{padding:6px 12px;font-size:.78rem}
.btn-ghost{background:var(--surface2);color:var(--text);border:1px solid var(--border)}
.btn-danger{background:#7f1d1d;color:var(--err);border:1px solid var(--err)}
.search-form{display:flex;gap:10px;margin-bottom:20px}
.search-input{flex:1;background:var(--surface2);border:1px solid var(--border);
border-radius:8px;padding:10px 14px;color:var(--text);font-size:.95rem;outline:none;transition:border .15s}
.search-input:focus{border-color:var(--accent)}
.opts{display:flex;gap:12px;margin-bottom:18px;flex-wrap:wrap}
.opt-group label{font-size:.72rem;color:var(--muted);display:block;margin-bottom:3px}
.opt-group input[type=number]{background:var(--surface2);border:1px solid var(--border);
border-radius:6px;color:var(--text);padding:5px 8px;width:70px;font-size:.85rem}
#status{font-size:.82rem;color:var(--muted);margin-bottom:14px;min-height:1.2em}
.result-card{background:var(--surface2);border:1px solid var(--border);
border-radius:var(--radius);padding:16px;margin-bottom:14px}
.result-header{display:flex;align-items:flex-start;gap:10px;margin-bottom:8px}
.rank-badge{background:var(--accent);color:#fff;border-radius:6px;
font-size:.72rem;font-weight:700;padding:2px 8px}
.score-badge{background:var(--surface);border:1px solid var(--border);
color:var(--muted);border-radius:6px;font-size:.72rem;padding:2px 8px}
.result-title{font-size:.92rem;font-weight:600}
.result-url{font-size:.72rem;color:var(--accent2);text-decoration:none;
display:block;margin:3px 0 8px;word-break:break-all}
.result-url:hover{text-decoration:underline}
.result-content{font-size:.82rem;color:var(--muted);line-height:1.5;
max-height:120px;overflow:hidden;position:relative}
.result-content::after{content:'';position:absolute;bottom:0;left:0;right:0;
height:40px;background:linear-gradient(transparent,var(--surface2))}
.result-meta{display:flex;gap:10px;margin-top:10px;flex-wrap:wrap}
.meta-tag{font-size:.7rem;color:var(--muted);background:var(--surface);
border:1px solid var(--border);border-radius:4px;padding:2px 7px}
.curl-box{background:var(--bg);border:1px solid var(--border);border-radius:6px;
padding:8px 12px;font-family:monospace;font-size:.75rem;color:var(--accent2);
margin-top:10px;cursor:pointer;word-break:break-all}
.curl-box:hover{border-color:var(--accent)}
.citation-block{background:var(--surface2);border:1px solid var(--border);
border-radius:var(--radius);padding:14px;margin-top:16px}
.citation-block pre{font-size:.75rem;color:var(--muted);white-space:pre-wrap;
word-break:break-word;font-family:monospace}
.health-row{display:flex;justify-content:space-between;align-items:center;
padding:8px 0;border-bottom:1px solid var(--border)}
.health-row:last-child{border-bottom:none}
.health-label{font-size:.83rem}
.health-latency{font-size:.75rem;color:var(--muted)}
.history-item{display:flex;justify-content:space-between;align-items:center;
padding:7px 0;border-bottom:1px solid var(--border);cursor:pointer}
.history-item:last-child{border-bottom:none}
.history-query{font-size:.83rem;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;max-width:180px}
.history-time{font-size:.7rem;color:var(--muted)}
.history-item:hover .history-query{color:var(--accent)}
#embed-progress{font-size:.82rem;color:var(--muted);margin-top:8px}
.empty-state{text-align:center;padding:40px 0;color:var(--muted);font-size:.9rem}
.loader{display:inline-block;width:16px;height:16px;border:2px solid var(--border);
border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
#billing-page{padding:24px 28px;max-width:960px}
.usage-bar-wrap{background:var(--surface2);border-radius:8px;height:12px;overflow:hidden;margin:10px 0 6px}
.usage-bar{height:100%;background:var(--accent);border-radius:8px;transition:width .4s}
.usage-bar.warn{background:var(--warn)}
.usage-bar.danger{background:var(--err)}
.usage-label{display:flex;justify-content:space-between;font-size:.78rem;color:var(--muted)}
.plan-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px;margin-top:14px}
.plan-card{background:var(--surface2);border:2px solid var(--border);
border-radius:var(--radius);padding:18px;cursor:pointer;transition:border-color .15s}
.plan-card:hover{border-color:var(--accent)}
.plan-card.current{border-color:var(--ok)}
.plan-card h3{font-size:1rem;font-weight:700;margin-bottom:4px}
.plan-card .price{font-size:1.5rem;font-weight:800;color:var(--accent)}
.plan-card .price span{font-size:.75rem;color:var(--muted);font-weight:400}
.plan-card .limit{font-size:.78rem;color:var(--muted);margin:6px 0 12px}
.key-table{width:100%;border-collapse:collapse;font-size:.84rem}
.key-table th{text-align:left;color:var(--muted);font-size:.72rem;text-transform:uppercase;
letter-spacing:.06em;padding:8px 10px;border-bottom:1px solid var(--border)}
.key-table td{padding:10px 10px;border-bottom:1px solid var(--border)}
.key-table tr:last-child td{border-bottom:none}
.key-badge{font-family:monospace;background:var(--bg);padding:2px 8px;
border-radius:4px;border:1px solid var(--border);font-size:.78rem}
.key-active{color:var(--ok);font-size:.72rem}
.key-inactive{color:var(--err);font-size:.72rem}
.register-form{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}
.register-form input{flex:1;min-width:180px;background:var(--surface2);border:1px solid var(--border);
border-radius:8px;padding:9px 13px;color:var(--text);font-size:.9rem;outline:none}
.register-form input:focus{border-color:var(--accent)}
#reg-result{font-size:.82rem;margin-top:10px}
.key-reveal{background:var(--bg);border:1px solid var(--ok);border-radius:8px;
padding:14px;margin-top:12px;font-family:monospace;color:var(--ok);font-size:.85rem;word-break:break-all}
</style>
</head>
<body>
<header>
<h1>&#9889; OLLA</h1>
<span style="font-size:.75rem;color:var(--muted)">for Agents</span>
<div style="flex:1"></div>
<span id="overall-status"></span>
<button class="btn btn-sm btn-ghost" onclick="refreshHealth()">&#8635; Health</button>
</header>

<div class="tabs">
<button class="tab-btn active" data-tab="search" onclick="showTab('search')">&#128269; Search</button>
<button class="tab-btn" data-tab="memory" onclick="showTab('memory')">&#128194; Memory</button>
<button class="tab-btn" data-tab="metrics" onclick="showTab('metrics')">&#128202; Metrics</button>
<button class="tab-btn" data-tab="admin" onclick="showTab('admin')">&#9881; Admin</button>
<button class="tab-btn" data-tab="billing" onclick="showTab('billing')">&#128179; Plan &amp; Billing</button>
</div>

<div id="tab-search" class="tab-content active">
<div class="page-grid">
<div>
<div class="search-form">
<input id="query-input" class="search-input" type="text"
placeholder="Ask anything — e.g. how does pgvector work"
onkeydown="if(event.key==='Enter')doSearch()"/>
<button class="btn" id="search-btn" onclick="doSearch()">Search</button>
<button class="btn btn-ghost" onclick="doSemantic()">Semantic</button>
</div>
<div class="opts">
<div class="opt-group"><label style="display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="opt-hybrid" checked style="width:auto"> Smart Routing (Hybrid)</label></div>
<div class="opt-group"><label>Max results</label><input type="number" id="opt-max" value="5" min="1" max="10"/></div>
<div class="opt-group"><label>Min score</label><input type="number" id="opt-score" value="0" min="0" max="1" step="0.05" style="width:80px"/></div>
</div>
<div id="status"></div>
<div id="results-container"></div>
</div>
<div style="display:flex;flex-direction:column;gap:18px">
<div class="panel">
<div class="panel-title">System health</div>
<div id="health-detail"><div style="color:var(--muted);font-size:.83rem">Loading...</div></div>
<div style="margin-top:12px">
<button class="btn btn-sm btn-ghost" style="width:100%" onclick="triggerEmbedStore()">&#8627; Backfill embeddings</button>
<div id="embed-progress"></div>
</div>
</div>
<div class="panel">
<div class="panel-title">Recent searches</div>
<div id="history-list"><div class="empty-state">No searches yet</div></div>
</div>
</div>
</div>
</div>


<div id="tab-memory" class="tab-content">
<div class="page-grid">
  <div class="panel">
    <div class="panel-title">Trusted Domains</div>
    <button class="btn btn-sm btn-ghost" onclick="loadTrustedDomains()">Refresh</button>
    <div id="trusted-domains-list" style="margin-top:10px;"><span class="loader"></span></div>
  </div>
  <div class="panel">
    <div class="panel-title">Recent Queries</div>
    <button class="btn btn-sm btn-ghost" onclick="loadRecentQueries()">Refresh</button>
    <div id="recent-queries-list" style="margin-top:10px;"><span class="loader"></span></div>
  </div>
</div>
</div>

<div id="tab-metrics" class="tab-content">
<div style="padding:24px 28px;max-width:960px">
<div class="panel section-gap">
  <div class="panel-title">Feedback Stats</div>
  <button class="btn btn-sm btn-ghost" onclick="loadMetrics()">Refresh</button>
  <div id="metrics-content" style="margin-top:10px;"><span class="loader"></span></div>
</div>
</div>
</div>

<div id="tab-admin" class="tab-content">
<div style="padding:24px 28px;max-width:960px">
<div class="panel section-gap">
  <div class="panel-title">Admin Operations</div>
  <p style="font-size:0.85rem;color:var(--muted);margin-bottom:10px">Requires Admin API Key.</p>
  <button class="btn btn-sm btn-ghost" onclick="loadAdminStats()">View DB Stats</button>
  <button class="btn btn-sm btn-danger" onclick="purgeData()">Purge Old Data</button>
  <div id="admin-content" style="margin-top:14px;"></div>
</div>
</div>
</div>

<div id="tab-billing" class="tab-content">

<div id="billing-page">
<div class="panel section-gap">
<div class="panel-title">Current plan</div>
<div id="plan-summary" style="color:var(--muted);font-size:.85rem"><span class="loader"></span> Loading...</div>
</div>
<div class="panel section-gap">
<div class="panel-title">Upgrade plan</div>
<div class="plan-cards" id="plan-cards"><div style="color:var(--muted);font-size:.83rem">Loading plans...</div></div>
</div>
<div class="panel section-gap">
<div class="panel-title">API Keys</div>
<div style="margin-bottom:18px">
<div style="font-size:.83rem;color:var(--muted);margin-bottom:10px">New here? Enter your email to get a free API key:</div>
<div class="register-form">
<input type="email" id="reg-email" placeholder="you@example.com"/>
<input type="text" id="reg-name" placeholder="Key name (optional)"/>
<button class="btn btn-sm" onclick="registerKey()">Get Free Key</button>
</div>
<div id="reg-result"></div>
</div>
<hr style="border:none;border-top:1px solid var(--border);margin:16px 0"/>
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
<span style="font-size:.83rem;color:var(--muted)">Your keys (requires X-API-Key header)</span>
<button class="btn btn-sm btn-ghost" onclick="loadKeys()">&#8635; Refresh</button>
</div>
<div style="display:flex;gap:8px;margin-bottom:12px">
<input type="text" id="mgmt-api-key" placeholder="Paste your API key to manage keys"
style="flex:1;background:var(--surface2);border:1px solid var(--border);
border-radius:8px;padding:8px 12px;color:var(--text);font-size:.85rem;outline:none"
onkeydown="if(event.key==='Enter')loadKeys()"/>
<button class="btn btn-sm" onclick="loadKeys()">Load Keys</button>
</div>
<div id="keys-table-wrap"><div style="color:var(--muted);font-size:.83rem">Enter your API key above to see your keys.</div></div>
<div style="margin-top:14px">
<button class="btn btn-sm btn-ghost" onclick="createKey()">+ Create additional key</button>
</div>
</div>
</div>
</div>

<script>
const API="/api/v1";
let searchHistory=[];
function showTab(name){
document.querySelectorAll(".tab-content").forEach(el=>el.classList.remove("active"));
document.querySelectorAll(".tab-btn").forEach(el=>el.classList.remove("active"));
document.getElementById("tab-"+name).classList.add("active");
document.querySelector(`.tab-btn[data-tab="${name}"]`).classList.add("active");
if(name==="billing")loadBilling();
if(name==="memory") { loadTrustedDomains(); loadRecentQueries(); }
if(name==="metrics")loadMetrics();
if(name==="admin")loadAdminStats();
}

async function getApiKeyHeader() {
  const apiKey=document.getElementById("mgmt-api-key") ? document.getElementById("mgmt-api-key").value.trim() : "";
  return apiKey ? {"X-API-Key":apiKey} : {};
}

async function loadTrustedDomains() {
  try {
    const d = await apiFetch(API+"/sources/trusted-domains", {headers: await getApiKeyHeader()});
    if(!d.domains || !d.domains.length) {
      document.getElementById("trusted-domains-list").innerHTML='<div class="empty-state">No trusted domains.</div>';
      return;
    }
    document.getElementById("trusted-domains-list").innerHTML=d.domains.map(td=>
      '<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:0.85rem">' +
      '<strong>' + escHtml(td.domain) + '</strong> - Trust: ' + td.trust_score.toFixed(2) + 
      '</div>'
    ).join("");
  } catch(e) {
    document.getElementById("trusted-domains-list").innerHTML='<span style="color:var(--err)">Failed to load: '+escHtml(e.message)+'</span>';
  }
}

async function loadRecentQueries() {
  try {
    const d = await apiFetch(API+"/sources/recent-queries", {headers: await getApiKeyHeader()});
    if(!d.queries || !d.queries.length) {
      document.getElementById("recent-queries-list").innerHTML='<div class="empty-state">No recent queries.</div>';
      return;
    }
    document.getElementById("recent-queries-list").innerHTML=d.queries.map(q=>
      '<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:0.85rem">' +
      escHtml(q.query_text) + ' <span style="color:var(--muted);font-size:0.75rem">(' + q.result_count + ' results)</span>' +
      '</div>'
    ).join("");
  } catch(e) {
    document.getElementById("recent-queries-list").innerHTML='<span style="color:var(--err)">Failed to load: '+escHtml(e.message)+'</span>';
  }
}

async function loadMetrics() {
  try {
    const d = await apiFetch(API+"/feedback/stats", {headers: await getApiKeyHeader()});
    const html = `
      <div style="font-size:0.9rem;margin-bottom:10px">
        <strong>Satisfaction Rate:</strong> ${(d.satisfaction_rate * 100).toFixed(1)}% <br/>
        <strong>Total Feedback:</strong> ${d.total_feedback_count}
      </div>
      <div style="font-size:0.85rem;color:var(--muted)">Top Domains:</div>
      <ul style="font-size:0.85rem;margin-left:20px;color:var(--text)">
        ${(d.top_domains||[]).map(td => `<li>${escHtml(td)}</li>`).join('')}
      </ul>
    `;
    document.getElementById("metrics-content").innerHTML=html;
  } catch(e) {
    document.getElementById("metrics-content").innerHTML='<span style="color:var(--err)">Failed to load metrics: '+escHtml(e.message)+'</span>';
  }
}

async function loadAdminStats() {
  const headers = await getApiKeyHeader();
  if(!headers["X-API-Key"]) {
     document.getElementById("admin-content").innerHTML='<span style="color:var(--err)">Please enter an Admin API Key in the Billing tab first.</span>';
     return;
  }
  document.getElementById("admin-content").innerHTML='<span class="loader"></span> Loading DB Stats...';
  try {
    const d = await apiFetch(API+"/admin/stats", {headers});
    const html = `
      <pre style="background:var(--surface2);padding:10px;border-radius:8px;font-size:0.8rem;overflow-x:auto;color:var(--text)">
${escHtml(JSON.stringify(d, null, 2))}
      </pre>
    `;
    document.getElementById("admin-content").innerHTML=html;
  } catch(e) {
    document.getElementById("admin-content").innerHTML='<span style="color:var(--err)">Failed to load admin stats: '+escHtml(e.message)+'</span>';
  }
}

async function purgeData() {
  if(!confirm("Are you sure you want to purge old data?")) return;
  const headers = await getApiKeyHeader();
  try {
    const d = await apiPost(API+"/admin/purge", {days_old: 30}, headers);
    alert("Purge successful: " + JSON.stringify(d));
    loadAdminStats();
  } catch(e) {
    alert("Purge failed: " + e.message);
  }
}

async function refreshHealth(){
try{const d=await apiFetch(API+"/health");renderHealth(d);}
catch(e){document.getElementById("health-detail").innerHTML=
'<div style="color:var(--err);font-size:.83rem">Cannot reach API.</div>';}
}
function renderHealth(d){
const cls=d.status==="ok"?"pill-ok":"pill-deg";
document.getElementById("overall-status").innerHTML='<span class="pill '+cls+'">'+d.status+"</span>";
const comps=d.components||{};
const rows=Object.entries(comps).map(([n,i])=>{
const c=i.status==="ok"?"pill-ok":i.status==="slow"?"pill-deg":"pill-err";
const lat=i.latency_ms!=null?'<span class="health-latency">'+i.latency_ms+"ms</span>":'';
return'<div class="health-row"><span class="health-label">'+n+'</span><div style="display:flex;align-items:center;gap:8px">'+lat+'<span class="pill '+c+'">'+i.status+"</span></div></div>";
}).join("");
document.getElementById("health-detail").innerHTML=rows||'<div style="color:var(--muted);font-size:.83rem">v'+d.version+"</div>";
}
async function doSearch(){
const q=document.getElementById("query-input").value.trim();if(!q)return;
setStatus('<span class="loader"></span> Searching...');setBtn(true);
try{
const body={query:q,max_results:parseInt(document.getElementById("opt-max").value)||5,
min_score:parseFloat(document.getElementById("opt-score").value)||0};
const useHybrid=document.getElementById("opt-hybrid")?.checked;
const endpoint=useHybrid?API+"/search/hybrid":API+"/search";
const d=await apiPost(endpoint,body);
addHistory(q,d.processing_time_ms,d.total_results);renderResults(d,body);
setStatus("Found <b>"+d.total_results+"</b> results in "+d.processing_time_ms+"ms"
+(d.cache_hit?' &nbsp;<span class="pill pill-ok">cache hit</span>':''));
}catch(e){setStatus('<span style="color:var(--err)">'+escHtml(e.message||"Search failed")+"</span>");}
finally{setBtn(false);}
}
async function doSemantic(){
const q=document.getElementById("query-input").value.trim();if(!q)return;
setStatus('<span class="loader"></span> Semantic search...');setBtn(true);
try{const d=await apiPost(API+"/search/semantic",{query:q,top_k:10,min_similarity:0.5});
renderSemanticResults(d);setStatus("Found <b>"+d.total_chunks+"</b> semantic chunks");}
catch(e){setStatus('<span style="color:var(--err)">'+escHtml(e.message||"Failed")+"</span>");}
finally{setBtn(false);}
}
function renderResults(d,reqBody){
if(!d.results||!d.results.length){
document.getElementById("results-container").innerHTML='<div class="empty-state">No results found.</div>';return;}
const cards=d.results.map(r=>'<div class="result-card"><div class="result-header"><span class="rank-badge">#'+r.rank+'</span><span class="score-badge">score '+r.score.toFixed(3)+'</span><span class="result-title">'+escHtml(r.title)+'</span></div><a class="result-url" href="'+escHtml(r.url)+'" target="_blank">'+escHtml(r.url)+'</a><div class="result-content">'+escHtml(r.content.slice(0,400))+'</div><div class="result-meta"><span class="meta-tag">'+r.char_count.toLocaleString()+' chars</span><span class="meta-tag">'+r.chunk_count+' chunks</span></div></div>').join("");
const cit=d.citations_markdown?'<div class="citation-block"><div class="panel-title" style="margin-bottom:8px">Citations</div><pre>'+escHtml(d.citations_markdown)+"</pre></div>":'';
document.getElementById("results-container").innerHTML=cards+cit;
}
function renderSemanticResults(d){
if(!d.chunks||!d.chunks.length){document.getElementById("results-container").innerHTML='<div class="empty-state">No semantic matches.</div>';return;}
document.getElementById("results-container").innerHTML=d.chunks.map((c,i)=>'<div class="result-card"><div class="result-header"><span class="rank-badge">#'+(i+1)+'</span><span class="score-badge">sim '+c.similarity.toFixed(3)+'</span><span class="result-title">'+escHtml(c.title)+'</span></div><a class="result-url" href="'+escHtml(c.url)+'" target="_blank">'+escHtml(c.url)+'</a><div class="result-content">'+escHtml(c.text)+'</div></div>').join("");
}
async function triggerEmbedStore(){
document.getElementById("embed-progress").innerHTML='<span class="loader"></span> Generating embeddings...';
try{const d=await apiPost(API+"/search/embed-and-store",{});
document.getElementById("embed-progress").innerHTML='<span style="color:var(--ok)">&#10003; '+d.message+" ("+d.processed+" chunks)</span>";}
catch(e){document.getElementById("embed-progress").innerHTML='<span style="color:var(--err)">Failed</span>';}
}
function addHistory(query,ms,count){
searchHistory.unshift({query,ms,count,time:new Date().toLocaleTimeString()});
if(searchHistory.length>20)searchHistory.pop();
const el=document.getElementById("history-list");
el.innerHTML=searchHistory.map(h=>'<div class="history-item" onclick="rerun(\''+ escAttr(h.query)+'\')">'+
'<span class="history-query" title="'+escAttr(h.query)+'">'+escHtml(h.query)+'</span>'+
'<span class="history-time">'+h.time+" &middot; "+h.count+" results</span></div>").join("");
}
function rerun(q){document.getElementById("query-input").value=q;showTab("search");doSearch();}
async function loadBilling(){
const apiKey=document.getElementById("mgmt-api-key").value.trim();
try{const d=await apiFetch(API+"/billing/usage",{headers:apiKey?{"X-API-Key":apiKey}:{}});
renderPlanSummary(d);renderPlanCards(d);}
catch(e){document.getElementById("plan-summary").innerHTML=
'<span style="color:var(--muted)">Log in with an API key to see your plan details.</span>';
renderDefaultPlanCards();}
}
function renderPlanSummary(d){
const pct=d.queries_limit?Math.min(100,Math.round(d.queries_used/d.queries_limit*100)):0;
const bc=pct>90?"danger":pct>70?"warn":"";
const lim=d.queries_limit?d.queries_limit.toLocaleString():"&#8734;";
const per=new Date(d.period_start).toLocaleDateString("en-US",{month:"short",day:"numeric"})+" - "+
new Date(d.period_end).toLocaleDateString("en-US",{month:"short",day:"numeric"});
document.getElementById("plan-summary").innerHTML=
'<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px"><span class="pill pill-plan">'+
d.plan.toUpperCase()+'</span><span style="font-size:.85rem;color:var(--muted)">'+escHtml(d.email)+'</span>'+
(d.plan!=="free"?'<button class="btn btn-sm btn-ghost" onclick="openPortal()">Manage billing &#8599;</button>':'')+"</div>"+
'<div style="font-size:.82rem;color:var(--muted);margin-bottom:6px">Queries this month ('+per+')</div>'+
'<div class="usage-bar-wrap"><div class="usage-bar '+bc+'" style="width:'+pct+'%"></div></div>'+
'<div class="usage-label"><span>'+d.queries_used.toLocaleString()+' used</span><span>'+lim+' limit</span></div>';
}
function renderPlanCards(d){
const P=[{plan:"free",label:"Free",price:"$0",limit:"1,000/mo"},{plan:"starter",label:"Starter",price:"$29",limit:"10,000/mo"},
{plan:"pro",label:"Pro",price:"$99",limit:"50,000/mo"},{plan:"team",label:"Team",price:"$299",limit:"200,000/mo"},
{plan:"enterprise",label:"Enterprise",price:"Custom",limit:"Unlimited"}];
document.getElementById("plan-cards").innerHTML=P.map(p=>
'<div class="plan-card '+( p.plan===d.plan?"current":"")+'" onclick="upgradeClicked(\''+ p.plan+'\',\''+ d.plan+'\')">'+
'<h3>'+p.label+(p.plan===d.plan?" &#10003;":"")+"</h3>"+
'<div class="price">'+p.price+'<span>'+( p.price!=="Custom"?"/mo":"")+"</span></div>"+
'<div class="limit">'+p.limit+"</div>"+
(p.plan===d.plan?'<div style="margin-top:10px;font-size:.75rem;color:var(--ok)">Current plan</div>':
p.plan==="free"?"":
'<button class="btn btn-sm" style="margin-top:10px;width:100%" onclick="event.stopPropagation();startCheckout(\''+ p.plan+'\')">'+
"Upgrade &rarr;</button>")+"</div>").join("");
}
function renderDefaultPlanCards(){
const P=[{plan:"free",label:"Free",price:"$0",limit:"1,000/mo"},{plan:"starter",label:"Starter",price:"$29",limit:"10,000/mo"},
{plan:"pro",label:"Pro",price:"$99",limit:"50,000/mo"},{plan:"team",label:"Team",price:"$299",limit:"200,000/mo"}];
document.getElementById("plan-cards").innerHTML=P.map(p=>
'<div class="plan-card"><h3>'+p.label+"</h3>"+'<div class="price">'+p.price+'<span>'+
(p.price!=="$0"?"/mo":"")+"</span></div><div class='limit'>"+p.limit+"</div>"+
(p.plan!=="free"?'<button class="btn btn-sm" style="margin-top:10px;width:100%" onclick="startCheckout(\''+ p.plan+'\')">'+
"Upgrade &rarr;</button>":"")+"</div>").join("");
}
function upgradeClicked(plan,current){if(plan===current||plan==="free"||plan==="enterprise")return;startCheckout(plan);}
async function startCheckout(plan){
const apiKey=document.getElementById("mgmt-api-key").value.trim();
if(!apiKey){alert("Enter your API key above before upgrading.");return;}
try{const d=await apiFetch(API+"/billing/checkout",{method:"POST",headers:{"Content-Type":"application/json","X-API-Key":apiKey},body:JSON.stringify({plan})});
window.location.href=d.checkout_url;}catch(e){alert("Checkout failed: "+e.message);}
}
async function openPortal(){
const apiKey=document.getElementById("mgmt-api-key").value.trim();
if(!apiKey){alert("Enter your API key first.");return;}
try{const d=await apiFetch(API+"/billing/portal",{method:"POST",headers:{"X-API-Key":apiKey}});
window.open(d.portal_url,"_blank");}catch(e){alert("Portal failed: "+e.message);}
}
async function registerKey(){
const email=document.getElementById("reg-email").value.trim();
const name=document.getElementById("reg-name").value.trim()||"Default key";
if(!email){document.getElementById("reg-result").innerHTML=
'<span style="color:var(--err)">Enter an email address.</span>';return;}
try{const d=await apiPost(API+"/keys/register",{email,name});
document.getElementById("reg-result").innerHTML=
'<div style="color:var(--ok);font-size:.83rem;margin-bottom:8px">&#10003; Key created! Plan: <b>'+d.plan+'</b></div>'+
'<div class="key-reveal"><div style="font-size:.72rem;color:var(--muted);margin-bottom:6px">&#9888; Copy now — won't be shown again:</div>'+
'<div id="new-key-val">'+escHtml(d.api_key)+'</div>'+
'<button class="btn btn-sm btn-ghost" style="margin-top:8px" onclick="navigator.clipboard.writeText(\''+ escAttr(d.api_key)+'\')">Copy</button></div>'+
'<div style="font-size:.78rem;color:var(--muted);margin-top:8px">Paste it below to manage your keys.</div>';
document.getElementById("mgmt-api-key").value=d.api_key;loadKeys();}
catch(e){document.getElementById("reg-result").innerHTML='<span style="color:var(--err)">'+escHtml(e.message)+"</span>";}
}
async function loadKeys(){
const apiKey=document.getElementById("mgmt-api-key").value.trim();
if(!apiKey)return;
try{const keys=await apiFetch(API+"/keys",{headers:{"X-API-Key":apiKey}});
document.getElementById("keys-table-wrap").innerHTML=renderKeysTable(keys,apiKey);loadBilling();}
catch(e){document.getElementById("keys-table-wrap").innerHTML=
'<span style="color:var(--err);font-size:.83rem">'+escHtml(e.message)+"</span>";}
}
function renderKeysTable(keys,apiKey){
if(!keys.length)return'<div style="color:var(--muted);font-size:.83rem">No keys found.</div>';
return'<table class="key-table"><thead><tr><th>Key</th><th>Name</th><th>Status</th><th>Created</th><th></th></tr></thead><tbody>'+
keys.map(k=>'<tr><td><span class="key-badge">'+escHtml(k.key_prefix)+'...</span></td><td>'+escHtml(k.name)+'</td>'+
'<td><span class="'+( k.is_active?"key-active":"key-inactive")+'">'+( k.is_active?"Active":"Revoked")+'</span></td>'+
'<td style="color:var(--muted);font-size:.75rem">'+new Date(k.created_at).toLocaleDateString()+'</td>'+
'<td>'+( k.is_active?'<button class="btn btn-sm btn-danger" onclick="revokeKey(\''+ k.id+'\',\''+ escAttr(apiKey)+'\')">'+
"Revoke</button>":"&mdash;")+"</td></tr>").join("")+"</tbody></table>";
}
async function createKey(){
const apiKey=document.getElementById("mgmt-api-key").value.trim();
if(!apiKey){alert("Enter your API key first.");return;}
const name=prompt("Key name:","New key");if(!name)return;
try{const d=await apiFetch(API+"/keys",{method:"POST",headers:{"Content-Type":"application/json","X-API-Key":apiKey},body:JSON.stringify({name})});
alert("New key created!\n\n"+d.api_key+"\n\nCopy it now.");loadKeys();}
catch(e){alert("Failed: "+e.message);}
}
async function revokeKey(keyId,apiKey){
if(!confirm("Revoke this key? Apps using it will stop working immediately."))return;
try{await apiFetch(API+"/keys/"+keyId,{method:"DELETE",headers:{"X-API-Key":apiKey}});loadKeys();}
catch(e){alert("Failed: "+e.message);}
}
async function apiFetch(url,opts={}){
const res=await fetch(url,opts);
if(!res.ok){const err=await res.json().catch(()=>({detail:res.statusText}));throw new Error(err.detail||res.statusText);}
return res.status===204?null:res.json();
}
async function apiPost(url,body,extra={}){
return apiFetch(url,{method:"POST",headers:{"Content-Type":"application/json",...extra},body:JSON.stringify(body)});
}
function setStatus(html){document.getElementById("status").innerHTML=html;}
function setBtn(d){document.getElementById("search-btn").disabled=d;}
function escHtml(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function escAttr(s){return String(s).replace(/'/g,"\\'");}
refreshHealth();
setInterval(refreshHealth,30000);
document.getElementById("query-input").focus();
if(location.hash==="#billing")showTab("billing");
</script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Serve the web dashboard UI."""
    return HTMLResponse(content=_DASHBOARD_HTML)
