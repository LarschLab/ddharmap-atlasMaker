# Brain Atlas Preprocessing App

Desktop app for reviewing Zeiss `.lsm` imaging stacks, assigning an approximate XY rotation from a DAPI maximum-intensity projection, selecting a square crop, and exporting preprocessed channel stacks for registration.

## Install

```bash
python -m pip install -e ".[test]"
```

## Run

```bash
brain-atlas-preprocess
```

The app writes a project state file named `brain_atlas_preprocess_project.json` in the selected output root. Raw `.lsm` files are read-only.

Use right mouse dragging in the preview to rotate the stack. Use left click to set the center of the square crop. The crop size defaults to `750 px` and outputs are written as `.nrrd` files with source/channel/spatial metadata in the NRRD header and manifest.

## Test

```bash
pytest
```
