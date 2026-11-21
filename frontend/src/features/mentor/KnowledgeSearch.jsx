import React, { useMemo, useState } from 'react';
import Timestamp from './Timestamp.jsx';
import { searchKnowledge } from './matchKnowledge.js';

// Read-only search over every mentor-approved answer.
export default function KnowledgeSearch({ knowledge }) {
  const { items, loaded, loading, error, refresh } = knowledge;
  const [query, setQuery] = useState('');
  const searching = query.trim().length > 0;
  const results = useMemo(() => searchKnowledge(query, items), [query, items]);

  return <section className="mentor-knowledge" aria-labelledby="mentor-knowledge-title">
    <div className="mentor-queue-heading">
      <div>
        <h2 id="mentor-knowledge-title">Approved answers</h2>
        <p className="mentor-help">
          {loaded ? `${items.length} mentor-approved ${items.length === 1 ? 'answer' : 'answers'} available for reuse. ` : ''}
          Search uses keyword matching, not AI.
        </p>
      </div>
      <button type="button" className="secondary" onClick={() => refresh()} disabled={loading}>
        {loading ? 'Refreshing…' : 'Refresh approved answers'}
      </button>
    </div>

    <label htmlFor="mentor-knowledge-search">Search approved answers</label>
    <input
      id="mentor-knowledge-search"
      type="search"
      value={query}
      maxLength={200}
      onChange={event => setQuery(event.target.value)}
      placeholder="e.g. backend setup"
    />
    {error && <p className="mentor-error" role="alert">
      Could not load approved answers. Reviewing still works; try Refresh approved answers again.
    </p>}

    {searching && <p className="mentor-help" role="status">
      {results.length
        ? `${results.length} matching ${results.length === 1 ? 'answer' : 'answers'}`
        : `No approved answers match “${query.trim()}”.`}
    </p>}
    {searching && results.length > 0 && <ul className="mentor-search-results">
      {results.map(item => <li key={item.id} className="mentor-match">
        <p className="mentor-match-question">#{item.id} · {item.question}</p>
        <p className="mentor-match-meta">
          Approved by {item.reviewer || 'unknown reviewer'} <Timestamp value={item.reviewed_at} prefix="on" />
        </p>
        <p className="mentor-text">{item.reviewed_answer}</p>
      </li>)}
    </ul>}
  </section>;
}
