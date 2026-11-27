# API Contract — CP2 v0.3 (proposed by A, additive over v0.1)

Base URL locally: `http://localhost:8000`. Frontend `VITE_API_URL` may override it.

## Shared question data

```json
{
  "id": 1,
  "question": "How do I start?",
  "ai_answer": "[DEMO PLACEHOLDER — NOT AI GENERATED] ...",
  "ai_status": "placeholder",
  "ai_error": null,
  "status": "pending",
  "reviewed_answer": null,
  "reviewer": null,
  "created_at": "2026-11-17T12:00:00+00:00",
  "reviewed_at": null,
  "citations": [
    { "source": "README.md", "snippet": "uvicorn app.main:app", "locator": "L14" }
  ]
}
```

New in v0.2 (all additive; v0.1 callers need no change):

- `ai_status`: `placeholder` (fixed demo text), `ok` (real AI draft) or `failed`. When `failed`, `ai_answer` is a fixed notice that no draft is available — never generated text — and `ai_error` holds a short category (`timeout`, `exception:<Type>`, `invalid_result`, `empty_answer`, or B's own code). Raw exception text is never returned.
- `citations`: sources returned by B's generator, `[]` when none. Only `source` is required.
- `ai_status` never affects `status`; only a mentor review can approve.

`status` is either `pending` or `approved`. Frontend displays `reviewed_answer` only when status is approved. Never label new AI generations as mentor-approved without an actual review record.

| Method | URL | Request | Result |
|---|---|---|---|
| GET | `/api/health` | — | `{ "ok": true, "mode": "placeholder", "schema_version": 2 }`; `mode` is `placeholder`, `claude`, `gemini` or `custom` |
| POST | `/api/questions` | `{ "question": "...", "client_request_id"?: "uuid" }` | 201 new; 200 when the same `client_request_id` is resent |
| GET | `/api/questions` | optional `?status=pending\|approved`, `?limit=1..500` (default 100; **no default cap for `status=pending`**, so the mentor queue always sees the oldest waiting question) | question array newest first |
| GET | `/api/questions/{id}` | — | question object |
| POST | `/api/questions/{id}/review` | `{ "answer": "...", "reviewer": "..." }` | approved question object |
| GET | `/api/questions/{id}/reviews` | — | review history, oldest first: `[{ "version": 1, "action": "approve", "answer": "...", "reviewer": "...", "created_at": "..." }]`; `[]` while pending; 404 for nonexistent ID |
| GET | `/api/knowledge` | optional `?q=text` (1–200 chars), `?limit=1..500` | approved question array; `q` is a case-insensitive substring match on question and reviewed answer |

Failure semantics: 422 for invalid or blank input (including `limit` out of range and a `client_request_id` that is not 1–100 of `A-Z a-z 0-9 _ -`), 404 for nonexistent ID, 409 for a second review of an already approved question, 409 when a `client_request_id` is reused for a different question, 422 when a review of an `ai_status="failed"` question submits the failure notice (`ai_answer`) unchanged. Approving an unchanged `placeholder` is still allowed for the demo; whether to block it is a pending team decision.

### Duplicate submission (`client_request_id`)

Optional. A client that generates one key per user submission and reuses it on retry gets the original question back (HTTP 200) instead of a duplicate, including when two retries race. The question text must match the original exactly after trimming. Without a key, behavior is unchanged from v0.1.

### AI generator boundary (A ↔ B)

`backend/app/ai_hook.py` defines `AnswerResult(answer, status, citations, error)` and `Citation(source, snippet, locator)`. B implements `generate(question) -> AnswerResult` and it is passed to `create_app(generator=...)`. The API calls it outside any database transaction, waits at most `CP2_AI_TIMEOUT` seconds (default 30, below the newcomer 60-second submit timeout), and stores any exception, timeout or malformed result as `ai_status="failed"` while still saving the question for mentor review.

`CP2_AI` picks the generator at startup: `placeholder` (default), `claude` or `gemini`. Both model modes run B's `RagGenerator` with `knowledge_source` reading up to 500 approved answers through `search_knowledge`; `claude` passes `call=claude_llm.call_api` (Anthropic API, `claude-opus-5-5`), `gemini` uses B's `llm.call_api`. A generator passed to `create_app` always wins (health reports `custom`). Any other value refuses to start. Tests and the Playwright backend force `placeholder`, so they never call a model.

### Review state and history (v0.3)

Allowed transitions live in one table, `TRANSITIONS` in `backend/app/repository.py`; today it is only `approve: pending -> approved`. An approval updates the question and appends a `reviews` row in **one transaction**: either both happen or neither does. Two concurrent approvals of the same question give exactly one 200 and one 409, and only the winner appears in the history. Questions approved before v0.3 get a backfilled version-1 history entry on upgrade.

`version` numbers a question's reviews (1, 2, ...). It is reserved so that a later "revise approved answer" action needs no schema change. Revising is **not** allowed yet: a second review still returns 409, and enabling it needs a team decision in DECISION.md.

### Storage

SQLite with WAL mode. The schema version is `PRAGMA user_version`; `backend/app/db.py` runs ordered migrations on startup and keeps existing data (v0 scaffold files are upgraded in place). A server refuses to start on a database newer than its code.

This is a **stable starter contract**, not a final schema. Owner B may propose extra retrieval metadata; Owner A coordinates schema migrations and changes to endpoint semantics. A and B should agree how to model AI errors rather than return an invented answer.

## Integration boundary

Frontend imports `frontend/src/api.js` only, not raw `fetch` scattered in feature components. Backend is authoritative for approval state. AI output alone must never update the approval status. Newcomer checks the shared list every five seconds while visible and refreshes when returning to the tab; Mentor checks the pending queue every five seconds while visible and refreshes when returning to the tab; manual refresh remains available.

The JS adapter accepts optional `{ signal }` as the last argument to `questions(status, options)`, `ask(question, options)`, `review(id, answer, reviewer, options)` and `knowledge(options)`. This supports cancelling obsolete requests and timeouts; HTTP paths, bodies, question fields and existing callers are unchanged. Mentor stops waiting for an approval after 15 seconds and re-reads the queue; it never resends the review POST automatically, because the server may already have saved it. Newcomer inserts the successful POST response immediately instead of treating a later list-read failure as a failed submission. There is no automatic POST retry. Without a `client_request_id` there is no server-side idempotency guarantee; with one, see Duplicate submission above.
