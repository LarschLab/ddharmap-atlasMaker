# UI Interaction Policy

Purpose: define ownership and validation rules for the PySide interface and preview rendering.

Use this file before changing preview drawing, crop overlay, mouse events, file-list status display, dialogs, progress, or worker behavior.

## Ownership

- `widgets.py` owns reusable visual components and direct interaction math.
- `app.py` owns layout, signals, worker lifecycle, dialogs, status messages, and workflow sequencing.
- `io.py` owns image data loaded into the UI; do not duplicate stack parsing or transform semantics in widgets or callbacks.
- `model.py` owns persisted state; do not add parallel UI-only status fields for persisted concepts.

## Preview rules

- Right mouse drag changes `rotation_degrees`.
- Left click sets `crop_center_yx`.
- Crop center coordinates are in `(y, x)` order.
- Crop overlay must reflect the rotated canvas dimensions used by export.
- The preview may normalize intensities for display only; display normalization must not affect export data.
- Empty preview state must remain legible and non-crashing.

## App workflow rules

- Background workers should stay thin and call owner functions.
- Long-running file reads and exports should not run on the main UI thread.
- Save project state after user changes when an output root exists.
- Keep dialogs user-facing; keep parsing/export detail in owner modules.

## Validation

- Pure helper changes in widgets: add or run focused tests when practical.
- Rendering, layout, or mouse interaction changes: launch `brain-atlas-preprocess` and inspect the affected state.
- Worker or dialog changes: smoke the relevant workflow with a small stack or mocked/local sample when available.
- For visual changes, verify that the preview is nonblank for loaded images, labels are readable, overlays align, and controls do not overlap.
