---
name: ecc-pipeline
description: Load pipeline ECC tools for workflows, automation, multi-step jobs, and repeatable process execution.
---

# ECC Pipeline

Use automatically when a task needs workflows, pipelines, automation, multi-step jobs, orchestration, or repeatable process execution.

## Workflow

1. Call `load_skill_tools("ecc/pipeline")`.
2. Use the loaded tools only when they are relevant to the current task.
3. Keep work scoped to the active thread.

## Tools

- `pipeline_builder`
- `pipeline_run`

## Error Handling

If loading fails, respond with:

```text
Failed operation: load_skill_tools("ecc/pipeline")
Reason: <tool error>
Recovery steps:
- Run `/help-agent101` to confirm ECC categories are available.
- Check that server/tools/ecc/pipeline.py imports correctly.
```
