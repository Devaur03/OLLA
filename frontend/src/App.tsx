import React, { useState, useEffect } from 'react';
import './App.css';

interface HealthComponent {
  status: string;
  latency_ms?: number;
  error?: string;
}

interface HealthResponse {
  status: string;
  version: string;
  components: Record<string, HealthComponent>;
}

interface SearchResult {
  rank: number;
  score: number;
  title: string;
  url: string;
  content: string;
  char_count: number;
  chunk_count: number;
}

interface SearchResponse {
  total_results: number;
  processing_time_ms: number;
  cache_hit: boolean;
  results: SearchResult[];
  citations_markdown: string;
}

interface SemanticChunk {
  title: string;
  url: string;
  text: string;
  similarity: number;
}

interface SemanticResponse {
  total_chunks: number;
  chunks: SemanticChunk[];
}

interface APIKeyItem {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string;
}

interface UsageResponse {
  plan: string;
  email: string;
  queries_used: number;
  queries_limit: number;
  period_start: string;
  period_end: string;
}

interface HistoryItem {
  query: string;
  mode: 'hybrid' | 'semantic';
  time: string;
  count: number;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'search' | 'keys' | 'billing'>('search');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [mgmtKey, setMgmtKey] = useState<string>(() => localStorage.getItem('mgmt-api-key') || '');
  
  // Search parameters
  const [query, setQuery] = useState<string>('');
  const [maxResults, setMaxResults] = useState<number>(5);
  const [minScore, setMinScore] = useState<number>(0.0);
  const [searchMode, setSearchMode] = useState<'hybrid' | 'semantic'>('hybrid');
  
  // Search state
  const [searching, setSearching] = useState<boolean>(false);
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [semanticResults, setSemanticResults] = useState<SemanticResponse | null>(null);
  const [searchStatus, setSearchStatus] = useState<{ text: string; isError?: boolean } | null>(null);
  
  // History state
  const [history, setHistory] = useState<HistoryItem[]>(() => {
    try {
      return JSON.parse(localStorage.getItem('search-history') || '[]');
    } catch {
      return [];
    }
  });

  // API Key management state
  const [regEmail, setRegEmail] = useState<string>('');
  const [regName, setRegName] = useState<string>('');
  const [regResult, setRegResult] = useState<{ api_key: string; plan: string } | null>(null);
  const [regError, setRegError] = useState<string | null>(null);
  const [registering, setRegistering] = useState<boolean>(false);
  const [keysList, setKeysList] = useState<APIKeyItem[]>([]);
  const [loadingKeys, setLoadingKeys] = useState<boolean>(false);
  
  // Billing usage state
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [loadingUsage, setLoadingUsage] = useState<boolean>(false);
  
  // Embedding backfill state
  const [backfilling, setBackfilling] = useState<boolean>(false);
  const [backfillResult, setBackfillResult] = useState<string | null>(null);

