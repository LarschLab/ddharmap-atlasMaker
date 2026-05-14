# Refactor Rules

Purpose: keep edits scoped to the real ownership boundaries in this repo.

Use this file before cleanup, extraction, migration, or broad behavior changes.

## Owner boundaries

- Put reusable imaging, metadata, transform, and export behavior in `io.py`.
- Put persisted state and JSON compatibility behavior in `model.py`.
- Put preview drawing, file-list rendering, and mouse-coordinate behavior in `widgets.py`.
- Put Qt orchestration, worker wiring, and user workflow sequencing in `app.py`.
- Put package metadata and CLI entrypoint mapping in `pyproject.toml`.

## Edit rules

- Fix bugs at the narrowest owning layer.
- Do not patch `app.py` to compensate for incorrect `io.py` or `model.py` semantics.
- Do not add new local helpers to `app.py` when the logic is reusable preprocessing or state behavior.
- Preserve canonical filenames, JSON field names, stage order, and user-visible workflow unless migration is explicit.
- Keep compatibility wrappers only when callers or tests still depend on them.
- Update `symbol-index.md` when public functions/classes/constants change.
- Update `data-contracts.md` when input, state, transform, export, or manifest semantics change.
- Update `preprocess-stage-map.md` when workflow order or owner boundaries change.

## Tests

- Prefer owner-layer tests over indirect end-to-end tests for pure behavior.
- Use GUI smoke checks for layout, rendering, worker, and dialog changes.
- Run the smallest relevant tests first, then broaden to `pytest` when the change crosses owners.
