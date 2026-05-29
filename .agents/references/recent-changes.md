# Recent Changes Index

Purpose: route agents to workflow-specific completed-change logs.

Use this file when starting from handoff context or after completing meaningful work.

## Logs

- Preprocess app workflow: `.agents/references/recent-changes-preprocess-app.md`

## Logging rule

Log meaningful completed changes that affect behavior, public workflow semantics, canonical outputs, validation expectations, ownership boundaries, or future rerun/debugging decisions. Do not log typo-only edits or mechanical formatting unless they change future agent behavior.

## Compact Query Route

Before opening a workflow-specific append-only log, query it with:

```bash
python3 /Users/ddharmap/gitRepo/agenticWorkflow/scripts/query_recent_changes.py --repo <repo-name> --query <term> --limit 5
```

Open the full log only when the compact result points to an entry that needs detailed reading.