  // Check health on mount and every 30s
  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  // Save mgmtKey to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('mgmt-api-key', mgmtKey);
    if (mgmtKey) {
      loadKeys();
      loadUsage();
    } else {
      setKeysList([]);
      setUsage(null);
    }
  }, [mgmtKey]);

  // Save history to localStorage
  useEffect(() => {
    localStorage.setItem('search-history', JSON.stringify(history));
  }, [history]);

  const fetchHealth = async () => {
    try {
      const response = await fetch('/api/v1/health');
      if (response.ok) {
        const data = await response.json();
        setHealth(data);
      } else {
        setHealth(null);
      }
    } catch {
      setHealth(null);
    }
  };

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setSearching(true);
    setSearchStatus({ text: 'Searching retrievable sources...' });
    setSearchResults(null);
    setSemanticResults(null);

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (mgmtKey) {
      headers['X-API-Key'] = mgmtKey;
    }

    try {
      if (searchMode === 'hybrid') {
        const response = await fetch('/api/v1/search', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            query: query.trim(),
            max_results: maxResults,
            min_score: minScore,
          }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({ detail: response.statusText }));
          throw new Error(errData.detail || response.statusText);
        }

        const data: SearchResponse = await response.json();
        setSearchResults(data);
        setSearchStatus({
          text: `Found ${data.total_results} results in ${data.processing_time_ms}ms${data.cache_hit ? ' (cache hit)' : ''}`,
        });

        // Add to history
        const newHistory: HistoryItem = {
          query: query.trim(),
          mode: 'hybrid',
          time: new Date().toLocaleTimeString(),
          count: data.total_results,
        };
        setHistory((prev) => [newHistory, ...prev.filter((h) => h.query !== query.trim())].slice(0, 20));
      } else {
        const response = await fetch('/api/v1/search/semantic', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            query: query.trim(),
            top_k: maxResults,
            min_similarity: minScore,
          }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({ detail: response.statusText }));
          throw new Error(errData.detail || response.statusText);
        }

        const data: SemanticResponse = await response.json();
        setSemanticResults(data);
        setSearchStatus({
          text: `Retrieved ${data.total_chunks} relevant vector chunks`,
        });

        // Add to history
        const newHistory: HistoryItem = {
          query: query.trim(),
          mode: 'semantic',
          time: new Date().toLocaleTimeString(),
          count: data.total_chunks,
        };
        setHistory((prev) => [newHistory, ...prev.filter((h) => h.query !== query.trim())].slice(0, 20));
      }
    } catch (err: any) {
      setSearchStatus({ text: err.message || 'Search request failed', isError: true });
    } finally {
      setSearching(false);
    }
  };

  const registerNewKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regEmail.trim()) return;

    setRegistering(true);
    setRegResult(null);
    setRegError(null);

    try {
      const response = await fetch('/api/v1/keys/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: regEmail.trim(),
          name: regName.trim() || 'Default Key',
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errData.detail || response.statusText);
      }

      const data = await response.json();
      setRegResult(data);
      setMgmtKey(data.api_key);
      setRegEmail('');
      setRegName('');
    } catch (err: any) {
      setRegError(err.message || 'Failed to register key');
    } finally {
      setRegistering(false);
    }
  };

  const loadKeys = async () => {
    if (!mgmtKey.trim()) return;
    setLoadingKeys(true);
    try {
      const response = await fetch('/api/v1/keys', {
        headers: { 'X-API-Key': mgmtKey },
      });
      if (response.ok) {
        const data = await response.json();
        setKeysList(data);
      } else {
        setKeysList([]);
      }
    } catch {
      setKeysList([]);
    } finally {
      setLoadingKeys(false);
    }
  };

  const loadUsage = async () => {
    if (!mgmtKey.trim()) return;
    setLoadingUsage(true);
    try {
      const response = await fetch('/api/v1/billing/usage', {
        headers: { 'X-API-Key': mgmtKey },
      });
      if (response.ok) {
        const data = await response.json();
        setUsage(data);
      } else {
        setUsage(null);
      }
    } catch {
      setUsage(null);
    } finally {
      setLoadingUsage(false);
    }
  };

  const handleCreateAdditionalKey = async () => {
    if (!mgmtKey) return;
    const name = prompt('Key Name:', 'New Key');
    if (!name) return;

    try {
      const response = await fetch('/api/v1/keys', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': mgmtKey,
        },
        body: JSON.stringify({ name }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errData.detail || response.statusText);
      }

      const data = await response.json();
      alert(`Key Created Successfully!\n\nKey: ${data.api_key}\n\nCopy now - it won't be shown again.`);
      loadKeys();
    } catch (err: any) {
      alert(`Failed: ${err.message}`);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!mgmtKey) return;
    if (!confirm('Revoke this API key? Systems utilizing this key will lose access immediately.')) return;

    try {
      const response = await fetch(`/api/v1/keys/${keyId}`, {
        method: 'DELETE',
        headers: { 'X-API-Key': mgmtKey },
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errData.detail || response.statusText);
      }

      loadKeys();
    } catch (err: any) {
      alert(`Failed to revoke key: ${err.message}`);
    }
  };

  const startCheckout = async (plan: string) => {
    if (!mgmtKey) {
      alert('Please enter or register an API key first.');
      return;
    }
    try {
      const response = await fetch('/api/v1/billing/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': mgmtKey,
        },
        body: JSON.stringify({ plan }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errData.detail || response.statusText);
      }

      const data = await response.json();
      window.location.href = data.checkout_url;
    } catch (err: any) {
      alert(`Checkout failed: ${err.message}`);
    }
  };

  const openPortal = async () => {
    if (!mgmtKey) return;
    try {
      const response = await fetch('/api/v1/billing/portal', {
        method: 'POST',
        headers: { 'X-API-Key': mgmtKey },
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errData.detail || response.statusText);
      }

      const data = await response.json();
      window.open(data.portal_url, '_blank');
    } catch (err: any) {
      alert(`Billing portal failed: ${err.message}`);
    }
  };

  const backfillEmbeddings = async () => {
    setBackfilling(true);
    setBackfillResult(null);
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (mgmtKey) headers['X-API-Key'] = mgmtKey;

      const response = await fetch('/api/v1/search/embed-and-store', {
        method: 'POST',
        headers,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errData.detail || response.statusText);
      }

      const data = await response.json();
      setBackfillResult(`Success! Processed ${data.processed} chunks.`);
    } catch (err: any) {
      setBackfillResult(`Backfill failed: ${err.message}`);
    } finally {
      setBackfilling(false);
    }
  };

  // Helper to generate curl command string
  const getCurlCmd = (queryText: string) => {
    const isHybrid = searchMode === 'hybrid';
    const url = `${window.location.origin}/api/v1/search${isHybrid ? '' : '/semantic'}`;
    const keyHeader = mgmtKey ? ` -H "X-API-Key: ${mgmtKey}"` : '';
    const bodyObj = isHybrid
      ? { query: queryText, max_results: maxResults, min_score: minScore }
      : { query: queryText, top_k: maxResults, min_similarity: minScore };
    return `curl -X POST "${url}" -H "Content-Type: application/json"${keyHeader} -d '${JSON.stringify(bodyObj)}'`;
  };

  return (
    <div className="min-h-screen bg-surface-container-lowest text-on-surface font-sans flex flex-col antialiased">
      {/* Top Header */}
      <header className="bg-surface border-b border-border-subtle px-6 py-4 flex items-center justify-between shadow-lg">
        <div className="flex items-center gap-3">
          <span className="text-2xl">⚡</span>
          <div>
            <h1 className="font-display-lg font-bold text-lg tracking-tight text-on-surface">
              HYBRID RETRIEVAL CONSOLE
            </h1>
            <p className="text-xs text-text-muted font-mono tracking-wider">DUCCDUCKGO + SEMANTIC EMBEDDINGS</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {health ? (
            <div className="flex items-center gap-2 px-3 py-1 bg-primary/10 border border-primary/20 rounded-full text-xs font-semibold text-primary">
              <span className="w-2 h-2 rounded-full bg-primary pulse-glow-dot inline-block"></span>
              API: ONLINE
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1 bg-error/10 border border-error/20 rounded-full text-xs font-semibold text-error">
              <span className="w-2 h-2 rounded-full bg-error inline-block"></span>
              API: OFFLINE
            </div>
          )}
          <button
            onClick={fetchHealth}
            className="px-3 py-1.5 bg-surface-container border border-border-subtle rounded-lg text-xs font-medium hover:bg-surface-bright transition-colors"
          >
            ↻ Refresh Status
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-surface border-b border-border-subtle flex px-6">
        <button
          onClick={() => setActiveTab('search')}
          className={`px-5 py-3.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'search'
              ? 'border-primary text-primary'
              : 'border-transparent text-text-muted hover:text-on-surface'
          }`}
        >
          🔍 Search playground
        </button>
        <button
          onClick={() => setActiveTab('keys')}
          className={`px-5 py-3.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'keys'
              ? 'border-primary text-primary'
              : 'border-transparent text-text-muted hover:text-on-surface'
          }`}
        >
          🔑 API Key registry
        </button>
        <button
          onClick={() => setActiveTab('billing')}
          className={`px-5 py-3.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'billing'
              ? 'border-primary text-primary'
              : 'border-transparent text-text-muted hover:text-on-surface'
          }`}
        >
          💳 Billing & limits
        </button>
      </div>

      {/* Main Grid Workspace */}
      <main className="flex-grow p-6">
        {activeTab === 'search' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Search Input / Controls & Results */}
            <div className="lg:col-span-2 space-y-6">
              <div className="bg-surface border border-border-subtle rounded-xl p-5 shadow-sm">
                <form onSubmit={handleSearch} className="space-y-4">
                  {/* Mode Select */}
                  <div className="flex gap-2 p-1 bg-surface-container-low rounded-lg w-fit">
                    <button
                      type="button"
                      onClick={() => setSearchMode('hybrid')}
                      className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${
                        searchMode === 'hybrid'
                          ? 'bg-primary text-on-primary shadow-sm'
                          : 'text-text-muted hover:text-on-surface'
                      }`}
                    >
                      Hybrid Search
                    </button>
                    <button
                      type="button"
                      onClick={() => setSearchMode('semantic')}
                      className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-all ${
                        searchMode === 'semantic'
                          ? 'bg-primary text-on-primary shadow-sm'
                          : 'text-text-muted hover:text-on-surface'
                      }`}
                    >
                      Semantic Cache
                    </button>
                  </div>

                  {/* Input field */}
                  <div className="flex gap-3">
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Ask anything... (e.g. how does pgvector work)"
                      className="flex-grow bg-surface-container-lowest border border-border-subtle focus:border-primary focus:ring-1 focus:ring-primary rounded-lg px-4 py-2.5 text-sm text-on-surface placeholder-text-muted outline-none transition-colors"
                    />
                    <button
                      type="submit"
                      disabled={searching}
                      className="px-6 py-2.5 bg-primary text-on-primary font-semibold text-sm rounded-lg hover:opacity-90 disabled:opacity-50 transition-opacity whitespace-nowrap shadow-sm"
                    >
                      {searching ? 'Running...' : 'Execute'}
                    </button>
                  </div>

                  {/* Search tuning controls */}
                  <div className="flex flex-wrap gap-6 pt-2">
                    <div className="flex items-center gap-3">
                      <label className="text-xs text-text-muted font-medium">Max Results:</label>
                      <input
                        type="range"
                        min="1"
                        max="15"
                        value={maxResults}
                        onChange={(e) => setMaxResults(parseInt(e.target.value))}
                        className="accent-primary w-24 h-1 bg-surface-container rounded-lg appearance-none cursor-pointer"
                      />
                      <span className="text-xs font-semibold font-mono text-primary bg-primary/10 px-2 py-0.5 rounded">
                        {maxResults}
                      </span>
                    </div>

                    <div className="flex items-center gap-3">
                      <label className="text-xs text-text-muted font-medium">
                        {searchMode === 'hybrid' ? 'Min Score:' : 'Min Similarity:'}
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={minScore}
                        onChange={(e) => setMinScore(parseFloat(e.target.value))}
                        className="accent-primary w-24 h-1 bg-surface-container rounded-lg appearance-none cursor-pointer"
                      />
                      <span className="text-xs font-semibold font-mono text-primary bg-primary/10 px-2 py-0.5 rounded">
                        {minScore.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </form>
              </div>

              {/* Status Output */}
              {searchStatus && (
                <div
                  className={`px-4 py-3 rounded-lg border text-xs font-mono flex items-center justify-between ${
                    searchStatus.isError
                      ? 'bg-error/10 border-error/30 text-error'
                      : 'bg-surface border-border-subtle text-primary'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {searching && <span className="w-1.5 h-1.5 rounded-full bg-primary pulse-glow-dot"></span>}
                    <span>{searchStatus.text}</span>
                  </div>
                  {query && (
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(getCurlCmd(query));
                        alert('cURL command copied!');
                      }}
                      className="text-[10px] text-text-muted hover:text-primary underline cursor-pointer"
                    >
                      Copy cURL
                    </button>
                  )}
                </div>
              )}

              {/* Results Lists */}
              <div className="space-y-4">
                {searchResults && searchResults.results && searchResults.results.length > 0 ? (
                  searchResults.results.map((res) => (
                    <div
                      key={res.rank}
                      className="bg-surface border border-border-subtle rounded-xl p-5 hover:border-primary/40 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-4 mb-2">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 bg-primary/10 border border-primary/20 text-primary text-[10px] font-mono rounded font-bold">
                            #{res.rank}
                          </span>
                          <span className="px-2 py-0.5 bg-surface-container border border-border-subtle text-text-muted text-[10px] font-mono rounded">
                            Score: {res.score.toFixed(3)}
                          </span>
                          <h3 className="font-semibold text-sm text-on-surface line-clamp-1">{res.title}</h3>
                        </div>
                        <a
                          href={res.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-primary hover:underline font-mono truncate max-w-[200px]"
                        >
                          Visit Link ↗
                        </a>
                      </div>
                      <p className="text-xs text-text-muted leading-relaxed line-clamp-3 mb-4">{res.content}</p>
                      <div className="flex gap-2">
                        <span className="text-[10px] text-text-muted bg-surface-container px-2.5 py-1 rounded">
                          {res.char_count.toLocaleString()} Chars
                        </span>
                        <span className="text-[10px] text-text-muted bg-surface-container px-2.5 py-1 rounded">
                          {res.chunk_count} Chunks
                        </span>
                      </div>
                    </div>
                  ))
                ) : semanticResults && semanticResults.chunks && semanticResults.chunks.length > 0 ? (
                  semanticResults.chunks.map((chunk, idx) => (
                    <div
                      key={idx}
                      className="bg-surface border border-border-subtle rounded-xl p-5 hover:border-primary/40 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-4 mb-2">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 bg-primary/10 border border-primary/20 text-primary text-[10px] font-mono rounded font-bold">
                            #{idx + 1}
                          </span>
                          <span className="px-2 py-0.5 bg-surface-container border border-border-subtle text-text-muted text-[10px] font-mono rounded">
                            Similarity: {chunk.similarity.toFixed(3)}
                          </span>
                          <h3 className="font-semibold text-sm text-on-surface line-clamp-1">{chunk.title}</h3>
                        </div>
                        <a
                          href={chunk.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-primary hover:underline font-mono truncate max-w-[200px]"
                        >
                          Source Link ↗
                        </a>
                      </div>
                      <p className="text-xs text-text-muted leading-relaxed mb-2 font-mono whitespace-pre-wrap">
                        {chunk.text}
                      </p>
                    </div>
                  ))
                ) : (
                  !searching && (
                    <div className="text-center py-12 bg-surface/50 border border-dashed border-border-subtle rounded-xl text-text-muted text-sm">
                      🔍 Run a search query to explore retrieval results.
                    </div>
                  )
                )}

                {/* Citations Pane */}
                {searchResults && searchResults.citations_markdown && (
                  <div className="bg-surface border border-border-subtle rounded-xl p-5">
                    <div className="flex items-center justify-between mb-3 border-b border-border-subtle pb-2">
                      <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Citations Markdown</h4>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(searchResults.citations_markdown);
                          alert('Citations copied!');
                        }}
                        className="text-xs text-primary hover:underline font-semibold"
                      >
                        Copy Markdown
                      </button>
                    </div>
                    <pre className="text-xs font-mono bg-surface-container-lowest border border-border-subtle rounded-lg p-3 overflow-x-auto text-text-muted whitespace-pre-wrap max-h-48">
                      {searchResults.citations_markdown}
                    </pre>
                  </div>
                )}
              </div>
            </div>

            {/* Sidebar widgets */}
            <div className="space-y-6">
              {/* System Health Detailed Component */}
              <div className="bg-surface border border-border-subtle rounded-xl p-5 shadow-sm">
                <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">System components</h3>
                <div className="divide-y divide-border-subtle">
                  {health && health.components ? (
                    Object.entries(health.components).map(([name, cmp]) => (
                      <div key={name} className="py-2.5 flex items-center justify-between text-xs">
                        <span className="font-semibold text-on-surface">{name}</span>
                        <div className="flex items-center gap-3">
                          {cmp.latency_ms != null && (
                            <span className="text-[10px] font-mono text-text-muted">{cmp.latency_ms}ms</span>
                          )}
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              cmp.status === 'ok'
                                ? 'bg-primary/10 text-primary border border-primary/20'
                                : cmp.status === 'slow'
                                ? 'bg-warn/10 text-warn border border-warn/20'
                                : 'bg-error/10 text-error border border-error/20'
                            }`}
                          >
                            {cmp.status.toUpperCase()}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="py-2 text-text-muted text-xs font-mono">No component status loaded.</div>
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-border-subtle space-y-2">
                  <button
                    onClick={backfillEmbeddings}
                    disabled={backfilling}
                    className="w-full py-2 bg-surface-container hover:bg-surface-bright border border-border-subtle text-xs font-semibold rounded-lg transition-colors text-on-surface"
                  >
                    {backfilling ? 'Backfilling...' : '⚡ Backfill DB Embeddings'}
                  </button>
                  {backfillResult && (
                    <p className="text-[10px] text-center font-mono text-primary mt-1">{backfillResult}</p>
                  )}
                </div>
              </div>

              {/* History list */}
              <div className="bg-surface border border-border-subtle rounded-xl p-5 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Search history</h3>
                  {history.length > 0 && (
                    <button
                      onClick={() => setHistory([])}
                      className="text-[10px] text-error hover:underline cursor-pointer"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {history.length > 0 ? (
                    history.map((h, idx) => (
                      <div
                        key={idx}
                        onClick={() => {
                          setQuery(h.query);
                          setSearchMode(h.mode);
                          handleSearch();
                        }}
                        className="p-2.5 bg-surface-container border border-border-subtle rounded-lg hover:border-primary/30 transition-colors cursor-pointer text-xs flex justify-between items-center gap-4"
                      >
                        <span className="font-semibold text-on-surface truncate flex-grow" title={h.query}>
                          {h.query}
                        </span>
                        <div className="text-right flex-shrink-0">
                          <div className="text-[9px] text-text-muted">{h.time}</div>
                          <div className="text-[9px] text-primary">{h.count} results</div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-6 text-xs text-text-muted">No search queries logged yet.</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'keys' && (
          <div className="max-w-4xl mx-auto space-y-6">
            {/* Create API Key Pane */}
            <div className="bg-surface border border-border-subtle rounded-xl p-5 shadow-sm">
              <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Request an API Key</h3>
              <p className="text-xs text-text-muted mb-4">
                Register with your email to obtain your free development API key instantly.
              </p>

              <form onSubmit={registerNewKey} className="flex flex-wrap gap-3 items-end">
                <div className="flex-grow min-w-[200px]">
                  <label className="text-[10px] text-text-muted block mb-1">Email Address</label>
                  <input
                    type="email"
                    required
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full bg-surface-container-lowest border border-border-subtle focus:border-primary rounded-lg px-3.5 py-2 text-xs text-on-surface outline-none"
                  />
                </div>
                <div className="flex-grow min-w-[200px]">
                  <label className="text-[10px] text-text-muted block mb-1">Key Name (Optional)</label>
                  <input
                    type="text"
                    value={regName}
                    onChange={(e) => setRegName(e.target.value)}
                    placeholder="e.g. agent-retrieval"
                    className="w-full bg-surface-container-lowest border border-border-subtle focus:border-primary rounded-lg px-3.5 py-2 text-xs text-on-surface outline-none"
                  />
                </div>
                <button
                  type="submit"
                  disabled={registering}
                  className="px-5 py-2 bg-primary text-on-primary font-semibold text-xs rounded-lg hover:opacity-90 disabled:opacity-50 transition-opacity"
                >
                  {registering ? 'Generating...' : 'Get Free Key'}
                </button>
              </form>

              {regError && <div className="mt-3 text-xs text-error font-mono">{regError}</div>}

              {regResult && (
                <div className="mt-4 bg-primary/10 border border-primary/20 rounded-xl p-4 text-xs font-mono">
                  <div className="text-primary font-bold mb-1.5">✓ Key Registered Successfully!</div>
                  <div className="text-text-muted mb-3">Copy your key now. It won't be shown again:</div>
                  <div className="flex items-center justify-between bg-surface-container-lowest border border-border-subtle p-3 rounded-lg text-primary select-all break-all font-bold">
                    <span>{regResult.api_key}</span>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(regResult.api_key);
                        alert('Copied to clipboard!');
                      }}
                      className="ml-3 px-2 py-1 bg-surface-container text-xs text-on-surface rounded hover:bg-surface-bright transition-colors"
                    >
                      Copy
                    </button>
                  </div>
                  <p className="text-[10px] text-text-muted mt-2">
                    This key has been automatically configured as your active management key.
                  </p>
                </div>
              )}
            </div>

            {/* Key list table */}
            <div className="bg-surface border border-border-subtle rounded-xl p-5 shadow-sm">
              <div className="flex items-center justify-between mb-4 border-b border-border-subtle pb-3">
                <div>
                  <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Active Keys</h3>
                  <p className="text-xs text-text-muted mt-0.5">Manage credentials associated with your account.</p>
                </div>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={mgmtKey}
                    onChange={(e) => setMgmtKey(e.target.value)}
                    placeholder="Enter X-API-Key to view registry"
                    className="bg-surface-container-lowest border border-border-subtle focus:border-primary rounded-lg px-3 py-1.5 text-xs text-on-surface outline-none w-64"
                  />
                  <button
                    onClick={loadKeys}
                    disabled={loadingKeys}
                    className="px-3 py-1.5 bg-surface-container hover:bg-surface-bright border border-border-subtle text-xs font-semibold rounded-lg"
                  >
                    {loadingKeys ? 'Loading...' : 'Load Keys'}
                  </button>
                </div>
              </div>

              {keysList.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border-subtle text-text-muted uppercase tracking-wider text-[10px]">
                        <th className="py-2.5">Key Prefix</th>
                        <th className="py-2.5">Name</th>
                        <th className="py-2.5">Status</th>
                        <th className="py-2.5">Created</th>
                        <th className="py-2.5 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle">
                      {keysList.map((k) => (
                        <tr key={k.id}>
                          <td className="py-3 font-mono font-bold text-primary">{k.key_prefix}...</td>
                          <td className="py-3">{k.name}</td>
                          <td className="py-3">
                            <span
                              className={`px-2 py-0.5 text-[9px] rounded font-bold ${
                                k.is_active
                                  ? 'bg-primary/10 text-primary border border-primary/20'
                                  : 'bg-error/10 text-error border border-error/20'
                              }`}
                            >
                              {k.is_active ? 'Active' : 'Revoked'}
                            </span>
                          </td>
                          <td className="py-3 text-text-muted">{new Date(k.created_at).toLocaleDateString()}</td>
                          <td className="py-3 text-right">
                            {k.is_active ? (
                              <button
                                onClick={() => handleRevokeKey(k.id)}
                                className="px-2.5 py-1 bg-error/10 text-error hover:bg-error/20 border border-error/30 text-[10px] font-semibold rounded"
                              >
                                Revoke
                              </button>
                            ) : (
                              <span className="text-text-muted">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-text-muted">
                  🔒 Enter and load your active management API key in the top right to retrieve registered keys.
                </div>
              )}

              {mgmtKey && (
                <div className="mt-4 pt-3 border-t border-border-subtle">
                  <button
                    onClick={handleCreateAdditionalKey}
                    className="px-4 py-2 bg-surface-container hover:bg-surface-bright border border-border-subtle text-xs font-semibold rounded-lg text-on-surface"
                  >
                    + Create Additional API Key
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'billing' && (
          <div className="max-w-4xl mx-auto space-y-6">
            {/* Current Plan Summary */}
            <div className="bg-surface border border-border-subtle rounded-xl p-5 shadow-sm">
              <div className="flex items-center justify-between mb-4 border-b border-border-subtle pb-3">
                <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Current Account Plan</h3>
                {mgmtKey ? (
                  <button
                    onClick={loadUsage}
                    disabled={loadingUsage}
                    className="text-xs text-primary hover:underline cursor-pointer"
                  >
                    {loadingUsage ? 'Reloading...' : 'Refresh Usage'}
                  </button>
                ) : (
                  <span className="text-xs text-text-muted">Enter key to see billing</span>
                )}
              </div>

              {usage ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <span className="px-3 py-1 bg-primary/10 border border-primary/20 text-primary font-bold text-xs rounded-full uppercase tracking-wider">
                      {usage.plan}
                    </span>
                    <span className="text-sm text-text-muted font-mono">{usage.email}</span>
                    {usage.plan !== 'free' && (
                      <button
                        onClick={openPortal}
                        className="px-3 py-1 bg-surface-container hover:bg-surface-bright border border-border-subtle text-xs font-semibold rounded-lg ml-auto"
                      >
                        Manage Stripe Billing ↗
                      </button>
                    )}
                  </div>

                  {/* Usage Meter */}
                  <div className="space-y-2 pt-2">
                    <div className="flex justify-between text-xs text-text-muted">
                      <span>Monthly Retriaval Queries</span>
                      <span className="font-semibold text-on-surface">
                        {usage.queries_used.toLocaleString()} /{' '}
                        {usage.queries_limit ? usage.queries_limit.toLocaleString() : '∞'}
                      </span>
                    </div>
                    <div className="w-full bg-surface-container-lowest border border-border-subtle h-3 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all duration-500 ease-out"
                        style={{
                          width: `${
                            usage.queries_limit ? Math.min(100, (usage.queries_used / usage.queries_limit) * 100) : 0
                          }%`,
                        }}
                      ></div>
                    </div>
                    <p className="text-[10px] text-text-muted text-right">
                      Billing Cycle: {new Date(usage.period_start).toLocaleDateString()} -{' '}
                      {new Date(usage.period_end).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="text-center py-6 text-xs text-text-muted">
                  🔒 Enter or load an API key in the API Key Registry tab to view plan and query limits.
                </div>
              )}
            </div>

            {/* Upgrade Pricing Matrix */}
            <div className="space-y-4">
              <div>
                <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1">Upgrade Plans</h3>
                <p className="text-xs text-text-muted">Scale your retrievals. Connect the API directly to your agents.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  { plan: 'free', label: 'Free', price: '$0', limit: '1,000 queries/mo' },
                  { plan: 'starter', label: 'Starter', price: '$29', limit: '10,000 queries/mo' },
                  { plan: 'pro', label: 'Pro', price: '$99', limit: '50,000 queries/mo' },
                  { plan: 'team', label: 'Team', price: '$299', limit: '200,000 queries/mo' },
                ].map((p) => {
                  const isCurrent = usage?.plan === p.plan;
                  return (
                    <div
                      key={p.plan}
                      className={`bg-surface border rounded-xl p-5 flex flex-col justify-between transition-colors ${
                        isCurrent ? 'border-primary shadow-sm shadow-primary/15' : 'border-border-subtle'
                      }`}
                    >
                      <div>
                        <div className="flex justify-between items-center mb-1">
                          <h4 className="font-semibold text-sm text-on-surface">{p.label}</h4>
                          {isCurrent && (
                            <span className="text-[9px] bg-primary/10 text-primary border border-primary/20 font-bold px-2 py-0.5 rounded">
                              Current
                            </span>
                          )}
                        </div>
                        <div className="text-xl font-bold text-primary mb-1">
                          {p.price}
                          {p.price !== '$0' && <span className="text-xs text-text-muted font-normal">/mo</span>}
                        </div>
                        <p className="text-xs text-text-muted font-mono mb-4">{p.limit}</p>
                      </div>

                      {p.plan !== 'free' && !isCurrent && (
                        <button
                          onClick={() => startCheckout(p.plan)}
                          className="w-full py-2 bg-primary text-on-primary font-bold text-xs rounded-lg hover:opacity-90 transition-opacity"
                        >
                          Upgrade →
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
