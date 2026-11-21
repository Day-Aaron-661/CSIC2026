# D — Mentor review implementation

Owner: Aaron. Implementation date: 2026-11-20 (Asia/Taipei).

This change builds on C's newcomer PR [#9](https://github.com/Day-Aaron-661/CSIC2026/pull/9), which provides the `{ signal }` option in `api.js`, the `App.jsx` React import fix and the Playwright setup. #9 has been merged into `chore/cp2-team-scaffold`, so this D PR also targets `chore/cp2-team-scaffold` and its diff shows only D's work. The scaffold branch, including C's and D's work, is expected to be merged into `main` together. This document records implementation rationale for review, not team consensus or a completed steward review.

## Scope

PR1 turns the scaffold Mentor shell into a review queue that is safe to use in a two-browser demo: review, edit and approve pending questions. Knowledge lookup/reuse and request cancellation for `api.review()` are deferred to a later D PR.

## Files and ownership

- `frontend/src/features/mentor/MentorView.jsx`: page composition, reviewer display name, queue status, notices and the list of cards.
- `frontend/src/features/mentor/ReviewCard.jsx`: one pending question with its unreviewed draft, the editable mentor answer and approve/reset actions.
- `frontend/src/features/mentor/useMentorQueue.js`: shared API calls, polling, request lifecycle, drafts and approval state.
- `frontend/src/features/mentor/mentor.css`: styles scoped under `.mentor`; does not restyle Newcomer.
- `frontend/tests/mentor.spec.js`: browser checks for pre-fill and approve, blank input, a double click, failed approval and retry, a 409, questions reviewed elsewhere, polling that keeps drafts, hidden-page pausing, the placeholder decision, narrow viewports with literal markup, and (after review) a stalled approval that must not freeze the queue, an older list arriving after an approval, a 409 while another approval is pending, a re-read queued behind a running read, a lost reply that was saved, and the retry hint. API responses are mocked; C's two-browser test covers the real backend path through the new view.
- `frontend/src/App.jsx`: the inline scaffold `MentorView` is removed and replaced by an import of D's view. The now-unused `useEffect` and `api` imports are removed. Navigation and the Newcomer view are unchanged.
- `docs/API_CONTRACT.md`: one sentence updated to say the Mentor queue now polls like Newcomer. Endpoints, request bodies and response fields are unchanged.

Backend handlers, database schema, `api.js` and C's newcomer files are unchanged by D.

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
- **D (next PR):** knowledge lookup/reuse of approved answers, and cancellation/timeout for `api.review()` once the `{ signal }` change to `api.js` is agreed in `docs/API_CONTRACT.md`.
- **All four:** real outside-team user sessions and substantive reviews. Automated browser tests are developer checks and do not count as user sessions.

Unsent mentor answers are component state: they survive refreshes, but not a page reload or switching away from the Mentor view.
