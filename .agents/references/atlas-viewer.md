# Atlas Viewer Reference

Purpose: compact ownership and contract reference for the registered atlas viewer.

## Files

- `brain_atlas_viewer/app.py`: primary viewer implementation.
- `brain_atlas_viewer/__init__.py`: package marker.
- `scripts/registered_atlas_viewer.py`: compatibility launcher that forwards to `brain_atlas_viewer.app`.
- `tests/test_registered_atlas_viewer.py`: pure helper and image-compositing tests.

## Contracts

- CLI entry point: `brain-atlas-viewer`.
- Compatibility script path: `python scripts/registered_atlas_viewer.py`.
- Manifest filename: `observed_channel_transform_manifest.csv`.
- Viewer serves HTML at `/`, metadata at `/api/metadata`, and RGB composite PNGs at `/api/composite`.
- Viewer serves lazy per-layer histogram metadata at `/api/histogram?layer=<id>`.
- Volumes are read as 3-D NRRD with `index_order="C"` and flipped on Z for display via `orient_volume_for_display`.
- Layer colors are assigned by sorted marker name using `MARKER_PALETTE`.
- Per-layer display windows are parsed from the `windows` query parameter as `layer_id:low_percentile:high_percentile`.
- Display windowing is viewer-only; do not write window settings to NRRD files, manifests, or preprocessing outputs.

## Edit Rules

- Do not import from `brain_atlas_preprocess` for viewer-only display behavior unless there is an explicit shared data contract.
- Preserve manifest column expectations unless intentionally migrating transformed-channel outputs.
- Keep browser UI assets in `PAGE_HTML` until the viewer grows enough to justify static-file packaging.
