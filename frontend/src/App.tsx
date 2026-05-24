import { useState, useEffect } from 'react'
import './App.css'

/* ============================================================
   OLLA frontend — Hybrid Search. Smarter Answers.
   Hero + tabbed console wired to the real OLLA API.
   ============================================================ */

// ---------- types ----------
interface Trace { stage: string; status: string; duration_ms: number; detail: string }
interface Result {
  rank: number; title: string; url: string; content: string
  score: number; char_count?: number; chunk_count?: number
}
interface SearchResp {
  query: string; total_results: number; processing_time_ms: number
  results: Result[]; answer: string; answer_model: string
  trace: Trace[]; degraded: boolean; cache_hit: boolean; query_id: string | null
}
interface HybridResp {
  query: string; retrieval_mode: string; query_class: string; confidence: number
  from_memory: boolean; processing_time_ms: number; answer: string; answer_model: string
  results: Result[]; routing_trace: string[]; cache_hit: boolean; degraded: boolean
}
interface GraphChunk {
  id: string; text: string; url: string; title: string
  similarity?: number; hop: number; edge_weight?: number
}
interface GraphResp {
  seed_chunks: GraphChunk[]; connected_chunks: GraphChunk[]
  total_chunks: number; hops: number
}
interface CompHealth { status: string; latency_ms?: number; error?: string }
interface HealthResp { status: string; version: string; service: string; components: Record<string, CompHealth> }
interface FeedbackResp { feedback_id: string; level: string; feedback_type: string; effects: string[] }
interface StatsResp {
  total: number; by_type: Record<string, number>; by_level: Record<string, number>
  satisfaction_rate: number; best_sources: Array<Record<string, unknown>>
  worst_sources: Array<Record<string, unknown>>
}
interface LastState { queryId: string | null; results: Result[] }

// ---------- api ----------
async function api(path: string, opts?: RequestInit) {
  const ctrl = new AbortController()
  const timer = window.setTimeout(() => ctrl.abort(), 180000)
  let res: Response
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
      signal: ctrl.signal,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error('Request timed out (180s) - the server may still be busy.')
    }
    throw new Error('Cannot reach the OLLA API. Make sure the backend is running on port 8000.')
  } finally {
    window.clearTimeout(timer)
  }
  const text = await res.text()
  let data: Record<string, unknown> = {}
  try { data = text ? JSON.parse(text) : {} } catch { data = {} }
  if (!res.ok) {
    const d = data.detail
    if (typeof d === 'string') throw new Error(d)
    if (Array.isArray(d)) throw new Error(d.map((x) => (x as { msg?: string }).msg || 'invalid').join('; '))
    throw new Error(`Request failed (${res.status})`)
  }
  return data
}

// ---------- icons ----------
const ICONS: Record<string, string> = {
  search: '<circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/>',
  layers: '<path d="M12 3 21 8 12 13 3 8z"/><path d="M3 13 12 18 21 13"/>',
  graph: '<circle cx="6" cy="6" r="2.4"/><circle cx="18" cy="7" r="2.4"/><circle cx="9" cy="18" r="2.4"/><line x1="8.3" y1="6.8" x2="15.7" y2="6.4"/><line x1="6.6" y1="8.3" x2="8.4" y2="15.6"/><line x1="10.7" y1="16.4" x2="16.3" y2="9"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  message: '<path d="M4 5h16v11H9l-4 4z"/>',
  chart: '<line x1="6" y1="20" x2="6" y2="11"/><line x1="12" y1="20" x2="12" y2="5"/><line x1="18" y1="20" x2="18" y2="14"/><line x1="3" y1="20.5" x2="21" y2="20.5"/>',
  key: '<circle cx="8" cy="8" r="4"/><path d="M10.8 10.8 20 20M16.5 16.5l2-2M18.8 18.8l2-2"/>',
  terminal: '<rect x="2.5" y="4" width="19" height="16" rx="2"/><path d="M7 9l3.2 3-3.2 3"/><line x1="12.5" y1="15.5" x2="17" y2="15.5"/>',
  arrow: '<line x1="4" y1="12" x2="18.5" y2="12"/><path d="M13 6l6 6-6 6"/>',
  check: '<path d="M5 13l4 4 10-11"/>',
  x: '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
  alert: '<path d="M12 3 22 20H2z"/><line x1="12" y1="9.5" x2="12" y2="14"/><circle cx="12" cy="17.3" r="0.5"/>',
  info: '<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16.5"/><circle cx="12" cy="7.8" r="0.5"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  refresh: '<path d="M20.5 12a8.5 8.5 0 1 1-2.5-6"/><path d="M20.5 4v5h-5"/>',
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  link: '<path d="M9 15 15 9"/><path d="M10 6.6 12.6 4a4 4 0 0 1 5.6 5.6L15.5 12.2"/><path d="M14 17.4 11.4 20a4 4 0 0 1-5.6-5.6L8.5 11.8"/>',
  bolt: '<path d="M13 2 4 14h6l-1 8 9-12h-6z"/>',
  book: '<path d="M5 4.5h13v15H7.5a2.5 2.5 0 0 1-2.5-2.5z"/><line x1="9" y1="4.5" x2="9" y2="19.5"/>',
  spark: '<path d="M12 3v6M12 15v6M3 12h6M15 12h6M6 6l3 3M15 15l3 3M18 6l-3 3M9 15l-3 3"/>',
  shield: '<path d="M12 3 20 6v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
}
function Icon({ name }: { name: string }) {
  return (
    <svg
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round"
      dangerouslySetInnerHTML={{ __html: ICONS[name] || '' }}
    />
  )
}

