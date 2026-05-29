# Agent Entrypoint

This repo uses a routed instruction system under `.agents/`. Start here, load the shared coding baseline, then follow the workflow router to the smallest relevant repo-specific reference before opening source files.

## Large Log Routing

Do not open workflow-specific `recent-changes-*.md` logs wholesale just to find context. First query them with:

```bash
python3 /Users/ddharmap/gitRepo/agenticWorkflow/scripts/query_recent_changes.py --repo <repo-name> --query <term> --limit 5
```

Open the full log only when the compact query shows that exact entries are needed.

## Answer-Direct Route

If the user asks a general question, asks for a short explanation, or provides enough context in the prompt to answer without repo/vault state, answer directly and do not load routers, references, indexes, logs, or templates.

Use repo/vault routing only when the request requires local files, durable updates, validation, provenance, or project-specific workflow rules.

## Required startup order

1. Open `coding.md` for baseline coding behavior.
2. Open `.agents/workflows/brain-atlas-router.md`.
3. Follow its dispatch table to the workflow profile router.
4. Read the smallest relevant reference doc under `.agents/references/`.
5. Open stage maps or symbol indexes only if needed.
6. Open owning modules before broad UI or workflow files.
7. Open large app regions only when owner-module context is insufficient.

## Non-negotiable repo rules

- Keep reusable preprocessing and data semantics in `brain_atlas_preprocess/io.py` or `brain_atlas_preprocess/model.py`.
- Keep `brain_atlas_preprocess/app.py` focused on Qt orchestration, worker wiring, dialogs, and project lifecycle.
- Keep preview rendering and mouse interaction behavior in `brain_atlas_preprocess/widgets.py`.
- Preserve canonical output names, JSON field names, channel ordering, and crop coordinate semantics unless intentionally migrating them.
- Validate after edits with the smallest relevant test or smoke check; do not claim success from static reasoning alone.
- Treat `coding.md` as required baseline behavior before applying these repo-specific rules.

## Reference files

- `.agents/workflows/brain-atlas-router.md`: top-level workflow dispatcher.
- `.agents/workflows/preprocess-app-router.md`: task router for the desktop preprocessing app.
- `.agents/references/preprocess-stage-map.md`: end-to-end app and export stages.
- `.agents/references/symbol-index.md`: compact public symbol ownership index.
- `.agents/references/data-contracts.md`: file, metadata, export, manifest, and project-state contracts.
- `.agents/references/ui-interaction-policy.md`: GUI rendering and interaction ownership rules.
- `.agents/references/refactor-rules.md`: repo-specific edit boundaries.
- `.agents/references/refactor-loop-policy.md`: working-unit, validation, and handoff policy.
- `.agents/references/current-state.md`: current caveats and unsettled context.
- `.agents/references/recent-changes.md`: index for workflow change logs.
- `.agents/references/remaining-work.md`: index for unresolved-work trackers.

## Scope note

Keep this file short. Workflow-specific details live under `.agents/`, while generic coding behavior lives in `coding.md`.
