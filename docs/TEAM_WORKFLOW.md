# CP2 team workflow (proposal for team review)

**Deadline:** November 23, 2026. Working prototype must be demonstrable before class.

1. One person owns each feature directory; avoid simultaneous edits to `App.jsx` or `backend/app/main.py`.
2. Start from latest `main`; branch `feature/a-...`, `feature/b-...`, `feature/c-...`, `feature/d-...`.
3. Keep each substantial implementation change as its own PR; do not count documentation-only PRs toward code contribution goals.
4. Every PR states scope, how to test it, evidence, alternatives for significant choices and linked decision log entry.
5. No one merges their own PR without steward review. Follow the course's steward rotation and record handoffs in `DECISIONS.md`.
6. Coordinate all shared API changes through `docs/API_CONTRACT.md` and review them with A + affected owners before implementation.
7. Run backend tests and frontend build locally; CI verifies both on PRs.
8. Two real outside-team user testing sessions are required; record observed behavior, not invented results.
9. On merge day, record the actual integration plan, owners, conflicts, tests and outcomes.
10. Do not alter CP1 history; this scaffold is a new proposal. Once approved, incorporate the genuine decisions into `DECISIONS.md` (existing repo has `DECISION.md`).

## Suggested handoff sequence

- Merge starter scaffold after peer review.
- A establishes baseline API/schema; B implements AI adapter in separate directory.
- C and D start against shared `api.js`, with fixture data only for isolated component development.
- Integrate C/D with real backend, then B's AI; verify in two separate sessions.
- Record prompt regression failures/revisions, two external user tests, PR links, contributor evidence and final demo checklist.

## Boundaries

This is not a completed assignment. Individual team members must contribute actual code and meaningful review; a single agent-generated scaffold does not prove collaboration.