// ---------- helpers ----------
function Answer({ text }: { text: string }) {
  const parts = (text || '').split(/(\[\d+\])/g)
  return (
    <>
      {parts.map((p, i) =>
        /^\[\d+\]$/.test(p)
          ? <span className="cite" key={i}>{p}</span>
          : <span key={i}>{p}</span>,
      )}
    </>
  )
}

function Pipeline({ trace }: { trace: Trace[] }) {
  return (
    <div className="pipeline">
      {trace.map((t, i) => (
        <span key={t.stage + i} style={{ display: 'contents' }}>
          {i > 0 && <span className="parrow">›</span>}
          <span
            className={`pstep s-${t.status}`}
            style={{ animationDelay: `${i * 70}ms` }}
            title={t.detail}
          >
            <span className="pd" />
            {t.stage}
            <span className="pst">{t.status}</span>
          </span>
        </span>
      ))}
    </div>
  )
}

function Sources({ results }: { results: Result[] }) {
  return (
    <>
      <div className="sub-h">Sources · {results.length}</div>
      {results.map((r) => (
        <div className="source" key={r.rank + r.url}>
          <span className="rank">{r.rank}</span>
          <div className="body">
            <div className="title">{r.title || 'Untitled'}</div>
            <a className="url" href={r.url} target="_blank" rel="noreferrer">{r.url}</a>
            {r.content && <div className="snip">{r.content.slice(0, 240)}</div>}
          </div>
          <span className="score">{(r.score ?? 0).toFixed(3)}</span>
        </div>
      ))}
    </>
  )
}

function Skeleton() {
  return (
    <div className="skeleton">
      <div className="sk w1" /><div className="sk w2" /><div className="sk w3" />
    </div>
  )
}

function ErrorNote({ msg }: { msg: string }) {
  return (
    <div className="notice err">
      <Icon name="alert" />
      <div>{msg}</div>
    </div>
  )
}

// ---------- nav ----------
function Nav({ online }: { online: boolean | null }) {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  return (
    <nav className={`nav${scrolled ? ' scrolled' : ''}`}>
      <div className="nav-inner">
        <a href="#top" className="brand">
          <span className="brand-mark" />
          OLLA
        </a>
        <ul className="nav-links">
          <li><a href="#features">Capabilities</a></li>
          <li><a href="#console">Console</a></li>
          <li><a href="#search">Search</a></li>
          <li><a href="#feedback">Feedback</a></li>
        </ul>
        <span className="nav-spacer" />
        <span className="nav-chip">
          <span className={`nav-dot${online === false ? ' off' : ''}`} />
          {online === null ? 'checking…' : online ? 'API online' : 'API offline'}
        </span>
        <span className="nav-chip">v1.0.0</span>
        <a href="#console" className="btn btn-primary btn-sm">
          Launch console <Icon name="arrow" />
        </a>
      </div>
    </nav>
  )
}

// ---------- hero ----------
const QUERIES = [
  'how does pgvector indexing work',
  'compare HNSW and IVFFlat recall',
  'what is retrieval-augmented generation',
  'best practices for chunking documents',
]
function useTypewriter(words: string[]) {
  const [text, setText] = useState('')
  useEffect(() => {
    let w = 0, c = 0, deleting = false, alive = true
    let timer = 0
    const tick = () => {
      if (!alive) return
      const word = words[w]
      if (!deleting) {
        c++
        setText(word.slice(0, c))
        if (c === word.length) { deleting = true; timer = window.setTimeout(tick, 1900); return }
      } else {
        c--
        setText(word.slice(0, c))
        if (c === 0) { deleting = false; w = (w + 1) % words.length }
      }
      timer = window.setTimeout(tick, deleting ? 34 : 66)
    }
    timer = window.setTimeout(tick, 500)
    return () => { alive = false; window.clearTimeout(timer) }
  }, [words])
  return text
}

