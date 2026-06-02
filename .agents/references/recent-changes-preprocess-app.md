# Recent Changes: Preprocess App

Purpose: append completed, meaningful workflow changes for future handoff.

Use this file after changes to preprocessing semantics, project state, UI workflow, exports, tests, or routing docs.

## Entry template

```text
## YYYY-MM-DD - short label

Slice goal:
Passes completed:
What changed:
Rerun implications:
Validation performed:
```

## 2026-05-30 - registered atlas viewer marker colors

Slice goal: Improve the registered atlas viewer so markers sharing acquisition wavelengths remain visually distinguishable, and correct inverted Z display orientation.
Passes completed: Added marker-level palette assignment, increased the default simultaneous layer cap to the 24-marker palette, flipped loaded NRRD volumes along Z for display, and tightened small sidebar layout issues found during browser QA.
What changed: `scripts/registered_atlas_viewer.py` now colors by marker instead of wavelength, exposes the layer display cap in metadata/status text, applies the same Z flip to marker volumes and the fixed DAPI reference, and uses a shorter search placeholder with taller layer rows.
Rerun implications: Restart the viewer process to pick up the new palette and orientation; no registered NRRD files or manifests need regeneration.
Validation performed: `pytest tests/test_registered_atlas_viewer.py`; `python3 -m py_compile scripts/registered_atlas_viewer.py`; `pytest`; in-app browser smoke at `http://127.0.0.1:8765/` selecting eight markers, toggling MIP/slice views, and clicking the axial canvas.

## 2026-05-26 - fluorescence preview LUTs

Slice goal: Tint single-channel previews with expected fluorescence colors instead of showing every channel in grayscale.
Passes completed: Added wavelength-aware preview pixmap rendering and threaded the selected channel wavelength through main previews and channel-mapping thumbnails.
What changed: `488 nm` previews render green, `546 nm` previews render yellow, and `647 nm` previews render red; other wavelengths remain grayscale. The change is display-only and does not alter loaded arrays, exports, project state, or channel ordering.
Rerun implications: Existing projects open normally; previews now use fluorescence colors when channel wavelengths are known.
Validation performed: `QT_QPA_PLATFORM=offscreen pytest tests/test_widgets.py -q`; `pytest tests/test_io.py tests/test_model.py -q`; rendered `/tmp/brain_atlas_lut_546.png` and `/tmp/brain_atlas_lut_647.png` from `/Users/ddharmap/dataProcessing/20260525_brainMapping_stitched/20260320_f02_cort_546_gad2_647_Stitch.lsm`.

## 2026-05-26 - NRRD microns unit token

Slice goal: Make preprocessed NRRD spacing metadata compatible with registration tools that distinguish `um` from `microns`.
Passes completed: Changed the exporter space-unit token and added a repair utility for existing output folders.
What changed: NRRD exports now write `space units` as `microns` while preserving micrometer-scale `space directions`. Added `scripts/repair_nrrd_space_units.py` to rewrite existing NRRD headers in place without recomputing image data.
Rerun implications: New GUI exports use `microns`; existing preprocessed folders can be repaired with the script or regenerated.
Validation performed: `python -m py_compile scripts/repair_nrrd_space_units.py`; `pytest tests/test_io.py tests/test_repair_nrrd_space_units.py -q`; `pytest -q`; temporary-copy repair validation against `/Users/ddharmap/dataProcessing/20260525_brainMapping_preprocessed/20260320_f01_cort_546_gad2_647_Stitch_preprocessed`.

## 2026-05-25 - persisted bridge channel selection

Slice goal: Support stacks with variable channel counts and nonstandard bridge-channel positions during review and export.
Passes completed: Added per-stack bridge-channel state, manual channel mapping validation, explicit channel preview loading, channel/stack keyboard shortcuts, and bridge-based QC export.
What changed: Project JSON now persists `bridge_channel_index`; ambiguous stacks can be accepted through a full channel-label dialog; preview cache keys include channel index; `a`/`d` cycle channels and `q`/`e` cycle stacks; manifest/QC metadata records the selected bridge channel.
Rerun implications: Existing projects load with DAPI 740 as the bridge when present, otherwise the last channel. Regenerate exports when bridge-channel QC identity matters.
Validation performed: `pytest tests/test_model.py tests/test_io.py`; `pytest`; offscreen Qt screenshot `/tmp/brain_atlas_bridge_ui.png`; local smoke against `/Users/ddharmap/dataProcessing/20260525_brainMapping_stitched`.

