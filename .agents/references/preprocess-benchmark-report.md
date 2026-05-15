# Preprocess Benchmark Report

Purpose: preserve current preprocessing speed findings and the open MPS/registration decision for later review.

## Benchmark Context

- Date: 2026-05-15.
- Source stack:
  `/Users/ddharmap/dataProcessing/testSample/20260311_f02_tph2_488_optb_546_gbx2_647_Stitch.lsm`
- Source shape: `ZCYX = 136 x 4 x 924 x 921`, dtype `uint8`.
- Export settings recovered from prior manifest:
  - preview rotation: `14.328666854465453` degrees.
  - applied export rotation: `-14.328666854465453` degrees.
  - crop center: `(560, 575)`.
  - crop size: `750 px`.
  - interpolation: `linear`.
  - canvas mode: `expand`.
- Main benchmark summary:
  `/Users/ddharmap/dataProcessing/testOutput/preprocess_benchmark_runs/20260515_100013/benchmark_summary.json`

## Results

| Variant | Exact vs CPU baseline | Wall time | Speedup vs `loop_raw` | Peak RSS | Notes |
| --- | --- | ---: | ---: | ---: | --- |
| `loop_raw` | yes | `12.409 s` | `1.00x` | `965.8 MB` | current raw CPU baseline |
| `loop_raw_threads_1` | yes | `12.349 s` | `1.00x` | `904.7 MB` | sanity check |
| `loop_raw_threads_2` | yes | `6.556 s` | `1.89x` | `1009.2 MB` | exact and moderate memory increase |
| `loop_raw_threads_4` | yes | `3.598 s` | `3.45x` | `1337.8 MB` | exact and fastest CPU option tested |
| `mps_fused_raw` | no | `2.160 s` | `5.74x` | `1594.5 MB` | experimental PyTorch MPS fused rotate/crop |

MPS memory during `mps_fused_raw`:

- Peak MPS current allocated memory: about `1317 MB`.
- Peak MPS driver allocated memory: about `2098 MB`.
- Recommended max MPS memory reported by PyTorch: about `12124 MB`.

## MPS Difference Metrics

`mps_fused_raw` preserved shape, dtype, channel order, and metadata, but was not bit-identical to the SciPy CPU baseline.

| Channel | Differing voxels | Differing fraction | Max absolute difference |
| --- | ---: | ---: | ---: |
| `optb` | `2448` | `0.0032%` | `5` |
| `tph2` | `6766` | `0.00884%` | `8` |
| `gbx2` | `1481` | `0.00194%` | `3` |
| `DAPI` | `6433` | `0.00841%` | `11` |

Interpretation:

- The MPS differences are sparse: less than `0.01%` of voxels differed in each channel in this sample.
- The differences are small in intensity relative to an 8-bit range, but not purely `±1`.
- The current MPS path is a fused rotate/crop implementation, so differences can come from both coordinate evaluation and interpolation/rounding behavior.

## Practical Recommendation

- CPU threading is the safest production acceleration because it is exact against the current SciPy export.
- `loop_raw_threads_4` has been selected as the production default: about `3.45x` faster than `loop_raw` on this sample, with peak RSS increasing by about `372 MB`.
- `loop_raw_threads_2` is the conservative memory option: about `1.89x` faster, with only a small RSS increase.
- MPS is a strong experimental candidate, but should not be promoted until downstream registration tolerance is checked.

## ANTs Registration Risk Assessment

The measured MPS differences are probably unlikely to materially change ANTs registration for this sample, but that should be treated as a hypothesis, not a conclusion.

Reasons the risk may be low:

- ANTs registration metrics are usually driven by spatially broad intensity structure, not isolated voxel-level equality.
- Typical registration pipelines use multi-resolution pyramids, interpolation, smoothing, and optimization over many voxels; sparse differences below `0.01%` are likely to be averaged away.
- The tested MPS output preserved crop shape, channel identity, orientation metadata, and apparent transform geometry.

Reasons to validate anyway:

- Differences are not strictly `±1`; DAPI reached max absolute difference `11`.
- Registration can be sensitive around sharp boundaries, sparse signals, masks, or low-contrast regions depending on metric and parameters.
- A small preprocessing difference can still change optimizer paths if registration is near a local optimum or if initialization is weak.
- The relevant endpoint is not voxel equality, but whether ANTs produces materially different transforms or registered outputs.

Suggested acceptance check before production MPS:

1. Run the same ANTs registration pipeline on CPU-threaded exact outputs and MPS outputs for several representative stacks.
2. Compare final transform parameters/fields, registered image similarity metrics, and visual overlays.
3. If segmentation, atlas assignment, or downstream quantification exists, compare those outputs directly.
4. Only consider MPS acceptable if downstream differences are below the scientific tolerance agreed by the group.

## Follow-Up Commands

Run exact CPU and MPS benchmark on the default sample:

```bash
python scripts/benchmark_preprocess.py --repeats 1 \
  --variants loop_raw loop_raw_threads_1 loop_raw_threads_2 loop_raw_threads_4 \
  --include-mps
```

Run more stable timing with three repeats:

```bash
python scripts/benchmark_preprocess.py --repeats 3 \
  --variants loop_raw loop_raw_threads_2 loop_raw_threads_4 \
  --include-mps
```

Use `--manifest <path/to/preprocess_manifest.json>` to benchmark a different processed stack's source and settings.
