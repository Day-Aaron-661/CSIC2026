# CSIC2026 — CP2 Team Scaffold

**Status:** Working integration skeleton, **not** a finished AI product. This baseline contains a persistent shared question/review flow with an explicitly labeled placeholder answer. RAG, prompt tests, richer UX and authentication are not implemented.

## Run locally

Python 3.11+ and Node 20+ recommended. In separate terminals:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. In one browser tab select **Newcomer** and submit a question; in another select **Mentor**, refresh the queue, enter a verified answer and approve; refresh the Newcomer list. Both views use the same SQLite-backed API. API docs: http://localhost:8000/docs.

Tests: `cd backend && pytest -q` and `cd frontend && npm run build`.

## Four independent work areas

| Owner | Area | First implementation PR | Second implementation PR |
|---|---|---|---|
| Aaron (A) | `backend/app/` | Data/API robustness, schema | Review state transitions, persistence tests |
| Wyatt (B) | `backend/app/ai/` (new) | Document retrieval + model adapter | Failure handling, citations, prompt regression tests |
| Joey (C) | `frontend/src/features/newcomer/` (new) | Newcomer question and answer UI | Refresh/status flow, error and accessibility UX |
| Vincent (D) | `frontend/src/features/mentor/` (new) | Mentor queue/review UI | Verified knowledge lookup/reuse |

**Important:** The starter UI is in `frontend/src/App.jsx`. Owners C and D should move their respective view into their own feature folders, rather than both editing App.jsx simultaneously. B's AI implementation should be called through a function behind `POST /api/questions` without changing the response contract. A is responsible for shared API/storage changes.

Before changing a shared contract, discuss it in a PR and update `docs/API_CONTRACT.md`. See `docs/TEAM_WORKFLOW.md` for work and PR rules. Existing CP1 files are intentionally untouched.

## Security and scope

Demo only. Reviewer name is just a string, not a verified login; do not use it as an authorization control. No secrets or real internal project data should be added. Do not report placeholder responses as AI results. Production needs authentication, authorization, private storage, input safeguards and a credible RAG evaluation.