function Hero() {
  const typed = useTypewriter(QUERIES)
  return (
    <header className="hero" id="top">
      <div className="wrap">
        <div className="hero-eyebrow reveal">
          <Icon name="spark" />
          Local-first retrieval engine · <b>knowledge graph</b> · synthesized answers
        </div>
        <h1 className="wordmark">OLLA</h1>
        <div className="hero-tag reveal">Hybrid Search · Smarter Answers</div>
        <p className="hero-lead reveal">
          OLLA crawls the web, ranks and cleans what it finds, builds a knowledge
          graph from it, and hands back a cited, LLM-synthesized answer — not a
          wall of blue links.
        </p>
        <div className="hero-cta reveal">
          <a href="#console" className="btn btn-primary">
            <Icon name="terminal" /> Open the console
          </a>
          <a href="#features" className="btn btn-ghost">
            <Icon name="book" /> See capabilities
          </a>
        </div>

        <div className="terminal">
          <div className="term-bar">
            <i className="r" /><i className="y" /><i className="g" />
            <span>olla — interactive shell</span>
          </div>
          <div className="term-body">
            <div className="term-line">
              <span className="term-prompt"><b>OLLA</b> ask ❯ </span>
              <span className="term-typed">{typed}</span>
              <span className="term-caret">&nbsp;</span>
            </div>
            <div className="term-out">
              <div><span className="cy">search</span>:success ›
                {' '}<span className="cy">rank</span>:success ›
                {' '}<span className="cy">answer</span>:success ›
                {' '}<span className="cy">store</span>:success ›
                {' '}<span className="cy">embed</span>:success ›
                {' '}<span className="ok">graph</span>:success</div>
              <div style={{ marginTop: 6 }}>
                <span className="vi">◆ OLLA ANSWER</span> — 5 sources · cited · 142 graph edges
              </div>
            </div>
          </div>
        </div>

        <div className="hero-stats reveal">
          <div className="hero-stat"><div className="v grad-text">7-stage</div><div className="l">TRACED PIPELINE</div></div>
          <div className="hero-stat"><div className="v grad-text">cited</div><div className="l">SYNTHESIZED ANSWERS</div></div>
          <div className="hero-stat"><div className="v grad-text">graph</div><div className="l">EXPANDING MEMORY</div></div>
          <div className="hero-stat"><div className="v grad-text">local</div><div className="l">FIRST BY DEFAULT</div></div>
        </div>
      </div>
    </header>
  )
}

