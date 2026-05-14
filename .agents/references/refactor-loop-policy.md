# Refactor Loop Policy

Purpose: keep agents moving through a complete ownership slice instead of stopping after one superficial edit.

Use this file for refactors, migrations, repeated cleanup, or tasks with unclear stopping points.

## Default working unit

A working unit is one owner-level slice with its callers and tests. Examples: channel mapping plus export tests, project-state serialization plus model tests, or preview coordinate math plus widget callers.

## Required sub-pass loop

1. Identify the semantic owner and callers.
2. Make the narrowest coherent edit in the owner.
3. Update direct callers only as needed.
4. Run the smallest relevant validation.
5. Remove or update stale tests/docs created by the change.
6. Repeat inside the same owner until no obvious same-slice breakage remains.

## Keep-going rules

- Continue if the next failure is in the same owner and has the same validation surface.
- Continue if a public symbol or data contract doc is now stale because of your change.
- Continue if tests reveal a caller expectation that must change with the owner semantics.

## Valid stop conditions

- The requested behavior is implemented and validated.
- Remaining work belongs to a different owner or requires new product/science decisions.
- Validation is blocked by missing local data or environment, and the blocker is recorded.

## Invalid stop conditions

- One helper was cleaned up while same-owner callers/tests are knowingly stale.
- Static reading suggests success but no relevant validation was run.
- Unresolved breakage is mentioned only in chat and not recorded in the remaining-work tracker.

## Handoff requirements

- Completed meaningful behavior changes go in `recent-changes-preprocess-app.md`.
- Unresolved actionable work goes in `remaining-work-preprocess-app.md`.
- Include validation performed or why it could not be run.