## 2026-05-25 - channel mapping dialog previews

Slice goal: Make manual channel mapping usable by showing the image content for each channel being labeled.
Passes completed: Added one-pass all-channel MIP loading, a compact thumbnail widget, and inline channel thumbnails in the mapping dialog.
What changed: `ChannelMappingDialog` now shows one preview thumbnail per channel row while preserving editable gene/wavelength fields and bridge selection.
Rerun implications: Manual channel mapping opens after loading per-channel MIPs; if preview loading fails, labels can still be edited with placeholder thumbnails.
Validation performed: `pytest tests/test_io.py tests/test_model.py`; offscreen Qt screenshot `/tmp/brain_atlas_channel_mapping_dialog.png`.

## 2026-05-14 - routed agent workflow bootstrap

Slice goal: Add repo-specific agent routing and reference docs for the preprocessing app.
Passes completed: Inspected README, package metadata, source modules, tests, and setup instructions; created a one-profile routed workflow.
What changed: Added `AGENTS.md`, `coding.md`, workflow routers, semantic references, handoff logs, and remaining-work tracker.
Rerun implications: Future agents should start with `AGENTS.md`, then route through `.agents/workflows/brain-atlas-router.md`.
Validation performed: Documentation sanity check; `pytest` passed with 14 tests.

## 2026-05-14 - NRRD external axis order

Slice goal: Fix exported NRRD stacks appearing with a swapped Z axis in FIJI/external readers.
Passes completed: Inspected `pynrrd` read/write index-order semantics; tightened the export regression to use unequal Z/Y/X dimensions.
What changed: `_write_stack_nrrd` now writes NumPy `ZYX` stacks with `index_order="C"`, records `array_axes: ZYX`, labels NRRD header axes as `x/y/z`, and writes NRRD spacings in `XYZ` header order.
Rerun implications: Existing exports written before this change may still open with swapped axes in FIJI; regenerate those NRRD outputs with the updated exporter.
Validation performed: `pytest tests/test_io.py` passed with 11 tests.

## 2026-05-15 - ITK-readable rotated NRRD export

Slice goal: Ensure rotated NRRD exports are readable by ITK/SimpleITK when voxel spacing metadata is present.
Passes completed: Reproduced synthetic rotated export read-back with `pynrrd` C-order and SimpleITK; isolated invalid `space units` without valid space directions.
What changed: `_write_stack_nrrd` now writes voxel metadata as `space dimension`, diagonal `space directions`, and `space units` instead of bare `spacings` plus units. Added a synthetic asymmetric 90-degree export regression that verifies SimpleITK reads the rotated `ZYX` array and expected `XYZ` spacing.
Rerun implications: Existing NRRD exports with voxel metadata should be regenerated so ITK/SimpleITK readers can load them.
Validation performed: `pytest tests/test_io.py -q` passed.

## 2026-05-15 - DAPI export QC image

Slice goal: Make export rotation visually unambiguous when reviewing outputs in FIJI or other image viewers.
Passes completed: Strengthened the synthetic rotated export test with an asymmetric DAPI stack, default `pynrrd` axis-order assertion, unrotated-crop negative assertion, SimpleITK read-back, and PNG QC validation.
What changed: `export_preprocessed_channels` now writes `preprocess_qc_dapi_mip.png`, a normalized max projection of the final rotated/cropped DAPI stack, and records it under manifest `qc`.
Rerun implications: Regenerate existing output folders to get the QC PNG and updated manifest metadata.
Validation performed: `pytest tests/test_io.py -q`; manual PNG artifact inspection from a temporary synthetic export.

## 2026-05-15 - preview/export rotation sign

Slice goal: Make exported rotation match the orientation shown in the Qt preview.
Passes completed: Compared Qt positive-angle visual direction with SciPy `ndimage.rotate`; confirmed the conventions are opposite in image coordinates.
What changed: Added a preview-to-export angle adapter so `rotation_degrees` stays as the user-visible preview angle while export applies the negated angle. Manifest, NRRD headers, and QC metadata now include `applied_rotation_degrees`.
Rerun implications: Existing output folders should be regenerated; existing project JSON angles do not need migration.
Validation performed: `pytest tests/test_io.py -q`; `pytest -q`; temporary asymmetric QC PNG inspection.

## 2026-05-15 - NRRD export integrity audit

