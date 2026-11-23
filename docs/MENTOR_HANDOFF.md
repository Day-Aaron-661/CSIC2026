# D — Mentor review implementation

Owner: Aaron. Implementation date: 2026-11-20 (Asia/Taipei).

This change builds on C's newcomer PR [#9](https://github.com/Day-Aaron-661/CSIC2026/pull/9), which provides the `{ signal }` option in `api.js`, the `App.jsx` React import fix and the Playwright setup; #9 reached `main` through the scaffold merge (#10). PR1 is [#11](https://github.com/Day-Aaron-661/CSIC2026/pull/11). PR2 (knowledge lookup/reuse and approval timeout, below) builds on PR1. This document records implementation rationale for review, not team consensus or a completed steward review.

## Scope

PR1 turns the scaffold Mentor shell into a review queue that is safe to use in a two-browser demo: review, edit and approve pending questions. PR2 adds lookup and reuse of mentor-approved answers and a timeout for approvals; see [PR2](#pr2--approved-answer-lookup-reuse-and-approval-timeout).

## Files and ownership

- `frontend/src/features/mentor/MentorView.jsx`: page composition, reviewer display name, queue status, notices and the list of cards.
- `frontend/src/features/mentor/ReviewCard.jsx`: one pending question with its unreviewed draft, the editable mentor answer and approve/reset actions.
- `frontend/src/features/mentor/useMentorQueue.js`: shared API calls, polling, request lifecycle, drafts and approval state.
- `frontend/src/features/mentor/mentor.css`: styles scoped under `.mentor`; does not restyle Newcomer.
- `frontend/tests/mentor.spec.js`: browser checks for pre-fill and approve, blank input, a double click, failed approval and retry, a 409, questions reviewed elsewhere, polling that keeps drafts, hidden-page pausing, the placeholder decision, narrow viewports with literal markup, and (after review) a stalled approval that must not freeze the queue, an older list arriving after an approval, a 409 while another approval is pending, a re-read queued behind a running read, a lost reply that was saved, and the retry hint. API responses are mocked; C's two-browser test covers the real backend path through the new view.
- `frontend/src/App.jsx`: the inline scaffold `MentorView` is removed and replaced by an import of D's view. The now-unused `useEffect` and `api` imports are removed. Navigation and the Newcomer view are unchanged.
- `docs/API_CONTRACT.md`: one sentence updated to say the Mentor queue now polls like Newcomer. Endpoints, request bodies and response fields are unchanged.

In PR1, backend handlers, database schema, `api.js` and C's newcomer files are unchanged by D (PR2 adds optional signals to `api.js`; see below).

## Interaction decisions

1. **Start from the draft, but label it.** Each answer box is pre-filled with the question's `ai_answer` so the mentor edits rather than retypes. The draft is also shown read-only as "AI draft · not reviewed", and the character counter says whether the answer is still unchanged from the draft. Only the backend's approval record turns an answer into a mentor-reviewed one.
2. **Demo placeholder is not blocked yet.** The backend currently returns a fixed `[DEMO PLACEHOLDER — NOT AI GENERATED]` text instead of an AI draft. For the demo, approving it is allowed. A check that would disable approval while the placeholder marker is present is written in `ReviewCard.jsx` but commented out, to be enabled if the team wants it before B's AI output lands.
3. **Poll like Newcomer.** The pending queue is read every five seconds while the page is visible, immediately when returning to the tab, and on demand with Refresh queue. Reads time out after 15 seconds, only one runs at a time, and polling stops when the view is hidden or unmounted. This is bounded polling, not a real-time guarantee.
4. **Never overwrite work in progress.** A draft is pre-filled only the first time a question is seen. Later refreshes keep whatever the mentor has typed. Reset to AI draft restores the original text on request.
5. **Explain disappearing questions.** If another mentor approves a question first, it leaves the queue on the next refresh. When the local mentor had edited that answer, a notice says it was already reviewed elsewhere and that the unsent edits were not saved. When the mentor's own approval attempt had failed, the notice is neutral instead: the question is no longer pending and may have been approved by them (if the reply was lost) or by another mentor, so they should check the Newcomer history. Untouched cards disappear without a notice.
6. **Approve exactly once, without freezing the queue.** A ref blocks a second click before React renders the disabled button. Polling and Refresh queue keep working while approvals are in flight, so one stalled approval cannot stop new questions from appearing. A card with an approval in flight keeps its current state until that approval settles, and questions approved in this session are ignored if an older list still contains them (approval is final; a second review returns 409).
7. **Recover without guessing.** A failed approval keeps the typed answer, shows an error on that card ("try again; if it keeps failing, refresh the queue") and re-reads the queue. If another read is already running, the re-read is queued and runs as soon as that read finishes, so it is never dropped. If the question is no longer pending (for example HTTP 409, or a lost response that actually saved), the notice from decision 5 explains it. The error message is not parsed to detect 409, so `api.js` did not need to change.
8. **Keep identity honest.** The reviewer name is a demo display string shown to newcomers. It is not verified; authentication remains outside this slice and will be written by a human.

These are D's implementation choices proposed for human review. Record the team's accepted decisions and actual steward handoff in the central decision log when reviewed; do not treat this file as evidence of a meeting or approval.

## Reviewer walkthrough

1. Start backend and frontend using the README commands, then open two browser sessions at `http://localhost:5173`.
2. In session 1 (Newcomer), submit a question. In session 2, choose Mentor. The question should appear within about five seconds without pressing Refresh queue.
3. Check that the answer box is pre-filled with the draft, the counter says "unchanged from AI draft", and Reset to AI draft is disabled until you edit.
4. Edit the answer, keep typing for more than five seconds and confirm the refresh does not overwrite your text. Clear the reviewer name and confirm Approve answer is disabled.
5. Approve. The card should leave the queue with a success notice, and session 1 should show the mentor-reviewed answer after its next refresh.
6. Open Mentor in both sessions on the same question, edit it in one and approve it in the other. The editing session should show the "already reviewed elsewhere" notice after its next refresh. Pressing Approve in the editing session instead gives a 409 and the neutral "no longer pending" notice right away.
7. Stop the backend. The last loaded queue should stay visible with an error, and a failed approval should keep the typed answer. Restore the backend and refresh.
8. Navigate by keyboard and at a narrow viewport. Confirm labels, focus, wrapping and readable status text.
9. Run the automated commands in README. The browser tests include network failures, a 409 and stale reads that are hard to reproduce manually.

## Remaining team integration

- **A:** identity/authentication for reviewers, data isolation, and any schema change for answer revisions after approval (currently a second review returns 409).
- **B:** real AI drafts and an agreed way to represent AI errors; then the team can decide whether to enable the placeholder check from decision 2 or extend it to AI error output.
- **C:** no change needed; the Newcomer view already shows `reviewed_answer`, the reviewer name and the original draft.
- **D:** knowledge lookup/reuse and the approval timeout are in PR2. If B adds retrieval, `findSimilar` in `matchKnowledge.js` is the single place to swap keyword matching for it.
- **All four:** real outside-team user sessions and substantive reviews. Automated browser tests are developer checks and do not count as user sessions.

Unsent mentor answers are component state: they survive refreshes, but not a page reload or switching away from the Mentor view.

## PR2 — approved-answer lookup, reuse and approval timeout

Implementation date: 2026-11-21 (Asia/Taipei). Goal: mentors should not have to answer the same basic question again (DECISION.md, Problem). No backend change: `GET /api/knowledge` already returns approved questions.

### What the mentor sees

1. **Similar approved answers on each card.** Under the AI draft, a card lists up to three previously approved questions that share keywords with the pending one, with reviewer, approval time and the approved answer (collapsed). The section is labeled "keyword match, not AI" and is hidden when nothing matches.
2. **Use as starting point.** Copies that approved answer into the answer box and focuses it. A confirmation asks first only when the box holds the mentor's own text; it does not ask when the box is empty, still the AI draft, or another suggestion copied in unchanged. Reuse only fills the box; the question is approved only when the mentor presses Approve answer.
3. **Search approved answers.** A search box above the queue searches every approved question and answer by keyword (read-only, up to ten results). If the typed text gives no keywords (a single Chinese character, or only common words such as "how"), it falls back to a case-insensitive text match and the result line says "(exact text match)", instead of wrongly reporting no matches.
4. **Fresh after each approval.** The approved-answer list is read on opening the Mentor view, on Refresh approved answers, right after each successful approval, and whenever a question leaves the queue because it was approved (by another mentor, or by this mentor with the reply lost). An answer just approved is therefore offered for the next similar question. The list itself is not polled; it is re-read when a queue refresh shows such a change.
5. **Approval timeout.** If an approval gets no reply within 15 seconds, the card shows "no reply after 15 seconds; it may still have been saved", keeps the typed answer and re-reads the queue. It never resends automatically. If the server did save it, the question leaves the queue with the neutral "no longer pending" notice from decision 5; otherwise the card stays and the mentor can try again (if the first request was in fact saved, the server answers 409 and the same notice follows). While an approval is waiting, the rest of the queue keeps refreshing (decision 6); the timeout additionally releases the stuck card.

### How matching works (and its limits)

`matchKnowledge.js` lower-cases and NFKC-normalizes text and removes Latin accents (so "café" matches "cafe"; Japanese voicing marks are kept). Scripts written without spaces (Chinese, Japanese kana) are split into overlapping two-character pairs; every other script, including Korean, is split into words. Common filler words are dropped. Card suggestions use the Dice coefficient between the two questions (threshold 0.25); search uses the share of typed keywords found in the question or answer (threshold 0.5), with the text-match fallback described above. Keywords of approved answers are computed once per approved-answer list (`prepareKnowledge`), not on every queue poll. This is string overlap, not semantic retrieval: a question worded differently can be missed, and a shared technical word can produce a weak suggestion. Mentors must check every suggestion before reusing it. Only entries with `status: "approved"` and a `reviewed_answer` are offered.

### Files

- New in `frontend/src/features/mentor/`: `matchKnowledge.js` (matching), `useKnowledge.js` (reads with 15 s timeout, one read at a time, cancelled on unmount; failures only affect the lookup panel), `KnowledgeMatches.jsx` (card section), `KnowledgeSearch.jsx` (search box), `Timestamp.jsx` (shared by the card and the lookup views).
- Changed: `MentorView.jsx`, `ReviewCard.jsx`, `useMentorQueue.js` (`onKnowledgeChange` callback, approval timeout, abort on unmount), `mentor.css`, `frontend/tests/mentor.spec.js` (12 new browser tests: suggestions and reuse, confirm before replacing, no confirmation for an empty box or an unchanged suggestion, Chinese matching, accented/Japanese/Korean matching, re-read after approval and after a lost reply that was saved, lookup failure, search, search text-match fallback, literal markup on mobile, approval timeout).
- **Shared files:** `frontend/src/api.js` — `review(id, answer, reviewer, { signal })` and `knowledge({ signal })` accept an optional signal, following C's change for `questions`/`ask`; existing callers are unaffected. `docs/API_CONTRACT.md` — the adapter paragraph lists the new options and the no-automatic-resend rule. HTTP paths, bodies and fields are unchanged.

### Reviewer walkthrough (PR2)

1. Start both servers. As Newcomer, ask "How do I start the backend?"; as Mentor, approve it with an edited answer.
2. As Newcomer, ask "How can I start the backend locally?". On its Mentor card, "Previously approved answers" lists the first question. Expand it, press Use as starting point, edit and approve.
3. Type a keyword in Search approved answers; try one that matches nothing, and a single Chinese character such as 庫 (text-match fallback).
4. Edit an answer, then press Use as starting point and cancel the confirmation: your text stays.
5. Stop the backend and press Refresh approved answers: an error appears in the lookup panel while the last loaded queue stays usable.