// ---------- features ----------
const FEATURES = [
  { icon: 'search', t: 'Hybrid retrieval', d: 'Cache, local semantic memory, and a fresh web crawl — confidence-routed so each query takes the fastest accurate path.' },
  { icon: 'graph', t: 'Knowledge graph', d: 'Every search embeds its chunks and links them by similarity, so OLLA’s memory and the relations between data keep expanding.' },
  { icon: 'bolt', t: 'Synthesized answers', d: 'A local LLM reads the ranked sources and writes a direct answer with inline [n] citations you can verify.' },
  { icon: 'activity', t: 'Traced pipeline', d: 'Search, fetch, clean, rank, answer, store, embed, graph — every stage reports status and timing for full observability.' },
  { icon: 'message', t: 'Feedback that learns', d: 'Rate an answer or a specific source; the signal feeds source-trust and ranking so results improve over time.' },
  { icon: 'shield', t: 'Local-first', d: 'Runs against your own API and a local model by default. Your queries and data stay on your machine.' },
]
function Features() {
  return (
    <section className="section" id="features">
      <div className="wrap">
        <div className="reveal">
          <span className="eyebrow">Capabilities</span>
          <h2 className="section-title">Everything the CLI does, <span className="grad-text">in the browser</span>.</h2>
          <p className="section-sub">The same engine behind the OLLA terminal — now with a console you can click through.</p>
        </div>
        <div className="feat-grid">
          {FEATURES.map((f, i) => (
            <div className="feat reveal" key={f.t} style={{ animationDelay: `${i * 70}ms` }}>
              <div className="fi"><Icon name={f.icon} /></div>
              <h4>{f.t}</h4>
              <p>{f.d}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ---------- search panel ----------
function SearchPanel({ onResults }: { onResults: (q: string | null, r: Result[]) => void }) {
  const [query, setQuery] = useState('')
  const [maxResults, setMaxResults] = useState('5')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [data, setData] = useState<SearchResp | null>(null)

  async function run() {
    if (!query.trim() || busy) return
    setBusy(true); setErr(''); setData(null)
    try {
      const d = await api('/api/v1/search', {
        method: 'POST',
        body: JSON.stringify({ query: query.trim(), max_results: Number(maxResults) || 5 }),
      }) as unknown as SearchResp
      setData(d)
      onResults(d.query_id ?? null, d.results || [])
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Search failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel" id="search">
      <div className="panel-intro">
        <div className="pi-icon"><Icon name="search" /></div>
        <div>
          <h3>Search</h3>
          <p>Crawl the web, rank and clean the results, and get a cited answer.</p>
        </div>
      </div>
      <div className="cmdbar">
        <span className="prompt">OLLA ❯</span>
        <input
          placeholder="Ask anything — e.g. how does pgvector work"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run() }}
        />
        <button className="btn btn-primary" onClick={run} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="arrow" />}
          {busy ? 'Searching' : 'Run'}
        </button>
      </div>
      <div className="field-row">
        <div className="field">
          <label>Max sources</label>
          <select value={maxResults} onChange={(e) => setMaxResults(e.target.value)}>
            {['3', '5', '8', '10'].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </div>

      {busy && <Skeleton />}
      {err && <ErrorNote msg={err} />}

      {data && (
        <>
          <div className="metaline">
            <span className="m"><b>{data.total_results}</b> <i>sources</i></span>
            <span className="m"><b>{data.processing_time_ms}</b> <i>ms</i></span>
            {data.cache_hit && <span className="tag cy">cached</span>}
            {data.degraded && <span className="tag am">degraded</span>}
          </div>
          {data.answer
            ? (
              <div className="answer">
                <div className="answer-head">
                  <Icon name="bolt" /> OLLA ANSWER
                  {data.answer_model && <span className="model">{data.answer_model}</span>}
                </div>
                <div className="answer-body"><Answer text={data.answer} /></div>
              </div>
            )
            : (
              <div className="notice info">
                <Icon name="info" />
                <div>The API returned no synthesized answer. The local LLM (Ollama) may not be running — start it, then check the Health tab. Retrieved sources are shown below.</div>
              </div>
            )}
          {(data.results || []).length > 0 && <Sources results={(data.results || [])} />}
          {(data.trace || []).length > 0 && (
            <>
              <div className="sub-h">Pipeline trace</div>
              <Pipeline trace={(data.trace || [])} />
            </>
          )}
          {data.query_id && (
            <div className="notice info" style={{ marginTop: 16 }}>
              <Icon name="message" />
              <div>Rate this answer or one of its sources in the <b>Feedback</b> tab.</div>
            </div>
          )}
        </>
      )}
      {!busy && !data && !err && (
        <div className="empty"><Icon name="search" /><div>Run a query to see the answer, sources and pipeline trace.</div></div>
      )}
    </div>
  )
}

// ---------- hybrid panel ----------
const MODES = ['auto', 'fast', 'fresh', 'hybrid', 'deep']
function HybridPanel({ onResults }: { onResults: (q: string | null, r: Result[]) => void }) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('auto')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [data, setData] = useState<HybridResp | null>(null)

  async function run() {
    if (!query.trim() || busy) return
    setBusy(true); setErr(''); setData(null)
    try {
      const d = await api('/api/v1/search/hybrid', {
        method: 'POST',
        body: JSON.stringify({ query: query.trim(), mode, max_results: 6 }),
      }) as unknown as HybridResp
      setData(d)
      onResults(null, d.results || [])
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Hybrid retrieval failed')
    } finally {
      setBusy(false)
    }
  }

  const conf = data?.confidence ?? 0
  const confClass = conf >= 0.7 ? 'gr' : conf >= 0.4 ? 'am' : 'cy'

  return (
    <div className="panel">
      <div className="panel-intro">
        <div className="pi-icon"><Icon name="layers" /></div>
        <div>
          <h3>Hybrid retrieval</h3>
          <p>Confidence-routed: cache → local memory → web. OLLA picks the path.</p>
        </div>
      </div>
      <div className="cmdbar">
        <span className="prompt">OLLA ❯</span>
        <input
          placeholder="Ask anything — routing decides cache, memory or a fresh crawl"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run() }}
        />
        <button className="btn btn-primary" onClick={run} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="arrow" />}
          {busy ? 'Routing' : 'Run'}
        </button>
      </div>
      <div className="field-row">
        <div className="field">
          <label>Retrieval mode</label>
          <div className="seg">
            {MODES.map((m) => (
              <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{m}</button>
            ))}
          </div>
        </div>
      </div>

      {busy && <Skeleton />}
      {err && <ErrorNote msg={err} />}

      {data && (
        <>
          <div className="metaline">
            <span className="m"><i>mode</i> <b>{data.retrieval_mode}</b></span>
            <span className="m"><i>class</i> <b>{data.query_class}</b></span>
            <span className={`tag ${confClass}`}>confidence {conf.toFixed(2)}</span>
            <span className="m"><i>from</i> <b>{data.from_memory ? 'memory' : 'web'}</b></span>
            <span className="m"><b>{data.processing_time_ms}</b> <i>ms</i></span>
            {data.cache_hit && <span className="tag cy">cached</span>}
          </div>
          {data.answer
            ? (
              <div className="answer">
                <div className="answer-head">
                  <Icon name="bolt" /> OLLA ANSWER
                  {data.answer_model && <span className="model">{data.answer_model}</span>}
                </div>
                <div className="answer-body"><Answer text={data.answer} /></div>
              </div>
            )
            : <div className="notice info"><Icon name="info" /><div>No synthesized answer — the local LLM (Ollama) may not be running. Check the Health tab.</div></div>}
          {(data.results || []).length > 0 && <Sources results={(data.results || [])} />}
          {(data.routing_trace || []).length > 0 && (
            <>
              <div className="sub-h">Routing trace</div>
              {(data.routing_trace || []).map((s, i) => (
                <div className="gchunk" key={i} style={{ borderLeftColor: 'var(--indigo)' }}>
                  <div className="gtext" style={{ WebkitLineClamp: 4 }}>{s}</div>
                </div>
              ))}
            </>
          )}
        </>
      )}
      {!busy && !data && !err && (
        <div className="empty"><Icon name="layers" /><div>Run a query to watch the router pick cache, memory or web.</div></div>
      )}
    </div>
  )
}

