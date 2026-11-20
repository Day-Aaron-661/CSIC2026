import React, { useState } from 'react';
import { flushSync } from 'react-dom';
import QuestionCard from './QuestionCard.jsx';
import useNewcomerQuestions from './useNewcomerQuestions.js';
import './newcomer.css';

export default function NewcomerView() {
  const [question, setQuestion] = useState('');
  const [filter, setFilter] = useState('all');
  const { items, loaded, refreshing, loadError, refresh, submitting, submitError, submittedId, submit } = useNewcomerQuestions();
  const pending = items.filter(item => item.status === 'pending').length;
  const approved = items.filter(item => item.status === 'approved').length;
  const visible = items.filter(item => filter === 'all' || item.status === filter);
  const filters = [
    { value: 'all', label: 'All', count: items.length },
    { value: 'pending', label: 'Awaiting review', count: pending },
    { value: 'approved', label: 'Reviewed', count: approved }
  ];

  const onSubmit = async (event) => {
    event.preventDefault();
    if (await submit(question)) {
      setQuestion('');
      setFilter('all');
    }
  };

  return <section className="newcomer" aria-labelledby="newcomer-title">
    <div className="newcomer-heading">
      <p className="newcomer-eyebrow">Newcomer workspace</p>
      <h2 id="newcomer-title">Ask about the project</h2>
      <p>Send a project question, then follow your mentor’s review here.</p>
    </div>

    <form className="newcomer-compose" onSubmit={onSubmit} aria-label="Ask a project question">
      <label htmlFor="newcomer-question">Project question</label>
      <p id="newcomer-question-help" className="newcomer-help">Include what you tried and where you got stuck.</p>
      <textarea
        id="newcomer-question"
        name="question"
        value={question}
        onChange={event => setQuestion(event.target.value)}
        maxLength={2000}
        rows={4}
        required
        disabled={submitting}
        aria-describedby="newcomer-question-help newcomer-question-count"
        placeholder="For example: How do I run the project locally?"
      />
      <div className="newcomer-compose-footer">
        <span id="newcomer-question-count" className="newcomer-help">{question.length.toLocaleString()} / 2,000 characters</span>
        <button type="submit" disabled={submitting || !question.trim() || question.trim().length > 2000}>
          {submitting ? 'Submitting…' : 'Submit question'}
        </button>
      </div>
      {submitError && <p className="newcomer-error" role="alert">We couldn’t confirm that your question was saved. Your draft is still here. Refresh the history before retrying, to avoid a duplicate.</p>}
      {submittedId !== null && <p className="newcomer-success" role="status">
        Question #{submittedId} submitted. <a href={`#question-${submittedId}`} onClick={() => flushSync(() => setFilter('all'))}>View question</a>
      </p>}
    </form>

    <section className="newcomer-history" aria-labelledby="newcomer-history-title">
      <div className="newcomer-history-heading">
        <div>
          <h2 id="newcomer-history-title">Shared question history</h2>
          <p className="newcomer-help">Everyone’s questions appear here. Checks for updates every 5 seconds while this page is visible.</p>
        </div>
        <button type="button" className="secondary" onClick={refresh} disabled={refreshing || submitting}>
          {refreshing ? 'Refreshing…' : 'Refresh answers'}
        </button>
      </div>

      <div className="newcomer-filters" role="group" aria-label="Filter question history">
        {filters.map(option => <button
          type="button"
          key={option.value}
          aria-pressed={filter === option.value}
          className={filter === option.value ? '' : 'secondary'}
          onClick={() => setFilter(option.value)}
        >{option.label} ({option.count})</button>)}
      </div>

      <p className="newcomer-review-summary" role="status">
        {loaded ? `${pending} awaiting review · ${approved} mentor reviewed` : ''}
      </p>

      {loadError && <p className="newcomer-error" role="alert">
        {loaded
          ? 'Could not refresh questions. The last loaded answers are still shown. Try Refresh answers again.'
          : 'Could not load questions. Check your connection and try Refresh answers again.'}
      </p>}
      {!loaded && !loadError && <p className="newcomer-empty" role="status">Loading questions…</p>}
      {loaded && visible.length === 0 && <div className="newcomer-empty">
        <h3>{items.length === 0 ? 'No questions yet' : filter === 'pending' ? 'No questions waiting for review' : 'No reviewed answers yet'}</h3>
        <p>{items.length === 0 ? 'Ask your first question above to start the conversation.' : 'Choose another filter to see the rest of the shared history.'}</p>
      </div>}
      <div className="newcomer-list">
        {visible.map(item => <QuestionCard key={item.id} item={item} />)}
      </div>
    </section>
  </section>;
}
