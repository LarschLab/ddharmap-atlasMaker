# Brain Atlas

Desktop preprocessing and atlas-viewing tools. Start from the requested code or test; load a reference only when its contract matters.

## Ownership and invariants

- Reusable preprocessing and data semantics belong in `brain_atlas_preprocess/io.py` or `model.py`.
- `app.py` owns Qt orchestration, workers, dialogs, and project lifecycle; `widgets.py` owns preview rendering and mouse interaction.
- Preserve canonical output names, JSON fields, channel ordering, crop coordinates, and orientation semantics unless explicitly migrating them.
- Validate with the smallest relevant test or smoke check. Visually inspect changed UI or rendered output.

## Conditional references

- Files, metadata, manifests, and exports: `.agents/references/data-contracts.md`
- Preprocessing flow: `.agents/references/preprocess-stage-map.md`
- UI behavior: `.agents/references/ui-interaction-policy.md`
- Current caveats: `.agents/references/current-state.md`

Benchmark reports, symbol indexes, and recent-change logs are lookup material, not startup requirements.
