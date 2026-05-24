import re

with open("app/api/routes/dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update tabs
new_tabs = """<div class="tabs">
<button class="tab-btn active" data-tab="search" onclick="showTab('search')">&#128269; Search</button>
<button class="tab-btn" data-tab="memory" onclick="showTab('memory')">&#128194; Memory</button>
<button class="tab-btn" data-tab="metrics" onclick="showTab('metrics')">&#128202; Metrics</button>
<button class="tab-btn" data-tab="admin" onclick="showTab('admin')">&#9881; Admin</button>
<button class="tab-btn" data-tab="billing" onclick="showTab('billing')">&#128179; Plan &amp; Billing</button>
</div>"""
content = re.sub(r'<div class="tabs">.*?</div>', new_tabs, content, flags=re.DOTALL)

# 2. Add tab contents
tab_contents = """
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
"""
content = content.replace('<div id="tab-billing" class="tab-content">', tab_contents)

# 3. Update showTab
new_show_tab = """function showTab(name){
document.querySelectorAll(".tab-content").forEach(el=>el.classList.remove("active"));
document.querySelectorAll(".tab-btn").forEach(el=>el.classList.remove("active"));
document.getElementById("tab-"+name).classList.add("active");
document.querySelector(`.tab-btn[data-tab="${name}"]`).classList.add("active");
if(name==="billing")loadBilling();
if(name==="memory") { loadTrustedDomains(); loadRecentQueries(); }
if(name==="metrics")loadMetrics();
if(name==="admin")loadAdminStats();
}"""
content = re.sub(r'function showTab\(name\)\{.*?\}', new_show_tab, content, flags=re.DOTALL)

# 4. Add new JS functions
new_js = """
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
"""
content = content.replace('async function refreshHealth(){', new_js + '\nasync function refreshHealth(){')

with open("app/api/routes/dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Dashboard UI updated successfully.")
