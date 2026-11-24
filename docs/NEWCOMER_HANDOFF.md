# C — Newcomer implementation and review

Owner: Wyatt. Implementation date: 2026-11-19 (Asia/Taipei).

This change builds on scaffold PR [#8](https://github.com/Day-Aaron-661/CSIC2026/pull/8). The scaffold is still awaiting human review; the C feature PR initially targets `chore/cp2-team-scaffold` so its diff shows only C's work. After #8 is merged, retarget the C PR to `main` and verify CI before merging it. This document records implementation rationale for review, not team consensus or a completed steward review.

## Architecture assessment

Keep React/Vite, FastAPI/SQLite, the shared `api.js` adapter and the agreed feature folders. They already support two independent browser sessions reading and changing the same persistent questions. The newcomer flow needs only the existing list and submit endpoints. A new state-management library, backend service or WebSocket protocol would add integration work without being necessary for this prototype.

One runtime defect was corrected: `App.jsx` needs a default React import because the current Vite setup uses classic JSX transformation. A successful bundle alone does not check this binding at runtime; the browser suite loads the real application and checks for page errors.

## Files and ownership

- `frontend/src/features/newcomer/NewcomerView.jsx`: composition, input, shared history, filters and feedback.
- `frontend/src/features/newcomer/QuestionCard.jsx`: pending/reviewed answers, reviewer, timestamps and original draft.
- `frontend/src/features/newcomer/useNewcomerQuestions.js`: shared API calls, request lifecycle and polling.
- `frontend/src/features/newcomer/newcomer.css`: styles scoped under `.newcomer`; does not restyle Mentor.
- `frontend/src/App.jsx`: imports C's view; Mentor stays available for D to extract.
- `frontend/src/api.js`: optional cancellation signal for list/submit, with existing call signatures still valid.
- `frontend/tests/` and `frontend/playwright.config.js`: browser verification and a disposable test backend.

Backend handlers, database schema, API response fields and the Mentor implementation are unchanged by C.

## Interaction decisions

1. **Show the status from the backend.** Pending drafts and mentor-reviewed answers have different text labels and visual treatments. An approved answer uses `reviewed_answer`; `ai_answer` remains visible under “Original draft.” Reviewer names are demo display strings, not verified identities.
2. **Describe the list as shared history.** There is no login or user ID in the current API, so the page does not claim these are only the current user's questions.
3. **Poll while visible.** Five-second reads and an immediate refresh when returning to the tab keep the two-browser demo current. Hidden tabs and unmounted views stop polling. This is bounded polling, not a real-time delivery guarantee. Manual refresh remains available.
4. **Keep saves distinct from reads.** A successful POST immediately adds its returned question to the history and clears only the submitted draft. A later failed read keeps the last loaded answers visible. In-flight read cancellation prevents an older list from erasing a new question.
5. **Recover without automatic resubmission.** Blank input and multiple simultaneous submissions are blocked. The input is disabled during submission so newer text cannot be accidentally cleared. Failed/timeout submissions retain the draft and advise checking history before retrying: a lost response may still correspond to a saved server record. Reads time out after 15 seconds; submissions after 60 seconds. Server-side idempotency remains A's responsibility.
6. **Make states usable.** Loading, empty, filtered-empty, submitting, success and failed-read/failed-submit states have explicit copy. Labels, focus indicators, pressed-state filters and status/error announcements support keyboard and assistive-technology use. Layout and long answer text wrap on narrow screens.
7. **Keep the source boundary honest.** The current contract has no citation fields and the backend uses a fixed demo placeholder. No links or AI results are invented. C's page says sources are unavailable; A/B must agree and document the citation schema before C renders real sources.

These are C's implementation choices proposed for human review. Record the team's accepted decisions and actual steward handoff in the central decision log when reviewed; do not treat this file as evidence of a meeting or approval.

## Reviewer walkthrough

1. Start backend and frontend using the README commands, then open two browser sessions at `http://localhost:5173`.
2. In Newcomer, try a blank question, then submit a real question. Check the pending label, the explicit placeholder and the shared history.
3. In the other session, choose Mentor, refresh its queue, enter a verified answer and a display name, then approve.
4. Return to the Newcomer tab. The reviewed answer should appear after refresh without re-submitting; expand Original draft and compare both versions. Test All / Awaiting review / Reviewed filters.
5. Stop the backend and refresh. The last known list should stay visible with an error. A failed submission should retain its draft. Restore the backend and refresh before choosing whether to retry.
6. Navigate by keyboard and at a narrow viewport. Confirm labels, focus, wrapping and readable status text.
7. Run the automated commands in README. The browser tests use isolated data and include network failures and stale requests that are difficult to reproduce manually.

## Remaining team integration

- **A:** deployment/CORS, identity/data isolation, schema changes and reliable server-side duplicate handling.
- **B:** real retrieval/model output, citation/error contracts, prompt documentation and prompt tests. The frontend currently shows the returned draft as plain text.
- **D:** Mentor editing/review and knowledge lookup/reuse. No knowledge-search UI is claimed as part of C.
- **C after A/B integration:** render the agreed source objects and verify real AI failure states; revise UX using actual user-test findings.
- **All four:** real outside-team user sessions, substantive reviews, decision history and CP2 evidence. Automated browser tests are developer checks and do not count as those user sessions or as a prompt test suite.

Unsent drafts are component state: they survive a failed submission or refresh, but not a page reload or switching away from the Newcomer view. Persistence and access control remain outside this C slice.

## CP2 C integration update — PR #18 (2026-11-24)

- The newcomer now displays structured `citations` (source, optional locator and excerpt) under the **original AI draft**, with an explicit notice that those references are not independently verified. A mentor's edited final answer is not automatically attributed to the AI draft's citations.
- New `ai_status` values (`ok`, `failed`, `placeholder`) have distinct labels. A demo placeholder is not described as an AI draft and does not show misleading “no AI citations” copy. Old backend responses without `citations` / `ai_status` still render safely.
- The `api.ask` request optionally includes A's `client_request_id`. A submitted question is not automatically retried: after an uncertain outcome, the same question text retains its request ID for a user-initiated retry, even after editing it away and back or reloading the tab. After confirmed success, its key is removed so an intentionally new submission starts fresh.
- Pending request IDs are kept in tab-scoped `sessionStorage` (up to 20 recent unconfirmed question/key pairs). Only unconfirmed questions are retained there; confirmed keys are removed. Storage denial or a missing crypto API must not block submission, but server-enforced duplicate suppression then cannot be guaranteed. `crypto.randomUUID` is used where supported; `crypto.getRandomValues` works on non-HTTPS LAN origins. If both are unavailable, the request is sent without an idempotency key.
- Backend compatibility: A/PR #12 returns 200 for a replayed key or 201 for a new question; both count as success. The old API ignores this optional field, so idempotency needs A/PR #12 to be merged to work across retries.
- This PR updates only C's files plus the common `api.ask` adapter. The new and existing Playwright tests cover insecure-origin key fallback, reused IDs across changed text and tab reload, missing/malformed citation fields, error/placeholder states, and original two-browser review flow.

**Privacy and limitations:** This prototype stores unconfirmed question text in session storage for retry matching until successful submission, tab closure, or eviction after 20 entries. Do not use it for secrets; no login/access controls are added here. Clearing browser tab storage means previously unconfirmed requests lose their old idempotency key. If crypto is entirely absent, manual retry can still create a duplicate.
