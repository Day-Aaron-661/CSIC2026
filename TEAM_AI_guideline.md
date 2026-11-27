# What AI tools we plan to use, and what we will use each for
1. We will use Claude Code, through the project provided by the course team, for generating boilerplate CRUD endpoints and first-draft unit tests — not for anything touching authentication or payment logic, which a human writes from scratch.
2. We will use GitHub Copilot's inline autocomplete while typing — not as a substitute for writing the PR description or DECISIONS.md entry ourselves.

# How we will document AI interactions
1. Every prompt used to generate code that ends up in the repo goes in the prompt engineering log: the prompt text, the model used, and what we kept vs. changed.
2. One-off debugging questions or syntax lookups don't need a log entry — only prompts that produced code, text, or decisions that ended up in the repo.
3. Every PR must explicitly state where AI was involved and how much: list the AI-assisted blocks (files, functions, or document sections) and the approximate proportion of the PR that came from AI. If AI was not involved, the PR says so.

# How we will handle disagreements about AI output quality
1. If two engineers disagree about whether AI-generated code is good enough to merge, the code steward has final say — not whoever wrote the prompt, and not whoever has more experience.
2. Evidence required before a merge decision: passes the existing test suite, passes the PR review checklist, includes the AI involvement statement from rule 3 above, and can be explained by someone other than whoever generated it.

# Change history
| # | Old rule (Week 3 wording) | New rule (checkable from a PR) | Evidence that made us change it |
|---|---|---|---|
| 1 | None | PRs must explicitly list the proportion and blocks of AI involvement | During our review, we found that we never required PRs to show how much of their content came from AI |
| 2 | We will use Claude Sonnet (via the API) for generating boilerplate CRUD endpoints and first-draft unit tests | We use Claude Code for this task | We now use the Claude Code project provided by the course team |