# Current State

Purpose: record active caveats and unsettled context that future agents should know before broad changes.

Use this file when a task touches migration state, compatibility behavior, or unclear project direction.

## Current notes

- The repo is a compact PySide desktop app with one real workflow profile: review `.lsm` stacks, choose rotation/crop, and export preprocessed channel stacks.
- No notebooks, services, or separate pipelines are currently present.
- `export_rotated_channels` remains as a compatibility wrapper around `export_preprocessed_channels`; do not treat it as the export authority.
- GUI behavior is not covered by automated Qt tests yet. Validate UI changes with a manual app smoke check unless a focused test is added.
- `tests/test_io.py` includes an optional local sample smoke test that skips when `/Users/ddharmap/dataProcessing/testSample/...` is unavailable.
- Existing source files may be dirty in the worktree. Do not revert unrelated user changes.

## When to update

Update this file when migration state changes, compatibility wrappers are removed, GUI test coverage is added, or the repo gains a second workflow profile.
