import React, { useState } from 'react';
import ReviewCard from './ReviewCard.jsx';
import useMentorQueue from './useMentorQueue.js';
import './mentor.css';

function noticeText(notice) {
  return notice.kind === 'approved'
    ? `Question #${notice.id} approved. Newcomers now see your reviewed answer.`
    : `Question #${notice.id} was already reviewed elsewhere and left your queue. Your unsent edits for it were not saved.`;
}

export default function MentorView() {
  const [reviewer, setReviewer] = useState('Mentor');
  const {
    items, drafts, loaded, refreshing, loadError, approving, approveErrors, notices,
    refresh, setDraft, resetDraft, approve, dismissNotice,
  } = useMentorQueue();
  const reviewerReady = reviewer.trim().length > 0;

  return <section className="mentor" aria-labelledby="mentor-title">
    <div className="mentor-heading">
      <p className="mentor-eyebrow">Mentor workspace</p>
      <h2 id="mentor-title">Mentor — Review queue</h2>
      <p>Verify each AI draft before newcomers rely on it. Only answers you approve are shown as mentor reviewed.</p>
    </div>

    <div className="mentor-reviewer">
      <label htmlFor="reviewer">Reviewer (demo display name)</label>
      <p id="reviewer-help" className="mentor-help">Shown to newcomers next to approved answers. Demo only: this name is not verified.</p>
      <input
        id="reviewer"
        value={reviewer}
        maxLength={100}
        onChange={event => setReviewer(event.target.value)}
        aria-describedby="reviewer-help"
      />
      {!reviewerReady && <p className="mentor-error" role="alert">Enter a reviewer name to approve answers.</p>}
    </div>

    <section className="mentor-queue" aria-labelledby="mentor-queue-title">
      <div className="mentor-queue-heading">
        <div>
          <h2 id="mentor-queue-title">Pending questions{loaded ? ` (${items.length})` : ''}</h2>
          <p className="mentor-help">Checks for new questions every 5 seconds while this page is visible.</p>
        </div>
        <button type="button" className="secondary" onClick={refresh} disabled={refreshing}>
          {refreshing ? 'Refreshing…' : 'Refresh queue'}
        </button>
      </div>

      <div className="mentor-notices" role="status">
        {notices.map(notice => <p key={notice.key} className={notice.kind === 'approved' ? 'mentor-success' : 'mentor-warning'}>
          <span>{noticeText(notice)}</span>
          <button type="button" className="secondary" onClick={() => dismissNotice(notice.key)}>Dismiss</button>
        </p>)}
      </div>

      {loadError && <p className="mentor-error" role="alert">
        {loaded
          ? 'Could not refresh the queue. The last loaded questions are still shown. Try Refresh queue again.'
          : 'Could not load the queue. Check that the backend is running and try Refresh queue again.'}
      </p>}
      {!loaded && !loadError && <p className="mentor-empty" role="status">Loading questions…</p>}
      {loaded && items.length === 0 && <div className="mentor-empty">
        <h3>No pending questions</h3>
        <p>New questions from the Newcomer tab appear here automatically.</p>
      </div>}

      <div className="mentor-list">
        {items.map(item => <ReviewCard
          key={item.id}
          item={item}
          draft={drafts[item.id] ?? item.ai_answer ?? ''}
          reviewerReady={reviewerReady}
          approving={Boolean(approving[item.id])}
          error={approveErrors[item.id]}
          onDraftChange={text => setDraft(item.id, text)}
          onReset={() => resetDraft(item.id)}
          onApprove={() => approve(item.id, drafts[item.id] ?? item.ai_answer ?? '', reviewer)}
        />)}
      </div>
    </section>
  </section>;
}
