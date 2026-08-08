import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import './index.css';

function App() {
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
  const [query, setQuery] = useState('');
  const [docType, setDocType] = useState('all');
  const [fullTextOnly, setFullTextOnly] = useState(false);
  const [topK, setTopK] = useState(5);
  
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [llmResponse, setLlmResponse] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    
    setLoading(true);
    setResults(null);
    setLlmResponse('');
    setError(null);

    try {
      const response = await fetch("http://localhost:8000/api/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          query: query,
          top_k: topK,
          filters: {
            doc_type: docType,
            full_text_only: fullTextOnly
          }
        })
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`);
      }

      const data = await response.json();
      setResults(data.results);
      setLlmResponse(data.llm_response);
    } catch (err) {
      console.error(err);
      setError("Failed to fetch results. Ensure the backend API is running.");
    } finally {
      setLoading(false);
    }
  };

  const getSourceUrl = (result) => {
    if (result.pmid) return `https://pubmed.ncbi.nlm.nih.gov/${result.pmid}`;
    if (result.nctId) return `https://clinicaltrials.gov/study/${result.nctId}`;
    if (result.doi) return `https://doi.org/${result.doi}`;
    return "#";
  };

  return (
    <>
      <header className="header">
        <div className="logo-container">
          <img src="/logo.jpg" alt="St. Bonaventure Logo" className="logo" />
          <div>
            <h1>ST. BONAVENTURE HOSPITAL</h1>
            <p className="subtitle">Surgery Department • Literature AI Workstation</p>
          </div>
          <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle Dark Mode">
            <span>{theme === 'dark' ? '☀️' : '🌙'}</span>
          </button>
        </div>
      </header>

      <main className="layout">
        <aside className="sidebar">
          <div className="filter-group">
            <h3>Document Type</h3>
            <label className="filter-option">
              <input 
                type="radio" 
                name="docType" 
                value="all" 
                checked={docType === 'all'}
                onChange={() => setDocType('all')} 
              />
              All Documents
            </label>
            <label className="filter-option">
              <input 
                type="radio" 
                name="docType" 
                value="pubmed_article" 
                checked={docType === 'pubmed_article'}
                onChange={() => setDocType('pubmed_article')} 
              />
              PubMed Articles
            </label>
            <label className="filter-option">
              <input 
                type="radio" 
                name="docType" 
                value="clinical_trial" 
                checked={docType === 'clinical_trial'}
                onChange={() => setDocType('clinical_trial')} 
              />
              Clinical Trials
            </label>
          </div>

          <div className="filter-group">
            <h3>Availability</h3>
            <label className="filter-option">
              <input 
                type="checkbox" 
                checked={fullTextOnly}
                onChange={(e) => setFullTextOnly(e.target.checked)} 
              />
              Full Text Only
            </label>
          </div>

          <div className="filter-group">
            <h3>Number of Results ({topK})</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <input 
                type="range" 
                min="3" 
                max="20" 
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                style={{ accentColor: 'var(--primary-teal)', cursor: 'pointer' }}
              />
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Higher values provide more context but take longer to process.
              </span>
            </div>
          </div>
        </aside>

        <section className="main-content">
          <form className="search-container" onSubmit={handleSearch}>
            <div className="search-bar-wrapper">
              <input 
                type="text" 
                className="search-input" 
                placeholder="Ask a surgical question (e.g. robotic vs open appendectomy outcomes...)"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button type="submit" className="search-btn" disabled={loading || !query.trim()}>
                Search
              </button>
            </div>
          </form>

          {loading && (
            <div className="loader">
              <div className="spinner"></div>
              <p>Analyzing medical literature...</p>
            </div>
          )}

          {error && (
            <div className="llm-response" style={{borderColor: 'var(--warning-red)', borderTopColor: 'var(--warning-red)'}}>
              <p style={{color: 'var(--warning-red)'}}>{error}</p>
            </div>
          )}

          {!loading && llmResponse && (
            <div className="llm-response">
              <h3>AI Assistant Answer</h3>
              <ReactMarkdown>{llmResponse}</ReactMarkdown>
            </div>
          )}

          {!loading && results && results.length > 0 && (
            <div className="results-container">
              <div className="results-header">
                Found {results.length} relevant sources
              </div>
              
              {results.map((result, idx) => (
                <div className="result-card" key={idx}>
                  <a href={getSourceUrl(result)} target="_blank" rel="noreferrer" className="result-title">
                    [{idx + 1}] {result.title}
                  </a>
                  
                  <div className="result-meta">
                    {result.rerank_score !== undefined && (
                      <span className="badge score">
                        Relevance: {((1 / (1 + Math.exp(-result.rerank_score))) * 100).toFixed(0)}%
                      </span>
                    )}
                    <span className="badge type">
                      {result.doc_type === 'pubmed_article' ? 'Article' : 'Clinical Trial'}
                    </span>
                    {result.full_text === 'yes' && (
                      <span className="badge fulltext">Full Text Available</span>
                    )}
                    {result.pub_date && <span>Date: {result.pub_date}</span>}
                    {result.journal && <span>Journal: {result.journal}</span>}
                    {result.nctId && <span>NCT ID: {result.nctId}</span>}
                  </div>

                  <div className="result-snippet">
                    {result.text ? result.text.substring(0, 400) + '...' : 'No text snippet available.'}
                  </div>
                  
                  <div className="result-actions">
                    <a href={getSourceUrl(result)} target="_blank" rel="noreferrer">
                      View Original Source ↗
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </>
  );
}

export default App;
