# API Contract — CP2 v0.1

Base URL locally: `http://localhost:8000`. Frontend `VITE_API_URL` may override it.

## Shared question data

```json
{
  "id": 1,
  "question": "How do I start?",
  "ai_answer": "[DEMO PLACEHOLDER — NOT AI GENERATED] ...",
  "status": "pending",
  "reviewed_answer": null,
  "reviewer": null,
  "created_at": "2026-11-17T12:00:00+00:00",
  "reviewed_at": null
}
```

`status` is either `pending` or `approved`. Frontend displays `reviewed_answer` only when status is approved. Never label new AI generations as mentor-approved without an actual review record.

| Method | URL | Request | Result |
|---|---|---|---|
| GET | `/api/health` | — | `{ "ok": true, "mode": "scaffold" }` |
| POST | `/api/questions` | `{ "question": "..." }` | 201; shared question object |
| GET | `/api/questions` | optional `?status=pending` or `approved` | question array newest first |
| GET | `/api/questions/{id}` | — | question object |
| POST | `/api/questions/{id}/review` | `{ "answer": "...", "reviewer": "..." }` | approved question object |
| GET | `/api/knowledge` | — | approved question array |

Failure semantics: 422 for invalid or blank input, 404 for nonexistent ID, 409 for a second review of an already approved question.

This is a **stable starter contract**, not a final schema. Owner B may propose a compatible `citations` array and retrieval metadata; Owner A coordinates schema migrations and changes to endpoint semantics. A and B should agree how to model AI errors rather than return an invented answer.

## Integration boundary

Frontend imports `frontend/src/api.js` only, not raw `fetch` scattered in feature components. Backend is authoritative for approval state. AI output alone must never update the approval status. UI refresh is manual in this skeleton, so two-browser demo requires clicking Refresh.
