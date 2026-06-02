# Symbol Index

Purpose: identify the stable public symbols future agents should prefer before adding new helpers or changing callers.

Use this file when locating owner modules, editing public behavior, or updating call surfaces.

## `brain_atlas_preprocess/model.py`

- `PROJECT_FILENAME`: canonical project JSON filename.
- `DEFAULT_CROP_SIZE_PX`: default square crop size.
- `SAME_FISH_CONFOCAL_PROFILE`: CLI/project identifier for constrained same-fish confocal exports.
- `SAME_FISH_CONFOCAL_CROP_SIZE_PX`: enforced crop default for same-fish confocal launches.
- `ChannelInfo`: channel index, gene, wavelength, label, and JSON serialization.
- `SameFishConfocalProfile`: optional project export profile with fish ID, `rbest`/`rn` role, and explicit `rn` round number.
- `StackFileState`: per-source review state, rotation, crop center, channel metadata, selected bridge channel, axes, shape, optional per-file output root, and optional per-file same-fish confocal profile.
- `StackFileState.status`: file-list status authority.
- `ProjectState`: output root, file list, interpolation/canvas/crop settings, optional project-level same-fish confocal profile, per-file override preservation, JSON round trip.
- `ProjectState.add_or_update_file`: canonical path-based insert/update behavior.
- `ProjectState.get_file`: canonical path-based lookup.
- `ProjectState.remove_files`: canonical path-based removal behavior.
- `ProjectState.save` / `ProjectState.load`: project persistence authority.

## `brain_atlas_preprocess/io.py`

- `StackFormatError`: user-facing input contract failure.
- `StackMetadata`: read-only source metadata and manifest serialization.
- `ChannelMappingInference`: inferred channel labels plus confirmation messages.
- `DEFAULT_TRANSFORM_WORKERS`: default CPU channel-transform worker count for exports.
- `parse_gene_wavelength_pairs`: filename gene/wavelength parser.
- `infer_channel_mapping`: LSM metadata channel-order inference and filename gene-label merge.
- `build_channel_mapping`: legacy strict filename channel order and DAPI append authority.
- `build_channel_mapping_suggestions`: prefilled labels for ambiguous/manual channel mapping.
- `validate_channel_mapping`: full channel mapping validation for manual labels.
- `read_lsm_metadata`: LSM metadata contract and axes validation.
- `make_file_state`: bridge from source stack to project file state.
- `load_channel_mip` / `load_channel_mips` / `load_labeled_channel_mip`: channel preview maximum-intensity projection.
- `load_dapi_mip`: compatibility wrapper for DAPI preview maximum-intensity projection.
- `rotate_stack_zyx`: ZYX rotation and dtype preservation.
- `crop_square_zyx`: square crop and zero-padding behavior.
- `export_preprocessed_channels`: canonical export pipeline, optional same-fish confocal output names, NRRD writes, and manifest.
- `export_rotated_channels`: legacy compatibility wrapper for `export_preprocessed_channels`.

## `brain_atlas_preprocess/widgets.py`

- `StackFileList`: list rendering, status color/text application, multi-selection, and stack drop/delete signals.
- `ChannelThumbnail`: compact non-interactive channel preview for mapping dialogs.
- `RotationPreview`: preview rendering, angle updates, crop overlay, and mouse interactions.
- `_rotated_shape_yx`: pure geometry helper used by crop overlay and coordinate mapping.
- `_array_to_pixmap`: preview intensity normalization and grayscale pixmap conversion.

## `brain_atlas_preprocess/app.py`

- `PreviewWorker`: background channel preview loading wrapper.
- `PreprocessWorker`: background export wrapper.
- `MainWindow`: UI composition and app workflow orchestration.
- `main`: CLI entrypoint target from `pyproject.toml`.

## Trusted implementation patterns

- Add reusable imaging or persistence logic to owner modules, then call from `app.py`.
- Keep worker classes thin; they call owner functions and report Qt signals.
- Prefer tests for pure functions in `io.py`, `model.py`, and pure widget helpers before GUI-only checks.
