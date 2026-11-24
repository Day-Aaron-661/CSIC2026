import React from 'react';
import Timestamp from './Timestamp.jsx';

// Approved answers to similar questions, shown inside one review card.
export default function KnowledgeMatches({ cardId, matches, disabled, onUse }) {
  if (!matches.length) return null;
  const titleId = `mentor-matches-${cardId}`;
  return <section className="mentor-matches" aria-labelledby={titleId}>
    <h4 id={titleId}>Previously approved answers <span className="mentor-match-note">· keyword match, not AI</span></h4>
    <p className="mentor-help">Mentors already answered these similar questions. Check that the answer still fits before reusing it.</p>
    <ul>
      {matches.map(match => {
        const questionId = `mentor-match-${cardId}-${match.id}`;
        return <li key={match.id} className="mentor-match">
          <p className="mentor-match-question" id={questionId}>#{match.id} · {match.question}</p>
          <p className="mentor-match-meta">
            Approved by {match.reviewer || 'unknown reviewer'} <Timestamp value={match.reviewed_at} prefix="on" />
          </p>
          <details>
            <summary>Show approved answer</summary>
            <p className="mentor-text">{match.reviewed_answer}</p>
          </details>
          <button
            type="button"
            className="secondary"
            onClick={() => onUse(match.reviewed_answer)}
            disabled={disabled}
            aria-describedby={questionId}
          >Use as starting point</button>
        </li>;
      })}
    </ul>
  </section>;
}
