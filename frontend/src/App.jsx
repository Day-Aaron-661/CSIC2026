import { useEffect, useState } from 'react';
import { api } from './api.js';

// These components are intentionally small, replaceable shells.
// Owner C: NewcomerView; Owner D: MentorView; Owner B: AI backend.
function NewcomerView() {
  const [question, setQuestion] = useState('');
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    try { setItems(await api.questions()); setError(''); }
    catch (err) { setError(err.message); }
  };
  useEffect(() => { refresh(); }, []);
  const submit = async (e) => {
    e.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    try { await api.ask(question.trim()); setQuestion(''); await refresh(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  return <section>
    <h2>Newcomer — Ask a question</h2>
    <form onSubmit={submit}>
      <label htmlFor="question">Project question</label>
      <textarea id="question" value={question} onChange={e => setQuestion(e.target.value)} maxLength={2000} placeholder="What should I read first?" />
      <button disabled={busy || !question.trim()}>{busy ? 'Submitting...' : 'Submit question'}</button>
    </form>
    <button className="secondary" onClick={refresh}>Refresh answers</button>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="stack">{items.map(item => <article key={item.id}>
      <div className="meta">Question #{item.id} · {item.status === 'approved' ? 'Mentor approved' : 'Pending mentor review'}</div>
      <h3>{item.question}</h3>
      <p>{item.status === 'approved' ? item.reviewed_answer : item.ai_answer}</p>
      {item.status === 'approved' && <small>Reviewed by {item.reviewer}</small>}
    </article>)}</div>
  </section>;
}

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
