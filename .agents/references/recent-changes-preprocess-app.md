# Recent Changes: Preprocess App

Purpose: append completed, meaningful workflow changes for future handoff.

Use this file after changes to preprocessing semantics, project state, UI workflow, exports, tests, or routing docs.

## Entry template

```text
## YYYY-MM-DD - short label

Slice goal:
Passes completed:
What changed:
Rerun implications:
Validation performed:
```

## 2026-05-14 - routed agent workflow bootstrap

Slice goal: Add repo-specific agent routing and reference docs for the preprocessing app.
Passes completed: Inspected README, package metadata, source modules, tests, and setup instructions; created a one-profile routed workflow.
What changed: Added `AGENTS.md`, `coding.md`, workflow routers, semantic references, handoff logs, and remaining-work tracker.
Rerun implications: Future agents should start with `AGENTS.md`, then route through `.agents/workflows/brain-atlas-router.md`.
Validation performed: Documentation sanity check; `pytest` passed with 14 tests.
