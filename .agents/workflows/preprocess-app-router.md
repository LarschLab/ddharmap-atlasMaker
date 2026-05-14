# Preprocess App Router

Purpose: route work on the Brain Atlas desktop preprocessing app by semantic owner before opening source files.

Use this file when tasks mention the PySide app, `.lsm` stacks, project state, preview rotation/crop, channel export, manifests, tests, or the `brain-atlas-preprocess` CLI.

## Read order

1. `coding.md`
2. `.agents/workflows/brain-atlas-router.md`
3. This profile router.
4. The smallest relevant reference from the routing table.
5. Owning module: `io.py`, `model.py`, `widgets.py`, or `app.py`.
6. Targeted tests under `tests/`.
7. Broader app regions only when the owning module does not answer the question.

## Task routing table

| Query content | Read first | Primary owner | Validation |
| --- | --- | --- | --- |
| Filename gene parsing, wavelength order, DAPI channel, LSM axes, metadata errors | `.agents/references/data-contracts.md` | `brain_atlas_preprocess/io.py` | `pytest tests/test_io.py` |
| DAPI maximum-intensity preview loading | `.agents/references/preprocess-stage-map.md` | `brain_atlas_preprocess/io.py`, then `app.py` worker wiring | `pytest tests/test_io.py`; GUI smoke if worker behavior changes |
| Rotation, interpolation, canvas expansion, crop geometry, dtype preservation | `.agents/references/data-contracts.md` | `brain_atlas_preprocess/io.py` | `pytest tests/test_io.py` |
| NRRD export paths, headers, manifest schema, output folder naming | `.agents/references/data-contracts.md` | `brain_atlas_preprocess/io.py` | `pytest tests/test_io.py`; inspect exported fixture output when behavior changes |
| Project JSON, crop-size default, reviewed status, file identity | `.agents/references/symbol-index.md` | `brain_atlas_preprocess/model.py` | `pytest tests/test_model.py` |
| Main window buttons, dialogs, save/open project, preprocess progress, thread lifecycle | `.agents/references/preprocess-stage-map.md` | `brain_atlas_preprocess/app.py` | targeted tests if available; otherwise `brain-atlas-preprocess` GUI smoke |
| Preview drawing, crop overlay, angle display, mouse interaction mapping | `.agents/references/ui-interaction-policy.md` | `brain_atlas_preprocess/widgets.py` | GUI smoke with rendered preview; add tests for pure geometry helpers where possible |
| CLI entrypoint or package metadata | `.agents/references/symbol-index.md` | `pyproject.toml`, `brain_atlas_preprocess/app.py` | `brain-atlas-preprocess` launches; `pytest` |
| Refactor, cleanup, ownership split, migration continuation | `.agents/references/refactor-rules.md`, then `.agents/references/refactor-loop-policy.md` | narrowest owning module | smallest relevant tests before and after |
| Prior work or handoff context | `.agents/references/recent-changes.md`, `.agents/references/remaining-work.md` | relevant workflow log/tracker | verify listed checks still match the task |

## Ownership guidance

- `io.py` owns imaging file contracts, preprocessing transforms, exports, and manifest/header semantics.
- `model.py` owns persisted project state, dataclass serialization, review status, and project filename constants.
- `widgets.py` owns reusable Qt widgets, rendering, preview normalization, and mouse-to-image coordinate behavior.
- `app.py` owns UI composition, signal/slot orchestration, background workers, dialogs, status messages, and user workflow sequencing.
- Tests own regression evidence; prefer adding tests at the owner layer over indirect UI assertions.
- Change logs live in `.agents/references/recent-changes-preprocess-app.md`.
- Unresolved follow-up lives in `.agents/references/remaining-work-preprocess-app.md`.