// ---------- graph panel ----------
function GraphPanel() {
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [data, setData] = useState<GraphResp | null>(null)

  async function run() {
    if (!query.trim() || busy) return
    setBusy(true); setErr(''); setData(null)
    try {
      const d = await api('/api/v1/search/graph', {
        method: 'POST',
        body: JSON.stringify({ query: query.trim(), hops: 2, seed_k: 5, top_k: 20 }),
      }) as unknown as GraphResp
      setData(d)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Graph query failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <div className="panel-intro">
        <div className="pi-icon"><Icon name="graph" /></div>
        <div>
          <h3>Knowledge graph</h3>
          <p>Find seed chunks by similarity, then walk the edges to connected context.</p>
        </div>
      </div>
      <div className="cmdbar">
        <span className="prompt">OLLA ❯</span>
        <input
          placeholder="Explore the graph — e.g. vector similarity"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run() }}
        />
        <button className="btn btn-primary" onClick={run} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="arrow" />}
          {busy ? 'Traversing' : 'Run'}
        </button>
      </div>

      {busy && <Skeleton />}
      {err && <ErrorNote msg={err} />}

      {data && (
        <>
          <div className="metaline">
            <span className="m"><b>{data.total_chunks}</b> <i>chunks</i></span>
            <span className="m"><b>{data.hops}</b> <i>hops</i></span>
            <span className="m"><b>{(data.seed_chunks || []).length}</b> <i>seeds</i></span>
            <span className="m"><b>{(data.connected_chunks || []).length}</b> <i>connected</i></span>
          </div>
          {data.total_chunks === 0 && (
            <div className="notice info">
              <Icon name="info" />
              <div>No graph results yet. Run a few searches first — each one embeds chunks and grows the graph.</div>
            </div>
          )}
          {(data.seed_chunks || []).length > 0 && <div className="sub-h">Seed chunks</div>}
          {(data.seed_chunks || []).map((c) => (
            <div className="gchunk" key={c.id}>
              <div className="gh">
                <span className="gbadge">SEED</span>
                <span className="gtitle">{c.title || 'chunk'}</span>
                {c.similarity != null && <span className="gsim">sim {c.similarity.toFixed(3)}</span>}
              </div>
              <div className="gtext">{c.text}</div>
            </div>
          ))}
          {(data.connected_chunks || []).length > 0 && <div className="sub-h">Connected context</div>}
          {(data.connected_chunks || []).map((c) => (
            <div className="gchunk hop" key={c.id}>
              <div className="gh">
                <span className="gbadge">HOP {c.hop}</span>
                <span className="gtitle">{c.title || 'chunk'}</span>
                {c.edge_weight != null && <span className="gsim">edge {c.edge_weight.toFixed(3)}</span>}
              </div>
              <div className="gtext">{c.text}</div>
            </div>
          ))}
        </>
      )}
      {!busy && !data && !err && (
        <div className="empty"><Icon name="graph" /><div>Query the knowledge graph to surface connected context.</div></div>
      )}
    </div>
  )
}

