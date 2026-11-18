import React, { useEffect, useState } from 'react';
import { api } from './api.js';
import NewcomerView from './features/newcomer/NewcomerView.jsx';

// Owner D can extract this shell into features/mentor/ in their own PR.
function MentorView() {
  const [items, setItems] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [reviewer, setReviewer] = useState('Mentor');
  const [error, setError] = useState('');
  const refresh = async () => {
    try { setItems(await api.questions('pending')); setError(''); }
    catch (err) { setError(err.message); }
  };
  useEffect(() => { refresh(); }, []);
  const approve = async (id) => {
    try { await api.review(id, drafts[id] || '', reviewer); await refresh(); }
    catch (err) { setError(err.message); }
  };
  return <section>
    <h2>Mentor — Review queue</h2>
    <label htmlFor="reviewer">Reviewer (demo display name)</label>
    <input id="reviewer" value={reviewer} maxLength={100} onChange={e => setReviewer(e.target.value)} />
    <button className="secondary" onClick={refresh}>Refresh queue</button>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="stack">{items.map(item => <article key={item.id}>
      <div className="meta">Pending · Question #{item.id}</div>
      <h3>{item.question}</h3><p>{item.ai_answer}</p>
      <label htmlFor={`review-${item.id}`}>Mentor verified answer</label>
      <textarea id={`review-${item.id}`} value={drafts[item.id] || ''} onChange={e => setDrafts(s => ({ ...s, [item.id]: e.target.value }))} placeholder="Write a verified answer based on project material" />
      <button disabled={!reviewer.trim() || !drafts[item.id]?.trim()} onClick={() => approve(item.id)}>Approve answer</button>
    </article>)}</div>
    {!items.length && !error && <p>No pending questions. Ask from the Newcomer tab first.</p>}
  </section>;
}

export default function App() {
  const [role, setRole] = useState('newcomer');
  return <main>
    <header><h1>CP2 Onboarding Assistant</h1><p>Team scaffold · shared API · two-person workflow</p></header>
    <nav aria-label="Choose demo view">
      <button className={role === 'newcomer' ? '' : 'secondary'} onClick={() => setRole('newcomer')}>Newcomer</button>
      <button className={role === 'mentor' ? '' : 'secondary'} onClick={() => setRole('mentor')}>Mentor</button>
    </nav>
    <div className="notice">Scaffold only: AI responses are explicitly labeled placeholders. No authentication, retrieval or citations yet. Do not use real confidential documents.</div>
    {role === 'newcomer' ? <NewcomerView /> : <MentorView />}
  </main>;
}