Slice goal: Explain channel file-size differences and guard against accidental data loss in compressed NRRD exports.
Passes completed: Inspected a real rotated/cropped sample output, decoded NRRD headers and arrays, and recomputed outputs from the source `.lsm`.
What changed: Added exporter integrity tests for gzip size differences, decoded voxel equality, transform-induced value changes, and opt-in real-sample source parity. Added `scripts/diagnose_nrrd_export.py` for per-channel size/stat/checksum/source-verification reports.
Rerun implications: Existing gzip-compressed outputs can have different file sizes even with identical decoded shapes and raw byte counts; use the diagnostic script with `--verify-source` when auditing a real output folder.
Validation performed: `pytest tests/test_export_integrity.py tests/test_io.py`; `BRAIN_ATLAS_SAMPLE_OUTPUT_DIR=/Users/ddharmap/dataProcessing/testOutput/20260311_f02_tph2_488_optb_546_gbx2_647_Stitch_preprocessed pytest tests/test_export_integrity.py`; `python scripts/diagnose_nrrd_export.py /Users/ddharmap/dataProcessing/testOutput/20260311_f02_tph2_488_optb_546_gbx2_647_Stitch_preprocessed --verify-source`.

## 2026-05-15 - preprocessing speed benchmark tooling

Slice goal: Measure preprocessing speed and memory tradeoffs before changing production behavior.
Passes completed: Added raw NRRD writer controls, implemented a subprocess-isolated benchmark runner, tested synthetic smoke behavior, and ran one real-stack benchmark repeat.
What changed: `export_preprocessed_channels` and `_write_stack_nrrd` now accept explicit NRRD encoding/compression settings. Added `scripts/benchmark_preprocess.py` with loop, batched, raw, gzip, and fused rotate/crop variants plus phase timing, output validation, output size, and peak RSS reporting.
Rerun implications: Raw benchmark variants are much faster but write larger NRRD files; fused rotate/crop remains experimental and is rejected under bit-identical correctness.
Validation performed: `pytest tests/test_io.py tests/test_benchmark_preprocess.py -q`; `python -m py_compile scripts/benchmark_preprocess.py`; `python scripts/benchmark_preprocess.py --repeats 1`.

## 2026-05-15 - raw NRRD default export

Slice goal: Use the benchmark result to speed up production preprocessing.
Passes completed: Switched the default NRRD writer encoding from gzip to raw while preserving explicit gzip support for diagnostics and benchmarks.
What changed: `export_preprocessed_channels` now writes uncompressed NRRD files by default. The data contract records raw encoding as canonical; gzip-specific tests opt into gzip explicitly.
Rerun implications: New preprocessing outputs will be larger but substantially faster to write. Existing gzip-compressed output folders remain readable.
Validation performed: `pytest tests/test_io.py tests/test_export_integrity.py tests/test_benchmark_preprocess.py -q`; `pytest -q`.

## 2026-05-15 - threaded CPU and MPS benchmark variants

Slice goal: Measure remaining transform acceleration options after raw NRRD removed the write bottleneck.
Passes completed: Added channel-threaded CPU variants and an experimental PyTorch MPS fused rotate/crop variant with tolerance reporting and peak MPS memory sampling.
What changed: `scripts/benchmark_preprocess.py` now benchmarks `loop_raw_threads_1/2/4` exactly against `loop_raw` and can include `mps_fused_raw` with `--include-mps`. Benchmark summaries now use `loop_raw` as the speedup baseline and include MPS memory fields.
Rerun implications: CPU thread variants are exact candidate optimizations; MPS is faster but remains non-bit-identical and should not be promoted without scientific tolerance review.
Validation performed: `pytest tests/test_benchmark_preprocess.py -q`; `python -m py_compile scripts/benchmark_preprocess.py`; `python scripts/benchmark_preprocess.py --repeats 1 --variants loop_raw loop_raw_threads_1 loop_raw_threads_2 loop_raw_threads_4 --include-mps`; `pytest -q`.

## 2026-05-15 - preprocessing benchmark report

Slice goal: Preserve benchmark conclusions and the open MPS/ANTs registration question for later group review.
Passes completed: Summarized raw CPU, threaded CPU, and MPS benchmark results from the representative stack.
What changed: Added `.agents/references/preprocess-benchmark-report.md` with timing, memory, MPS difference metrics, production recommendations, and suggested downstream ANTs validation.
Rerun implications: Use the report as the starting point before changing production acceleration defaults.
Validation performed: Documentation-only update.

## 2026-05-15 - four-worker CPU transform default

