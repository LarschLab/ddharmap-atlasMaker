# Atlas Viewer Recent Changes

Purpose: append-only log for completed registered atlas viewer changes.

## 2026-06-18 - separate viewer package

Slice goal: Separate the registered atlas viewer from the preprocessing app code and routing.
What changed: Moved the viewer implementation to `brain_atlas_viewer/app.py`, added `brain_atlas_viewer/__init__.py`, added the `brain-atlas-viewer` console entry point, and kept `scripts/registered_atlas_viewer.py` as a compatibility launcher. Tests now import from `brain_atlas_viewer.app`, and `.agents/` routing now has an atlas-viewer workflow profile.
Rerun implications: Prefer `brain-atlas-viewer` or imports from `brain_atlas_viewer.app`; existing direct script launches still work.
Validation performed: `python3 -m pytest tests/test_registered_atlas_viewer.py`; `python3 -m py_compile brain_atlas_viewer/app.py scripts/registered_atlas_viewer.py`; `python3 -m pytest`.

## 2026-06-18 - percentile histogram display window

Slice goal: Replace per-layer gain with display-only percentile windowing and keep the selected-layer controls reachable in the sidebar.
What changed: The registered channel list now caps its visible height to eight rows with its own scroll. The selected-layer settings panel now shows an inline full-stack histogram, low/high percentile controls, and p1-p99.5 reset actions. Per-layer manual windows are encoded in the share URL as `windows=layer_id:low:high`; no NRRD, manifest, or preprocessing output data is changed. The server now exposes `/api/histogram` and uses binned histogram percentiles for manual display windows during `/api/composite`.
Rerun implications: Restart the viewer process to pick up the new HTML/JS. Old gain URL parameters are ignored; new shared links should use `windows`.
Validation performed: `python3 -m pytest tests/test_registered_atlas_viewer.py`; `python3 -m py_compile brain_atlas_viewer/app.py scripts/registered_atlas_viewer.py`; `python3 -m pytest`; in-app browser smoke at `http://127.0.0.1:8766/`, including eight-row channel-list check, histogram visibility, layer selection, manual high-percentile adjustment to `93.3%`, URL `windows` persistence, and screenshot `/tmp/atlas-viewer-window-final.png`.
