# Brain Atlas Router

Purpose: dispatch future agent tasks to the smallest workflow profile and reference docs for this repo.

Use this file when any task begins after loading `AGENTS.md` and `coding.md`.

## Read this first

1. Apply `coding.md` baseline behavior.
2. Classify the primary target: data/export semantics, project state, UI orchestration, preview widgets, tests, or documentation.
3. Route to `.agents/workflows/preprocess-app-router.md`.
4. Read the smallest relevant reference before source files.

## Workflow profile dispatch

| Primary target or query content | Profile router |
| --- | --- |
| Desktop app behavior, PySide main window, workers, dialogs, project lifecycle | `.agents/workflows/preprocess-app-router.md` |
| `.lsm` metadata, channel mapping, DAPI preview, rotation, crop, NRRD export, manifest | `.agents/workflows/preprocess-app-router.md` |
| Project JSON schema, file status, crop defaults, saved state | `.agents/workflows/preprocess-app-router.md` |
| Preview rendering, crop overlay, mouse rotation, file-list status colors | `.agents/workflows/preprocess-app-router.md` |
| Tests, validation, packaging, CLI entrypoint | `.agents/workflows/preprocess-app-router.md` |

## Cross-workflow invariants

- Prefer package/module edits over orchestration edits when changing reusable behavior.
- Preserve canonical outputs and stage semantics unless the task explicitly asks for migration.
- Do not treat wrappers or UI callbacks as business-logic authority.
- Fix semantics at the writer stage, not by compensating in downstream consumers.
- Update reference docs when public behavior, output contracts, stage ownership, or public symbols change.
- Append the workflow recent-changes log for meaningful completed changes.
- Update the workflow remaining-work tracker when stopping with unresolved follow-up.

## Compact scaling rule

Keep new entrypoints in the preprocessing-app profile when they share the same `.lsm` review/export semantics and validation surface. Add a new workflow profile only for a genuinely separate pipeline, service, notebook, or artifact family with its own owners, stage map, and validation cadence.
