# Symbol Index

Purpose: identify the stable public symbols future agents should prefer before adding new helpers or changing callers.

Use this file when locating owner modules, editing public behavior, or updating call surfaces.

## `brain_atlas_preprocess/model.py`

- `PROJECT_FILENAME`: canonical project JSON filename.
- `DEFAULT_CROP_SIZE_PX`: default square crop size.
- `ChannelInfo`: channel index, gene, wavelength, label, and JSON serialization.
- `StackFileState`: per-source review state, rotation, crop center, channel metadata, axes, and shape.
- `StackFileState.status`: file-list status authority.
- `ProjectState`: output root, file list, interpolation/canvas/crop settings, JSON round trip.
- `ProjectState.add_or_update_file`: canonical path-based insert/update behavior.
- `ProjectState.get_file`: canonical path-based lookup.
- `ProjectState.save` / `ProjectState.load`: project persistence authority.

## `brain_atlas_preprocess/io.py`

- `StackFormatError`: user-facing input contract failure.
- `StackMetadata`: read-only source metadata and manifest serialization.
- `DEFAULT_TRANSFORM_WORKERS`: default CPU channel-transform worker count for exports.
- `parse_gene_wavelength_pairs`: filename gene/wavelength parser.
- `build_channel_mapping`: channel order and DAPI append authority.
- `read_lsm_metadata`: LSM metadata contract and axes validation.
- `make_file_state`: bridge from source stack to project file state.
- `load_dapi_mip`: DAPI preview maximum-intensity projection.
- `rotate_stack_zyx`: ZYX rotation and dtype preservation.
- `crop_square_zyx`: square crop and zero-padding behavior.
- `export_preprocessed_channels`: canonical export pipeline, output names, NRRD writes, and manifest.
- `export_rotated_channels`: legacy compatibility wrapper for `export_preprocessed_channels`.

## `brain_atlas_preprocess/widgets.py`

- `StackFileList`: list rendering and status color/text application.
- `RotationPreview`: preview rendering, angle updates, crop overlay, and mouse interactions.
- `_rotated_shape_yx`: pure geometry helper used by crop overlay and coordinate mapping.
- `_array_to_pixmap`: preview intensity normalization and grayscale pixmap conversion.

## `brain_atlas_preprocess/app.py`

- `PreviewWorker`: background DAPI preview loading wrapper.
- `PreprocessWorker`: background export wrapper.
- `MainWindow`: UI composition and app workflow orchestration.
- `main`: CLI entrypoint target from `pyproject.toml`.

## Trusted implementation patterns

- Add reusable imaging or persistence logic to owner modules, then call from `app.py`.
- Keep worker classes thin; they call owner functions and report Qt signals.
- Prefer tests for pure functions in `io.py`, `model.py`, and pure widget helpers before GUI-only checks.
