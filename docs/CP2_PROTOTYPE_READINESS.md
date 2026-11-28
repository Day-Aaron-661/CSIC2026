# CP2 prototype — PR evidence and final integration checklist

Updated: 2026-11-28. This checklist reflects observed repository state; unchecked items are **not** claimed as completed.

## 1. Merged implementation PRs

| Area | Owner | Pull requests | Status |
| --- | --- | --- | --- |
| Shared starter API / layout | Wyatt (C) | [#8](https://github.com/Day-Aaron-661/CSIC2026/pull/8), [#9](https://github.com/Day-Aaron-661/CSIC2026/pull/9), [#10](https://github.com/Day-Aaron-661/CSIC2026/pull/10) | Merged |
| A — API / database | Vincent | [#12](https://github.com/Day-Aaron-661/CSIC2026/pull/12), [#13](https://github.com/Day-Aaron-661/CSIC2026/pull/13) | Merged |
| B — retrieval and LLM adapter | Joey | [#15](https://github.com/Day-Aaron-661/CSIC2026/pull/15), [#16](https://github.com/Day-Aaron-661/CSIC2026/pull/16) | Merged |
| C — newcomer citations, request IDs and resilient UI | Wyatt | [#18](https://github.com/Day-Aaron-661/CSIC2026/pull/18) | Merged |
| D — mentor review / knowledge reuse | Aaron | [#11](https://github.com/Day-Aaron-661/CSIC2026/pull/11), [#14](https://github.com/Day-Aaron-661/CSIC2026/pull/14) | Merged |

Owners should choose their own substantive PRs as submission evidence. PRs and review records are different from actual external user tests.

C evidence: [PR #18 Actions run](https://github.com/Day-Aaron-661/CSIC2026/actions/runs/45322003269) — 8 backend tests, 33 browser tests, and production build passed **for that PR revision**. This does not automatically verify the integrated tip of `main`.

## 2. Key integration blocker

At this snapshot, `backend/app/main.py` in `main` still uses `PlaceholderGenerator()`; merging B's adapter did not automatically enable real model calls. Vincent has an **open [PR #24](https://github.com/Day-Aaron-661/CSIC2026/pull/24)** (`feature/a-ai-switch`) which adds `CP2_AI=placeholder|gemini|claude` and B's generator wiring. This is in A's ownership boundary and should be reviewed and merged by the team; this document does **not** merge it or claim that the AI switch is live.

- [x] A/B/C/D's principal feature PRs are merged.
- [ ] A: review/merge [PR #24](https://github.com/Day-Aaron-661/CSIC2026/pull/24) into `main`, with CI and a manual smoke test; avoid overwriting Vincent's branch.
- [ ] Demo operator: configure a **real** API credential locally, never in Git or in a PR. Which provider to use depends on the accepted AI-switch branch.
- [ ] Confirm model access and document retrieval with actual project documents; do not count a placeholder as a model-generated response.
- [ ] Run the end-to-end scenario below and capture real screenshots/results.
- [ ] Collect actual outside-team feedback, review notes and final submission documents (do not fabricate testing results).

Other open documentation PRs: [#20 (PR template)](https://github.com/Day-Aaron-661/CSIC2026/pull/20), [#21 (AI guidelines)](https://github.com/Day-Aaron-661/CSIC2026/pull/21), and [#25 (A decisions)](https://github.com/Day-Aaron-661/CSIC2026/pull/25). Their owners/steward should check review status; these are not described as merged.

## 3. Safe key setup on the demo machine

Gemini's existing adapter reads a local file; `backend/app/ai/gemini_api_keys.txt` is gitignored. **Do not commit, paste in an issue, or post the actual key in chat or group messages.** After the A switch has landed, copy the tracked example into this ignored location and insert the secret locally:

```bash
cp backend/app/ai/gemini_api_keys.example.txt backend/app/ai/gemini_api_keys.txt
# Edit gemini_api_keys.txt locally: one actual key per line (do not commit)
cd backend
CP2_AI=gemini CP2_AI_DOCS_DIR=../docs uvicorn app.main:app --port 8000
```

For Claude, the pending A branch expects `ANTHROPIC_API_KEY` in the process environment and `CP2_AI=claude`; if used, make sure the SDK and account have actual API access. A consumer Claude subscription or login by itself does not establish API billing permission.

For development **without** credentials, use the default placeholder mode and label it truthfully. Never change security settings or upload credentials to make the demo appear complete.

## 4. Smoke-test steps after A's AI integration

1. Start backend and frontend using the README commands. Verify `GET http://localhost:8000/api/health` reports the expected mode. A placeholder health mode means real AI is not active.
2. In a Newcomer tab, ask a question covered by the supplied project documents. Verify an answer or explicit failure state; when `ai_status=ok`, check any `citations` for accuracy.
3. In another browser, review/edit/approve the pending answer as a Mentor. Verify the Newcomer view updates and keeps the original draft distinct from the approved answer.
4. Ask a related follow-up; inspect whether the mentor-approved knowledge is retrieved appropriately, and whether the citations and refusal/error states remain honest.
5. Test no-key/no-context, duplicate submission, and backend-restart cases. Record actual observations rather than assuming tests passed.
6. From the repository root, run `PYTHONPATH=backend python -m pytest -q backend/tests`; from `frontend/` run `npm ci && npx playwright install chromium && npm test && npm run build`. Save the CI URL associated with the final integrated commit.

## 5. What to report in the group

C's work is **already merged**, including source citations, AI status labels and idempotent retry support. The final live-AI integration and provider credential belong to A / the demo operator. Treat PR evidence, integrated CI, external user testing and final deliverables as separate checklist items.