// ---------- health panel ----------
function HealthPanel() {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [data, setData] = useState<HealthResp | null>(null)

  async function run() {
    setBusy(true); setErr('')
    try {
      const d = await api('/api/v1/health') as unknown as HealthResp
      setData(d)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Health check failed')
      setData(null)
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => { run() }, [])

  const dotClass = (s: string) => (s === 'ok' || s === 'healthy' ? 'ok' : s === 'slow' ? 'warn' : 'bad')

  return (
    <div className="panel">
      <div className="panel-intro">
        <div className="pi-icon"><Icon name="activity" /></div>
        <div>
          <h3>API health</h3>
          <p>Live status of OLLA and every backing component.</p>
        </div>
        <span className="nav-spacer" />
        <button className="btn btn-ghost btn-sm" onClick={run} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="refresh" />} Refresh
        </button>
      </div>

      {busy && !data && <Skeleton />}
      {err && <ErrorNote msg={err} />}

      {data && (
        <>
          <div className="metaline">
            <span className={`tag ${data.status === 'healthy' ? 'gr' : 'am'}`}>{data.status.toUpperCase()}</span>
            <span className="m"><i>service</i> <b>{data.service}</b></span>
            <span className="m"><i>version</i> <b>{data.version}</b></span>
          </div>
          <div className="stat-grid">
            {Object.entries(data.components).map(([name, c]) => (
              <div className="stat-card" key={name}>
                <div className="sc-h"><span className={`dot ${dotClass(c.status)}`} />{name}</div>
                <div className="sc-v">{c.status.toUpperCase()}</div>
                <div className="sc-l">
                  {c.latency_ms != null ? `${c.latency_ms} ms` : c.error || 'no latency reported'}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ---------- feedback panel ----------
const FB_TYPES = [
  { k: 'useful', d: 'it was helpful' },
  { k: 'not_useful', d: 'it was not helpful' },
  { k: 'incorrect', d: 'it was wrong' },
  { k: 'outdated', d: 'it was out of date' },
  { k: 'bad_source', d: 'a source was low quality' },
  { k: 'missing_context', d: 'context was missing' },
]
function FeedbackPanel({ last }: { last: LastState }) {
  const [target, setTarget] = useState('answer')
  const [srcUrl, setSrcUrl] = useState('')
  const [fbType, setFbType] = useState('')
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState<FeedbackResp | null>(null)

  async function submit() {
    setErr(''); setDone(null)
    if (!fbType) { setErr('Pick a rating first.'); return }
    if (target === 'answer' && !last.queryId) {
      setErr('No recent answer to rate — run a search first, then come back.')
      return
    }
    if (target === 'source' && !srcUrl) { setErr('Pick a source to rate.'); return }
    setBusy(true)
    try {
      const d = await api('/api/v1/feedback', {
        method: 'POST',
        body: JSON.stringify({
          level: target,
          feedback_type: fbType,
          query_id: last.queryId,
          source_url: target === 'source' ? srcUrl : null,
          comment: comment.trim() || null,
        }),
      }) as unknown as FeedbackResp
      setDone(d); setComment('')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not record feedback')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel" id="feedback">
      <div className="panel-intro">
        <div className="pi-icon"><Icon name="message" /></div>
        <div>
          <h3>Feedback</h3>
          <p>Rate the last answer or a source it used — the signal trains ranking.</p>
        </div>
      </div>

      <div className="sub-h">What are you rating?</div>
      <div className="choice-grid">
        <button className={`choice${target === 'answer' ? ' on' : ''}`} onClick={() => setTarget('answer')}>
          <div className="ch-t"><Icon name="bolt" /> The answer</div>
          <div className="ch-d">{last.queryId ? 'Rate the synthesized answer from your last search.' : 'Run a search first to enable this.'}</div>
        </button>
        <button className={`choice${target === 'source' ? ' on' : ''}`} onClick={() => setTarget('source')}>
          <div className="ch-t"><Icon name="link" /> A source / site</div>
          <div className="ch-d">{last.results.length ? `${last.results.length} sources available from your last search.` : 'Run a search first to list sources.'}</div>
        </button>
      </div>

      {target === 'source' && (
        <>
          <div className="sub-h">Pick a source</div>
          {last.results.length === 0
            ? <div className="notice info"><Icon name="info" /><div>No sources yet — run a search in the Search or Hybrid tab.</div></div>
            : last.results.map((r) => (
              <button
                key={r.url}
                className={`source${srcUrl === r.url ? '' : ''}`}
                style={{ width: '100%', textAlign: 'left', cursor: 'pointer', borderColor: srcUrl === r.url ? 'var(--violet)' : undefined, background: srcUrl === r.url ? 'rgba(192,132,252,0.07)' : undefined }}
                onClick={() => setSrcUrl(r.url)}
              >
                <span className="rank">{r.rank}</span>
                <div className="body">
                  <div className="title">{r.title || 'Untitled'}</div>
                  <span className="url">{r.url}</span>
                </div>
                {srcUrl === r.url && <span className="score" style={{ color: 'var(--violet)' }}>selected</span>}
              </button>
            ))}
        </>
      )}

      <div className="sub-h">Rating</div>
      <div className="rate-grid">
        {FB_TYPES.map((t, i) => (
          <button key={t.k} className={`rate${fbType === t.k ? ' on' : ''}`} onClick={() => setFbType(t.k)}>
            <span className="rate-num">{i + 1}</span>
            <span>
              <span className="rk">{t.k}</span><br />
              <span className="rd">{t.d}</span>
            </span>
          </button>
        ))}
      </div>

      <textarea
        className="cmt"
        placeholder="Optional comment…"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />

      <div style={{ marginTop: 14 }}>
        <button className="btn btn-primary" onClick={submit} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="check" />}
          {busy ? 'Sending' : 'Submit feedback'}
        </button>
      </div>

      {err && <ErrorNote msg={err} />}
      {done && (
        <div className="notice ok">
          <Icon name="check" />
          <div>
            Thanks — {done.level} feedback recorded as <code>{done.feedback_type}</code>.
            {done.effects.length > 0 && (
              <div className="effects">{done.effects.map((x, i) => <div key={i}>· {x}</div>)}</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------- analytics panel ----------
function AnalyticsPanel() {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [data, setData] = useState<StatsResp | null>(null)

  async function run() {
    setBusy(true); setErr('')
    try {
      const d = await api('/api/v1/feedback/stats') as unknown as StatsResp
      setData(d)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not load analytics')
      setData(null)
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => { run() }, [])

  const maxType = data ? Math.max(1, ...Object.values(data.by_type)) : 1

  return (
    <div className="panel">
      <div className="panel-intro">
        <div className="pi-icon"><Icon name="chart" /></div>
        <div>
          <h3>Feedback analytics</h3>
          <p>Aggregate satisfaction and source quality across all feedback.</p>
        </div>
        <span className="nav-spacer" />
        <button className="btn btn-ghost btn-sm" onClick={run} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="refresh" />} Refresh
        </button>
      </div>

      {busy && !data && <Skeleton />}
      {err && <ErrorNote msg={err} />}

      {data && (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="sc-h"><Icon name="message" /> Total events</div>
              <div className="sc-v grad-text">{data.total}</div>
              <div className="sc-l">feedback signals recorded</div>
            </div>
            <div className="stat-card">
              <div className="sc-h"><Icon name="check" /> Satisfaction</div>
              <div className="sc-v grad-text">{Math.round(data.satisfaction_rate * 100)}%</div>
              <div className="gauge" style={{ marginTop: 8 }}>
                <i style={{ width: `${Math.round(data.satisfaction_rate * 100)}%` }} />
              </div>
            </div>
          </div>

          {Object.keys(data.by_type).length > 0 && (
            <>
              <div className="sub-h">By type</div>
              <div className="bars">
                {Object.entries(data.by_type).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                  <div className="bar-row" key={k}>
                    <span className="bt">{k}</span>
                    <span className="bar-track"><i style={{ width: `${(v / maxType) * 100}%` }} /></span>
                    <span className="bn">{v}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {data.best_sources.length > 0 && (
            <>
              <div className="sub-h">Top-trust sources</div>
              {data.best_sources.slice(0, 5).map((s, i) => (
                <div className="source" key={i}>
                  <span className="rank" style={{ color: 'var(--green)' }}>{i + 1}</span>
                  <div className="body"><div className="title">{String(s.domain ?? 'unknown')}</div></div>
                  <span className="score">trust {Number(s.trust_score ?? 0).toFixed(2)}</span>
                </div>
              ))}
            </>
          )}
          {data.worst_sources.length > 0 && (
            <>
              <div className="sub-h">Low-trust sources</div>
              {data.worst_sources.slice(0, 5).map((s, i) => (
                <div className="source" key={i}>
                  <span className="rank" style={{ color: 'var(--amber)' }}>{i + 1}</span>
                  <div className="body"><div className="title">{String(s.domain ?? 'unknown')}</div></div>
                  <span className="score">trust {Number(s.trust_score ?? 0).toFixed(2)}</span>
                </div>
              ))}
            </>
          )}
          {data.total === 0 && (
            <div className="notice info"><Icon name="info" /><div>No feedback recorded yet — submit some in the Feedback tab.</div></div>
          )}
        </>
      )}
    </div>
  )
}

// ---------- keys panel ----------
function KeysPanel() {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [key, setKey] = useState<{ api_key: string; key_prefix: string } | null>(null)
  const [copied, setCopied] = useState(false)

  async function run() {
    if (!email.trim() || busy) return
    setBusy(true); setErr(''); setKey(null); setCopied(false)
    try {
      const d = await api('/api/v1/register', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), name: name.trim() || 'Default key' }),
      }) as unknown as { api_key: string; key_prefix: string }
      setKey({ api_key: d.api_key, key_prefix: d.key_prefix })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not create key')
    } finally {
      setBusy(false)
    }
  }
  function copy() {
    if (!key) return
    navigator.clipboard.writeText(key.api_key).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    }).catch(() => {})
  }

  return (
    <div className="panel">
      <div className="panel-intro">
        <div className="pi-icon"><Icon name="key" /></div>
        <div>
          <h3>API keys</h3>
          <p>Register an email to mint a free-tier OLLA API key.</p>
        </div>
      </div>
      <div className="field-row">
        <div className="field field-grow">
          <label>Email</label>
          <input
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') run() }}
          />
        </div>
        <div className="field field-grow">
          <label>Key label</label>
          <input
            placeholder="Default key"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') run() }}
          />
        </div>
      </div>
      <div style={{ marginTop: 14 }}>
        <button className="btn btn-primary" onClick={run} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="key" />}
          {busy ? 'Minting' : 'Create API key'}
        </button>
      </div>

      {err && <ErrorNote msg={err} />}
      {key && (
        <div className="keybox">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--cyan)', fontFamily: 'var(--mono)', fontSize: '0.85rem' }}>
            <Icon name="check" /> Key created — copy it now, it is shown only once.
          </div>
          <div className="keystr">
            <span>{key.api_key}</span>
            <button className="btn btn-ghost btn-sm" onClick={copy}>
              <Icon name={copied ? 'check' : 'copy'} /> {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <div style={{ color: 'var(--text-mute)', fontSize: '0.78rem', marginTop: 8, fontFamily: 'var(--mono)' }}>
            prefix {key.key_prefix} · send as the X-API-Key header
          </div>
        </div>
      )}
      {!key && !err && (
        <div className="notice info" style={{ marginTop: 16 }}>
          <Icon name="info" />
          <div>Keys authenticate requests to the OLLA API. The raw key is displayed once and stored only as a hash.</div>
        </div>
      )}
    </div>
  )
}

// ---------- console ----------
const TABS = [
  { id: 'search', label: 'search', icon: 'search' },
  { id: 'hybrid', label: 'hybrid', icon: 'layers' },
  { id: 'graph', label: 'graph', icon: 'graph' },
  { id: 'health', label: 'health', icon: 'activity' },
  { id: 'feedback', label: 'feedback', icon: 'message' },
  { id: 'analytics', label: 'analytics', icon: 'chart' },
  { id: 'keys', label: 'keys', icon: 'key' },
]
function Console() {
  const [tab, setTab] = useState('search')
  const [last, setLast] = useState<LastState>({ queryId: null, results: [] })
  const onResults = (queryId: string | null, results: Result[]) =>
    setLast((p) => ({ queryId: queryId ?? p.queryId, results }))

  return (
    <section className="section" id="console">
      <div className="wrap">
        <div className="console-head reveal">
          <span className="eyebrow">Live console</span>
          <h2 className="section-title">Drive <span className="grad-text">OLLA</span> from the browser</h2>
          <p className="section-sub">Every tab calls the real API — the same endpoints the CLI uses.</p>
        </div>
        <div className="console reveal">
          <div className="tabs">
            {TABS.map((t) => (
              <button
                key={t.id}
                className={`tab${tab === t.id ? ' active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                <Icon name={t.icon} /> {t.label}
              </button>
            ))}
          </div>
          {tab === 'search' && <SearchPanel onResults={onResults} />}
          {tab === 'hybrid' && <HybridPanel onResults={onResults} />}
          {tab === 'graph' && <GraphPanel />}
          {tab === 'health' && <HealthPanel />}
          {tab === 'feedback' && <FeedbackPanel last={last} />}
          {tab === 'analytics' && <AnalyticsPanel />}
          {tab === 'keys' && <KeysPanel />}
        </div>
      </div>
    </section>
  )
}

// ---------- footer ----------
function Footer() {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <div>
          <div className="brand"><span className="brand-mark" /> OLLA</div>
          <p style={{ marginTop: 8 }}>Hybrid Search. Smarter Answers.</p>
        </div>
        <div className="links">
          <a href="#features">Capabilities</a>
          <a href="#console">Console</a>
          <a href="#search">Search</a>
          <a href="#feedback">Feedback</a>
        </div>
        <p>© {new Date().getFullYear()} OLLA · local-first retrieval</p>
      </div>
    </footer>
  )
}

// ---------- app ----------
export default function App() {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    api('/api/v1/health')
      .then(() => setOnline(true))
      .catch(() => setOnline(false))
  }, [])

  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add('in')
          io.unobserve(e.target)
        }
      })
    }, { threshold: 0.12 })
    const els = document.querySelectorAll('.reveal')
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])

  return (
    <div className="shell">
      <Nav online={online} />
      <Hero />
      <Features />
      <Console />
      <Footer />
    </div>
  )
}