Slice goal: Promote the exact threaded CPU benchmark winner to production preprocessing.
Passes completed: Changed channel transforms to use four CPU worker threads by default while preserving single-worker output semantics and main-thread NRRD writing.
What changed: `export_preprocessed_channels` now defaults to four channel transform workers. Added a regression comparing one-worker and four-worker exports byte-for-byte after NRRD readback.
Rerun implications: New preprocessing exports should be faster and remain bit-identical to the prior single-worker SciPy transform path.
Validation performed: `pytest tests/test_io.py -q`; `pytest -q`.

## 2026-06-02 - LSM metadata channel autodiscovery

Slice goal: Use Zeiss LSM metadata to infer channel order and reduce manual channel mapping in the preprocess app.
Passes completed: Inspected real LSM metadata for 488/546/647 and 488/647/DAPI stacks, then added reusable metadata channel inference with filename gene-label merging.
What changed: `read_lsm_metadata` now auto-accepts complete, conflict-free metadata channel mappings. `read_unlabeled_lsm_metadata` and the channel dialog use metadata-derived suggestions and show confirmation messages when filename and metadata disagree.
Rerun implications: Existing project JSON and exported outputs remain compatible. Newly added files with clear metadata may skip the manual mapping dialog; conflicting files still require user confirmation.
Validation performed: `pytest tests/test_io.py`; real-stack inference check for `L758_f02_H2B-GC6s_488_sst1_1_546_pth2_647.lsm` and `trha_546_kiss2_647_DAPI_740nm_f03_Stitch.lsm`.

## 2026-06-02 - stack list drag/drop and deletion

Slice goal: Make stack list management faster in the preprocess app.
Passes completed: Added extended multi-selection, local `.lsm` file/folder drop handling, and Delete/Backspace removal from the project list.
What changed: `StackFileList` now emits dropped local paths and delete-key requests. `MainWindow` reuses the existing add-stack flow for dropped `.lsm` files and immediate child `.lsm` files from dropped folders. `ProjectState.remove_files` owns path-based project removal.
Rerun implications: Project JSON schema is unchanged. Delete/Backspace removes stacks from the project only; source files and output folders are untouched.
Validation performed: `pytest tests/test_model.py tests/test_widgets.py`; `pytest`.

## 2026-06-02 - same-fish confocal export profile

Slice goal: Support a constrained workflow for preprocessing repeated confocal staining rounds from the same fish while preserving default app naming.
Passes completed: Added project-state profile metadata, CLI preseed flags, profile-aware export directory and filename builders, and a personal Codex skill with a staging/launch helper script.
What changed: `brain-atlas-preprocess --profile same_fish_confocal` writes to `rbest/` or `rn/` under the output root, uses `1500 px` crop by default when no crop is supplied, normalizes channel index `0` to `GCaMP`, and names outputs as `<fish_id>_<rbest|rN>_channel<index>_<gene>.nrrd`. Regular app use keeps the existing `<source_stem>_preprocessed/` naming.
Rerun implications: Existing projects and default exports remain compatible. Same-fish confocal projects should be launched through the CLI/profile or the `same-fish-confocal-preprocess` skill helper.
Validation performed: `pytest tests/test_model.py tests/test_io.py`; `python -m brain_atlas_preprocess.app --help`; helper script no-launch and verify-only smoke checks with a temporary fish folder.

## 2026-06-02 - same-fish confocal batch launch

Slice goal: Avoid opening one preprocessing app instance per fish when staging multiple same-fish confocal cases.
Passes completed: Added per-file same-fish confocal profile and output-root overrides, plus CLI startup from an existing project JSON. Updated the personal staging helper to accept repeated `--batch-case FISH_ID=SOURCE_STACK` arguments, create one batch project, and launch one app instance.
What changed: `PreprocessWorker` resolves `file_state.output_root` and `file_state.same_fish_confocal` before falling back to project-level values. Batch helper projects can contain multiple fish that export to their own `02_reg/00_preprocessing/<rbest|rn>/` folders from a single GUI window.
Rerun implications: Existing project-level same-fish launches remain compatible. For multiple fish, prefer the helper batch form instead of invoking the helper once per source stack.
Validation performed: `pytest tests/test_model.py tests/test_app.py tests/test_io.py -k 'same_fish_confocal or file_specific_output_roots or parse_args_rejects or round_trip'`; `python3 -m py_compile brain_atlas_preprocess/model.py brain_atlas_preprocess/app.py /Users/ddharmap/.codex/skills/same-fish-confocal-preprocess/scripts/stage_and_launch.py`; batch helper `--verify-only` on L765_f02/L765_f03.
