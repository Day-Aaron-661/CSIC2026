# CSIC2026 — CP2 Team Scaffold

**Status:** CP2 prototype in progress, **not** a finished AI product. The newcomer workspace supports question submission, shared history, review filters and automatic status updates against the persistent API. The mentor review queue pre-fills each answer with the draft for editing, checks for new questions automatically and approves each question at most once. Answers are still explicitly labeled placeholders; RAG, citations, prompt tests and authentication remain future work.

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
npm ci
npm run dev
```

Open http://localhost:5173. In one browser tab select **Newcomer** and submit a question; in another select **Mentor**. The question appears in the queue within about five seconds (**Refresh queue** is also available); the answer box is pre-filled with the unreviewed draft, so check and edit it, then approve. Return to Newcomer: it refreshes on returning to the visible tab and checks every five seconds while visible. **Refresh answers** is also available. Both views use the same SQLite-backed API. API docs: http://localhost:8000/docs.

## Verify

From the repository root, after installing backend requirements:

```bash
PYTHONPATH=backend python -m pytest -q backend/tests
cd frontend
npm ci
npx playwright install chromium
npm test
npm run build
```

Browser tests start their own frontend and backend with a disposable SQLite database. Stop development servers on ports 5173 and 8000 first. Linux CI uses `npx playwright install --with-deps chromium`. For an already installed Chromium, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable path.

See [Newcomer implementation and handoff](docs/NEWCOMER_HANDOFF.md) for the C scope, design rationale, error behavior and review steps, and [Mentor implementation and handoff](docs/MENTOR_HANDOFF.md) for the D equivalent.

## Four independent work areas

| Owner | Area | First implementation PR | Second implementation PR |
|---|---|---|---|
| Available (A) | `backend/app/` | Data/API robustness, schema | Review state transitions, persistence tests |
| Available (B) | `backend/app/ai/` (new) | Document retrieval + model adapter | Failure handling, citations, prompt regression tests |
| Wyatt (C) | `frontend/src/features/newcomer/` | Newcomer question and answer UI | Refresh/status flow, error and accessibility UX |
| Aaron (D) | `frontend/src/features/mentor/` | Mentor queue/review UI | Verified knowledge lookup/reuse |

**Integration:** C's view is now in `frontend/src/features/newcomer/` with scoped styles and a local data hook. D's view is now in `frontend/src/features/mentor/` with scoped styles and a local data hook; `App.jsx` keeps the shared header, notice and view switch. Coordinate edits to App.jsx. B's AI implementation should be called through a function behind `POST /api/questions` without changing the response contract. A is responsible for shared API/storage changes.

Before changing a shared contract, discuss it in a PR and update `docs/API_CONTRACT.md`. See `docs/TEAM_WORKFLOW.md` for work and PR rules. Existing CP1 files are intentionally untouched.

## Security and scope

Demo only. Reviewer name is just a string, not a verified login; do not use it as an authorization control. No secrets or real internal project data should be added. Do not report placeholder responses as AI results. Production needs authentication, authorization, private storage, input safeguards and a credible RAG evaluation.
