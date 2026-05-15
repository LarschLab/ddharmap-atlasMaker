# Remaining Work: Preprocess App

Purpose: track actionable unresolved work for the preprocessing app workflow.

Use this file when stopping with known breakage, incomplete validation, or follow-up required in this workflow.

## Entry template

```text
## YYYY-MM-DD - short label

Status:
What remains broken:
Remaining in-slice work:
Next likely breakpoint:
Blocking context:
Validation or rerun needed:
```

## Active items

## 2026-05-15 - MPS transform production decision

Status: Benchmark implemented; production adoption deferred.
What remains broken: Nothing is broken; CPU threaded variants are exact and MPS benchmark output is intentionally tolerance-reported.
Remaining in-slice work: Decide whether MPS output differences are scientifically acceptable before adding any GPU path to production preprocessing.
Next likely breakpoint: Review `mps_fused_raw` max-difference and differing-voxel-fraction results across several representative stacks.
Blocking context: MPS is not bit-identical to the SciPy CPU baseline.
Validation or rerun needed: Run the MPS benchmark on additional real stacks and, if needed, compare downstream registration behavior.
