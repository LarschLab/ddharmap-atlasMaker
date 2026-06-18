# Data Contracts

Purpose: record canonical input, state, transform, export, and manifest semantics.

Use this file before changing parsing, channel order, crop/rotation behavior, output filenames, NRRD headers, or project JSON.

## Input stack contract

- Input files are Zeiss LSM/TIFF stacks and are read-only.
- `read_lsm_metadata` requires the primary series axes to be `ZCYX`.
- Source shape is interpreted as `(Z, C, Y, X)`.
- Filename gene/wavelength pairs use tokens like `<gene>_<wavelength>`.
- Supported gene wavelengths are `546`, `488`, and `647`; DAPI may appear as `740`/`740nm`.
- Automatic channel mapping prefers LSM metadata channel order from `ScanInformation`, `ChannelWavelength`, and dye/illumination hints.
- Filename tokens supply biological gene names after metadata establishes channel wavelength/order.
- Conflict-free metadata mappings are accepted automatically; filename/metadata conflicts or incomplete metadata require user confirmation.
- Ambiguous stacks may be accepted with a user-provided full channel mapping.

## Project state contract

- Project state is written as `brain_atlas_preprocess_project.json` in the selected output root.
- `ProjectState` version is currently `1`.
- Stable fields include `output_root`, `interpolation`, `canvas_mode`, `crop_size_px`, and `files`.
- Optional `same_fish_confocal` project metadata activates the constrained same-fish confocal export profile only for explicit CLI/project use.
- Per-file stable fields include `path`, `rotation_degrees`, `reviewed`, `crop_center_yx`, `channels`, `bridge_channel_index`, `axes`, `shape`, optional `output_root`, and optional `same_fish_confocal`.
- Per-file `output_root` and `same_fish_confocal` override the project-level values during export; this supports one GUI project containing multiple same-fish confocal fish.
- Crop coordinates are stored as `(y, x)` and serialized as `crop_center_yx`.
- Default crop size is `750 px`.
- Same-fish confocal profile launches default to `1500 px` crop size.

## Transform contract

- Rotation operates on `ZYX` stacks around the `Y/X` plane.
- Stored `rotation_degrees` uses the Qt preview convention; export applies the negated angle so output orientation matches the preview.
- Supported interpolation names are `nearest`, `linear`, and `cubic`.
- Export transforms channels with four CPU worker threads by default; this must remain bit-identical to single-worker SciPy output.
- Zero-degree rotation returns a copy, not the original object.
- Integer dtypes are rounded, clipped, and preserved after rotation.
- Cropping returns shape `(Z, crop_size_px, crop_size_px)`.
- Out-of-bounds crop regions are zero-padded.
- A missing crop center defaults to the current stack center after rotation.

## Export contract

- Export writer is `export_preprocessed_channels`.
- Export directory is `<source_stem>_preprocessed/` under the output root.
- Channel file name is `<source_stem>_<safe_gene>_<wavelength>nm_preprocessed.nrrd`.
- Manifest file name is `preprocess_manifest.json`.
- DAPI QC image file name is `preprocess_qc_dapi_mip.png`.
- Same-fish confocal profile exports to `<output_root>/rbest/` or `<output_root>/rn/` and writes `<fish_id>_<rbest|rN>_channel<index>_<gene>.nrrd`; when a stack has a per-file output root, that root is used for that stack.
- Same-fish confocal profile normalizes channel index `0` to `GCaMP`; default app exports keep inferred/manual channel names.
- Same-fish confocal manifests and QC images are suffixed by round label, e.g. `preprocess_manifest_rbest.json` and `preprocess_qc_r2_mip.png`.
- QC image generation uses the per-stack selected bridge channel.
- Exported channel arrays are processed in memory as `ZYX`, but NRRD files are written with `pynrrd` C-order so external tools interpret header sizes and spatial metadata as `XYZ`.
- NRRD files use raw/uncompressed encoding by default to keep preprocessing runtime practical; gzip remains available only as an explicit writer option.
- NRRD headers carry source path/name, source axes/shape/dtype, `array_axes`, channel metadata, preview rotation, applied export rotation, crop size, crop center, labels, and ITK-readable voxel `space directions` with `microns` space units when spacings are available.
- Manifest carries source metadata, rotation, interpolation, canvas mode, crop size, crop center, selected bridge channel, QC image metadata, and output file list.

## Validation

- Parser, mapping, transform, crop, and export changes: `pytest tests/test_io.py`.
- Project JSON changes: `pytest tests/test_model.py`.
- Export schema changes: inspect `preprocess_manifest.json` and at least one NRRD header from a fixture or mocked export.
- If writer-stage semantics change, verify the first downstream consumer: preview/app display, manifest reader expectations, or registration handoff notes if added later.
