# Preprocess Stage Map

Purpose: describe the ordered desktop-app workflow and the owner for each stage.

Use this file when changing app workflow, worker sequencing, preview loading, export behavior, or validation expectations.

## End-to-end stages

1. Select input stacks.
   - UI owner: `MainWindow._add_files` in `brain_atlas_preprocess/app.py`.
   - Data owner: `make_file_state`, `read_lsm_metadata`, `build_channel_mapping` in `brain_atlas_preprocess/io.py`.
   - Output: `StackFileState` entries added to `ProjectState.files`.

2. Select output root.
   - UI owner: `MainWindow._select_output_root`.
   - State owner: `ProjectState.output_root` and `ProjectState.save` in `model.py`.
   - Output: `brain_atlas_preprocess_project.json` under the output root.

3. Load DAPI preview.
   - Orchestration owner: `PreviewWorker` and `MainWindow._start_preview_worker`.
   - Data owner: `load_dapi_mip` in `io.py`.
   - Rendering owner: `RotationPreview.set_image` in `widgets.py`.
   - Output: in-memory preview cache keyed by file path.

4. Review stack rotation and crop.
   - Interaction owner: `RotationPreview` mouse handlers and crop overlay methods.
   - State owner: `StackFileState.rotation_degrees`, `reviewed`, and `crop_center_yx`.
   - Output: project JSON updates when an output root exists.

5. Preprocess selected project files.
   - Orchestration owner: `PreprocessWorker` and `MainWindow._preprocess`.
   - Data/export owner: `export_preprocessed_channels` in `io.py`.
   - Output: one `<source_stem>_preprocessed/` folder per source.

6. Write canonical exports.
   - Writer owner: `export_preprocessed_channels`, `_write_stack_nrrd`, and manifest construction in `io.py`.
   - Outputs: per-channel `.nrrd` stacks and `preprocess_manifest.json`.

## Key outputs by stage

- Project state: `brain_atlas_preprocess_project.json`.
- Preview data: DAPI maximum-intensity projection, not persisted.
- Export folder: `<source_stem>_preprocessed/`.
- Export files: `<source_stem>_<gene>_<wavelength>nm_preprocessed.nrrd`.
- Export manifest: `preprocess_manifest.json`.

## Concept ownership

- File/metadata/channel contracts: `io.py`.
- Persisted project state: `model.py`.
- Workflow orchestration: `app.py`.
- Rendering and direct interaction: `widgets.py`.

## Navigation notes

Use `data-contracts.md` before editing output schema, channel semantics, or crop/rotation behavior. Use `ui-interaction-policy.md` before changing preview rendering or mouse mapping. Use `symbol-index.md` when looking for stable public surfaces.
