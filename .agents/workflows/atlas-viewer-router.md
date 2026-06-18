# Atlas Viewer Router

Purpose: route work on the registered atlas viewer without pulling preprocessing-app ownership into viewer changes.

Use this file when tasks mention the registered atlas viewer, orthogonal slice viewer, transformed-channel manifest browsing, layer colors, layer gain, composite image serving, or the `brain-atlas-viewer` CLI.

## Read order

1. `coding.md`
2. `.agents/workflows/brain-atlas-router.md`
3. This profile router.
4. `.agents/references/atlas-viewer.md`
5. Owning module: `brain_atlas_viewer/app.py`
6. `tests/test_registered_atlas_viewer.py`

## Ownership guidance

- `brain_atlas_viewer/app.py` owns viewer HTTP serving, manifest loading, NRRD display orientation, compositing, layer state, and CLI parsing.
- `scripts/registered_atlas_viewer.py` is only a compatibility launcher; do not add viewer behavior there.
- Keep preprocessing review/export behavior in `brain_atlas_preprocess/`.
- Viewer tests live in `tests/test_registered_atlas_viewer.py`.
- Change logs live in `.agents/references/recent-changes-atlas-viewer.md`.
- Unresolved follow-up lives in `.agents/references/remaining-work-atlas-viewer.md`.

## Validation

- For pure viewer helpers, run `pytest tests/test_registered_atlas_viewer.py`.
- For import or CLI changes, also run `python3 -m py_compile brain_atlas_viewer/app.py scripts/registered_atlas_viewer.py`.
- Use a browser smoke check when layout or browser interaction changes.
