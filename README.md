# Brain Atlas Preprocessing App

Desktop app for reviewing Zeiss `.lsm` imaging stacks, assigning an approximate XY rotation from a DAPI maximum-intensity projection, and exporting rotated channel stacks for registration.

## Install

```bash
python -m pip install -e ".[test]"
```

## Run

```bash
brain-atlas-preprocess
```

The app writes a project state file named `brain_atlas_preprocess_project.json` in the selected output root. Raw `.lsm` files are read-only.

## Test

```bash
pytest
```
