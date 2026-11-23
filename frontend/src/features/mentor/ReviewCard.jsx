import React from 'react';

const MAX_ANSWER = 10000;

// Disabled for the demo (decision 2026-11-20): the backend still returns a fixed
// placeholder instead of an AI draft, and approving it is allowed for now.
// Uncomment this and the two marked lines below to block approving placeholder text.
// const DEMO_PLACEHOLDER_MARKER = '[DEMO PLACEHOLDER';
// function isDemoPlaceholder(text) {
//   return text.includes(DEMO_PLACEHOLDER_MARKER);
// }

function Timestamp({ value, prefix }) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return null;
  return <span>{prefix} <time dateTime={value}>{date.toLocaleString()}</time></span>;
}

export default function ReviewCard({ item, draft, reviewerReady, approving, error, onDraftChange, onReset, onApprove }) {
  const aiAnswer = item.ai_answer ?? '';
  const answerId = `mentor-answer-${item.id}`;
  const countId = `mentor-answer-count-${item.id}`;
  const trimmed = draft.trim();
  const unchanged = draft === aiAnswer;
  const canApprove = reviewerReady && !approving && trimmed.length > 0 && trimmed.length <= MAX_ANSWER;
  // const canApprove = reviewerReady && !approving && trimmed.length > 0 && trimmed.length <= MAX_ANSWER && !isDemoPlaceholder(draft);

  return <article className="mentor-card" aria-labelledby={`mentor-question-${item.id}`} id={`mentor-card-${item.id}`}>
    <div className="mentor-card-meta">
      <span>Question #{item.id}</span>
      <span className="mentor-badge">Awaiting your review</span>
    </div>
    <h3 id={`mentor-question-${item.id}`}>{item.question}</h3>
    <p className="mentor-timestamp"><Timestamp value={item.created_at} prefix="Asked" /></p>

    <div className="mentor-draft">
      <h4>AI draft · not reviewed</h4>
      <p className="mentor-text">{aiAnswer}</p>
    </div>

    <label htmlFor={answerId}>Mentor verified answer</label>
    <p className="mentor-help" id={`${answerId}-help`}>
      Pre-filled with the AI draft. Check it against project material and edit before approving.
    </p>
    <textarea
      id={answerId}
      value={draft}
      onChange={event => onDraftChange(event.target.value)}
      maxLength={MAX_ANSWER}
      rows={6}
      disabled={approving}
      aria-describedby={`${answerId}-help ${countId}`}
    />
    <div className="mentor-card-footer">
      <span id={countId} className="mentor-help">
        {draft.length.toLocaleString()} / {MAX_ANSWER.toLocaleString()} characters{unchanged ? ' · unchanged from AI draft' : ' · edited'}
      </span>
      <div className="mentor-actions">
        <button type="button" className="secondary" onClick={onReset} disabled={approving || unchanged}>Reset to AI draft</button>
        <button type="button" onClick={onApprove} disabled={!canApprove}>{approving ? 'Approving…' : 'Approve answer'}</button>
      </div>
    </div>
    {/* {isDemoPlaceholder(draft) && <p className="mentor-help">Replace the demo placeholder with a verified answer before approving.</p>} */}
    {error && <p className="mentor-error" role="alert">
      Approval was not confirmed ({error}). Your answer is still here. Try again; if it keeps failing, refresh the queue.
    </p>}
  </article>;
}
