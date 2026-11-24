import React from 'react';

function Timestamp({ value, prefix }) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return null;
  return <span>{prefix} <time dateTime={value}>{date.toLocaleString()}</time></span>;
}

export default function QuestionCard({ item }) {
  const approved = item.status === 'approved';
  const aiFailed = item.ai_status === 'failed';
  const aiPlaceholder = item.ai_status === 'placeholder';
  // An approved answer is written by the mentor; these citations belong to the
  // original AI draft only, not necessarily to the mentor's final wording.
  const sources = Array.isArray(item.citations)
    ? item.citations.filter(source => source && typeof source.source === 'string' && source.source.trim())
    : [];

  return <article className="newcomer-question" aria-labelledby={'question-title-' + item.id} id={'question-' + item.id}>
    <div className="newcomer-question-meta">
      <span>Question #{item.id}</span>
      <span className={'newcomer-badge ' + (approved ? 'newcomer-badge-approved' : 'newcomer-badge-pending')}>
        {approved ? 'Mentor reviewed' : 'Awaiting mentor review'}
      </span>
    </div>
    <h3 id={'question-title-' + item.id}>{item.question}</h3>
    <p className="newcomer-timestamp"><Timestamp value={item.created_at} prefix="Asked" /></p>
    <div className={'newcomer-answer ' + (approved ? 'newcomer-answer-approved' : '')}>
      <h4>{approved ? 'Mentor-reviewed answer' : aiFailed ? 'AI draft unavailable' : aiPlaceholder ? 'Demo placeholder · not AI generated' : 'Draft answer · not reviewed'}</h4>
      <p className="newcomer-answer-text">{approved ? item.reviewed_answer : item.ai_answer}</p>
      {approved
        ? <p className="newcomer-reviewer">Reviewed by {item.reviewer} · <Timestamp value={item.reviewed_at} prefix="" /></p>
        : <p className="newcomer-answer-note">
          {aiFailed
            ? 'The AI could not generate a draft. Your question is still waiting for mentor review.'
            : aiPlaceholder
              ? 'This is demo text, not an AI-generated answer. Wait for your mentor to verify a real answer.'
              : 'Wait for your mentor to verify this draft before relying on it.'}
        </p>}
    </div>
    {approved && <details className="newcomer-original">
      <summary>Original draft</summary>
      <p className="newcomer-answer-text">{item.ai_answer}</p>
    </details>}
    {!aiFailed && !aiPlaceholder && (sources.length ? <section className="newcomer-sources" aria-label="Sources for AI draft">
      <h4>Sources for AI draft · not independently verified</h4>
      <ol>
        {sources.map((source, index) => <li key={index}>
          <span className="newcomer-source-name">{source.source}</span>
          {typeof source.locator === 'string' && source.locator.trim() && <span className="newcomer-source-locator"> · {source.locator}</span>}
          {typeof source.snippet === 'string' && source.snippet.trim() && <details className="newcomer-source-excerpt">
            <summary>Show source excerpt</summary>
            <p>{source.snippet}</p>
          </details>}
        </li>)}
      </ol>
    </section> : <p className="newcomer-sources">
      {Array.isArray(item.citations)
        ? 'No document citations were provided for this AI draft.'
        : 'Sources are not available with this backend yet.'}
    </p>)}
  </article>;
}
