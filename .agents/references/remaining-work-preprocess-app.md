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

## 2026-05-15 - GPU transform acceleration benchmark

Status: Deferred.
What remains broken: Nothing is broken; CPU preprocessing benchmark tooling now exists.
Remaining in-slice work: Evaluate a future GPU backend for rotate/crop transforms after deciding whether non-bit-identical fused CPU output can ever be acceptable.
Next likely breakpoint: Add a dedicated GPU benchmark variant only if CUDA/CuPy or another supported backend is available on the target processing machine.
Blocking context: Current correctness preference requires bit-identical output versus SciPy rotate-then-crop.
Validation or rerun needed: Compare GPU output against the fresh CPU baseline and record wall time plus peak host/device memory.
