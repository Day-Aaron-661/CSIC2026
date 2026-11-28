# CP2 備援方案（獨立分支，不合併）

Branch: `feature/backup-prototype-fallback`  
Base: `main`（建立分支當下的版本）  
Purpose: If A's AI-switch PR [#24](https://github.com/Day-Aaron-661/CSIC2026/pull/24) is not ready for the prototype demo, this branch can enable the already-merged B Gemini RAG implementation without waiting for the Claude integration.

**This is a backup, not a replacement for anyone else's work. Keep it unmerged unless the team decides to use it.**

## Ready now

- Newcomer question -> stored AI draft -> Mentor review -> Newcomer sees approved answer, using the existing frontend and SQLite API.
- `CP2_AI=gemini` selects B's `RagGenerator` with project document retrieval and mentor-approved answers as a knowledge source. AI citations are persisted in the existing response contract.
- `CP2_AI=claude` reuses Vincent's Claude adapter from [A/PR #24](https://github.com/Day-Aaron-661/CSIC2026/pull/24), plugged into exactly the same B RAG pipeline. The adapter and its unit tests were copied into this backup branch so it remains usable independently of that unmerged PR.
- `CP2_AI=placeholder` is still the default and does not require API credentials. Placeholder text is **not** an AI-generated answer.
- `GET /api/health` reports which generator is **selected** (`placeholder`, `gemini`, or `custom`). The selected mode alone does not prove an actual provider request succeeded.
- Missing keys, unavailable model, or missing relevant documents produce `ai_status=failed` instead of a fabricated model answer. The question is still sent to Mentor for review.
- Invalid `CP2_AI` mode and non-positive `CP2_AI_TIMEOUT` fail clearly at startup.
- No API key or internal document was committed. Nothing was pushed to `main`.

## Preflight before the demo

From the repo root, after installing `backend/requirements.txt`, check the intended model without contacting it:

```bash
python3 scripts/backup_preflight.py --mode placeholder
python3 scripts/backup_preflight.py --mode gemini --docs docs
# or when using Claude and its key is configured in your environment:
python3 scripts/backup_preflight.py --mode claude --docs docs
```

If the check reports `NEEDS SETUP`, fix that before the demo; it never prints API keys. Passing preflight **only checks local setup**, not real provider model access. After switching the backend to the selected mode, still send an actual question and verify `ai_status=ok` and meaningful citations. For a custom key path, set `CP2_GEMINI_KEYS_FILE` consistently for both preflight and backend.

## Start with no external account (placeholder demo)

```bash
git fetch origin
git switch --track origin/feature/backup-prototype-fallback
python3 -m pip install -r backend/requirements.txt
cd backend
CP2_AI=placeholder uvicorn app.main:app --port 8000
```

In a second terminal from repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. The two-role Newcomer/Mentor demo works without key, but AI answers are clearly labeled placeholders.

## Enable real Gemini AI for the demo

First, **locally** create an ignored key file (never commit or paste its contents into PRs/LINE):

```bash
cp backend/app/ai/gemini_api_keys.example.txt backend/app/ai/gemini_api_keys.txt
# Edit backend/app/ai/gemini_api_keys.txt on your own device.
# Put your valid Google Gemini API key on its own non-comment line.
```

Start the API from `backend/` with project docs indexed:

```bash
CP2_AI=gemini CP2_AI_DOCS_DIR=../docs uvicorn app.main:app --port 8000
```

The actual Gemini model in `backend/app/ai/llm.py` must be available to **your** API account. If the default is unsupported, set `CP2_GEMINI_MODEL` to a currently supported model ID that you have verified in Google AI Studio / its API docs. Do not infer that a green CI run proves external model availability. This branch is an integration backup; it does not provision or verify paid/provider API credentials.

Check the selected mode:

```bash
curl -s http://localhost:8000/api/health
```

It should include `"mode":"gemini"`. Then submit a question covered by `docs/` and inspect `ai_status` and `citations`; `ai_status=ok` with meaningful, checkable citations is the evidence of a generated draft. If `ai_status=failed`, inspect the short `ai_error` category and fix the docs/key/model setup. Do not present a failed draft as a working AI model.

For LAN testing, update both `CP2_CORS_ORIGINS` (real frontend origins) and `VITE_API_URL` (API address reachable by the **client**). `localhost` on someone's phone does not point to your laptop.

## Claude alternative (also available in the backup)

The backup includes `CP2_AI=claude` by reusing A's work in [PR #24](https://github.com/Day-Aaron-661/CSIC2026/pull/24); its `claude_llm.py`, dependency and offline tests were brought here, not reimplemented from scratch.

Install dependencies using `python3 -m pip install -r backend/requirements.txt`, set **your own** Anthropic API credential in the demo machine's environment (do not commit), then start from `backend/`:

```bash
CP2_AI=claude CP2_AI_DOCS_DIR=../docs uvicorn app.main:app --port 8000
```

The adapter reads `ANTHROPIC_API_KEY` (or supported SDK credentials). A consumer subscription alone does not guarantee Anthropic API access. The optional `CP2_CLAUDE_MODEL` must be one available to your API account. All tests mock provider calls; a real-key smoke test is still necessary. If an SDK experimental parameter is unavailable for your account, the request will correctly fail rather than manufacture an answer; Gemini can be used as the alternative.

## Tests / verification

```bash
PYTHONPATH=backend python -m pytest -q backend/tests
cd frontend
npm ci
npx playwright install chromium
npm test
npm run build
```

The new `backend/tests/test_backup_prototype.py` and reused/adapted A's `backend/tests/test_backup_ai_switch.py` use **fake provider calls** and a disposable SQLite file to verify real B retriever/adapter wiring, source citations, idempotent retry, Mentor approval, subsequent reuse of approved knowledge, and failure states. Tests never contact the provider. The existing browser tests cover Newcomer/Mentor interaction with a disposable backend. Neither replaces a real key-backed smoke test on the demo machine.

## Cutover if needed

1. Keep A's [PR #24](https://github.com/Day-Aaron-661/CSIC2026/pull/24) as the preferred team integration.
2. If that PR cannot land in time, choose this backup branch on the **demo machine** and run the commands above. No merge is required just to demonstrate it.
3. Only if the team/steward agrees to merge, review its diff against the **latest** `main`. Both implementations edit `backend/app/main.py` and `backend/app/routes.py`, so **do not blindly merge or cherry-pick both**; choose one integration strategy. This backup intentionally reuses A's Claude adapter and B's existing RAG pipeline, and credits those upstream contributions.
4. Do not store actual secrets or private lab data in Git, public screenshots, or PR comments.

### What this backup does *not* guarantee

- No real Gemini API key has been supplied or verified here.
- No live Gemini response was tested by CI. Offline tests use controlled model stubs.
- No authentication/authorization is added; use a safe demo environment only.
- PR template, user-testing evidence, final submission files, and team decisions still require their actual owners.
- Claude is available through the copied *in-progress* A adapter. Its live API access is unverified until the demo operator supplies valid credentials and confirms a successful request.
