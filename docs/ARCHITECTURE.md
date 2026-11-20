# Architecture & integration boundaries

```text
Two browser views (Newcomer / Mentor)
           |
frontend/src/api.js  (stable HTTP adapter)
           |
       FastAPI /api
           |
      SQLite storage
           |
    AI adapter hook (TODO: B)
     -> project docs -> retrieval -> LLM -> source citations
```

## Ownership

- **A / Open — Backend & integration:** Own `backend/app/main.py`, persistence, API tests, schema evolution, deployment and shared integration.
- **B / Open — AI & testing:** Create `backend/app/ai/` containing an interchangeable retrieval/model interface. A connects this to the API after reviewing the contract. Add prompt tests and documentation.
- **C / Wyatt — Newcomer UX:** Move NewcomerView from `frontend/src/App.jsx` into `frontend/src/features/newcomer/`; develop question submission, answers, citations, statuses and error UX using `api.js`.
- **D / Open — Mentor UX:** Move MentorView from `frontend/src/App.jsx` into `frontend/src/features/mentor/`; develop review/edit/approve and knowledge reuse using `api.js`.

Two PRs per person are suggested as substantial, separately reviewable slices. The scaffold commit is infrastructure, **not** a substitute for anyone's individual implementation PR.

## Core state machine

```text
new question -> pending (placeholder/AI draft) -> mentor approves -> approved
```

The original `ai_answer` remains available after review. The verified `reviewed_answer` is stored separately. A second review returns HTTP 409. Future revisions need a deliberate versioning design and DECISIONS entry.

## Definition of done

1. Feature works against the **real** shared backend, not only local mock state.
2. At least one expected path and one failure path are tested.
3. No fabricated citations or fake approvals.
4. PR includes testing instructions/screenshots, rationale and actual reviewer discussion.
5. CI passes; code steward confirms integration before merge.

This scaffold supports an **interactive demonstration** but does not yet solve domain questions. AI generation, actual project document ingestion, citations, answer reuse UI, security and participant testing are the next PRs.
