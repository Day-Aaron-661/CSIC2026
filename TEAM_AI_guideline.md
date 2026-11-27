# What AI tools we plan to use, and what we will use each for
1. We will use Claude Sonnet (via the API) for generating boilerplate CRUD endpoints and first-draft unit tests — not for anything touching authentication or payment logic, which a human writes from scratch.
2. We will use GitHub Copilot's inline autocomplete while typing — not as a substitute for writing the PR description or DECISIONS.md entry ourselves.

# How we will document AI interactions
1. Every prompt used to generate code that ends up in the repo goes in the prompt engineering log: the prompt text, the model used, and what we kept vs. changed.
2. One-off debugging questions or syntax lookups don't need a log entry — only prompts that produced code, text, or decisions that ended up in the repo.

# How we will handle disagreements about AI output quality
1. If two engineers disagree about whether AI-generated code is good enough to merge, the code steward has final say — not whoever wrote the prompt, and not whoever has more experience.
2. Evidence required before a merge decision: passes the existing test suite, passes the PR review checklist, and can be explained by someone other than whoever generated it.