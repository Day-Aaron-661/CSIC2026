import React from 'react';

function Timestamp({ value, prefix }) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return null;
  return <span>{prefix} <time dateTime={value}>{date.toLocaleString()}</time></span>;
}

export default function QuestionCard({ item }) {
  const approved = item.status === 'approved';
  return <article className="newcomer-question" aria-labelledby={`question-title-${item.id}`} id={`question-${item.id}`}>
    <div className="newcomer-question-meta">
      <span>Question #{item.id}</span>
      <span className={`newcomer-badge ${approved ? 'newcomer-badge-approved' : 'newcomer-badge-pending'}`}>
        {approved ? 'Mentor reviewed' : 'Awaiting mentor review'}
      </span>
    </div>
    <h3 id={`question-title-${item.id}`}>{item.question}</h3>
    <p className="newcomer-timestamp"><Timestamp value={item.created_at} prefix="Asked" /></p>
    <div className={`newcomer-answer ${approved ? 'newcomer-answer-approved' : ''}`}>
      <h4>{approved ? 'Mentor-reviewed answer' : 'Draft answer · not reviewed'}</h4>
      <p className="newcomer-answer-text">{approved ? item.reviewed_answer : item.ai_answer}</p>
      {approved
        ? <p className="newcomer-reviewer">Reviewed by {item.reviewer} · <Timestamp value={item.reviewed_at} prefix="" /></p>
        : <p className="newcomer-answer-note">Wait for your mentor to verify this draft before relying on it.</p>}
    </div>
    {approved && <details className="newcomer-original">
      <summary>Original draft</summary>
      <p className="newcomer-answer-text">{item.ai_answer}</p>
    </details>}
    <p className="newcomer-sources">Sources are not available in the current demo.</p>
  </article>;
}
