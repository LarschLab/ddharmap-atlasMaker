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
