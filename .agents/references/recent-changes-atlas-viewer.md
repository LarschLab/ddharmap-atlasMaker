# Atlas Viewer Recent Changes

Purpose: append-only log for completed registered atlas viewer changes.

## 2026-06-18 - separate viewer package

Slice goal: Separate the registered atlas viewer from the preprocessing app code and routing.
What changed: Moved the viewer implementation to `brain_atlas_viewer/app.py`, added `brain_atlas_viewer/__init__.py`, added the `brain-atlas-viewer` console entry point, and kept `scripts/registered_atlas_viewer.py` as a compatibility launcher. Tests now import from `brain_atlas_viewer.app`, and `.agents/` routing now has an atlas-viewer workflow profile.
Rerun implications: Prefer `brain-atlas-viewer` or imports from `brain_atlas_viewer.app`; existing direct script launches still work.
Validation performed: `python3 -m pytest tests/test_registered_atlas_viewer.py`; `python3 -m py_compile brain_atlas_viewer/app.py scripts/registered_atlas_viewer.py`; `python3 -m pytest`.
